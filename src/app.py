#!/usr/bin/env python3
"""
AI RPP/RPM Pembelajaran Mendalam Generator - Web Server
Flask application with REST API endpoints
"""

import sys
import io
import copy
import json
import os
import re
import tempfile
import sqlite3
import logging
import threading
import time
import uuid
from dataclasses import fields as dataclass_fields
from dataclasses import asdict as dataclass_asdict
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from html import escape as html_escape

from module_generation_pipeline import (
    Module, TPEntry, KKTPEntry, ActivityEntry,
    ProtectionValidator, FinalValidator, MasterOutlineValidator,
    PedagogicalValidator, FactualityValidator, allowed_profile_values,
    build_rubric, build_blueprint, build_instrument_recap,
    build_learning_phases, build_meetings, validate_time_budget,
    attach_meeting_principles, NineRouterError, ModuleGenerationPipeline,
    AntiSlopProcessor,
)
from curriculum_context import CurriculumContext
from module_store import (
    ModuleStore, VersionStore, GenerationLogStore, AsyncJobStore,
    StaleVersionError, utc_now_iso,
)
from pathlib import Path
from datetime import datetime
from flask import Flask, redirect, render_template, request, jsonify, send_file, send_from_directory, after_this_request, make_response

# Force UTF-8 (but skip in testing mode or if stdout is already wrapped)
try:
    if 'pytest' not in sys.modules and not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (AttributeError, ValueError):
    # If we can't wrap stdout, just continue
    pass

# Muat .env proyek (opsional) sebelum membaca konfigurasi apa pun,
# agar user self-host cukup mengisi file .env. Environment proses
# selalu menang atas isi file. Di bawah pytest, lewati agar .env user
# tidak bocor ke tes (hermetik).
if 'PYTEST_CURRENT_TEST' not in os.environ and 'pytest' not in sys.modules:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / '.env', override=False)
    except ImportError:
        pass

# Initialize Flask
app = Flask(__name__)

# Batch 2 §2: bound request bodies server-side (never trust the client to
# size input forwarded to the AI gateway). 413 on excess.
# Global 2MB melindungi endpoint JSON generate; route upload RPM
# (/api/modules/import) dinaikkan ke 10MB via before_request (R-35)
# karena file tidak diteruskan ke gateway AI.
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024


@app.before_request
def _raise_upload_limit():
    """Set batas body upload pada request ini saja."""
    try:
        if request.endpoint in ('import_modules', 'upload_buku'):
            request.max_content_length = 10 * 1024 * 1024
    except Exception:
        pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ACCESS-CONTROL MODEL (Batch 2 §3 audit).
#
# This application has NO multi-user authentication mechanism: it is a
# single-operator local deployment. The development server is bound to the
# loopback interface, so browser access remains on the same machine.
#
# LIMITATIONS (documented, not silently assumed):
# - For shared hosting, put the app behind a reverse proxy with
#   authentication; this local server is not a multi-user deployment.
# - GET /api/module/download serves the last in-memory module of this
#   single-operator process by design.
# - No secrets are ever exposed: the 9Router API key lives only in the
#   server environment, is sent only as an Authorization header to the
#   gateway, and never appears in responses, logs, or the frontend.
# ---------------------------------------------------------------------------

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
# DB override for tests/tooling (e.g. a subprocess restart test that needs a
# fully separate database). Production default stays db/rpm_generator.db.
DB_PATH = Path(os.environ.get('RPM_GENERATOR_DB')
               or (PROJECT_ROOT / 'db' / 'rpm_generator.db'))

# Store for context during generation
generation_context = {}

class _BoundedJobStore(dict):
    """Thread-safe terminal-job store with TTL and count bound."""

    def __init__(self, max_items=512, ttl_seconds=3600):
        super().__init__()
        self._lock = threading.RLock()
        self._updated = {}
        self._max_items = max_items
        self._ttl_seconds = ttl_seconds

    def _prune_locked(self):
        now = time.monotonic()
        for key in list(self):
            value = super().get(key) or {}
            if value.get('status') == 'running':
                continue
            if now - self._updated.get(key, now) > self._ttl_seconds:
                super().pop(key, None)
                self._updated.pop(key, None)
        while len(self) >= self._max_items:
            removable = next((key for key in self
                              if (dict.get(self, key) or {}).get('status')
                              != 'running'), None)
            if removable is None:
                break
            super().pop(removable, None)
            self._updated.pop(removable, None)

    def __setitem__(self, key, value):
        with self._lock:
            if key not in self:
                self._prune_locked()
            super().__setitem__(key, value)
            self._updated[key] = time.monotonic()

    def get(self, key, default=None):
        with self._lock:
            self._prune_locked()
            return super().get(key, default)

    def pop(self, key, *args):
        with self._lock:
            self._updated.pop(key, None)
            return super().pop(key, *args)

    def clear(self):
        with self._lock:
            super().clear()
            self._updated.clear()


class _BoundedContextStore(dict):
    """Keep restart-safe storage authoritative while bounding RAM fallback."""

    def __init__(self, max_items=512):
        super().__init__()
        self._lock = threading.RLock()
        self._max_items = max_items

    def __setitem__(self, key, value):
        with self._lock:
            if key not in self and len(self) >= self._max_items:
                oldest = next(iter(self), None)
                if oldest is not None:
                    super().pop(oldest, None)
            super().__setitem__(key, value)

    def get(self, key, default=None):
        with self._lock:
            return super().get(key, default)

    def clear(self):
        with self._lock:
            super().clear()


# In-process async generation jobs (UI polls instead of holding a
# long-lived connection open, which proxy layers may drop).
generation_jobs = _BoundedJobStore()

# Lock serializing module generation: the pipeline mutates shared state
# (single shared pipeline instance), so only one job may run at a time.
generation_lock = threading.Lock()
_generation_pipeline_lock = threading.Lock()

# Bound background work. Each slot covers one queued/running job; rejected
# submissions return a structured backpressure response instead of creating
# unbounded daemon threads.
_JOB_MAX_PENDING = 8
_job_slots = threading.BoundedSemaphore(_JOB_MAX_PENDING)
_job_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='rpm-job')
_job_state_lock = threading.RLock()

# Feedback is a small JSON store. Keep read/modify/write atomic across
# concurrent browser requests and replace the file atomically on disk.
_feedback_lock = threading.RLock()


def _submit_background_job(fn, *args) -> bool:
    """Submit bounded background work; return False when queue is full."""
    if not _job_slots.acquire(blocking=False):
        return False

    def run():
        try:
            fn(*args)
        finally:
            _job_slots.release()

    try:
        _job_executor.submit(run)
    except Exception:
        _job_slots.release()
        raise
    return True


def _async_db_path() -> str:
    """Use test-bound pipeline DB when present, otherwise production DB."""
    pipeline = _generation_pipeline
    return str(getattr(pipeline, 'db_path', DB_PATH))


def _async_store(db_path: Optional[str] = None) -> AsyncJobStore:
    return AsyncJobStore(str(db_path or _async_db_path()))


def _memory_job(row: Dict) -> Dict:
    """Convert persistent job row to legacy in-process polling shape."""
    return {
        'status': row.get('status', 'running'),
        'result': dict(row.get('result') or {}),
        'kind': row.get('kind'),
        'progress': row.get('progress', 0),
        'tahap': row.get('tahap', ''),
        'timing': dict(row.get('timing') or {}),
    }


def _job_get(job_id: str, db_path: Optional[str] = None) -> Optional[Dict]:
    job = generation_jobs.get(job_id)
    if job is not None:
        return job
    row = _async_store(db_path).get(job_id)
    if row is None:
        return None
    job = _memory_job(row)
    generation_jobs[job_id] = job
    return job


def _job_create(job_id: str, kind: str, payload: Dict, **kwargs) -> Dict:
    accepted_mono = kwargs.pop('accepted_mono', None)
    row = _async_store().create(job_id, kind, payload, **kwargs)
    job = _memory_job(row)
    if accepted_mono is not None:
        job['_accepted_mono'] = accepted_mono
    generation_jobs[job_id] = job
    return job


def _job_set(job_id: str, value: Dict) -> Dict:
    """Update memory and SQLite atomically enough for polling/restart."""
    current = _job_get(job_id) or {}
    merged = dict(value)
    for key in ('kind', 'progress', 'tahap', 'timing', '_accepted_mono'):
        if key not in merged and key in current:
            merged[key] = current[key]
    row = _async_store().update(
        job_id,
        status=merged.get('status'),
        result=merged.get('result') or {},
        timing=merged.get('timing') or {},
        progress=merged.get('progress', 0),
        tahap=merged.get('tahap', ''),
    )
    if row is not None:
        memory = _memory_job(row)
        if '_accepted_mono' in merged:
            memory['_accepted_mono'] = merged['_accepted_mono']
        merged = memory
    generation_jobs[job_id] = merged
    return merged


def _job_update(job_id: str, **changes) -> Optional[Dict]:
    current = _job_get(job_id)
    if current is None:
        return None
    next_job = dict(current)
    next_job.update(changes)
    return _job_set(job_id, next_job)


def _job_remove(job_id: str) -> None:
    generation_jobs.pop(job_id, None)
    _async_store().delete(job_id)

# Curriculum options change only when authoritative mapping/DB sources change.
# Cache the assembled payload so every form render does not reread a 100KB JSON
# mapping file and rescan learning_outcomes. Key includes source metadata, so a
# curriculum update invalidates the cache without changing response semantics.
_CURRICULUM_OPTIONS_CACHE = {}
_CURRICULUM_OPTIONS_LOCK = threading.Lock()

# Live CurriculumContext objects per generation_id (legacy in-process
# accelerator; PUT no longer DEPENDS on it - the authoritative context is
# always rebuilt from generated_modules.context_json, so editing works
# across server restarts).
# to compare protected fields against the ORIGINAL authoritative context
# (client-sent copies are never trusted).
_context_objects = _BoundedContextStore()

# Authoritative subject list per education system (single source used by
# /api/subjects and /api/curriculum/options). Konsisten dengan
# db/curriculum_mappings.json (sumber otoritatif).
CURRICULUM_SUBJECTS = {
    'KEMENAG': [
        "Al-Qur'an Hadis",
        'Akidah Akhlak',
        'Fikih',
        'Sejarah Kebudayaan Islam',
        'Bahasa Arab'
    ],
    'KEMENDIKDASMEN': [
        'Pendidikan Agama dan Budi Pekerti'
    ]
}


def _subjects_from_mapping(system: str, institution: Optional[str] = None) -> List[str]:
    """Read subjects from authoritative system/institution mapping.

    Legacy constant remains fallback for old/missing mapping files only.
    """
    try:
        mapping = _curriculum_mappings().get('subjects', {}).get(system, {})
        institutions = [institution] if institution else list(mapping)
        names: List[str] = []
        seen = set()
        for inst in institutions:
            for item in mapping.get(inst, []) or []:
                name = item.get('name') if isinstance(item, dict) else item
                if isinstance(name, str) and name not in seen:
                    seen.add(name)
                    names.append(name)
        if names:
            return names
    except Exception:
        logger.exception("Authoritative subject mapping lookup failed")
    return list(CURRICULUM_SUBJECTS.get(system, []))

# React UI build, served as primary application at the public root.
UI_REACT_DIR = PROJECT_ROOT / 'ui-react'
# Keep legacy files only for the regression harness and feedback widget asset.
UI_DIR = PROJECT_ROOT / 'ui'


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _serve_react_index():
    """Serve React as the public root application."""
    html = (UI_REACT_DIR / 'index.html').read_text(encoding='utf-8')
    html = _inject_feedback_widget(html)
    resp = make_response(html)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/', methods=['GET'])
def index():
    """Serve the React application at the public root URL."""
    return _serve_react_index()


@app.route('/api', methods=['GET'])
def api_index():
    """Describe API endpoints without occupying the public app root."""
    return jsonify({
        'status': 'online',
        'app': 'AI RPP/RPM Pembelajaran Mendalam Generator',
        'version': '2.0',
        'endpoints': {
            'GET /api/health': 'Server health check',
            'GET /api/systems': 'List education systems',
            'GET /api/subjects/<system>': 'Get subjects for system',
            'GET /api/cp/<subject>/<phase>': 'Get CP for subject-phase',
            'POST /api/context/generate': 'Generate curriculum context',
            'POST /api/topic/relevance': 'Check topic-element relevance',
            'POST /api/module/generate': 'Generate RPP/RPM',
            'GET /api/module/download': 'Download generated RPP/RPM'
        }
    })


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM source_fragments")
        count = cursor.fetchone()[0]
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'fragments': count,
            'timestamp': datetime.now().isoformat()
        })
    except Exception:
        logger.exception("Health check failed")
        return jsonify({
            'status': 'unhealthy',
            'error': 'Database unavailable'
        }), 500
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


@app.route('/api/systems', methods=['GET'])
def get_systems():
    """Get available education systems."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities")
        systems = [dict(row) for row in cursor.fetchall()]
        return jsonify({
            'status': 'success',
            'systems': systems
        })
    except Exception:
        logger.exception("Systems lookup failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load education systems'
        }), 500
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


@app.route('/api/subjects/<system>', methods=['GET'])
def get_subjects(system):
    """Get subjects for a system."""
    try:
        subjects = _subjects_from_mapping(system)
        
        if not subjects:
            return jsonify({
                'status': 'error',
                'message': f'System {system} not found'
            }), 404
        
        return jsonify({
            'status': 'success',
            'system': system,
            'subjects': subjects
        })
    except Exception:
        logger.exception("Subjects lookup failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load subjects'
        }), 500


def _institution_family(education_system: str, institution_type: str) -> str:
    """Map UI unit codes (MTs, SMP, SDLB) to DB institution families."""
    if education_system == 'KEMENAG' and institution_type in {
            'RA', 'MI', 'MTs', 'MA', 'MAK'}:
        return 'madrasah'
    if education_system == 'KEMENDIKDASMEN':
        if institution_type in {'TKLB', 'SDLB', 'SMPLB', 'SMALB'}:
            return 'pendidikan_khusus'
        if institution_type in {'TK', 'SD', 'SMP', 'SMA', 'SMK'}:
            return 'sekolah'
    return institution_type


@app.route('/api/curriculum/elements', methods=['GET'])
def get_curriculum_elements():
    """Load only active elements for one subject and phase. Subject
    matching is case-insensitive so UPPERCASE dropdown values resolve to
    the canonical DB spelling."""
    subject = (request.args.get('subject') or '').strip()
    phase = (request.args.get('phase') or '').strip()
    if not subject or not phase:
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_ELEMENTS_INPUT_REQUIRED',
            'message': 'subject dan phase wajib diisi',
        }), 400

    education_system = (request.args.get('education_system') or '').strip()
    institution_type = (request.args.get('institution_type') or '').strip()
    # UI sends unit codes (MTs, SMP), while CP rows store institution
    # families (madrasah, sekolah, pendidikan_khusus).
    institution_family = _institution_family(education_system, institution_type)
    clauses = [
        "UPPER(subject) = UPPER(?)",
        "phase = ?",
        "COALESCE(status, 'active') = 'active'",
        "element IS NOT NULL",
        "element != ''",
    ]
    params = [subject, phase]
    if education_system:
        clauses.append('education_system = ?')
        params.append(education_system)
    if institution_type:
        clauses.append('institution_type = ?')
        params.append(institution_family)

    conn = None
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT DISTINCT element FROM learning_outcomes WHERE ' +
            ' AND '.join(clauses) + ' ORDER BY element',
            params,
        ).fetchall()
        return jsonify({
            'status': 'success',
            'subject': subject,
            'phase': phase,
            'elements': [row['element'] for row in rows],
        })
    except Exception:
        logger.exception('Curriculum elements lookup failed')
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_ELEMENTS_LOOKUP_FAILED',
            'message': 'Failed to load curriculum elements',
        }), 500
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/curriculum/subjects', methods=['GET'])
def get_curriculum_subjects():
    """Subjects with active reguler CP for one grade's phase.

    Filters by the selected grade's phase from DB learning_outcomes, so the
    dropdown never offers a subject with no CP for the class. Values keep
    canonical DB spelling (the form displays them UPPERCASE) so exact-match
    element/CP lookups keep working.
    """
    education_system = (request.args.get('education_system') or '').strip()
    institution_type = (request.args.get('institution_type') or '').strip()
    grade = (request.args.get('grade') or '').strip()
    if not education_system or not institution_type or not grade:
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_SUBJECTS_INPUT_REQUIRED',
            'message': 'education_system, institution_type, dan grade wajib diisi',
        }), 400
    try:
        mappings = _curriculum_mappings()
        grade_meta = (mappings.get('grade_to_phase_mappings', {})
                      .get(education_system, {})
                      .get(institution_type, {})
                      .get(grade, {}) or {})
        phase = grade_meta.get('phase') or ''
    except Exception:
        logger.exception('Curriculum subjects mapping lookup failed')
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_SUBJECTS_LOOKUP_FAILED',
            'message': 'Failed to load curriculum subjects',
        }), 500
    if not phase:
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_SUBJECTS_UNKNOWN_GRADE',
            'message': f'Fase tidak ditemukan untuk {grade}',
        }), 400
    family = _institution_family(education_system, institution_type)
    conn = None
    try:
        conn = get_db()
        base = ("SELECT DISTINCT subject FROM learning_outcomes "
                "WHERE education_system = ? AND phase = ? "
                "AND COALESCE(status, 'active') = 'active' "
                "AND COALESCE(program_type, 'reguler') = 'reguler' ")
        # Mirror the generation pipeline: pendidikan_khusus also resolves
        # CP rows stored under the 'sekolah' family.
        if family == 'pendidikan_khusus':
            base += "AND institution_type IN ('pendidikan_khusus', 'sekolah') "
            params: list = [education_system, phase]
        else:
            base += "AND institution_type = ? "
            params = [education_system, phase, family]
        rows = conn.execute(base + "ORDER BY UPPER(subject)", params).fetchall()
        return jsonify({
            'status': 'success',
            'education_system': education_system,
            'institution_type': institution_type,
            'grade': grade,
            'phase': phase,
            'subjects': [row['subject'] for row in rows],
        })
    except Exception:
        logger.exception('Curriculum subjects lookup failed')
        return jsonify({
            'status': 'error',
            'code': 'CURRICULUM_SUBJECTS_LOOKUP_FAILED',
            'message': 'Failed to load curriculum subjects',
        }), 500
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/curriculum/options', methods=['GET'])
def get_curriculum_options():
    """Authoritative curriculum options for the UI form.

    Reads db/curriculum_mappings.json (the same authoritative source the
    generation pipeline uses), so the form never hardcodes curriculum data.
    The assembled response is cached until either authoritative source file
    changes. Cache is process-local and does not change response semantics.
    """
    try:
        mappings_path = PROJECT_ROOT / 'db' / 'curriculum_mappings.json'
        db_path = Path(DB_PATH)

        def source_stamp(path):
            stat = path.stat()
            return (stat.st_mtime_ns, stat.st_size)

        compact = request.args.get('compact') == '1'
        cache_key = (str(db_path.resolve()), source_stamp(mappings_path),
                     source_stamp(db_path), compact)
        with _CURRICULUM_OPTIONS_LOCK:
            cached = _CURRICULUM_OPTIONS_CACHE.get(cache_key)
            if cached is not None:
                return jsonify(cached)

            with open(mappings_path, encoding='utf-8') as f:
                mappings = json.load(f)

            grade_to_phase = mappings.get('grade_to_phase_mappings', {})

            # Full options keeps legacy response semantics. Compact mode
            # loads elements on demand through /api/curriculum/elements.
            elements_by_subject = {}
            if not compact:
                conn = get_db()
                try:
                    element_rows = conn.execute(
                        "SELECT DISTINCT subject, phase, element "
                        "FROM learning_outcomes "
                        "WHERE COALESCE(status, 'active') = 'active' "
                        "AND element IS NOT NULL AND element != ''"
                    ).fetchall()
                finally:
                    conn.close()
                elements_by_subject = {}
                for row in element_rows:
                    elements_by_subject.setdefault(row['subject'], {}).setdefault(
                        row['phase'], []).append(row['element'])

            systems = {}
            for system, institutions in grade_to_phase.items():
                systems[system] = {
                    # Backward-compatible aggregate list for existing clients.
                    'subjects': _subjects_from_mapping(system),
                    'institutions': {
                        inst: (
                            {
                                'grades': list(grades.keys()),
                                'grade_phase': {
                                    g: meta.get('phase')
                                    for g, meta in grades.items()
                                    if meta.get('phase')
                                },
                            }
                            if compact else
                            {
                                'subjects': _subjects_from_mapping(system, inst),
                                'grades': list(grades.keys()),
                                'grade_labels': {
                                    g: meta.get('description', g)
                                    for g, meta in grades.items()
                                },
                                # deterministic grade -> phase mapping from the same
                                # authoritative file the pipeline uses
                                'grade_phase': {
                                    g: meta.get('phase')
                                    for g, meta in grades.items()
                                    if meta.get('phase')
                                },
                                'phases': sorted({
                                    meta.get('phase') for meta in grades.values()
                                    if meta.get('phase')
                                }),
                            }
                        )
                        for inst, grades in institutions.items()
                    },
                }

            payload = {
                'status': 'success',
                'systems': systems,
            }
            if not compact:
                payload['elements_by_subject'] = elements_by_subject
            _CURRICULUM_OPTIONS_CACHE.clear()
            _CURRICULUM_OPTIONS_CACHE[cache_key] = payload
            return jsonify(payload)
    except Exception as e:
        logger.error("Curriculum options error: %s", e)
        return jsonify({
            'status': 'error',
            'message': 'Failed to load curriculum options'
        }), 500


# ============================================================
# FEEDBACK WIDGET (click-to-comment untuk revisi UI)
# ============================================================
FEEDBACK_FILE = PROJECT_ROOT / 'db' / 'feedback.json'
FEEDBACK_WIDGET_TAG = '<script src="/feedback-widget.js"></script>'


def _load_feedback():
    with _feedback_lock:
        try:
            if FEEDBACK_FILE.exists():
                value = json.loads(FEEDBACK_FILE.read_text(encoding='utf-8'))
                return value if isinstance(value, list) else []
        except Exception:
            pass
        return []


def _save_feedback(items):
    """Write feedback atomically so readers never see partial JSON."""
    with _feedback_lock:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f'.{FEEDBACK_FILE.name}.',
            suffix='.tmp',
            dir=str(FEEDBACK_FILE.parent),
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(items, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, FEEDBACK_FILE)
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _inject_feedback_widget(html):
    """Sisipkan widget komentar bila URL mengandung ?feedback=1."""
    try:
        if request.args.get('feedback') == '1' and '</body>' in html:
            return html.replace('</body>', FEEDBACK_WIDGET_TAG + '</body>')
    except Exception:
        pass
    return html


@app.route('/api/feedback', methods=['POST'])
def api_feedback_save():
    """Simpan komentar revisi UI dari widget."""
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Body harus object JSON'}), 400
        fields = ('comment', 'timestamp', 'page_url', 'selector', 'tag',
                  'text_snippet', 'viewport')
        for field in fields:
            value = data.get(field)
            if value is not None and not isinstance(value, str):
                return jsonify({
                    'status': 'error',
                    'message': f"Field '{field}' harus string",
                }), 400
        comment = (data.get('comment') or '').strip()
        if not comment:
            return jsonify({'status': 'error', 'message': 'Komentar kosong'}), 400
        entry = {
            'id': uuid.uuid4().hex[:8],
            'timestamp': data.get('timestamp') or '',
            'page_url': (data.get('page_url') or '')[:300],
            'selector': (data.get('selector') or '')[:300],
            'tag': (data.get('tag') or '')[:30],
            'text_snippet': (data.get('text_snippet') or '')[:200],
            'comment': comment[:2000],
            'viewport': (data.get('viewport') or '')[:20],
            'status': 'open',
        }
        # Lock complete read-modify-write transaction; separate locks inside
        # helpers are insufficient because two requests can read same list.
        with _feedback_lock:
            items = _load_feedback()
            items.append(entry)
            _save_feedback(items)
        return jsonify({'status': 'ok', 'id': entry['id']})
    except Exception as e:
        logger.error("Feedback save error: %s", e)
        return jsonify({'status': 'error', 'message': 'Gagal menyimpan'}), 500


@app.route('/api/feedback', methods=['GET'])
def api_feedback_list():
    """Daftar semua komentar (JSON, terbaru dulu)."""
    items = _load_feedback()
    for it in items:
        it.setdefault('status', 'open')
    items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return jsonify({'status': 'ok', 'count': len(items), 'items': items})


@app.route('/api/feedback/<fid>/done', methods=['POST'])
def api_feedback_done(fid):
    """Tandai komentar selesai."""
    return _set_feedback_status(fid, 'done')


@app.route('/api/feedback/<fid>/reopen', methods=['POST'])
def api_feedback_reopen(fid):
    """Buka lagi komentar yang sudah selesai."""
    return _set_feedback_status(fid, 'open')


def _set_feedback_status(fid, status):
    with _feedback_lock:
        items = _load_feedback()
        for it in items:
            if it.get('id') == fid:
                it['status'] = status
                _save_feedback(items)
                return jsonify({'status': 'ok', 'id': fid, 'new_status': status})
    return jsonify({'status': 'error', 'message': 'Komentar tidak ditemukan'}), 404


@app.route('/feedback', methods=['GET'])
def feedback_viewer():
    """Halaman baca semua komentar revisi UI."""
    items = _load_feedback()
    for it in items:
        it.setdefault('status', 'open')
    items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    open_count = sum(1 for it in items if it.get('status') == 'open')
    cards = []
    for it in items:
        ts = _esc(str(it.get('timestamp') or '').replace('T', ' '))
        done = it.get('status') == 'done'
        badge = ('<span style="background:#D6E4D0;color:#3F6212;font-size:12px;font-weight:600;padding:4px 12px;border-radius:9999px;">Selesai</span>' if done else '<span style="background:#FFE4C7;color:#9A3412;font-size:12px;font-weight:600;padding:4px 12px;border-radius:9999px;">Belum</span>')
        fid = it.get('id', '')
        action = ('<button onclick="setStatus(\'' + fid + '\',\'reopen\')" style="margin-top:12px;padding:8px 18px;border-radius:9999px;border:1px solid #E7E5E0;background:#fff;font-size:13px;cursor:pointer;">Buka lagi</button>' if done else '<button onclick="setStatus(\'' + fid + '\',\'done\')" style="margin-top:12px;padding:8px 18px;border-radius:9999px;border:none;background:#A8C3A0;color:#292524;font-weight:600;font-size:13px;cursor:pointer;">&#10003; Tandai selesai</button>')
        dim = 'opacity:0.65;' if done else ''
        card = '<div style="background:#fff;border:1px solid #E7E5E0;border-radius:24px;padding:20px;margin-bottom:16px;' + dim + '">'
        card += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' + badge + '<span style="font-size:12px;color:#78716C;">' + ts + ' &middot; ' + _esc(it.get('viewport', '')) + '</span></div>'
        card += '<div style="font-size:13px;color:#78716C;margin-bottom:4px;">' + _esc(it.get('page_url', '')) + '</div>'
        card += '<div style="font-family:monospace;font-size:12px;background:#F9F7F2;border-radius:8px;padding:6px 10px;margin-bottom:10px;word-break:break-all;">' + _esc(it.get('selector', '')) + '</div>'
        card += '<div style="font-size:16px;color:#292524;">' + _esc(it.get('comment', '')).replace(chr(10), '<br>') + '</div>' + action + '</div>'
        cards.append(card)
    body = ''.join(cards) if cards else '<div style="text-align:center;color:#78716C;padding:60px 20px;">Belum ada komentar.</div>'
    html = '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Komentar Revisi UI</title></head>'
    html += '<body style="margin:0;background:#FDFCF8;font-family:sans-serif;"><div style="max-width:720px;margin:0 auto;padding:24px 16px 60px;">'
    html += '<h1 style="font-size:28px;color:#292524;">Komentar Revisi UI <span style="color:#78716C;font-size:16px;font-weight:400;">(' + str(open_count) + ' belum)</span></h1>' + body
    html += '<script>function setStatus(id,act){fetch("/api/feedback/"+id+"/"+act,{method:"POST"}).then(function(){location.reload();}).catch(function(){alert("Gagal");});}</script></div></body></html>'
    return make_response(html)


def _esc(s):
    """Escape arbitrary persisted feedback before embedding in HTML."""
    return html_escape('' if s is None else str(s), quote=True)






def _react_url(path='/'):
    """Build a public React URL while preserving query parameters."""
    query = request.query_string.decode('utf-8')
    return path + (f'?{query}' if query else '')


def _serve_react_asset(asset):
    """Serve React build assets from the public root."""
    resp = make_response(send_from_directory(str(UI_REACT_DIR), asset))
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/assets/<path:asset>', methods=['GET'])
def react_asset(asset):
    """Serve Vite assets referenced by the root React application."""
    return _serve_react_asset(f'assets/{asset}')


@app.route('/feedback-widget.js', methods=['GET'])
def root_feedback_widget_asset():
    """Serve optional click-to-comment feedback asset at the root."""
    resp = make_response(send_from_directory(str(UI_DIR), 'feedback-widget.js'))
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/app', methods=['GET'])
def ui_app_redirect():
    """Redirect the former primary path to the public root."""
    return redirect(_react_url('/'), code=301)


@app.route('/app/', methods=['GET'])
def ui_app_slash_redirect():
    """Redirect bookmarked /app URLs to the public root."""
    return redirect(_react_url('/'), code=301)


@app.route('/app/feedback-widget.js', methods=['GET'])
def feedback_widget_asset():
    """Keep the old feedback asset URL available."""
    return redirect('/feedback-widget.js', code=301)


@app.route('/app/<path:asset>', methods=['GET'])
def ui_react_asset_redirect(asset):
    """Redirect old React asset URLs to their public-root equivalents."""
    return redirect(_react_url(f'/{asset}'), code=301)


@app.route('/app2', methods=['GET'])
def legacy_react_app_redirect():
    """Move the former React route to the public root."""
    return redirect(_react_url('/'), code=301)


@app.route('/app2/', methods=['GET'])
def legacy_react_app_slash_redirect():
    """Move bookmarked /app2 URLs to the public root."""
    return redirect(_react_url('/'), code=301)


@app.route('/app2/<path:asset>', methods=['GET'])
def legacy_react_asset_redirect(asset):
    """Move old React asset URLs to public-root equivalents."""
    return redirect(_react_url(f'/{asset}'), code=301)


@app.route('/api/cp/<subject>/<phase>', methods=['GET'])
def get_cp(subject, phase):
    """Legacy CP lookup that refuses ambiguous subject/phase pairs.

    A CP is only authoritative with its full identity, including element and
    education system. Clients should use ``/api/context/generate`` for a
    validated lookup; this route remains for integrations with one active CP.
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM learning_outcomes
            WHERE subject = ? AND phase = ?
              AND COALESCE(status, 'active') = 'active'
            ORDER BY source_page, id
        """, (subject, phase))
        rows = cursor.fetchall()

        if not rows:
            return jsonify({
                'status': 'not_found',
                'message': f'CP not found for {subject} - Fase {phase}'
            }), 404

        if len(rows) != 1:
            return jsonify({
                'status': 'error',
                'errors': [{
                    'code': 'AMBIGUOUS_CP_LOOKUP',
                    'message': ('CP harus dipilih dengan identitas lengkap, '
                                'termasuk sistem pendidikan dan elemen.'),
                    'stage': 'curriculum',
                }],
            }), 409
        
        return jsonify({
            'status': 'success',
            'cp': dict(rows[0])
        })
    except Exception:
        logger.exception("CP lookup failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load CP'
        }), 500
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


@app.route('/api/context/generate', methods=['POST'])
def generate_context():
    """Resolve a read-only curriculum context from authoritative data."""
    try:
        try:
            data = request.get_json(force=False, silent=False)
        except Exception as json_err:
            # JSON parsing error - return 400
            return jsonify({
                'status': 'error',
                'message': 'Invalid JSON in request body'
            }), 400
        
        if data is None:
            return jsonify({
                'status': 'error',
                'message': 'Invalid JSON in request body'
            }), 400
        
        # Batch 2 §2: server-side field validation (panjang, tipe,
        # identifier vs mapping otoritatif) sebelum query CP.
        ctx_errors: List[Dict] = []
        for field, cap in (('education_system', MAX_INSTITUTION_CHARS),
                           ('institution_type', MAX_INSTITUTION_CHARS),
                           ('grade', MAX_GRADE_CHARS),
                           ('subject', MAX_SUBJECT_CHARS),
                           ('phase', MAX_PHASE_CHARS),
                           ('element', MAX_ELEMENT_CHARS),
                           ('topic', MAX_TOPIC_CHARS)):
            _check_text_field(data, field, cap, field != 'element'
                              and field != 'topic', ctx_errors)
        _validate_elements_field(data, ctx_errors)
        _check_identifiers(data, ctx_errors)
        if ctx_errors:
            return jsonify({
                'status': 'error',
                'errors': ctx_errors
            }), 400

        # Multi-elemen: preview memakai elemen primer bila 'element'
        # tunggal absen (aturan resolve sama seperti pipeline generate).
        preview = dict(data)
        _primary = _normalize_elements(preview)
        if _primary and not str(preview.get('element') or '').strip():
            preview['element'] = _primary[0]

        # Use the same validator and element-selection rule as the generation
        # pipeline. A preview never fabricates TP/ATP or creates hidden state
        # for a later request.
        with generation_lock:
            is_valid, context_obj, errors = (
                get_generation_pipeline().curriculum_validator.validate(
                    preview))
        if not is_valid or context_obj is None:
            return jsonify({
                'status': 'error',
                'errors': [{'code': 'CURRICULUM_CONTEXT_INVALID',
                            'message': error,
                            'stage': 'curriculum'} for error in errors],
            }), 422
        context_obj.topic = str(data.get('topic') or '').strip()
        context = context_obj.to_dict()
        
        return jsonify({
            'status': 'success',
            'message': 'Context resolved successfully',
            'context': context
        })
    except Exception:
        logger.exception("Context resolve failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to resolve curriculum context'
        }), 500


@app.route('/api/topic/relevance', methods=['POST'])
def topic_relevance():
    """Soft gate relevansi topik<->elemen (advisory, bukan blokir).

    Body sama seperti /api/module/generate (+ flag opsional
    'skip_relevance_check'). Konteks di-resolve via validator kurikulum
    yang sama; AI suhu rendah menilai tiap elemen (RELEVAN /
    KURANG_RELEVAN + alasan 1 kalimat) + saran elemen alternatif dari
    daftar elemen mapel otoritatif. AI down = fail open: lanjut tanpa
    warning. Tidak pernah mengubah perilaku lain.
    """
    try:
        try:
            data = request.get_json(force=False, silent=False)
        except Exception:
            return jsonify({
                'status': 'error',
                'message': 'Invalid JSON in request body'
            }), 400
        if not isinstance(data, dict):
            return jsonify({
                'status': 'error',
                'message': 'Invalid JSON in request body'
            }), 400
        ctx_errors: List[Dict] = []
        for field, cap in (('education_system', MAX_INSTITUTION_CHARS),
                           ('institution_type', MAX_INSTITUTION_CHARS),
                           ('grade', MAX_GRADE_CHARS),
                           ('subject', MAX_SUBJECT_CHARS),
                           ('phase', MAX_PHASE_CHARS),
                           ('element', MAX_ELEMENT_CHARS),
                           ('topic', MAX_TOPIC_CHARS)):
            _check_text_field(data, field, cap, field != 'element'
                              and field != 'topic', ctx_errors)
        _validate_elements_field(data, ctx_errors)
        _check_identifiers(data, ctx_errors)
        if ctx_errors:
            return jsonify({
                'status': 'error',
                'errors': ctx_errors
            }), 400
        if _is_skip_relevance(data):
            return jsonify({
                'status': 'success',
                'relevansi': [],
                'saran': '',
                'perlu_warning': False,
                'skipped': True,
            }), 200
        payload = _check_topic_relevance(data)
        if payload is None:
            # Fail open: konteks/AI tak tersedia — lanjut tanpa warning.
            return jsonify({
                'status': 'success',
                'relevansi': [],
                'saran': '',
                'perlu_warning': False,
                'fail_open': True,
            }), 200
        return jsonify({
            'status': 'success',
            'relevansi': payload.get('relevansi', []),
            'saran': payload.get('saran', ''),
            'perlu_warning': bool(payload.get('perlu_warning')),
        }), 200
    except Exception:
        logger.exception("Topic relevance check failed")
        return jsonify({
            'status': 'success',
            'relevansi': [],
            'saran': '',
            'perlu_warning': False,
            'fail_open': True,
        }), 200


def _to_semester(value) -> Optional[int]:
    """Normalisasi input semester user: 1/2 valid, selain itu None.

    None berarti tidak dirender (pipeline tidak memakai default
    diam-diam)."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    return number if number in (1, 2) else None


def _to_count(value) -> Optional[int]:
    """Normalisasi input hitung user (pertemuan/JP): int >= 1 valid,
    selain itu None (pipeline fail closed bila salah satu terisi)."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    if isinstance(value, bool):
        return None
    return number if number >= 1 else None


def _validate_meetings_input(raw_n, raw_jp) -> Optional[str]:
    """Error jelas bila alokasi pertemuan sebagian/invalid; None bila
    absen total (mode lama) atau lengkap valid."""
    has_n = raw_n is not None and str(raw_n).strip() != ''
    has_jp = raw_jp is not None and str(raw_jp).strip() != ''
    if not has_n and not has_jp:
        return None
    if _to_count(raw_n) is None or _to_count(raw_jp) is None:
        return ("Input alokasi waktu invalid: 'jumlah_pertemuan' dan "
                "'jp_per_pertemuan' wajib bilangan bulat >= 1 bila salah "
                "satu diisi.")
    return None


# ---------------------------------------------------------------------------
# Batch 2 §2: server-side input limits (frontend validation is never
# trusted). All caps are deterministic and documented here.
# ---------------------------------------------------------------------------
MAX_TOPIC_CHARS = 200
MAX_PENYUSUN_CHARS = 100
MAX_SATUAN_CHARS = 200
MAX_READINESS_CHARS = 2000
MAX_TAHUN_CHARS = 20
MAX_ELEMENT_CHARS = 100
MAX_SUBJECT_CHARS = 100
MAX_GRADE_CHARS = 20
MAX_INSTITUTION_CHARS = 30
MAX_PHASE_CHARS = 10
MAX_MEETINGS = 16
MAX_JP_PER_MEETING = 10
MAX_TOTAL_MINUTES = 7200  # 16 pertemuan x 10 JP x 45 menit
# Relevansi topik<->elemen (soft gate: AI suhu rendah, fail open tanpa
# warning bila gateway down). Batas item menjaga prompt tetap bounded.
MAX_ELEMENTS_COUNT = 10
MAX_CP_SNIPPET_CHARS = 500
RELEVANCE_TEMPERATURE = 0.1
RELEVANCE_MAX_TOKENS = 1500
VALID_SYSTEMS = ('KEMENAG', 'KEMENDIKDASMEN')
VALID_PHASES = ('A', 'B', 'C', 'D', 'E', 'F', 'Fondasi')

_mappings_cache: Optional[Dict] = None


def _curriculum_mappings() -> Dict:
    """db/curriculum_mappings.json (sumber otoritatif, di-cache)."""
    global _mappings_cache
    if _mappings_cache is None:
        with open(PROJECT_ROOT / 'db' / 'curriculum_mappings.json',
                  encoding='utf-8') as f:
            _mappings_cache = json.load(f)
    return _mappings_cache


def _reject(message: str) -> Dict:
    return {'code': 'INVALID_PARAMS', 'message': message, 'stage': 'input'}


def _check_text_field(data: Dict, field: str, max_chars: int,
                      required: bool, errors: List[Dict]) -> None:
    """Validasi satu field string: tipe, null byte, kosong, panjang."""
    value = data.get(field)
    if value is None:
        if required:
            errors.append(_reject(f"Field wajib kosong: '{field}'."))
        return
    if not isinstance(value, str):
        errors.append(_reject(
            f"Field '{field}' harus string."))
        return
    if '\x00' in value:
        errors.append(_reject(
            f"Field '{field}' mengandung karakter invalid."))
        return
    if required and not value.strip():
        errors.append(_reject(f"Field wajib kosong: '{field}'."))
        return
    if len(value) > max_chars:
        errors.append(_reject(
            f"Field '{field}' melebihi {max_chars} karakter "
            f"({len(value)} diterima)."))


def _check_identifiers(context: Dict, errors: List[Dict]) -> None:
    """Identifier kurikulum vs mapping otoritatif (fail fast 400)."""
    system = context.get('education_system')
    if system not in VALID_SYSTEMS:
        errors.append(_reject(
            f"education_system invalid: {system!r}."))
        return
    try:
        mappings = _curriculum_mappings()
        institutions = mappings.get('grade_to_phase_mappings', {}).get(
            system, {})
    except Exception:
        return  # mapping tak terbaca: pipeline yang menutup (422)
    inst = context.get('institution_type')
    if not isinstance(inst, str) or len(inst) > MAX_INSTITUTION_CHARS \
            or inst not in institutions:
        errors.append(_reject(
            f"institution_type invalid untuk {system}: {inst!r}."))
        return
    grade = context.get('grade')
    grades = institutions.get(inst) or {}
    if not isinstance(grade, str) or len(grade) > MAX_GRADE_CHARS \
            or grade not in grades:
        errors.append(_reject(
            f"grade invalid untuk {inst}: {grade!r}."))
        return
    phase = context.get('phase')
    if phase is not None and (
            not isinstance(phase, str) or len(phase) > MAX_PHASE_CHARS
            or phase not in VALID_PHASES):
        errors.append(_reject(f"phase invalid: {phase!r}."))
        return
    expected_phase = (grades.get(grade) or {}).get('phase')
    if isinstance(phase, str) and expected_phase and phase != expected_phase:
        errors.append(_reject(
            f"phase {phase!r} tidak sesuai grade {grade!r} "
            f"(seharusnya {expected_phase!r})."))


def _check_meeting_caps(data: Dict, context: Dict,
                        errors: List[Dict]) -> None:
    """Batas pertemuan/JP/total alokasi (400 bila melanggar)."""
    raw_n, raw_jp = data.get('jumlah_pertemuan'), data.get('jp_per_pertemuan')
    has_n = raw_n is not None and str(raw_n).strip() != ''
    has_jp = raw_jp is not None and str(raw_jp).strip() != ''
    if not has_n and not has_jp:
        return
    n, jp = _to_count(raw_n), _to_count(raw_jp)
    if n is None or jp is None:
        return  # pesan invalid rinci milik _validate_meetings_input
    if n > MAX_MEETINGS:
        errors.append(_reject(
            f"'jumlah_pertemuan' melebihi {MAX_MEETINGS} ({n} diterima)."))
    if jp > MAX_JP_PER_MEETING:
        errors.append(_reject(
            f"'jp_per_pertemuan' melebihi {MAX_JP_PER_MEETING} ({jp} diterima)."))
    if errors:
        return
    try:
        from module_generation_pipeline import resolve_jp_menit
        minutes, _ = resolve_jp_menit(
            context.get('institution_type'), context.get('phase'),
            context.get('grade'))
        if minutes and n * jp * minutes > MAX_TOTAL_MINUTES:
            errors.append(_reject(
                f"Total alokasi {n * jp * minutes} menit melebihi "
                f"{MAX_TOTAL_MINUTES} menit."))
    except Exception:
        pass  # JP tak teresolusi: pipeline menutup dengan 422


def _validate_elements_field(data: Dict, errors: List[Dict]) -> None:
    """Validasi 'elements' list (multi-elemen); 'element' tunggal lama tetap
    divalidasi _check_text_field. Absen = mode lama (valid)."""
    if data.get('elements') is None:
        return
    raw = data.get('elements')
    if not isinstance(raw, list):
        errors.append(_reject("Field 'elements' harus list string."))
        return
    if len(raw) > MAX_ELEMENTS_COUNT:
        errors.append(_reject(
            f"Field 'elements' melebihi {MAX_ELEMENTS_COUNT} item "
            f"({len(raw)} diterima)."))
        return
    for item in raw:
        if not isinstance(item, str):
            errors.append(_reject("Tiap item 'elements' harus string."))
            return
        if '\x00' in item:
            errors.append(_reject(
                "Field 'elements' mengandung karakter invalid."))
            return
        if not item.strip():
            errors.append(_reject(
                "Tiap item 'elements' tidak boleh kosong."))
            return
        if len(item) > MAX_ELEMENT_CHARS:
            errors.append(_reject(
                f"Tiap item 'elements' melebihi {MAX_ELEMENT_CHARS} "
                f"karakter ({len(item)} diterima)."))
            return


def _normalize_elements(data: Dict) -> List[str]:
    """List elemen unik (urut stabil): 'element' primer dulu, lalu
    'elements'. Primer di depan agar validator kurikulum me-resolve CP dari
    elemen yang sama seperti mode tunggal lama."""
    out: List[str] = []
    seen = set()
    primary = data.get('element')
    if isinstance(primary, str) and primary.strip():
        out.append(primary.strip())
        seen.add(primary.strip())
    raw = data.get('elements')
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip() \
                    and item.strip() not in seen:
                seen.add(item.strip())
                out.append(item.strip())
    return out


def validate_generate_body(data: Dict, context: Optional[Dict]) -> List[Dict]:
    """Validasi server-side penuh body /api/module/generate (sync+async).

    Return list error terstruktur (kosong = valid). Tidak memanggil AI.
    """
    errors: List[Dict] = []
    if not isinstance(data, dict):
        return [_reject('Request body harus object JSON.')]
    for field, cap in (('topic', MAX_TOPIC_CHARS),
                       ('penyusun', MAX_PENYUSUN_CHARS),
                       ('satuan_pendidikan', MAX_SATUAN_CHARS),
                       ('student_readiness', MAX_READINESS_CHARS),
                       ('tahun_ajaran', MAX_TAHUN_CHARS),
                       ('element', MAX_ELEMENT_CHARS)):
        _check_text_field(data, field, cap, False, errors)
    # Multi-elemen: 'elements' list string (tiap <= MAX_ELEMENT_CHARS);
    # 'element' tunggal lama tetap valid.
    _validate_elements_field(data, errors)
    ctx = context or {}
    if isinstance(ctx.get('subject'), str) and len(ctx['subject']) > MAX_SUBJECT_CHARS:
        errors.append(_reject('subject melebihi batas panjang.'))
    _check_identifiers(ctx, errors)
    _check_meeting_caps(data, ctx, errors)
    return errors


def _generation_params_from_request(data: Dict) -> Dict:
    """Build generation input from this request only.

    The pipeline resolves CP and all normative curriculum fields itself. A
    preceding preview must never become hidden state for a later generation.
    Multi-elemen: 'elements' list ikut dibawa; 'element' = primer (item
    pertama hasil normalisasi) agar validator CP me-resolve elemen yang
    sama seperti mode tunggal lama.
    """
    elements = _normalize_elements(data)
    return {
        'subject': data.get('subject'),
        'grade': data.get('grade'),
        'institution_type': data.get('institution_type'),
        'education_system': data.get('education_system'),
        'phase': data.get('phase'),
        'topic': str(data.get('topic') or '').strip(),
        'element': elements[0] if elements else data.get('element'),
        'elements': elements,
        'semester': _to_semester(data.get('semester')),
        'year': str(data.get('tahun_ajaran') or '').strip() or None,
        'satuan_pendidikan': (
            str(data.get('satuan_pendidikan') or '').strip() or None),
        'penyusun': str(data.get('penyusun') or '').strip() or None,
        'student_readiness': (
            str(data.get('student_readiness') or '').strip() or None),
        'jumlah_pertemuan': _to_count(data.get('jumlah_pertemuan')),
        'jp_per_pertemuan': _to_count(data.get('jp_per_pertemuan')),
        'assessment_counts': data.get('assessment_counts'),
        'buku_document_id': str(data.get('buku_document_id') or '').strip()
        or None,
    }


def _is_skip_relevance(data: Dict) -> bool:
    """Flag 'skip_relevance_check': bool True / 1 / string true-like =
    lewati gate relevansi (AI tidak dipanggil)."""
    raw = data.get('skip_relevance_check')
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw == 1
    if isinstance(raw, str):
        return raw.strip().lower() in ('1', 'true', 'ya', 'yes', 'y')
    return False


def _relevance_preview_params(data: Dict) -> Dict:
    """Body untuk validator kurikulum: 'element' diisi primer bila tunggal
    absen (aturan resolve sama seperti pipeline generate)."""
    preview = dict(data)
    primary = _normalize_elements(preview)
    if primary and not str(preview.get('element') or '').strip():
        preview['element'] = primary[0]
    return preview


def _parse_relevance_response(response, elements: List[str]) -> Optional[Dict]:
    """Normalisasi JSON AI -> payload relevansi; None bila tak terpahami
    (fail open). Nilai valid: RELEVAN / KURANG_RELEVAN."""
    if not isinstance(response, dict):
        return None
    raw_items = response.get('relevansi')
    if not isinstance(raw_items, list):
        return None
    seen = set()
    relevansi: List[Dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get('elemen') or '').strip()
        if not name or name in seen:
            continue
        nilai = str(item.get('nilai') or '').strip().upper().replace(
            ' ', '_').replace('-', '_')
        if nilai in ('KURANG', 'KURANG_RELEVAN', 'TIDAK_RELEVAN',
                     'TIDAKRELEVAN'):
            nilai = 'KURANG_RELEVAN'
        elif nilai != 'RELEVAN':
            continue  # nilai tak dikenal: buang item, jangan karang
        seen.add(name)
        relevansi.append({
            'elemen': name,
            'nilai': nilai,
            'alasan': str(item.get('alasan') or '').strip(),
        })
    if not relevansi:
        return None
    perlu_warning = (any(r['nilai'] != 'RELEVAN' for r in relevansi)
                     or bool(response.get('perlu_warning')))
    return {
        'relevansi': relevansi,
        'saran': str(response.get('saran') or '').strip(),
        'perlu_warning': perlu_warning,
    }


def _check_topic_relevance(data: Dict,
                           context_obj=None) -> Optional[Dict]:
    """Soft gate relevansi topik<->elemen via AI suhu rendah.

    Return payload {'relevansi', 'saran', 'perlu_warning'}; None = fail
    open (AI down / respons tak terpahami / konteks tak teresolusi) —
    pemanggil lanjut tanpa warning. Tidak pernah raise, tidak memblokir
    generate, tidak mengubah perilaku lain. Seluruh akses engine + AI
    di bawah generation_lock (serialisasi akses engine + metadata
    respons AI, sama seperti stage pipeline).
    """
    try:
        elements = _normalize_elements(data)
        topic = str(data.get('topic') or '').strip()
        if not elements or not topic:
            return {'relevansi': [], 'saran': '', 'perlu_warning': False}
        pipeline = get_generation_pipeline()
        with generation_lock:
            if context_obj is None:
                preview = _relevance_preview_params(data)
                is_valid, context_obj, _err = (
                    pipeline.curriculum_validator.validate(preview))
                if not is_valid or context_obj is None:
                    return None  # error kurikulum milik pipeline (422 sendiri)
            try:
                cp_text = str(getattr(context_obj.cp, 'text', '') or '')
            except Exception:
                cp_text = ''
            if len(cp_text) > MAX_CP_SNIPPET_CHARS:
                cp_text = cp_text[:MAX_CP_SNIPPET_CHARS] + '…'
            subject = str(context_obj.subject or '')
            phase = str(context_obj.phase or '')
            primary = str(context_obj.element or '')
            # Kandidat saran alternatif: daftar elemen mapel otoritatif
            # dari DB.
            candidates: List[str] = []
            try:
                from module_generation_pipeline import (
                    default_curriculum_version)
                engine = pipeline.curriculum_validator.curriculum_engine
                cp_list = engine.get_cp_by_subject_phase(
                    subject, phase,
                    education_system=context_obj.education_system,
                    institution_type=context_obj.institution_type,
                    curriculum_version_id=default_curriculum_version(
                        context_obj.education_system),
                )
                candidates = sorted({str(c.element or '').strip()
                                     for c in cp_list
                                     if str(c.element or '').strip()})
            except Exception:
                candidates = []
            numbered = '\n'.join(
                f"{i}. {e}" for i, e in enumerate(elements, 1))
            system_prompt = (
                "Anda adalah ahli kurikulum Indonesia. Nilai relevansi "
                "topik pembelajaran terhadap tiap elemen mata pelajaran. "
                "Respond dengan JSON ONLY, tanpa markdown."
            )
            user_prompt = (
                f"Topik pembelajaran: {topic}\n"
                f"Mata pelajaran: {subject} | Fase: {phase} | "
                f"Elemen primer: {primary}\n"
                f"Ringkasan CP elemen primer: {cp_text}\n\n"
                f"Nilai relevansi topik di atas terhadap tiap elemen "
                f"berikut:\n"
                f"{numbered}\n\n"
                f"Daftar elemen valid mata pelajaran ini (untuk saran "
                f"alternatif): "
                f"{', '.join(candidates) if candidates else '-'}\n\n"
                f"Respond dengan JSON:\n"
                f'{{"relevansi": [{{"elemen": "<nama elemen>", '
                f'"nilai": "RELEVAN" atau "KURANG_RELEVAN", '
                f'"alasan": "<satu kalimat>"}}], '
                f'"saran": "<elemen alternatif dari daftar di atas bila '
                f'ada yang KURANG_RELEVAN, atau string kosong>", '
                f'"perlu_warning": <true bila ada KURANG_RELEVAN>}}'
            )
            try:
                response = pipeline.ai_client.generate_json(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                    temperature=RELEVANCE_TEMPERATURE,
                    max_tokens=RELEVANCE_MAX_TOKENS,
                )
            except Exception:
                logger.warning("Relevance check: AI unavailable (fail open)")
                return None
        return _parse_relevance_response(response, elements)
    except Exception:
        logger.warning("Relevance check failed (fail open)", exc_info=True)
        return None


def _relevance_gate_response(data: Dict):
    """Return respons Flask 422 bila soft gate terpicu; None bila lolos
    (skip flag / fail open / semua relevan). Bukan blokir: klien dapat
    mengulang dengan 'skip_relevance_check': true."""
    if _is_skip_relevance(data):
        return None
    payload = _check_topic_relevance(data)
    if payload is None or not payload.get('perlu_warning'):
        return None
    return jsonify({
        'status': 'warning',
        'code': 'RELEVANCE_WARNING',
        'message': ('Topik kurang relevan dengan elemen yang dipilih. '
                    "Periksa 'saran' elemen alternatif, lalu ulangi dengan "
                    "'skip_relevance_check': true untuk tetap melanjutkan."),
        'relevansi': payload.get('relevansi', []),
        'saran': payload.get('saran', ''),
        'perlu_warning': True,
    }), 422


def _valid_generation_id(generation_id) -> bool:
    """Format ID aman: string pendek tanpa traversal/pemisah (400 bila
    malformed; ID tak dikenal tetap 404 — tidak membocorkan apa pun)."""
    return (isinstance(generation_id, str) and 1 <= len(generation_id) <= 128
            and '/' not in generation_id and '\\' not in generation_id
            and '..' not in generation_id and '\x00' not in generation_id)


# Phase C.2: real generation pipeline (lazy-initialized, shared across requests)
_generation_pipeline = None


def get_generation_pipeline():
    """Get or create the shared ModuleGenerationPipeline instance."""
    global _generation_pipeline
    if _generation_pipeline is None:
        with _generation_pipeline_lock:
            if _generation_pipeline is None:
                _generation_pipeline = ModuleGenerationPipeline(
                    db_path=str(DB_PATH))
    return _generation_pipeline


# ---------------------------------------------------------------------------
# Persistent edit (PUT /api/module/<generation_id>)
#
# Storage: generated_modules table (see module_store.py) holding the final
# module JSON plus the AUTHORITATIVE generation context. Protected values
# are always re-loaded from that stored context — the client is never
# trusted for CP / provenance / phase / subject / education system /
# curriculum version.
#
# Validation before save (all reuse pipeline validators, nothing new):
#   schema -> protected fields vs original context -> pedagogical ->
#   alignment (Master Outline incl. KKTP level floors) -> final
# Only if every stage passes is the database written; a failed PUT leaves
# storage byte-identical.
# ---------------------------------------------------------------------------

# Top-level module keys the client may NOT alter through PUT. The stored
# authoritative context is spliced back into the module instead.
PUT_PROTECTED_TOP_KEYS = {
    'id', 'generation_id', 'curriculum_version', 'curriculum_context',
    'master_outline', 'approach_principles',
    'validation_results', 'generated_at', 'generated_by',
    # D terstruktur per pertemuan adalah hasil komputasi deterministik
    # dari aktivitas tervalidasi, bukan field editabel klien.
    'meetings',
    # Provenance konsultasi regulasi (BKPDM/KMA): deterministik dari
    # DB, bukan field yang boleh diubah klien.
    'regulatory_consultation',
}

# Dataclass field types used to rebuild typed entries from client JSON.
_TP_FIELDS = [f.name for f in dataclass_fields(TPEntry)]
_KKTP_FIELDS = [f.name for f in dataclass_fields(KKTPEntry)]
_ACT_FIELDS = [f.name for f in dataclass_fields(ActivityEntry)]


def _resolve_app_store():
    """ModuleStore bound to the same DB the pipeline uses."""
    pipeline = get_generation_pipeline()
    return ModuleStore(pipeline.db_path)


def _rebuild_context_from_storage(generation_id: str, stored: Dict):
    """Restore the authoritative CurriculumContext OBJECT from the persisted
    context JSON.

    RESTART-SAFE: this never consults in-memory state — the context needed
    for edit re-validation (protection + KKTP level rules) is rebuilt from
    ``generated_modules.context_json`` written at generation time, which is
    a full asdict() of the original context (cp provenance, tp, atp, topic,
    metadata).
    """
    ctx_data = stored.get('context')
    if not isinstance(ctx_data, dict) or not ctx_data:
        return None
    try:
        return CurriculumContext.from_dict(ctx_data)
    except (ValueError, TypeError):
        logger.warning("Stored context for %s is not rebuildable", generation_id)
        return None


def _coerce_typed_lists(payload: Dict) -> None:
    """Rebuild typed entries from JSON dicts so the dataclass validators run
    on real objects (in place)."""
    payload['learning_objectives'] = [
        TPEntry(**{k: tp.get(k) for k in _TP_FIELDS})
        for tp in payload.get('learning_objectives') or []
        if isinstance(tp, dict)
    ]
    payload['success_criteria'] = [
        KKTPEntry(**{k: k_ for k, k_ in kk.items() if k in _KKTP_FIELDS})
        for kk in payload.get('success_criteria') or []
        if isinstance(kk, dict)
    ]
    payload['learning_activities'] = [
        ActivityEntry(**{k: a.get(k) for k in _ACT_FIELDS})
        for a in payload.get('learning_activities') or []
        if isinstance(a, dict)
    ]


# ---------------------------------------------------------------------------
# Batch 5: editing, partial regeneration & versioning.
#
# Model: v1 = AI baseline (materialized from generated_modules on first
# versioned write), vN = teacher edit / partial regen (parent linked).
# Old versions are immutable (INSERT-only store). Optimistic concurrency
# via base_version (HTTP 409 on stale). Export serves the selected
# version through the existing final-validation hard gate.
# ---------------------------------------------------------------------------

EDITABLE_SECTIONS = (
    'tp', 'kktp', 'topic', 'readiness', 'material', 'materi',
    'aktivitas', 'refleksi', 'asesmen', 'rubrik', 'lkpd', 'glosarium', 'meta',
    'pertemuan',
)

REGEN_TARGETS = (
    'tp', 'kktp', 'materi', 'praktik_pedagogis', 'aktivitas', 'asesmen',
    'rubrik', 'refleksi', 'glosarium', 'diagnostik', 'formatif', 'sumatif',
)

# Sub-bucket asesmen -> bucket assessments (diagnostic/formative/summative).
REGEN_SUBBUCKET = {
    'diagnostik': 'diagnostic',
    'formatif': 'formative',
    'sumatif': 'summative',
}

# Dependency eksplisit (Batch 5 §9): perubahan section dapat membuat
# section lain tidak selaras. Tidak ada regenerate otomatis.
SECTION_DEPENDENTS = {
    'tp': ['kktp', 'materi', 'aktivitas', 'asesmen', 'rubrik', 'glosarium'],
    'kktp': ['asesmen', 'rubrik'],
    'topic': ['glosarium'],
    'readiness': [],
    'material': ['aktivitas', 'asesmen', 'glosarium'],
    'materi': ['aktivitas', 'asesmen', 'glosarium'],
    'aktivitas': ['asesmen', 'rubrik'],
    'refleksi': [],
    'asesmen': ['rubrik'],
    'diagnostik': ['rubrik'],
    'formatif': ['rubrik'],
    'sumatif': ['rubrik'],
    'rubrik': [],
    'lkpd': [],
    'glosarium': [],
    'meta': [],
}

# Error alignment (downstream belum disesuaikan) vs struktural.
# Alignment-only failures may persist as Needs-review drafts; structural
# failures always reject (422, no version).
ALIGNMENT_SOFT_CODES = {
    'TP_ALIGNMENT_ERROR', 'ASSESSMENT_ERROR', 'RUBRIC_ERROR',
    'RUBRIC_DESCRIPTOR_WEAK', 'BLUEPRINT_ERROR', 'ACTIVITY_ERROR',
}

# Impor (R-37): KKTP_ERROR level + ALIGNMENT_SOFT_CODES → draf
# berflag, bukan tolak. Struktural (skema, proteksi, faktualitas,
# final, TP_LEVEL_INVALID, glosarium, KKTP hilang) tetap tolak.
IMPORT_DRAFTABLE_CODES = frozenset(ALIGNMENT_SOFT_CODES | {
    'KKTP_ERROR',
})


def _split_import_errors(errors: List[Dict]
                         ) -> Tuple[List[Dict], List[Dict]]:
    """Pisah error baterai impor: (hard_tolak, soft_draf).

    KKTP hilang total ('has no KKTP') tetap tolak: tanpa KKTP tidak
    ada bukti ketercapaian sama sekali.
    """
    hard, soft = [], []
    for err in errors or []:
        code = (err.get('code') or '') if isinstance(err, dict) \
            else ''
        msg = (err.get('message') or '') if isinstance(err, dict) \
            else str(err)
        if code == 'KKTP_ERROR' and 'has no KKTP' in msg:
            hard.append(err)
        elif code in IMPORT_DRAFTABLE_CODES or _is_soft_error(
                code, msg):
            soft.append(err)
        else:
            hard.append(err)
    return hard, soft

_COG_ORDER = {'C1': 1, 'C2': 2, 'C3': 3, 'C4': 4, 'C5': 5, 'C6': 6}


def _is_soft_error(code: str, message: str) -> bool:
    if code in ALIGNMENT_SOFT_CODES:
        return True
    # KKTP hilang setelah TP diedit = downstream belum disesuaikan
    # (reviewable); level-drop = pelanggaran rules (hard).
    if code == 'KKTP_ERROR' and 'has no KKTP' in (message or ''):
        return True
    return False


def _dependency_warnings(changed: List[str]) -> List[str]:
    warnings = []
    for section in changed or []:
        deps = SECTION_DEPENDENTS.get(section, [])
        if deps:
            warnings.append(
                f"Perubahan {section} dapat membuat "
                f"{', '.join(deps)} menjadi tidak selaras. Simpan saja, "
                f"atau regenerate bagian terkait.")
    return warnings


def _meetings_spec_from_module(module_dict: Dict) -> Optional[Dict]:
    """Spec alokasi dari meetings tersimpan (deterministik)."""
    meetings = module_dict.get('meetings') or []
    if not meetings or not isinstance(meetings, list):
        return None
    first = meetings[0] if isinstance(meetings[0], dict) else {}
    try:
        return {
            'n_meetings': len(meetings),
            'jp_per_meeting': int(first.get('jp')),
            'minutes_per_jp': int(first.get('minutes_per_jp')),
        }
    except (TypeError, ValueError):
        return None


def _build_module_from_merged(merged: Dict, original_context) -> Module:
    """Bangun Module typed dari dict gabungan (dipakai PUT + versions).

    Identik dengan konstruksi PUT legacy — diekstrak agar kedua jalur
    memakai objek yang sama persis (tidak ada divergensi validasi).
    """
    return Module(
        id=merged.get('id', ''),
        title=merged.get('title', ''),
        subject=merged.get('subject', ''),
        grade=merged.get('grade', ''),
        phase=merged.get('phase', ''),
        curriculum_version=merged.get('curriculum_version', ''),
        module_identity=merged.get('module_identity', {}),
        facilities=merged.get('facilities', []),
        target_students=merged.get('target_students', {}),
        learning_model=merged.get('learning_model', ''),
        methods=merged.get('methods', []),
        learning_objectives=merged.get('learning_objectives', []),
        success_criteria=merged.get('success_criteria', []),
        essential_understanding=merged.get('essential_understanding', {}),
        guiding_questions=merged.get('guiding_questions', []),
        learning_activities=merged.get('learning_activities', []),
        assessments=merged.get('assessments', {}),
        reflection=merged.get('reflection', []),
        remedial=merged.get('remedial'),
        enrichment=merged.get('enrichment'),
        references=merged.get('references', []),
        appendices=merged.get('appendices', {}),
        initial_competence=merged.get('initial_competence'),
        profile_dimensions=merged.get('profile_dimensions', []),
        approach_principles=merged.get('approach_principles', {}),
        learning_phases=merged.get('learning_phases', {}),
        blueprint=merged.get('blueprint', []),
        rubric=merged.get('rubric', {}),
        lkpd=merged.get('lkpd', []),
        glosarium=merged.get('glosarium', []),
        instrument_recap=merged.get('instrument_recap', {}),
        learner_readiness=merged.get('learner_readiness'),
        material_characteristics=merged.get('material_characteristics'),
        pedagogical_practices=merged.get('pedagogical_practices', []),
        learning_partnerships=merged.get('learning_partnerships', []),
        learning_environment=merged.get('learning_environment', {}),
        digital_use=merged.get('digital_use', {}),
        unit=merged.get('unit'),
        regulatory_consultation=merged.get('regulatory_consultation'),
        curriculum_context=original_context,
        validation_results={},
        generation_id=merged.get('generation_id', ''),
        generated_at=merged.get('generated_at', ''),
        generated_by=merged.get('generated_by', ''),
        topic=merged.get('topic', ''),
        topic_seed=merged.get('topic_seed', ''),
        profile_dimension_notes=merged.get('profile_dimension_notes', {}),
        penyusun=merged.get('penyusun', ''),
        student_readiness=merged.get('student_readiness', ''),
        meetings=merged.get('meetings', []),
    )

def _prepare_merged_for_battery(merged: Dict, original_context,
                                pipeline) -> Tuple[Optional[Module], List[Dict]]:
    """Coerce + build + re-derivasi deterministik + sync balik ke merged.

    Return (module, schema_errors). Re-derivasi (level TP dari teks,
    A.3, blueprint, rubrik, rekap, kktp_linked tunggal, fase, meetings
    + budget) dihitung dari konten, tidak dipercaya dari klien.
    """
    schema_errors: List[Dict] = []
    try:
        _coerce_typed_lists(merged)
        module = _build_module_from_merged(merged, original_context)
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return None, [{'code': 'SCHEMA_ERROR',
                       'message': 'Module payload does not match the module '
                                  'schema.',
                       'stage': 'schema'}]
    hard: List[Dict] = []
    # Level TP dari teks (floor C3).
    for tp in module.learning_objectives:
        level = pipeline.rule_validator._extract_cognitive_level(
            tp.text or '')
        if level not in ('C3', 'C4', 'C5', 'C6'):
            hard.append({'code': 'TP_LEVEL_INVALID',
                         'message': f'{tp.id} has cognitive level {level!r} '
                                    f'(minimum C3 required)',
                         'stage': 'rules'})
        else:
            tp.cognitive_level = level
    if not hard:
        # A.3 + catatan relevansi dipertahankan dari otoritatif tersimpan
        # (Batch 8.5 §2: pasangan dimensi-alasan tidak boleh tercerai;
        # reset ke full-8 legacy dihapus karena merusak pairing).
        tp_texts = [t.text for t in module.learning_objectives]
        tp_level_by_id = {t.id: t.cognitive_level
                          for t in module.learning_objectives}
        asm = module.assessments if isinstance(
            module.assessments, dict) else {}
        module.blueprint = build_blueprint(tp_texts, asm)
        for row in module.blueprint:
            row['cognitive_level'] = tp_level_by_id.get(row.get('tp_id'))
        descriptors = asm.get('rubric_descriptors') \
            if isinstance(asm.get('rubric_descriptors'), dict) else {}
        module.rubric = build_rubric(module.success_criteria, descriptors)
        module.instrument_recap = build_instrument_recap(asm)
        kktp_by_tp: Dict[str, List[str]] = {}
        for kktp in module.success_criteria:
            kktp_by_tp.setdefault(kktp.tp_id, []).append(kktp.id)
        for item in asm.get('formative') or []:
            if isinstance(item, dict) and not item.get('kktp_linked'):
                candidates = kktp_by_tp.get(item.get('tp_linked'), [])
                if len(candidates) == 1:
                    item['kktp_linked'] = candidates[0]
        module.learning_phases = build_learning_phases(
            module.learning_activities)
        spec = _meetings_spec_from_module(
            {'meetings': module.meetings} if isinstance(
                getattr(module, 'meetings', None), list) else {})
        acts_dicts = [dataclass_asdict(a) for a in module.learning_activities]
        if spec is not None and acts_dicts:
            budget_errors = validate_time_budget(
                acts_dicts, spec['n_meetings'],
                spec['jp_per_meeting'] * spec['minutes_per_jp'],
                {t.id for t in module.learning_objectives})
            for e in budget_errors:
                code, _, message = str(e).partition(': ')
                hard.append({'code': code or 'TIME_BUDGET_INVALID',
                             'message': message or str(e),
                             'stage': 'time_budget'})
            if not budget_errors:
                # Prinsip per pertemuan dibawa per indeks bila lengkap;
                # pertemuan baru/tanpa prinsip lengkap tidak dikarang
                # (render skip senyap). Berlaku saat jumlah sama maupun
                # berubah (tambah/kurang pertemuan).
                previous = [m.get('principles') for m in
                            (module.meetings or [])]
                rebuilt = build_meetings(
                    acts_dicts, spec['n_meetings'], spec['jp_per_meeting'],
                    spec['minutes_per_jp'])
                carried = []
                for i in range(len(rebuilt)):
                    prev = previous[i] if i < len(previous) else None
                    if isinstance(prev, dict) and all(
                            prev.get(k) for k in
                            ('berkesadaran', 'bermakna', 'menggembirakan')):
                        carried.append({'meeting': i + 1, **prev})
                    else:
                        carried.append({'meeting': i + 1})
                module.meetings = attach_meeting_principles(
                    rebuilt, carried)
    # KBC traceability dihitung ulang dari aktivitas saat ini agar
    # activity_ids tidak basi setelah edit (deterministik, Batch 1).
    try:
        from module_generation_pipeline import (
            resolve_kbc_insertions as _resolve_kbc)
        ap = module.approach_principles
        kbc = (ap or {}).get('kbc') if isinstance(ap, dict) else None
        if isinstance(kbc, dict) and kbc.get('enabled'):
            kbc = dict(kbc)
            kbc['insertions'] = _resolve_kbc(
                kbc, [dataclass_asdict(a)
                      for a in module.learning_activities])
            module.approach_principles = dict(ap, kbc=kbc)
            merged['approach_principles'] = module.approach_principles
    except Exception:
        pass
    # Sync balik: yang disimpan/dikembalikan adalah nilai turunan.
    # Bila derivasi menemukan hard error, tidak ada sync (tidak ada
    # save pada pemanggil) — kembalikan None agar pemanggil 422.
    if hard:
        return None, hard
    merged['learning_objectives'] = [
        dataclass_asdict(t) for t in module.learning_objectives]
    merged['success_criteria'] = [
        dataclass_asdict(k) for k in module.success_criteria]
    merged['learning_activities'] = [
        dataclass_asdict(a) for a in module.learning_activities]
    merged['blueprint'] = module.blueprint
    merged['rubric'] = module.rubric
    merged['instrument_recap'] = module.instrument_recap
    merged['learning_phases'] = module.learning_phases
    merged['meetings'] = module.meetings
    merged['profile_dimensions'] = module.profile_dimensions
    merged['profile_dimension_notes'] = dict(
        module.profile_dimension_notes or {})
    return module, hard


def _run_version_battery(module: Module, original_context,
                         pipeline) -> Tuple[List[Dict], List[Dict]]:
    """Validator Batch 1–3 atas Module (murni validasi, tanpa mutasi).

    Return (hard_errors, soft_errors); soft = downstream misalignment
    yang boleh menjadi draft Needs-review di jalur versions.
    """
    hard: List[Dict] = []
    soft: List[Dict] = []

    def add_hard(code, message, stage):
        hard.append({'code': code, 'message': message, 'stage': stage})

    def add_soft(code, message, stage):
        soft.append({'code': code, 'message': message, 'stage': stage})

    def add_split(code, message, stage):
        (add_soft if _is_soft_error(code, message) else add_hard)(
            code, message, stage)

    # Glosarium: duplikat istilah dalam satu version ditolak (hard;
    # bentuk/kekosongan sudah dijaga applier + kontrak regen).
    seen_terms = set()
    for entry in module.glosarium or []:
        if not isinstance(entry, dict):
            add_hard('GLOSARIUM_INVALID',
                     'Glosarium entry is not an object', 'glosarium')
            break
        istilah = entry.get('istilah')
        definisi = entry.get('definisi')
        if not isinstance(istilah, str) or not istilah.strip() \
                or not isinstance(definisi, str) or not definisi.strip():
            add_hard('GLOSARIUM_INVALID',
                     'Glosarium entry has empty istilah/definisi',
                     'glosarium')
            break
        key = istilah.strip().lower()
        if key in seen_terms:
            add_hard('GLOSARIUM_INVALID',
                     f'Glosarium has duplicate istilah {istilah!r}',
                     'glosarium')
            break
        seen_terms.add(key)

    # 1. Protection: immutable curriculum identity vs ORIGINAL context.
    prot_ok, prot_errors = pipeline.protection_validator.validate(
        original_context, module
    )
    if not prot_ok:
        for e in prot_errors:
            add_hard('PROTECTED_FIELD_MODIFICATION', e, 'protection')

    # 2. Pedagogical: activities/assessments coverage.
    act_ok, act_errors = PedagogicalValidator.validate_activity_alignment(
        module.learning_activities, len(module.learning_objectives)
    )
    if not act_ok:
        for e in act_errors:
            add_split('ACTIVITY_ERROR', e, 'pedagogical')

    # 3. KKTP cognitive levels: declared level must not sit below its TP's
    # level (the blocker-2 rule; uses the shared KKO order). TP levels
    # di sini adalah hasil derivasi deterministik dari prepare.
    tp_level_by_id = {t.id: t.cognitive_level
                      for t in module.learning_objectives}
    for kktp in module.success_criteria:
        tp_level = tp_level_by_id.get(kktp.tp_id)
        kk_level = kktp.cognitive_level
        if kk_level not in _COG_ORDER:
            add_hard('KKTP_ERROR',
                     f'{kktp.id} has invalid cognitive level {kk_level!r}',
                     'rules')
        elif tp_level is None:
            add_hard('KKTP_ERROR',
                     f'{kktp.tp_id} has invalid cognitive level', 'rules')
        elif _COG_ORDER[kk_level] < _COG_ORDER[tp_level]:
            add_hard('KKTP_ERROR',
                     f'{kktp.id} declares {kk_level} but measures {kktp.tp_id} '
                     f'at {tp_level} (tp_id={kktp.tp_id}, tp_level={tp_level}, '
                     f'kktp_level={kk_level})', 'rules')

    # 4. Master Outline structure + alignment + provenance rules.
    mo_ok, mo_errors = MasterOutlineValidator.validate(module)
    if not mo_ok:
        for e in mo_errors:
            add_split(e.get('code', 'MASTER_OUTLINE_ERROR'),
                      e.get('message', ''), e.get('stage', 'master_outline'))

    # 5. Final completeness + relationships.
    complete, comp_errors = pipeline.final_validator.validate_completeness(module)
    if not complete:
        for e in comp_errors:
            add_hard('FINAL_VALIDATION_ERROR', e, 'final')
    related, rel_errors = pipeline.final_validator.validate_relationships(module)
    if not related:
        for e in rel_errors:
            add_hard('FINAL_VALIDATION_ERROR', e, 'final')

    # 6. Factuality gate (CP/provenance vs database + regulatory claims
    # vs canonical docs) — fail closed on edit too.
    for e in FactualityValidator(pipeline.db_path).validate(module):
        code, _, message = str(e).partition(': ')
        add_hard(code or 'FACTUALITY_ERROR', message or str(e), 'factuality')

    return hard, soft


def _validate_edited_module(module: Module, original_context) -> Tuple[bool, List[Dict]]:
    """PUT legacy semantics: ANY error (alignment included) fails 422."""
    pipeline = get_generation_pipeline()
    hard, soft = _run_version_battery(module, original_context, pipeline)
    structured = hard + soft
    return (not structured), structured


@app.route('/api/buku', methods=['GET'])
def daftar_buku():
    """Daftar buku ajar user untuk dipilih saat generate (R-43)."""
    try:
        from buku_ajar import daftar_buku as _daftar
        pipeline = get_generation_pipeline()
        return jsonify({'status': 'success',
                        'buku': _daftar(pipeline.db_path)}), 200
    except Exception:  # noqa: BLE001
        logger.exception("Daftar buku error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Gagal memuat daftar buku.',
                                    'stage': 'server'}]}), 500


@app.route('/api/buku/<document_id>', methods=['DELETE'])
def hapus_buku(document_id):
    """Hapus buku ajar permanen: DB + fragmen + file fisik (R-43)."""
    try:
        from buku_ajar import hapus_buku as _hapus
        pipeline = get_generation_pipeline()
        ok = _hapus(pipeline.db_path, document_id)
        if not ok:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'NOT_FOUND',
                                        'message': 'Buku tidak ditemukan.',
                                        'stage': 'input'}]}), 404
        return jsonify({'status': 'success',
                        'deleted': document_id}), 200
    except Exception:  # noqa: BLE001
        logger.exception("Hapus buku error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Gagal menghapus buku.',
                                    'stage': 'server'}]}), 500


@app.route('/api/buku/upload', methods=['POST'])
def upload_buku():
    """Upload PDF/DOCX buku ajar -> source_documents+fragments (R-43).

    Maksimal 5 buku per koleksi; hapus salah satu dulu bila penuh.
    """
    from rpm_importer import check_extension
    pipeline = get_generation_pipeline()
    try:
        from buku_ajar import daftar_buku as _daftar
        if len(_daftar(pipeline.db_path)) >= 5:
            return jsonify({'status': 'error',
                            'errors': [{
                                'code': 'BUKU_PENUH',
                                'message': 'Koleksi sudah 5 buku (maksimal). '
                                           'Hapus salah satu dulu.',
                                'stage': 'input'}]}), 422
    except Exception:  # noqa: BLE001
        logger.exception("Hitung koleksi buku error")
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'UPLOAD_FILE_MISSING',
                        'message': 'Pilih file PDF atau DOCX dulu.',
                        'stage': 'input'}]
        }), 400
    err = check_extension(uploaded.filename)
    if err:
        return jsonify({'status': 'error', 'errors': [err]}), 422
    judul = (request.form.get('judul') or '').strip() or None
    async_mode = (request.form.get('async') or '').strip() == '1'
    try:
        pipeline = get_generation_pipeline()
        suffix = '.pdf' if uploaded.filename.lower().endswith(
            '.pdf') else '.docx'
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            uploaded.save(tmp.name)
            tmp.close()
            size = os.path.getsize(tmp.name)
            if size > 10 * 1024 * 1024:
                return jsonify({'status': 'error', 'errors': [{
                    'code': 'UPLOAD_TOO_LARGE',
                    'message': 'File melebihi 10MB.',
                    'stage': 'input'}]}), 413
            from buku_ajar import ingest_buku
            if async_mode:
                job_id = str(uuid.uuid4())
                _job_create(
                    job_id, 'upload_buku', {
                        'tmp_path': tmp.name + '.job' + suffix,
                        'db_path': str(pipeline.db_path),
                        'nama_asli': uploaded.filename,
                        'judul': judul,
                        'size': size,
                    },
                    progress=0,
                    tahap='Menyimpan file…',
                )
                # Pindah ke lokasi permanen: finally di bawah langsung
                # menghapus tmp, dan worker butuh file sampai selesai.
                tetap = tmp.name + '.job' + suffix
                os.replace(tmp.name, tetap)
                db_path = pipeline.db_path
                fname = uploaded.filename
                if not _submit_background_job(
                        _run_upload_buku_job, job_id, tetap, db_path,
                        fname, judul, size):
                    _job_remove(job_id)
                    try:
                        os.unlink(tetap)
                    except OSError:
                        pass
                    return jsonify({'status': 'error', 'errors': [{
                        'code': 'JOB_QUEUE_FULL',
                        'message': 'Antrean pekerjaan penuh. Coba lagi.',
                        'stage': 'queue'}]}), 429
                return jsonify(
                    {'status': 'accepted', 'job_id': job_id}), 202
            hasil = ingest_buku(pipeline.db_path, tmp.name,
                                uploaded.filename, judul)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return jsonify({'status': 'success', **hasil}), 200
    except ValueError as exc:
        return jsonify({'status': 'error', 'errors': [{
            'code': 'UPLOAD_INVALID', 'message': str(exc),
            'stage': 'input'}]}), 422
    except Exception:  # noqa: BLE001
        logger.exception("Upload buku error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Upload buku gagal.',
                                    'stage': 'server'}]}), 500


@app.route('/api/buku/upload/status/<job_id>', methods=['GET'])
def upload_buku_status(job_id):
    """Poll progress ekstraksi upload buku (persen + tahap nyata)."""
    if not _valid_generation_id(job_id):
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'NOT_FOUND',
                        'message': 'Unknown upload job.',
                        'stage': 'poll'}]
        }), 404
    job = _job_get(job_id)
    if job is None or job.get('kind') != 'upload_buku':
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'NOT_FOUND',
                        'message': 'Unknown upload job.',
                        'stage': 'poll'}]
        }), 404
    if job['status'] == 'running':
        return jsonify({'status': 'running',
                        'progress': job.get('progress', 0),
                        'tahap': job.get('tahap', 'Memproses…')}), 200
    if job['status'] == 'success':
        return jsonify({'status': 'success',
                        'progress': 100,
                        **(job.get('result') or {})}), 200
    return jsonify({'status': 'error',
                    'errors': (job.get('result') or {}).get(
                        'errors', [{'code': 'INTERNAL_ERROR',
                                    'message': 'Upload buku gagal.',
                                    'stage': 'server'}])}), 500


@app.route('/api/modules/import', methods=['POST'])
def import_modules():
    """Impor RPM dari DOCX/PDF hasil generate aplikasi (R-32..R-36).

    Multipart field 'file'. 1 segmen = 1 RPM (PDF multi-RPM pecah
    otomatis, R-36). Tiap segmen: gate layout -> identitas ->
    CP resmi DB (beda = 422 tolak keras, R-32) -> baterai validasi
    yang sama dengan PUT/versions -> simpan ModuleStore + v1
    validated badge 'Hasil upload' (R-34). Tanpa AI, tanpa karangan.
    """
    from rpm_importer import (
        check_extension, check_size, extract_docx_rows,
        split_segments, split_pdf_segments,
        gate_layout, parse_identity, resolve_grade_phase,
        resolve_subject, extract_cp, match_cp_official,
        parse_tp_kktp, parse_praktik, parse_activities,
        parse_assessments, parse_readiness_material,
        build_module_dict, run_import_battery,
    )
    from module_generation_pipeline import default_curriculum_version
    from curriculum_context import (
        CurriculumContext, CPEntry, ATPEntry)
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'UPLOAD_FILE_MISSING',
                        'message': 'Pilih file DOCX atau PDF dulu.',
                        'stage': 'input'}]
        }), 400
    err = check_extension(uploaded.filename)
    if err:
        return jsonify({'status': 'error', 'errors': [err]}), 422
    try:
        pipeline = get_generation_pipeline()
        mappings = _curriculum_mappings()
        suffix = '.pdf' if uploaded.filename.lower().endswith(
            '.pdf') else '.docx'
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            uploaded.save(tmp.name)
            tmp.close()
            size = os.path.getsize(tmp.name)
            err = check_size(size)
            if err:
                return jsonify(
                    {'status': 'error', 'errors': [err]}), 413
            if suffix == '.pdf':
                try:
                    segments = split_pdf_segments(tmp.name)
                except Exception:
                    return jsonify({
                        'status': 'error',
                        'errors': [{
                            'code': 'UPLOAD_FILE_UNREADABLE',
                            'message': 'File PDF tidak bisa dibaca. '
                                       'Dokumen ditolak.',
                            'stage': 'input'}]
                    }), 422
            else:
                try:
                    title, rows = extract_docx_rows(tmp.name)
                except Exception:
                    return jsonify({
                        'status': 'error',
                        'errors': [{
                            'code': 'UPLOAD_FILE_UNREADABLE',
                            'message': 'File DOCX tidak bisa dibaca. '
                                       'Dokumen ditolak.',
                            'stage': 'input'}]
                    }), 422
                segments = split_segments(title, rows)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        if not segments:
            return jsonify({
                'status': 'error',
                'errors': [{
                    'code': 'UPLOAD_LAYOUT_INVALID',
                    'message': 'Dokumen bukan hasil generate aplikasi '
                               'ini (judul A-E tidak ditemukan). '
                               'Dokumen ditolak.',
                    'stage': 'layout'}]
            }), 422
        imported = []
        rejected = []
        store = ModuleStore(pipeline.db_path)
        vstore = VersionStore(pipeline.db_path)
        for seg in segments:
            seg_title = seg.get('title') or '(tanpa judul)'
            seg_errors = gate_layout(seg.get('lines') or [])
            if seg_errors:
                rejected.append({'title': seg_title,
                                 'errors': seg_errors})
                continue
            ident = parse_identity(seg['lines'])
            sys2, inst, gkey, phase = resolve_grade_phase(
                ident, mappings)
            if sys2 is None:
                rejected.append({'title': seg_title, 'errors': [{
                    'code': 'UPLOAD_IDENTITY_INCOMPLETE',
                    'message': phase, 'stage': 'input'}]})
                continue
            assert isinstance(sys2, str) and isinstance(inst, str) \
                and isinstance(gkey, str) and isinstance(phase, str)
            subj, serr = resolve_subject(ident, mappings, sys2, inst)
            if subj is None:
                rejected.append({'title': seg_title, 'errors': [{
                    'code': 'UPLOAD_IDENTITY_INCOMPLETE',
                    'message': serr, 'stage': 'input'}]})
                continue
            cp_text, _sumber = extract_cp(seg['lines'])
            if not cp_text:
                rejected.append({'title': seg_title, 'errors': [{
                    'code': 'UPLOAD_CP_MISSING',
                    'message': 'Teks CP tidak terbaca dari dokumen. '
                               'Dokumen ditolak.',
                    'stage': 'content'}]})
                continue
            cp, cerr = match_cp_official(
                cp_text, subj, phase,
                pipeline.curriculum_validator.curriculum_engine,
                sys2, inst, '')
            if cerr:
                rejected.append({'title': seg_title,
                                 'errors': [cerr]})
                continue
            assert cp is not None
            tps, kktps, errs = parse_tp_kktp(seg['lines'])
            seg_errors.extend(errs)
            praktik = parse_praktik(seg['lines'])
            acts, meets, errs = parse_activities(seg['lines'])
            seg_errors.extend(errs)
            asm, errs = parse_assessments(seg['lines'])
            seg_errors.extend(errs)
            red, mat, dims, kbc, dim_notes = parse_readiness_material(
                seg['lines'], include_notes=True)
            if seg_errors:
                rejected.append({'title': seg_title,
                                 'errors': seg_errors})
                continue
            parsed = {'title': seg.get('title') or subj,
                      'identity': ident, 'tps': tps,
                      'kktps': kktps, 'praktik': praktik,
                      'activities': acts, 'meetings': meets,
                      'assessments': asm, 'readiness': red,
                      'material': mat, 'dims': dims,
                      'profile_dimension_notes': dim_notes,
                      'kbc_insertions': kbc}
            version = default_curriculum_version(sys2)
            ctx_extra = {'education_system': sys2,
                         'institution_type': inst, 'grade': gkey,
                         'phase': phase, 'subject': subj,
                         'curriculum_version': version}
            module_dict = build_module_dict(parsed, cp, ctx_extra,
                                            pipeline)
            original = CurriculumContext(
                education_system=sys2, institution_type=inst,
                grade=gkey, phase=phase, subject=subj,
                element=cp.element, curriculum_version=version,
                cp=CPEntry(
                    id=cp.id, text=cp.text,
                    source_document_id=cp.source_document,
                    source_fragment_id=cp.source_fragment_id,
                    source_page=cp.source_page, phase=cp.phase,
                    element=cp.element),
                tp_list=[], atp=ATPEntry(id='', tp_ids=[]))
            _module, merged, battery = run_import_battery(
                module_dict, pipeline, original)
            hard_errs, soft_errs = _split_import_errors(battery)
            if hard_errs:
                rejected.append({'title': seg_title,
                                 'errors': hard_errs})
                continue
            # R-37: soft-only (level KKTP/alignment) → simpan draf
            # berflag, bukan tolak. Export tetap blokir sampai
            # diperbaiki jadi validated.
            draft_mode = bool(soft_errs)
            try:
                merged['master_outline'] = \
                    module_dict.get('master_outline') or {}
                from module_generation_pipeline import Module
                rebuilt = Module.from_stored_dict(merged, original)
                merged['master_outline'] = \
                    rebuilt.build_master_outline()
                merged['validation_results'] = {
                    'final': {'passed': not draft_mode,
                              'errors': soft_errs if draft_mode
                              else []},
                    'import': {'passed': not draft_mode,
                               'errors': soft_errs,
                               'at': utc_now_iso(),
                               'origin': 'import'}}
                store.save(merged['generation_id'], merged,
                           merged['curriculum_context'])
                # R-39: judul sama (aktif) = arsipkan otomatis yang lama
                # agar Beranda tidak nabrak. Tanpa ubah isi yang lama.
                archived_lama = []
                try:
                    for lama in store.find_active_by_title(
                            merged.get('title') or seg_title,
                            exclude_id=merged['generation_id'],
                            subject=merged.get('subject') or '',
                            grade=merged.get('grade') or '',
                            phase=merged.get('phase') or ''):
                        if store.set_archived(lama, True):
                            archived_lama.append(lama)
                except Exception:  # noqa: BLE001 - arsip best-effort
                    logger.exception("Auto-archive on import failed")
                saved = vstore.save_new(
                    merged['generation_id'], 0, None,
                    'draft' if draft_mode else 'validated',
                    merged, merged['validation_results'],
                    'Needs review' if draft_mode else 'Aligned',
                    ['import'],
                    (['Draf impor: perbaiki hingga validated.'] +
                     [str((e.get('message') if isinstance(
                         e, dict) else e))[:160]
                      for e in soft_errs[:5]]
                     if draft_mode else
                     ['Hasil upload (bukan hasil generate AI).']))
            except Exception:  # noqa: BLE001 - never leak internals
                logger.exception("Import persistence failed")
                rejected.append({'title': seg_title, 'errors': [{
                    'code': 'STORAGE_ERROR',
                    'message': 'Gagal menyimpan RPM impor.',
                    'stage': 'storage'}]})
                continue
            imported.append({
                'generation_id': merged['generation_id'],
                'title': merged.get('title') or seg_title,
                'subject': merged.get('subject') or '',
                'grade': merged.get('grade') or '',
                'phase': merged.get('phase') or '',
                'version_no': saved['version_no'],
                'status': saved['status'],
                'draft_errors': soft_errs if draft_mode else [],
                'archived_lama': archived_lama})
        status = 'success' if imported and not rejected else (
            'partial' if imported else 'error')
        code = 200 if imported else 422
        return jsonify({'status': status, 'imported': imported,
                        'rejected': rejected}), code
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module import error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module import failed due to an '
                                   'internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/module/<generation_id>', methods=['GET'])
def get_module(generation_id):
    """Retrieve a persisted module + its authoritative context.

    RESTART-SAFE: reads only from generated_modules storage (no in-memory
    dependency), so a module can be re-opened and re-edited after a server
    restart. The context is echoed for transparency; the client is never
    trusted for protected values (PUT splices them back from storage).
    """
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        store = _resolve_app_store()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'MODULE_NOT_FOUND',
                            'message': 'No stored module for this generation_id.',
                            'stage': 'storage'}]
            }), 404
        # VersionStore is source of truth after edit/regenerate. The legacy
        # generated_modules row remains baseline compatibility storage.
        latest = VersionStore(get_generation_pipeline().db_path).latest(
            generation_id)
        if latest is not None:
            module = latest['module']
            validation = latest.get('validation') or module.get(
                'validation_results', {})
            version_no = latest['version_no']
        else:
            module = stored['module']
            validation = module.get('validation_results', {})
            version_no = None
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'module': module,
            'context': stored['context'],
            'validation': validation,
            'version_no': version_no,
            'updated_at': stored['updated_at'],
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module retrieval error")
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module retrieval failed due to an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/generations', methods=['GET'])
def list_generations():
    """Riwayat generate: ringkasan per generation_id dari audit trail.

    Read-only atas generation_logs (tanpa perubahan schema, tanpa
    menyentuh raw prompt/response yang memang tidak disimpan).
    RPM sukses tetap dibaca via /api/modules; endpoint ini juga
    menampilkan generate yang gagal (status/error per stage).
    """
    try:
        pipeline = get_generation_pipeline()
        store = GenerationLogStore(pipeline.db_path)
        items = store.list_generations()
        return jsonify({'status': 'success', 'generations': items}), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Generation log listing error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Generation log listing failed due to '
                                   'an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/generations/<generation_id>', methods=['GET'])
def get_generation_log(generation_id):
    """Detail satu generate: seluruh record stage-attempt terurut waktu."""
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        store = GenerationLogStore(pipeline.db_path)
        records = store.fetch(generation_id)
        if not records:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'GENERATION_NOT_FOUND',
                            'message': 'No generation log for this '
                                       'generation_id.',
                            'stage': 'storage'}]
            }), 404
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'records': records,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Generation log retrieval error")
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Generation log retrieval failed due to '
                                   'an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/generations/<generation_id>', methods=['DELETE'])
def delete_generation_log(generation_id):
    """Hapus permanen baris audit satu generation_id.

    Hanya generation_logs; modul di generated_modules + versinya
    TIDAK ikut (keputusan user: hapus log = hanya baris audit).
    404 bila tak ada baris audit untuk ID itu.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        store = GenerationLogStore(pipeline.db_path)
        removed = store.delete(generation_id)
        if not removed:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'GENERATION_NOT_FOUND',
                            'message': 'No generation log for this '
                                       'generation_id.',
                            'stage': 'storage'}]
            }), 404
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'deleted': True,
            'rows_removed': removed,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Generation log deletion error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Generation log deletion failed due to '
                                   'an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/generations', methods=['DELETE'])
def delete_generation_logs():
    """Hapus permanen baris audit banyak generation_id sekaligus.

    Body: {"generation_ids": [...]}. Hanya generation_logs; modul TIDAK
    ikut. Return jumlah ID yang barisnya terhapus + yang tak ditemukan.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Request body must be a JSON object.',
                        'stage': 'input'}]
        }), 400
    ids = data.get('generation_ids')
    if not isinstance(ids, list) or not ids:
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INVALID_PARAMS',
                        'message': "'generation_ids' harus list non-kosong.",
                        'stage': 'input'}]
        }), 400
    bad = [g for g in ids if not _valid_generation_id(g)]
    if bad:
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        store = GenerationLogStore(pipeline.db_path)
        removed_ids = []
        missing = []
        for gid in ids:
            if store.delete(gid):
                removed_ids.append(gid)
            else:
                missing.append(gid)
        return jsonify({
            'status': 'success',
            'deleted': removed_ids,
            'missing': missing,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Generation logs bulk deletion error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Generation logs deletion failed due to '
                                   'an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/module/<generation_id>/versions/<int:version_no>',
           methods=['DELETE'])
def delete_version(generation_id, version_no):
    """Hapus permanen satu baris riwayat versi modul terbuka.

    Versi terakhir TIDAK boleh dihapus (modul tanpa versi = rusak):
    422 + modul tetap utuh. Versi yang sedang tampil boleh dihapus;
    UI lalu menampilkan versi terbaru yang tersisa.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        vstore, mstore = _version_stores()
        rows = vstore.history(generation_id)
        if not rows:
            # Belum ada baris versi: modul baseline generated_modules
            # adalah satu-satunya wujud -> hapus = hancurkan modul.
            if mstore.load(generation_id) is not None:
                return jsonify({
                    'status': 'error',
                    'generation_id': generation_id,
                    'errors': [{'code': 'LAST_VERSION_PROTECTED',
                                'message': 'Versi terakhir tidak boleh '
                                           'dihapus; modul harus punya '
                                           'minimal 1 versi.',
                                'stage': 'storage'}]
                }), 422
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'VERSION_NOT_FOUND',
                            'message': 'No versions for this generation_id.',
                            'stage': 'storage'}]
            }), 404
        if len(rows) <= 1:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'LAST_VERSION_PROTECTED',
                            'message': 'Versi terakhir tidak boleh dihapus; '
                                       'modul harus punya minimal 1 versi.',
                            'stage': 'storage'}]
            }), 422
        if not any(r['version_no'] == version_no for r in rows):
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'VERSION_NOT_FOUND',
                            'message': f'Version {version_no} tidak ada.',
                            'stage': 'storage'}]
            }), 404
        ok = vstore.delete_one(generation_id, version_no)
        if not ok:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'INTERNAL_ERROR',
                            'message': 'Version deletion failed.',
                            'stage': 'server'}]
            }), 500
        latest = vstore.latest(generation_id)
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'deleted_version': version_no,
            'latest_version': latest['version_no'] if latest else None,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Version deletion error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Version deletion failed due to an '
                                   'internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/modules', methods=['GET'])
def list_modules():
    """Dashboard history: all successfully stored RPMs, newest first.

    Read-only over existing stores (no schema change, no new table).
    generated_modules is written only on success, so failed
    generations never appear here.
    """
    try:
        pipeline = get_generation_pipeline()
        store = ModuleStore(pipeline.db_path)
        vstore = VersionStore(pipeline.db_path)
        summaries = store.list_summaries()
        latest_by_id = {}
        try:
            latest_by_id = vstore.latest_many(
                [s['generation_id'] for s in summaries])
        except Exception:  # noqa: BLE001 - versions optional
            logger.exception("Bulk latest-version lookup failed")
        items = []
        for summary in summaries:
            latest = latest_by_id.get(summary['generation_id'])
            if latest is not None:
                status = latest.get('status') or 'validated'
                updated = latest.get('created_at') or summary['updated_at']
                latest_version = latest.get('version_no')
            else:
                status = 'validated' if summary.pop('passed', False) else 'draft'
                updated = summary['updated_at']
                latest_version = None
            summary['status'] = status
            summary['updated_at'] = updated
            summary['latest_version'] = latest_version
            items.append(summary)
        items.sort(key=lambda m: m.get('updated_at') or '',
                   reverse=True)
        return jsonify({'status': 'success', 'modules': items}), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module listing error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module listing failed due to an '
                                   'internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/modules/<generation_id>/archive', methods=['POST'])
def archive_module(generation_id):
    """Arsipkan satu RPM (R-38): hanya flag, baris+versi+log utuh."""
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        store = ModuleStore(pipeline.db_path)
        if not store.set_archived(generation_id, True):
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'MODULE_NOT_FOUND',
                            'message': 'No stored module for this '
                                       'generation_id.',
                            'stage': 'storage'}]
            }), 404
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'archived': True,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module archive error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module archive failed due to an '
                                   'internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/modules/<generation_id>/unarchive', methods=['POST'])
def unarchive_module(generation_id):
    """Kembalikan RPM arsip jadi aktif (R-38)."""
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        store = ModuleStore(pipeline.db_path)
        if not store.set_archived(generation_id, False):
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'MODULE_NOT_FOUND',
                            'message': 'No stored module for this '
                                       'generation_id.',
                            'stage': 'storage'}]
            }), 404
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'archived': False,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module unarchive error")
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module unarchive failed due to an '
                                   'internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/modules/<generation_id>', methods=['DELETE'])
def delete_module(generation_id):
    """Hapus satu RPM dari riwayat (modul + seluruh versinya).

    Tanpa perubahan schema: DELETE biasa pada generated_modules dan
    module_versions dalam SATU transaksi (atomic — tidak ada partial
    delete). Log generasi (audit) dipertahankan.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    try:
        pipeline = get_generation_pipeline()
        conn = sqlite3.connect(str(pipeline.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.execute(
                "DELETE FROM generated_modules WHERE generation_id = ?",
                (generation_id,),
            )
            removed = cur.rowcount > 0
            cur = conn.execute(
                "DELETE FROM module_versions WHERE generation_id = ?",
                (generation_id,),
            )
            versions_removed = cur.rowcount
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if not removed and not versions_removed:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'MODULE_NOT_FOUND',
                            'message': 'No stored module for this generation_id.',
                            'stage': 'storage'}]
            }), 404
        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'deleted': True,
            'versions_removed': versions_removed,
        }), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Module deletion error")
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module deletion failed due to an internal error.',
                        'stage': 'server'}]
        }), 500


@app.route('/api/module/<generation_id>', methods=['PUT'])
def update_module(generation_id):
    """Persist an edited module after full re-validation."""
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Malformed generation_id.',
                        'stage': 'input'}]
        }), 400
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Request body must be a JSON object.',
                        'stage': 'input'}]
        }), 400

    incoming = payload.get('module') if isinstance(payload.get('module'), dict) else payload
    if not isinstance(incoming, dict) or not incoming:
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INVALID_REQUEST',
                        'message': 'Module payload missing.',
                        'stage': 'input'}]
        }), 400

    try:
        store = _resolve_app_store()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'MODULE_NOT_FOUND',
                            'message': 'No stored module for this generation_id.',
                            'stage': 'storage'}]
            }), 404

        # RESTART-SAFE: the authoritative context is rebuilt from the
        # PERSISTED context JSON, never from in-memory state. The live
        # object (kept at generation time) is only a same-value accelerator
        # for rows written by very old versions without a full context.
        original_context = _rebuild_context_from_storage(generation_id, stored)
        if original_context is None:
            original_context = _context_objects.get(generation_id)
        if original_context is None:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'CONTEXT_UNAVAILABLE',
                            'message': 'Stored context is incomplete and cannot be rebuilt; regenerate the module.',
                            'stage': 'storage'}]
            }), 422

        # --- protected fields: detect attempts to change authoritative data
        protected_touched = []

        # Top-level protected keys (any difference vs stored = attempt).
        for k in PUT_PROTECTED_TOP_KEYS:
            if k in incoming and k != 'curriculum_context' and \
                    incoming.get(k) != stored['module'].get(k):
                protected_touched.append(k)

        # Curriculum identity keys are protected wherever they appear.
        for key in ('cp', 'phase', 'subject', 'element', 'education_system',
                    'institution_type', 'grade', 'topic'):
            if key in incoming and incoming.get(key) != stored['module'].get(key):
                protected_touched.append(key)

        # Nested curriculum_context: authoritative identity must be untouched.
        inc_ctx = incoming.get('curriculum_context') or {}
        st_ctx = stored['module'].get('curriculum_context') or {}
        for key in ('phase', 'subject', 'element', 'education_system',
                    'institution_type', 'grade', 'curriculum_version'):
            if key in inc_ctx and inc_ctx.get(key) != st_ctx.get(key):
                protected_touched.append(f'curriculum_context.{key}')
        inc_cp = inc_ctx.get('cp') or {}
        st_cp = st_ctx.get('cp') or {}
        for key in ('id', 'text', 'source_document_id', 'source_fragment_id',
                    'source_page', 'phase', 'element'):
            if key in inc_cp and inc_cp.get(key) != st_cp.get(key):
                protected_touched.append(f'curriculum_context.cp.{key}')

        # Build the module dict: start from the STORED module (authoritative
        # baseline), overlay ONLY editable fields from the client.
        merged = dict(stored['module'])
        for key, value in incoming.items():
            if key in PUT_PROTECTED_TOP_KEYS or key in (
                    'cp', 'phase', 'subject', 'element', 'education_system',
                    'institution_type', 'grade', 'topic_seed',
                    'profile_dimensions', 'profile_dimension_notes'):
                continue  # authoritative values win, client copies ignored
            merged[key] = value
        merged['id'] = stored['module']['id']
        merged['generation_id'] = stored['module']['generation_id']
        merged['topic'] = stored['module'].get('topic', '')
        merged['topic_seed'] = stored['module'].get('topic_seed', '')
        merged['profile_dimensions'] = stored['module'].get(
            'profile_dimensions', [])
        merged['profile_dimension_notes'] = stored['module'].get(
            'profile_dimension_notes', {})
        merged['curriculum_version'] = stored['module'].get('curriculum_version', '')
        merged['approach_principles'] = stored['module'].get('approach_principles', {})
        merged['curriculum_context'] = stored['module'].get('curriculum_context')
        merged['generated_at'] = stored['module'].get('generated_at', '')
        merged['generated_by'] = stored['module'].get('generated_by', '')
        # A.3 + catatan relevansi dipertahankan dari otoritatif tersimpan
        # (Batch 8.5 §2: pasangan dimensi-alasan utuh; reset full-8
        # legacy dihapus). Klien tidak dapat menulis keduanya.
        # (displice di atas dari stored['module'])
        # C.5 rubric descriptors: AI-authored content lives in
        # assessments['rubric_descriptors'] at generation time; the rubric
        # rows themselves are rebuilt here so legacy rows keep their
        # descriptors across an edit.
        rub_desc = merged.get('assessments', {}).get('rubric_descriptors') \
            if isinstance(merged.get('assessments'), dict) else None
        if not isinstance(rub_desc, dict):
            rub_desc = {}
        rubric_rows = merged.get('rubric', {}).get('kktp_rubric') \
            if isinstance(merged.get('rubric'), dict) else None
        if isinstance(rubric_rows, list):
            for row in rubric_rows:
                if isinstance(row, dict) and not row.get('descriptors'):
                    d = rub_desc.get(row.get('kktp_id'))
                    if isinstance(d, list) and d:
                        row['descriptors'] = [str(x) for x in d]

        if protected_touched:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': [{'code': 'PROTECTED_FIELD_MODIFICATION',
                            'message': 'Attempt to modify protected field(s): '
                                       + ', '.join(sorted(set(protected_touched)))
                                       + '. Protected values were ignored; '
                                         're-submit with only editable changes.',
                            'stage': 'protection'}]
            }), 422

        pipeline = get_generation_pipeline()
        module, schema_errors = _prepare_merged_for_battery(
            merged, original_context, pipeline)
        if module is None:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': schema_errors
            }), 422

        ok, errors = _validate_edited_module(module, original_context)
        if not ok:
            return jsonify({
                'status': 'error',
                'generation_id': generation_id,
                'errors': errors
            }), 422

        # Derive pengalaman-belajar view + refresh validation summary, then SAVE.
        merged['learning_phases'] = module.build_master_outline()[
            'learning_experience']['experiences']
        merged['validation_results'] = dict(
            stored['module'].get('validation_results', {}),
            edited={'passed': True, 'errors': [], 'at': utc_now_iso()},
        )
        merged['master_outline'] = module.build_master_outline()
        store.save(generation_id, merged, stored['context'])

        return jsonify({
            'status': 'success',
            'generation_id': generation_id,
            'module': merged,
            'validation': merged['validation_results'],
            'updated_at': utc_now_iso(),
        }), 200
    except Exception as exc:  # noqa: BLE001 - never leak internals
        logger.error("Module update error: %s", exc)
        return jsonify({
            'status': 'error',
            'generation_id': generation_id,
            'errors': [{'code': 'INTERNAL_ERROR',
                        'message': 'Module update failed due to an internal error.',
                        'stage': 'server'}]
        }), 500


class _SectionError(ValueError):
    """Malformed section edit (HTTP 400)."""


def _require_str(value, field, max_chars):
    if not isinstance(value, str) or not value.strip():
        raise _SectionError(f"Section '{field}' harus string non-kosong.")
    if len(value) > max_chars:
        raise _SectionError(
            f"Section '{field}' melebihi {max_chars} karakter.")
    return value.strip()


def _require_str_list(value, field, max_items=50, max_chars=2000):
    if not isinstance(value, list) or not value:
        raise _SectionError(f"Section '{field}' harus list non-kosong.")
    if len(value) > max_items:
        raise _SectionError(f"Section '{field}' melebihi {max_items} item.")
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _SectionError(f"Section '{field}' berisi item kosong.")
        if len(item) > max_chars:
            raise _SectionError(f"Section '{field}' berisi item terlalu panjang.")
        out.append(item.strip())
    return out


def _apply_section_changes(merged: Dict, changes: Dict) -> List[str]:
    """Terapkan section edits whitelist ke merged (in place).

    Hanya section EDITABLE_SECTIONS; protected (CP/provenance/konteks/
    KBC) tidak tersentuh. Return daftar section yang berubah. Bentuk
    malformed -> _SectionError (400). Validasi isi pedagogis tetap
    menjadi tugas battery (422/draft).
    """
    if not isinstance(changes, dict) or not changes:
        raise _SectionError("Field 'changes' harus object non-kosong.")
    unknown = [k for k in changes if k not in EDITABLE_SECTIONS]
    if unknown:
        raise _SectionError(
            f"Section tidak dikenal/tidak editable: {', '.join(sorted(unknown))}. "
            f"Section editable: {', '.join(EDITABLE_SECTIONS)}.")
    changed: List[str] = []
    tp_ids = [t.get('id') for t in merged.get('learning_objectives') or []]
    kk_ids = [k.get('id') for k in merged.get('success_criteria') or []]

    if 'tp' in changes:
        items = changes['tp']
        if not isinstance(items, list) or not items:
            raise _SectionError("Section 'tp' harus list non-kosong.")
        seen = set()
        for item in items:
            if not isinstance(item, dict) or item.get('id') not in tp_ids:
                raise _SectionError(
                    "Section 'tp': setiap item wajib memakai id TP existing "
                    f"{tp_ids} (TP baru hanya via regenerate).")
            if item['id'] in seen:
                raise _SectionError("Section 'tp': id duplikat "
                                    f"{item['id']!r}.")
            seen.add(item['id'])
            _require_str(item.get('text'), 'tp.text', 2000)
        if set(seen) != set(tp_ids):
            raise _SectionError("Section 'tp': jumlah TP harus tetap "
                                f"{len(tp_ids)} (regenerate untuk menambah).")
        by_id = {t['id']: t for t in merged['learning_objectives']}
        merged['learning_objectives'] = [
            dict(by_id[item['id']], text=item['text'].strip())
            for item in items]
        changed.append('tp')

    if 'kktp' in changes:
        items = changes['kktp']
        if not isinstance(items, list) or not items:
            raise _SectionError("Section 'kktp' harus list non-kosong.")
        seen = set()
        for item in items:
            if not isinstance(item, dict) or item.get('id') not in kk_ids:
                raise _SectionError(
                    "Section 'kktp': setiap item wajib memakai id KKTP "
                    f"existing {kk_ids}.")
            if item['id'] in seen:
                raise _SectionError("Section 'kktp': id duplikat.")
            seen.add(item['id'])
            item['criteria'] = _require_str_list(
                item.get('criteria'), 'kktp.criteria', max_items=10)
            level = item.get('cognitive_level')
            if level is not None and level not in _COG_ORDER:
                raise _SectionError(
                    "Section 'kktp.cognitive_level' harus C1-C6.")
        if set(seen) != set(kk_ids):
            raise _SectionError("Section 'kktp': jumlah KKTP harus tetap.")
        by_id = {k['id']: k for k in merged['success_criteria']}
        merged['success_criteria'] = [dict(
            by_id[item['id']],
            criteria=item['criteria'],
            **({'cognitive_level': item['cognitive_level']}
               if item.get('cognitive_level') else {}))
            for item in items]
        changed.append('kktp')

    if 'topic' in changes:
        topic = _require_str(changes['topic'], 'topic', MAX_TOPIC_CHARS)
        merged['topic'] = topic
        subject = merged.get('subject', '')
        merged['title'] = (f"RPP/RPM {subject}: {topic}" if topic
                           else f"RPP/RPM {subject}")
        unit = dict(merged.get('unit') or {})
        unit['name'] = topic
        merged['unit'] = unit
        ident = dict(merged.get('module_identity') or {})
        ident['title'] = f"RPP/RPM {subject}"
        merged['module_identity'] = ident
        changed.append('topic')

    if 'readiness' in changes:
        payload = changes['readiness']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'readiness' harus object.")
        text = payload.get('student_readiness')
        if text is None:
            raise _SectionError("Section 'readiness.student_readiness' wajib ada.")
        if not isinstance(text, str):
            raise _SectionError("Section 'readiness.student_readiness' harus string.")
        if len(text) > MAX_READINESS_CHARS:
            raise _SectionError("Section 'readiness' melebihi batas panjang.")
        text = text.strip()
        merged['student_readiness'] = text
        aspects = ((merged.get('learner_readiness') or {}).get('aspects')
                   if isinstance(merged.get('learner_readiness'), dict) else [])
        merged['learner_readiness'] = {
            'summary': text,
            'data_available': bool(text),
            'aspects': aspects if isinstance(aspects, list) else [],
            'data_status': 'available' if text else 'not-yet-collected',
            'note': ('Kesiapan murid berdasarkan observasi/asesmen awal guru.'
                     if text else
                     'Data kesiapan murid belum tersedia dalam sumber '
                     'kurikulum yang terdaftar.'),
        }
        changed.append('readiness')

    if 'material' in changes:
        payload = changes['material']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'material' harus object.")
        current = dict(merged.get('material_characteristics') or {})
        if 'summary' in payload:
            current['summary'] = _require_str(
                payload['summary'], 'material.summary', 2000)
        for key in ('prerequisites', 'potential_misconceptions'):
            if key in payload:
                current[key] = _require_str_list(
                    payload[key], f'material.{key}', max_items=20)
        merged['material_characteristics'] = current
        changed.append('material')

    if 'materi' in changes:
        payload = changes['materi']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'materi' harus object.")
        eu = {}
        for key in ('core_insight', 'relationship', 'application', 'value'):
            eu[key] = _require_str(payload.get(key), f'materi.{key}', 2000)
        merged['essential_understanding'] = eu
        changed.append('materi')

    if 'aktivitas' in changes:
        items = changes['aktivitas']
        if not isinstance(items, list) or not items:
            raise _SectionError("Section 'aktivitas' harus list non-kosong.")
        if len(items) > 40:
            raise _SectionError("Section 'aktivitas' melebihi 40 aktivitas.")
        seen = set()
        for act in items:
            if not isinstance(act, dict):
                raise _SectionError("Section 'aktivitas': item harus object.")
            aid = act.get('id')
            if not isinstance(aid, str) or not aid.strip() or aid in seen:
                raise _SectionError(
                    "Section 'aktivitas': setiap item wajib id unik non-kosong.")
            seen.add(aid)
            _require_str(act.get('name'), 'aktivitas.name', 200)
            _require_str(act.get('description'), 'aktivitas.description', 2000)
            for key in ('duration', 'meeting'):
                value = act.get(key)
                if not isinstance(value, int) or isinstance(value, bool) \
                        or value < 0:
                    raise _SectionError(
                        f"Section 'aktivitas.{key}' harus bilangan bulat >= 0.")
            for key, allowed in (
                    ('stage', ('Pembuka', 'Inti', 'Penutup')),
                    ('experience', ('memahami', 'mengaplikasi', 'merefleksi'))):
                if act.get(key) not in allowed:
                    raise _SectionError(
                        f"Section 'aktivitas.{key}' harus salah satu dari "
                        f"{', '.join(allowed)}.")
            tp = act.get('tp_linked')
            if tp is not None and tp not in tp_ids:
                raise _SectionError(
                    f"Section 'aktivitas.tp_linked' {tp!r} bukan TP valid.")
        merged['learning_activities'] = items
        changed.append('aktivitas')

    if 'pertemuan' in changes:
        # Ubah jumlah pertemuan (tambah = kloning deterministik dari
        # pertemuan terakhir; kurang = buang dari belakang). Tanpa AI,
        # tanpa karangan: budget waktu tervalidasi battery seperti biasa.
        payload = changes['pertemuan']
        if not isinstance(payload, dict):
            raise _SectionError(
                "Section 'pertemuan' harus object {'n': int}.")
        n = payload.get('n')
        if isinstance(n, bool) or not isinstance(n, int):
            raise _SectionError(
                "Section 'pertemuan.n' harus bilangan bulat.")
        if not 1 <= n <= 16:
            raise _SectionError(
                "Section 'pertemuan.n' harus 1..16.")
        cur_meetings = [m for m in (merged.get('meetings') or [])
                        if isinstance(m, dict)]
        cur_n = len(cur_meetings)
        if not cur_n:
            raise _SectionError(
                "Section 'pertemuan': modul tanpa pertemuan.")
        if n == cur_n:
            raise _SectionError(
                "Section 'pertemuan.n' sama dengan jumlah saat ini.")
        acts = [dict(a) for a in
                (merged.get('learning_activities') or [])
                if isinstance(a, dict)]
        if n < cur_n:
            acts = [a for a in acts
                    if a.get('meeting', 0) <= n]
            merged['meetings'] = cur_meetings[:n]
        else:
            last = cur_meetings[-1]
            jp = last.get('jp')
            if not (isinstance(jp, int) and not isinstance(jp, bool)
                    and jp > 0):
                jp = 2
            mpp = last.get('minutes_per_jp')
            if not (isinstance(mpp, int) and not isinstance(mpp, bool)
                    and mpp > 0):
                minutes = last.get('minutes')
                mpp = minutes // jp if isinstance(minutes, int) \
                    and minutes > 0 else 45
            sumber = [a for a in acts if a.get('meeting') == cur_n]
            if not sumber:
                sumber = [a for a in acts if a.get('meeting') == 1]
            if not sumber:
                raise _SectionError(
                    "Section 'pertemuan': tidak ada aktivitas "
                    "untuk dikloning.")
            used = {a.get('id') for a in acts}
            k = 1
            tmpl = list(cur_meetings)
            for i in range(cur_n + 1, n + 1):
                for a in sumber:
                    while True:
                        cand = f'ACT-{k}'
                        k += 1
                        if cand not in used:
                            break
                    used.add(cand)
                    klon = dict(a)
                    klon['id'] = cand
                    klon['meeting'] = i
                    acts.append(klon)
                tmpl.append({'index': i, 'jp': jp,
                             'minutes': jp * mpp, 'minutes_per_jp': mpp,
                             'stages': {}, 'principles': {}})
            merged['meetings'] = tmpl
        merged['learning_activities'] = acts
        changed.append('aktivitas')

    if 'refleksi' in changes:
        payload = changes['refleksi']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'refleksi' harus object.")
        student = _require_str_list(
            payload.get('student'), 'refleksi.student', max_items=20)
        teacher = _require_str_list(
            payload.get('teacher'), 'refleksi.teacher', max_items=20)
        merged['reflection'] = [
            {'role': 'student', 'questions': student},
            {'role': 'teacher', 'questions': teacher},
        ]
        changed.append('refleksi')

    if 'asesmen' in changes:
        payload = changes['asesmen']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'asesmen' harus object.")
        out = dict(merged.get('assessments') if isinstance(
            merged.get('assessments'), dict) else {})
        for key in ('diagnostic', 'formative'):
            if key in payload:
                items = payload[key]
                if not isinstance(items, list) or not items:
                    raise _SectionError(
                        f"Section 'asesmen.{key}' harus list non-kosong.")
                for item in items:
                    if not isinstance(item, dict):
                        raise _SectionError(
                            f"Section 'asesmen.{key}': item harus object.")
                    _require_str(item.get('question'),
                                 f'asesmen.{key}.question', 2000)
                    _require_str(item.get('type'), f'asesmen.{key}.type', 60)
                    for link_key in ('tp_linked', 'kktp_linked'):
                        link = item.get(link_key)
                        if link is not None and not isinstance(link, str):
                            raise _SectionError(
                                f"Section 'asesmen.{key}.{link_key}' harus string.")
                out[key] = items
        if 'summative' in payload:
            summ = payload['summative']
            if not isinstance(summ, dict) or not isinstance(
                    summ.get('items'), list) or not summ['items']:
                raise _SectionError(
                    "Section 'asesmen.summative' harus object dengan "
                    "'items' non-kosong.")
            for item in summ['items']:
                if not isinstance(item, dict):
                    raise _SectionError(
                        "Section 'asesmen.summative': item harus object.")
                _require_str(item.get('question'),
                             'asesmen.summative.question', 2000)
                _require_str(item.get('type'), 'asesmen.summative.type', 60)
            out['summative'] = summ
        if 'rubric_descriptors' in payload:
            desc = payload['rubric_descriptors']
            if not isinstance(desc, dict):
                raise _SectionError(
                    "Section 'asesmen.rubric_descriptors' harus object.")
            out['rubric_descriptors'] = desc
        merged['assessments'] = out
        changed.append('asesmen')

    if 'rubrik' in changes:
        payload = changes['rubrik']
        if not isinstance(payload, dict) or not isinstance(
                payload.get('descriptors'), dict):
            raise _SectionError(
                "Section 'rubrik' harus object {'descriptors': {...}}.")
        asm = dict(merged.get('assessments') if isinstance(
            merged.get('assessments'), dict) else {})
        asm['rubric_descriptors'] = payload['descriptors']
        merged['assessments'] = asm
        changed.append('rubrik')

    if 'lkpd' in changes:
        items = changes['lkpd']
        if not isinstance(items, list):
            raise _SectionError("Section 'lkpd' harus list.")
        for sheet in items:
            if not isinstance(sheet, dict):
                raise _SectionError("Section 'lkpd': item harus object.")
            _require_str(sheet.get('id'), 'lkpd.id', 40)
            _require_str(sheet.get('title'), 'lkpd.title', 200)
            _require_str(sheet.get('task'), 'lkpd.task', 2000)
            tp = sheet.get('tp_linked')
            if tp is not None and tp not in tp_ids:
                raise _SectionError(
                    f"Section 'lkpd.tp_linked' {tp!r} bukan TP valid.")
        merged['lkpd'] = items
        changed.append('lkpd')

    if 'glosarium' in changes:
        items = changes['glosarium']
        if not isinstance(items, list):
            raise _SectionError("Section 'glosarium' harus list.")
        if len(items) > 15:
            raise _SectionError(
                "Section 'glosarium' melebihi 15 istilah.")
        seen = set()
        for entry in items:
            if not isinstance(entry, dict):
                raise _SectionError(
                    "Section 'glosarium': item harus object.")
            istilah = _require_str(
                entry.get('istilah'), 'glosarium.istilah', 200)
            _require_str(entry.get('definisi'), 'glosarium.definisi', 2000)
            key = istilah.strip().lower()
            if key in seen:
                raise _SectionError(
                    f"Section 'glosarium': duplikat istilah {istilah!r}.")
            seen.add(key)
        merged['glosarium'] = [
            {'istilah': e['istilah'].strip(),
             'definisi': e['definisi'].strip()}
            for e in items]
        changed.append('glosarium')

    if 'meta' in changes:
        payload = changes['meta']
        if not isinstance(payload, dict):
            raise _SectionError("Section 'meta' harus object.")
        if 'penyusun' in payload:
            value = payload['penyusun']
            if value is not None and not isinstance(value, str):
                raise _SectionError("Section 'meta.penyusun' harus string.")
            value = (value or '').strip()
            if len(value) > MAX_PENYUSUN_CHARS:
                raise _SectionError("Section 'meta.penyusun' terlalu panjang.")
            merged['penyusun'] = value
        if 'satuan_pendidikan' in payload:
            value = payload['satuan_pendidikan']
            if value is not None and not isinstance(value, str):
                raise _SectionError(
                    "Section 'meta.satuan_pendidikan' harus string.")
            value = (value or '').strip()
            if len(value) > MAX_SATUAN_CHARS:
                raise _SectionError(
                    "Section 'meta.satuan_pendidikan' terlalu panjang.")
            merged['satuan_pendidikan'] = value
            ident = dict(merged.get('module_identity') or {})
            ident['satuan_pendidikan'] = value or None
            merged['module_identity'] = ident
        if 'semester' in payload:
            raw = payload['semester']
            if raw in (None, ''):
                merged['semester'] = None
                ident = dict(merged.get('module_identity') or {})
                ident['semester'] = None
                merged['module_identity'] = ident
            else:
                sem = _to_semester(raw)
                if sem is None:
                    raise _SectionError(
                        "Section 'meta.semester' harus 1 atau 2.")
                merged['semester'] = sem
                ident = dict(merged.get('module_identity') or {})
                ident['semester'] = sem
                merged['module_identity'] = ident
        if 'year' in payload:
            value = payload['year']
            if value is not None and not isinstance(value, str):
                raise _SectionError("Section 'meta.year' harus string.")
            value = (value or '').strip()
            if len(value) > MAX_TAHUN_CHARS:
                raise _SectionError("Section 'meta.year' terlalu panjang.")
            merged['year'] = value or None
            ident = dict(merged.get('module_identity') or {})
            ident['year'] = value or None
            merged['module_identity'] = ident
        if 'facilities' in payload:
            merged['facilities'] = _require_str_list(
                payload['facilities'], 'meta.facilities', max_items=20,
                max_chars=200)
        changed.append('meta')

    return sorted(set(changed))


def _version_stores():
    """VersionStore + ModuleStore pada DB pipeline aktif."""
    pipeline = get_generation_pipeline()
    return VersionStore(pipeline.db_path), ModuleStore(pipeline.db_path)


def _materialize_baseline(vstore: VersionStore, stored: Dict,
                          generation_id: str) -> Dict:
    """Buat v1 dari baris generated_modules bila belum ada version.

    Status v1 mengikuti hasil validasi final tersimpan (validated bila
    final PASS, draft bila tidak) — tidak ada klaim baru.
    """
    latest = vstore.latest(generation_id)
    if latest is not None:
        return latest
    module = stored['module']
    final = (module.get('validation_results') or {}).get('final') or {}
    status = 'validated' if final.get('passed') else 'draft'
    return vstore.save_new(
        generation_id, 0, None, status, module,
        module.get('validation_results') or {},
        'Aligned' if status == 'validated' else 'Needs review',
        [], [])


def _version_payload(version: Dict, include_module: bool = True) -> Dict:
    payload = {
        'version_no': version['version_no'],
        'parent_version_no': version['parent_version_no'],
        'status': version['status'],
        'alignment_status': version['alignment_status'],
        'changed_sections': version['changed_sections'],
        'warnings': version['warnings'],
        'created_at': version['created_at'],
    }
    if include_module:
        payload['module'] = version['module']
        payload['validation'] = version['validation']
    return payload


@app.route('/api/module/<generation_id>/versions', methods=['GET'])
def list_versions(generation_id):
    """History version (tanpa payload penuh per baris)."""
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    vstore, store = _version_stores()
    stored = store.load(generation_id)
    if stored is None and not vstore.history(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'MODULE_NOT_FOUND',
                                    'message': 'No stored module for this '
                                               'generation_id.',
                                    'stage': 'storage'}]}), 404
    if stored is not None and not vstore.history(generation_id):
        # Generasi lama tanpa version rows: materialisasi v1 dari modul
        # tersimpan agar regen/finalize/export-versioned berfungsi.
        # Gagal materialisasi -> perilaku lama (riwayat kosong).
        try:
            _materialize_baseline(vstore, stored, generation_id)
        except Exception:  # noqa: BLE001 - bootstrap best-effort
            logger.exception("Baseline materialize gagal")
    history = vstore.history(generation_id)
    latest = history[-1] if history else None
    return jsonify({
        'status': 'success',
        'generation_id': generation_id,
        'versions': [{k: v for k, v in _version_payload(h, False).items()}
                     for h in history],
        'latest_version': latest['version_no'] if latest else None,
    }), 200


@app.route('/api/module/<generation_id>/versions/<int:version_no>',
           methods=['GET'])
def get_version(generation_id, version_no):
    """Satu version lengkap (payload module untuk Review)."""
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    vstore, _store = _version_stores()
    version = vstore.get(generation_id, version_no)
    if version is None:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'MODULE_NOT_FOUND',
                                    'message': f'Version {version_no} tidak ada.',
                                    'stage': 'storage'}]}), 404
    return jsonify({'status': 'success', 'generation_id': generation_id,
                    'version': _version_payload(version)}), 200


def _structured_candidate_errors(errors):
    """Normalize domain validation errors for API/UI logic."""
    result = []
    for error in errors or []:
        if isinstance(error, str):
            error = {'code': 'FINAL_VALIDATION_ERROR', 'message': error}
        item = dict(error)
        item.setdefault('code', 'FINAL_VALIDATION_ERROR')
        item.setdefault('section', item.get('stage', 'candidate'))
        item.setdefault('entity_id', None)
        item.setdefault('severity', 'error')
        result.append(item)
    return result


@app.route('/api/module/<generation_id>/versions', methods=['POST'])
def save_version(generation_id):
    """Simpan candidate RPM secara global setelah validasi penuh.

    Body: {"base_version": int, "changes": {section: ...}}.
    Validasi seluruh candidate sebelum persistence.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Request body must be a JSON object.',
                                    'stage': 'input'}]}), 400
    base = data.get('base_version')
    if not isinstance(base, int) or isinstance(base, bool) or base < 1:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_PARAMS',
                                    'message': "'base_version' harus bilangan "
                                               'bulat >= 1.',
                                    'stage': 'input'}]}), 400
    try:
        vstore, store = _version_stores()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'MODULE_NOT_FOUND',
                                        'message': 'No stored module for this '
                                                   'generation_id.',
                                        'stage': 'storage'}]}), 404
        latest = _materialize_baseline(vstore, stored, generation_id)
        if base != latest['version_no']:
            return jsonify({'status': 'error',
                            'errors': [{
                                'code': 'STALE_VERSION',
                                'message': f"Version {base} sudah kedaluwarsa; "
                                           f"versi terbaru adalah v{latest['version_no']}. "
                                           f"Muat ulang sebelum menyimpan.",
                                'stage': 'concurrency',
                                'latest_version': latest['version_no']}]}), 409
        merged = copy.deepcopy(latest['module'])
        candidate = data.get('candidate')
        if candidate is not None:
            if not isinstance(candidate, dict):
                return jsonify({'status': 'error', 'errors': [{
                    'code': 'INVALID_PARAMS',
                    'message': 'Candidate document harus object.',
                    'stage': 'input'}]}), 400
            merged = copy.deepcopy(candidate)
        try:
            if candidate is not None and data.get('changes'):
                changed = _apply_section_changes(merged, data.get('changes'))
            else:
                changed = _apply_section_changes(merged, data.get('changes')) if candidate is None else [
                    key for key in merged.keys() if merged.get(key) != latest['module'].get(key)]
            if candidate is not None and not changed:
                return jsonify({'status': 'success', 'generation_id': generation_id,
                                'version': _version_payload(latest),
                                'unchanged': True}), 200
        except _SectionError as exc:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'INVALID_PARAMS',
                                        'message': str(exc),
                                        'stage': 'input'}]}), 400
        original_context = _rebuild_context_from_storage(
            generation_id, stored)
        if original_context is None:
            original_context = _context_objects.get(generation_id)
        if original_context is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'CONTEXT_UNAVAILABLE',
                                        'message': 'Stored context is incomplete '
                                                   'and cannot be rebuilt.',
                                        'stage': 'storage'}]}), 422
        # Kunci proteksi versi: CP/konteks/KBC selalu dari otoritatif.
        merged['curriculum_context'] = stored['module'].get(
            'curriculum_context')
        merged['approach_principles'] = stored['module'].get(
            'approach_principles', {})
        merged['id'] = stored['module']['id']
        merged['generation_id'] = stored['module']['generation_id']
        pipeline = get_generation_pipeline()
        module, schema_errors = _prepare_merged_for_battery(
            merged, original_context, pipeline)
        if module is None:
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'valid': False,
                            'errors': _structured_candidate_errors(schema_errors),
                            'warnings': []}), 422
        hard, soft = _run_version_battery(
            module, original_context, pipeline)
        if hard:
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'valid': False,
                            'errors': _structured_candidate_errors(hard + soft),
                            'warnings': []}), 422
        if soft:
            status, alignment = 'draft', 'Needs review'
        else:
            status, alignment = 'validated', 'Aligned'
        merged['master_outline'] = module.build_master_outline()
        merged['validation_results'] = dict(
            latest['module'].get('validation_results', {}),
            edited={'passed': not soft, 'errors': soft,
                    'at': utc_now_iso(), 'base_version': base})
        warnings = _dependency_warnings(changed)
        saved = vstore.save_new(
            generation_id, latest['version_no'], latest['version_no'],
            status, merged, merged['validation_results'], alignment,
            changed, warnings)
        return jsonify({'status': 'success', 'generation_id': generation_id,
                        'version': _version_payload(saved)}), 200
    except StaleVersionError as exc:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'STALE_VERSION',
                                    'message': str(exc),
                                    'stage': 'concurrency'}]}), 409
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Version save error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Version save failed due to an '
                                               'internal error.',
                                    'stage': 'server'}]}), 500


@app.route('/api/module/<generation_id>/versions/<int:version_no>/restore',
           methods=['POST'])
def restore_version(generation_id, version_no):
    """Restore version lama sebagai version BARU (history tidak dihapus)."""
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    try:
        vstore, store = _version_stores()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'MODULE_NOT_FOUND',
                                        'message': 'No stored module.',
                                        'stage': 'storage'}]}), 404
        source = vstore.get(generation_id, version_no)
        if source is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'MODULE_NOT_FOUND',
                                        'message': f'Version {version_no} tidak ada.',
                                        'stage': 'storage'}]}), 404
        latest = _materialize_baseline(vstore, stored, generation_id)
        original_context = _rebuild_context_from_storage(
            generation_id, stored)
        if original_context is None:
            original_context = _context_objects.get(generation_id)
        if original_context is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'CONTEXT_UNAVAILABLE',
                                        'message': 'Stored context is incomplete.',
                                        'stage': 'storage'}]}), 422
        merged = copy.deepcopy(source['module'])
        merged['curriculum_context'] = stored['module'].get(
            'curriculum_context')
        merged['approach_principles'] = stored['module'].get(
            'approach_principles', {})
        pipeline = get_generation_pipeline()
        module, schema_errors = _prepare_merged_for_battery(
            merged, original_context, pipeline)
        if module is None:
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'errors': schema_errors}), 422
        hard, soft = _run_version_battery(
            module, original_context, pipeline)
        if hard:
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'errors': hard + soft}), 422
        status = 'validated' if not soft else 'draft'
        alignment = 'Aligned' if not soft else 'Needs review'
        merged['master_outline'] = module.build_master_outline()
        merged['validation_results'] = dict(
            latest['module'].get('validation_results', {}),
            edited={'passed': not soft, 'errors': soft,
                    'at': utc_now_iso(),
                    'restored_from': version_no})
        saved = vstore.save_new(
            generation_id, latest['version_no'], version_no, status, merged,
            merged['validation_results'], alignment, ['restore'],
            [f'Dikembalikan dari v{version_no} sebagai version baru; '
             f'history tetap utuh.'])
        return jsonify({'status': 'success', 'generation_id': generation_id,
                        'version': _version_payload(saved)}), 200
    except StaleVersionError as exc:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'STALE_VERSION',
                                    'message': str(exc),
                                    'stage': 'concurrency'}]}), 409
    except Exception:  # noqa: BLE001
        logger.exception("Version restore error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Restore failed due to an '
                                               'internal error.',
                                    'stage': 'server'}]}), 500


@app.route('/api/module/<generation_id>/finalize', methods=['POST'])
def finalize_version(generation_id):
    """Kunci latest yang validated menjadi finalized (version baru).

    Setelah finalized, edit/regenerate membuat version baru (kembali
    draft/validated); tidak ada silent modification.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    try:
        vstore, store = _version_stores()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'MODULE_NOT_FOUND',
                                        'message': 'No stored module.',
                                        'stage': 'storage'}]}), 404
        latest = _materialize_baseline(vstore, stored, generation_id)
        if latest['status'] == 'finalized':
            return jsonify({'status': 'error',
                            'errors': [{'code': 'ALREADY_FINALIZED',
                                        'message': f"v{latest['version_no']} sudah "
                                                   'finalized.',
                                        'stage': 'finalize'}]}), 422
        if latest['status'] != 'validated':
            return jsonify({'status': 'error',
                            'errors': [{'code': 'FINALIZE_NOT_ALLOWED',
                                        'message': 'Hanya version validated yang '
                                                   'dapat di-finalize. Perbaiki '
                                                   'draft hingga Needs review '
                                                   'hilang lebih dulu.',
                                        'stage': 'finalize'}]}), 422
        saved = vstore.save_new(
            generation_id, latest['version_no'], latest['version_no'],
            'finalized', latest['module'],
            dict(latest['module'].get('validation_results', {}),
                 finalized={'passed': True, 'errors': [],
                            'at': utc_now_iso()}),
            latest.get('alignment_status') or 'Aligned', [],
            ['Difinalisasi dari v%d.' % latest['version_no']])
        return jsonify({'status': 'success', 'generation_id': generation_id,
                        'version': _version_payload(saved)}), 200
    except StaleVersionError as exc:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'STALE_VERSION',
                                    'message': str(exc),
                                    'stage': 'concurrency'}]}), 409
    except Exception:  # noqa: BLE001
        logger.exception("Finalize error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Finalize failed due to an '
                                               'internal error.',
                                    'stage': 'server'}]}), 500


def _regen_inputs_from_version(version_module: Dict, stored: Dict,
                               pipeline, generation_id: str):
    """Bangun context + input stage dari version terkini (teacher edits
    ikut — regeneration memakai current TP/materi/meeting, bukan baseline).
    """
    original_context = _rebuild_context_from_storage(
        generation_id, stored)
    if original_context is None:
        return None, None
    tp_entries = version_module.get('learning_objectives') or []
    tp_texts = [t.get('text', '') for t in tp_entries
                if isinstance(t, dict)]
    kktp_entries = []
    for k in version_module.get('success_criteria') or []:
        if not isinstance(k, dict):
            continue
        kktp_entries.append(KKTPEntry(
            id=k.get('id', ''), tp_id=k.get('tp_id', ''),
            criteria=list(k.get('criteria') or []),
            cognitive_level=k.get('cognitive_level', ''),
            source_type=k.get('source_type') or 'ai_generated'))
    original_context.topic = version_module.get('topic') or ''
    regulatory = pipeline.build_regulatory_context_for_generate({
        'education_system': original_context.education_system,
        'subject': original_context.subject,
        'phase': original_context.phase,
    })
    spec = _meetings_spec_from_module(version_module)
    meetings_spec = None
    if spec is not None:
        meetings_spec = {
            'n_meetings': spec['n_meetings'],
            'jp_per_meeting': spec['jp_per_meeting'],
            'minutes_per_jp': spec['minutes_per_jp'],
            'minutes_per_meeting': (spec['jp_per_meeting']
                                    * spec['minutes_per_jp']),
            'total_minutes': (spec['n_meetings'] * spec['jp_per_meeting']
                              * spec['minutes_per_jp']),
        }
    return {
        'context': original_context,
        'tp_texts': tp_texts,
        'kktp_entries': kktp_entries,
        'regulatory': regulatory,
        'meetings_spec': meetings_spec,
        'student_readiness': version_module.get('student_readiness') or '',
    }, None


@app.route('/api/module/<generation_id>/regenerate', methods=['POST'])
def regenerate_section(generation_id):
    """Partial regeneration satu section (bounded, tervalidasi penuh).

    Body: {"base_version": int, "target": tp|kktp|materi|aktivitas|
    asesmen|rubrik|refleksi|diagnostik|formatif|sumatif,
    "counts"?: {diagnostik|formatif|sumatif: int 1..30},
    "n_meetings"?: int 1..16 (khusus target aktivitas)}.
    Hanya section target yang berubah; field
    lain (termasuk edit guru) dipertahankan. Hasil invalid -> 422 tanpa
    version baru; version valid saat ini tetap aman.

    n_meetings (opsional, hanya aktivitas): AI memecah/menggabung
    aktivitas mengikuti jumlah pertemuan baru (budget/JP per pertemuan
    sama). Tanpa ini, regen mempertahankan jumlah versi saat ini.
    """
    if not _valid_generation_id(generation_id):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Malformed generation_id.',
                                    'stage': 'input'}]}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_REQUEST',
                                    'message': 'Request body must be a JSON object.',
                                    'stage': 'input'}]}), 400
    if data.get('async'):
        job_id = str(uuid.uuid4())
        worker_data = dict(data)
        worker_data.pop('async', None)
        _job_create(
            job_id, 'regenerate', {
                'generation_id': generation_id,
                'data': worker_data,
            })
        if not _submit_background_job(
                _run_regenerate_job, job_id, generation_id, worker_data):
            _job_remove(job_id)
            return jsonify({'status': 'error', 'errors': [{
                'code': 'JOB_QUEUE_FULL',
                'message': 'Antrean pekerjaan penuh. Coba lagi.',
                'stage': 'queue'}]}), 429
        return jsonify({'status': 'accepted', 'job_id': job_id,
                        'generation_id': generation_id}), 202
    draft_only = bool(data.get('draft'))
    base = data.get('base_version')
    target = data.get('target')
    if not isinstance(base, int) or isinstance(base, bool) or base < 1:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_PARAMS',
                                    'message': "'base_version' harus bilangan "
                                               'bulat >= 1.',
                                    'stage': 'input'}]}), 400
    if target not in REGEN_TARGETS:
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INVALID_PARAMS',
                                    'message': f"'target' harus salah satu dari "
                                               f"{', '.join(REGEN_TARGETS)}.",
                                    'stage': 'input'}]}), 400
    # Jumlah soal kustom per sub-bucket (opsional; 1..30). Tanpa ini,
    # regen mempertahankan jumlah versi saat ini.
    count_override = {}
    raw_counts = data.get('counts')
    if raw_counts is not None:
        if not isinstance(raw_counts, dict):
            return jsonify({'status': 'error',
                            'errors': [{'code': 'INVALID_PARAMS',
                                        'message': "'counts' harus object.",
                                        'stage': 'input'}]}), 400
        nama_ke_kunci = {'diagnostik': 'diagnostic',
                         'formatif': 'formative',
                         'sumatif': 'summative'}
        for nama, nilai in raw_counts.items():
            if nama not in nama_ke_kunci:
                return jsonify({'status': 'error',
                                'errors': [{
                                    'code': 'INVALID_PARAMS',
                                    'message': "'counts' hanya menerima kunci "
                                               'diagnostik/formatif/sumatif.',
                                    'stage': 'input'}]}), 400
            if isinstance(nilai, bool) or not isinstance(nilai, int) or not (
                    1 <= nilai <= ModuleGenerationPipeline
                    .ASSESSMENT_COUNT_MAX):
                return jsonify({'status': 'error',
                                'errors': [{
                                    'code': 'INVALID_PARAMS',
                                    'message': f"'counts.{nama}' harus bilangan "
                                               'bulat 1..30.',
                                    'stage': 'input'}]}), 400
            count_override[nama_ke_kunci[nama]] = nilai
    # Jumlah pertemuan kustom untuk regen aktivitas (opsional; 1..16).
    # Tanpa ini, regen mempertahankan jumlah versi saat ini.
    # Key hadir eksplisit (termasuk null) -> divalidasi ketat.
    n_meetings_override = None
    if 'n_meetings' in data:
        if target != 'aktivitas':
            return jsonify({'status': 'error',
                            'errors': [{'code': 'INVALID_PARAMS',
                                        'message': "'n_meetings' hanya untuk "
                                                   "target 'aktivitas'.",
                                        'stage': 'input'}]}), 400
        nilai_ptm = data.get('n_meetings')
        if isinstance(nilai_ptm, bool) or \
                not isinstance(nilai_ptm, int) or \
                not (1 <= nilai_ptm <= MAX_MEETINGS):
            return jsonify({'status': 'error',
                            'errors': [{'code': 'INVALID_PARAMS',
                                        'message': "'n_meetings' harus bilangan "
                                                   'bulat 1..16.',
                                        'stage': 'input'}]}), 400
        n_meetings_override = nilai_ptm
    try:
        vstore, store = _version_stores()
        stored = store.load(generation_id)
        if stored is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'MODULE_NOT_FOUND',
                                        'message': 'No stored module.',
                                        'stage': 'storage'}]}), 404
        latest = _materialize_baseline(vstore, stored, generation_id)
        if base != latest['version_no']:
            return jsonify({'status': 'error',
                            'errors': [{
                                'code': 'STALE_VERSION',
                                'message': f"Version {base} sudah kedaluwarsa; "
                                           f"versi terbaru adalah v{latest['version_no']}.",
                                'stage': 'concurrency',
                                'latest_version': latest['version_no']}]}), 409
        pipeline = get_generation_pipeline()
        stored_with_id = dict(stored)
        stored_with_id['generation_id'] = generation_id
        inputs, _err = _regen_inputs_from_version(
            latest['module'], stored_with_id, pipeline, generation_id)
        if inputs is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'CONTEXT_UNAVAILABLE',
                                        'message': 'Stored context is incomplete.',
                                        'stage': 'storage'}]}), 422
        ctx = inputs['context']
        tp_texts = inputs['tp_texts']
        if not tp_texts:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'INVALID_STATE',
                                        'message': 'Version ini tidak memiliki TP; '
                                                   'regeneration tidak dapat berjalan.',
                                        'stage': 'regen'}]}), 422
        import uuid as _uuid
        from module_store import GenerationLogStore
        regen_id = str(_uuid.uuid4())
        pipeline._gen_records = []
        ai_failed = None
        try:
            with generation_lock:
                if target == 'tp':
                    output = pipeline._ai_stage_call(
                        'tp', lambda fb: pipeline._generate_tp(
                            ctx, len(tp_texts),
                            regulatory_context=inputs['regulatory'],
                            feedback=fb))
                    applied = {
                        'learning_objectives': [
                            {'id': f'TP-{i}', 'text': text,
                             'cognitive_level': '',
                             'cp_reference': ctx.cp.id,
                             'source_type': 'ai_generated'}
                            for i, text in enumerate(output, 1)],
                    }
                    tp_for_downstream = list(output)
                elif target == 'kktp':
                    output = pipeline._ai_stage_call(
                        'kktp', lambda fb: pipeline._generate_kktp(
                            tp_texts, ctx, feedback=fb))
                    if len(output) != len(tp_texts):
                        raise ValueError(
                            f"KKTP regenerated {len(output)} untuk "
                            f"{len(tp_texts)} TP")
                    applied = {'success_criteria': [
                        {'id': k.id, 'tp_id': k.tp_id,
                         'criteria': list(k.criteria),
                         'cognitive_level': k.cognitive_level,
                         'source_type': k.source_type or 'ai_generated'}
                        for k in output]}
                    tp_for_downstream = None
                elif target == 'materi':
                    output = pipeline._ai_stage_call(
                        'materials', lambda fb: pipeline._generate_materials(
                            tp_texts, ctx, feedback=fb))
                    applied = {'essential_understanding': dict(
                        output['essential_understanding'])}
                    tp_for_downstream = None
                elif target == 'praktik_pedagogis':
                    output = pipeline._ai_stage_call(
                        'outline',
                        lambda fb: pipeline._generate_outline_content(
                            tp_texts, inputs['kktp_entries'], ctx,
                            regulatory_context=inputs['regulatory'],
                            feedback=fb,
                            student_readiness=inputs['student_readiness']))
                    if not isinstance(output.get('pedagogical_practices'), list) \
                            or not output['pedagogical_practices']:
                        raise ValueError(
                            "AI tidak mengembalikan praktik pedagogis")
                    applied = {
                        'pedagogical_practices': list(
                            output['pedagogical_practices'])}
                    tp_for_downstream = None
                elif target == 'aktivitas':
                    # n_meetings override: AI memecah/menggabung aktivitas
                    # mengikuti jumlah baru (JP/menit per pertemuan sama).
                    if n_meetings_override is not None:
                        cur_spec = inputs['meetings_spec']
                        if cur_spec is None:
                            raise ValueError(
                                "Modul tanpa meetings_spec; n_meetings "
                                "tidak dapat dipakai.")
                        _cur_n = cur_spec.get('n_meetings')
                        _jp = cur_spec.get('jp_per_meeting')
                        _mpp = cur_spec.get('minutes_per_jp')
                        if not (isinstance(_cur_n, int)
                                and isinstance(_jp, int)
                                and isinstance(_mpp, int)):
                            raise ValueError(
                                "meetings_spec tersimpan invalid.")
                        inputs['meetings_spec'] = {
                            'n_meetings': n_meetings_override,
                            'jp_per_meeting': _jp,
                            'minutes_per_jp': _mpp,
                            'minutes_per_meeting': _jp * _mpp,
                            'total_minutes': (n_meetings_override
                                              * _jp * _mpp),
                        }
                    output = pipeline._ai_stage_call(
                        'activities',
                        lambda fb: pipeline._generate_activities(
                            tp_texts, ctx, feedback=fb,
                            meetings_spec=inputs['meetings_spec'],
                            student_readiness=inputs.get(
                                'student_readiness') or ''))
                    applied = {'learning_activities': [
                        dataclass_asdict(a) for a in output]}
                    # Regen aktivitas = jalur AI mentah: jalankan anti-slop
                    # skills root (sama seperti STAGE 8 generate() penuh)
                    # pada deskripsi aktivitas, agar frasa AI dan istilah
                    # non-baku tidak lolos ke versi baru.
                    _regen_report = {
                        'skill_version':
                            AntiSlopProcessor.ANTISLOP_SKILL_VERSION,
                        'fields_processed': {}, 'rewrites': {},
                        'findings': []}
                    for _a in applied['learning_activities']:
                        _desc = _a.get('description') \
                            if isinstance(_a, dict) else None
                        if isinstance(_desc, str) and _desc:
                            _a['description'] = \
                                AntiSlopProcessor._normalize_text(
                                    _desc, 'activity_description',
                                    'activity_description', _regen_report)
                    tp_for_downstream = None
                elif target in ('asesmen', 'rubrik', 'diagnostik',
                                  'formatif', 'sumatif'):
                    asm_cur = latest['module'].get('assessments') or {}
                    summ_cur = asm_cur.get('summative') or {}
                    s_items = summ_cur.get('items') \
                        if isinstance(summ_cur, dict) else None
                    # Batch 8.5 §7: regen mempertahankan jumlah soal versi
                    # saat ini (default bila bucket kosong). R-42: bucket
                    # lain yang kosong = 0 (tidak digenerate ulang);
                    # hanya target yang memakai default/override.
                    if target in REGEN_SUBBUCKET:
                        sub_target = REGEN_SUBBUCKET[target]
                        counts = {'diagnostic': 0, 'formative': 0,
                                  'summative': 0}
                        cur_len = None
                        if sub_target == 'summative':
                            if isinstance(s_items, list) and s_items:
                                cur_len = len(s_items)
                        else:
                            cur_items = asm_cur.get(sub_target)
                            if isinstance(cur_items, list) and cur_items:
                                cur_len = len(cur_items)
                        if cur_len is not None:
                            counts[sub_target] = cur_len
                        else:
                            counts[sub_target] = (
                                ModuleGenerationPipeline
                                .DEFAULT_ASSESSMENT_COUNTS[sub_target])
                    else:
                        counts = dict(
                            ModuleGenerationPipeline
                            .DEFAULT_ASSESSMENT_COUNTS)
                        for key, items in (
                                ('diagnostic', asm_cur.get('diagnostic')),
                                ('formative', asm_cur.get('formative'))):
                            if isinstance(items, list) and items:
                                counts[key] = len(items)
                        if isinstance(s_items, list) and s_items:
                            counts['summative'] = len(s_items)
                    counts.update(count_override)
                    output = pipeline._ai_stage_call(
                        'assessments',
                        lambda fb: pipeline._generate_assessments(
                            tp_texts, inputs['kktp_entries'], ctx,
                            counts=counts,
                            feedback=fb,
                            student_readiness=inputs.get(
                                'student_readiness') or ''))
                    if target == 'asesmen':
                        applied = {'assessments': dict(output)}
                    elif target in REGEN_SUBBUCKET:
                        # Regen sub-bucket: hanya bucket diminta yang
                        # diganti; bucket lain + rubrik dipertahankan.
                        sub = REGEN_SUBBUCKET[target]
                        asm = copy.deepcopy(
                            latest['module'].get('assessments') or {})
                        if sub == 'summative':
                            if not isinstance(
                                    output.get('summative'), dict):
                                raise ValueError(
                                    "AI tidak mengembalikan bucket summative")
                            asm['summative'] = dict(output['summative'])
                        else:
                            if not isinstance(output.get(sub), list):
                                raise ValueError(
                                    "AI tidak mengembalikan bucket " + sub)
                            asm[sub] = list(output[sub])
                        applied = {'assessments': asm}
                    else:
                        if not isinstance(
                                output.get('rubric_descriptors'), dict):
                            raise ValueError(
                                "AI tidak mengembalikan rubric_descriptors")
                        asm = copy.deepcopy(
                            latest['module'].get('assessments') or {})
                        asm['rubric_descriptors'] = dict(
                            output['rubric_descriptors'])
                        applied = {'assessments': asm}
                    tp_for_downstream = None
                elif target == 'refleksi':
                    output = pipeline._ai_stage_call(
                        'outline',
                        lambda fb: pipeline._generate_outline_content(
                            tp_texts, inputs['kktp_entries'], ctx,
                            regulatory_context=inputs['regulatory'],
                            feedback=fb,
                            student_readiness=inputs['student_readiness']))
                    applied = {'reflection': [
                        {'role': 'student',
                         'questions': list(
                             output.get('student_reflection') or [])},
                        {'role': 'teacher',
                         'questions': list(
                             output.get('teacher_reflection') or [])},
                    ]}
                    tp_for_downstream = None
                else:  # glosarium
                    eu = (latest['module'].get('essential_understanding')
                          or {})
                    summary = ' '.join(str(eu.get(k) or '') for k in
                                       ('core_insight', 'relationship',
                                        'application', 'value'))
                    output = pipeline._ai_stage_call(
                        'glosarium',
                        lambda fb: pipeline._generate_glosarium(
                            tp_texts, ctx, materi_summary=summary,
                            feedback=fb))
                    applied = {'glosarium': list(output)}
                    tp_for_downstream = None
        except Exception as exc:
            ai_failed = exc
        finally:
            try:
                records = list(getattr(pipeline, '_gen_records', None) or [])
                for r in records:
                    r['generation_id'] = regen_id
                records.append({
                    'generation_id': regen_id, 'stage': 'regen', 'attempt': 1,
                    'prompt_version': None, 'prompt_hash': None,
                    'model': pipeline.ai_client.config.combo,
                    'provider': '9router', 'status': 'success',
                    'error_category': None, 'error': None, 'duration_ms': None,
                    'response_chars': None, 'empty_flag': None,
                    'truncated_flag': None,
                })
                GenerationLogStore(pipeline.db_path).save_records(records)
            except Exception:
                pass
        if ai_failed is not None:
            # AI failure dibedakan dari server error (§14); tanpa version.
            if isinstance(ai_failed, NineRouterError):
                code, msg = 'AI_GENERATION_FAILED', (
                    f"AI generation failed: {ai_failed}")
            else:
                code, msg = 'AI_GENERATION_FAILED', (
                    f"AI response malformed: {ai_failed}")
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'regen_id': regen_id,
                            'errors': [{'code': code, 'message': msg,
                                        'stage': 'pipeline'}]}), 422
        merged = copy.deepcopy(latest['module'])
        merged['curriculum_context'] = stored['module'].get(
            'curriculum_context')
        merged['approach_principles'] = stored['module'].get(
            'approach_principles', {})
        merged['id'] = stored['module']['id']
        merged['generation_id'] = stored['module']['generation_id']
        if target == 'tp':
            merged['learning_objectives'] = applied['learning_objectives']
            tp_ids = [t['id'] for t in merged['learning_objectives']]
            merged_ctx = dict(merged.get('curriculum_context') or {})
            merged_ctx['tp_list'] = [
                {'id': tid, 'text': text}
                for tid, text in zip(tp_ids, tp_for_downstream)]
            merged_ctx['atp'] = dict(
                merged_ctx.get('atp') or {}, tp_ids=list(tp_ids))
            merged['curriculum_context'] = merged_ctx
        elif target == 'kktp':
            merged['success_criteria'] = applied['success_criteria']
        elif target == 'materi':
            merged['essential_understanding'] = applied[
                'essential_understanding']
        elif target == 'praktik_pedagogis':
            merged['pedagogical_practices'] = applied[
                'pedagogical_practices']
        elif target == 'aktivitas':
            merged['learning_activities'] = applied['learning_activities']
            # n_meetings override: meetings lama diganti hasil rebuild
            # dari aktivitas AI baru (jumlah baru, JP/menit sama).
            # Battery lalu validasi budget lawan spec baru; hasil AI
            # invalid -> 422 tanpa version (fail closed).
            if n_meetings_override is not None:
                _nspec = inputs.get('meetings_spec') or {}
                try:
                    merged['meetings'] = build_meetings(
                        merged['learning_activities'],
                        int(_nspec['n_meetings']),
                        int(_nspec['jp_per_meeting']),
                        int(_nspec['minutes_per_jp']))
                except (TypeError, ValueError, KeyError) as exc:
                    return jsonify({
                        'status': 'error',
                        'generation_id': generation_id,
                        'errors': [{'code': 'AI_GENERATION_FAILED',
                                    'message': 'AI response malformed: '
                                               f'{exc}',
                                    'stage': 'pipeline'}]}), 422
            # KBC traceability dihitung ulang dari aktivitas baru
            # (Batch 5 §8; Batch 1 traceability tetap aktif).
            try:
                from module_generation_pipeline import (
                    resolve_kbc_insertions as _rkbc)
                kbc = copy.deepcopy(
                    (merged.get('approach_principles') or {}).get('kbc')
                    or {})
                if kbc.get('enabled'):
                    kbc['insertions'] = _rkbc(
                        kbc, merged['learning_activities'])
                    merged['approach_principles'] = dict(
                        merged.get('approach_principles') or {}, kbc=kbc)
            except Exception:
                pass
        elif target in ('asesmen', 'rubrik', 'diagnostik',
                          'formatif', 'sumatif'):
            merged['assessments'] = applied['assessments']
        elif target == 'glosarium':
            merged['glosarium'] = applied['glosarium']
        else:
            merged['reflection'] = applied['reflection']
        original_context = _rebuild_context_from_storage(
            generation_id, stored)
        if original_context is None:
            original_context = _context_objects.get(generation_id)
        if original_context is None:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'CONTEXT_UNAVAILABLE',
                                        'message': 'Stored context is incomplete.',
                                        'stage': 'storage'}]}), 422
        module, schema_errors = _prepare_merged_for_battery(
            merged, original_context, pipeline)
        if module is None:
            return jsonify({'status': 'error', 'generation_id': generation_id,
                            'errors': schema_errors}), 422
        hard, soft = _run_version_battery(
            module, original_context, pipeline)
        if hard or soft:
            # Regen invalid -> tanpa version baru; current valid aman.
            return jsonify({
                'status': 'error', 'generation_id': generation_id,
                'errors': hard + soft,
                'affected': SECTION_DEPENDENTS.get(target, [])}), 422
        if target == 'aktivitas':
            # UAT FIX: pakai prinsip FRESH dari respons regen ini, bukan
            # carry-over basi dari meetings lama (sudah tervalidasi
            # _validate_meeting_principles di stage call).
            fresh = getattr(pipeline, '_last_meeting_principles', None) or []
            if fresh and len(fresh) == len(merged.get('meetings') or []):
                merged['meetings'] = attach_meeting_principles(
                    merged['meetings'], fresh)
                module.meetings = merged['meetings']
        merged['master_outline'] = module.build_master_outline()
        merged['validation_results'] = dict(
            latest['module'].get('validation_results', {}),
            edited={'passed': True, 'errors': [],
                    'at': utc_now_iso(), 'base_version': base,
                    'regenerated': target, 'regen_id': regen_id})
        warnings = _dependency_warnings([target])
        if draft_only:
            candidate = dict(latest)
            candidate['module'] = merged
            candidate['validation'] = merged['validation_results']
            candidate['changed_sections'] = [target]
            candidate['warnings'] = warnings
            return jsonify({'status': 'success', 'generation_id': generation_id,
                            'regen_id': regen_id, 'draft': True,
                            'version': _version_payload(candidate)}), 200
        try:
            saved = vstore.save_new(
                generation_id, latest['version_no'], latest['version_no'],
                'validated', merged, merged['validation_results'],
                'Aligned', [target], warnings)
        except StaleVersionError as exc:
            return jsonify({'status': 'error',
                            'errors': [{'code': 'STALE_VERSION',
                                        'message': str(exc),
                                        'stage': 'concurrency'}]}), 409
        return jsonify({'status': 'success', 'generation_id': generation_id,
                        'regen_id': regen_id,
                        'version': _version_payload(saved)}), 200
    except Exception:  # noqa: BLE001 - never leak internals
        logger.exception("Regeneration error")
        return jsonify({'status': 'error',
                        'errors': [{'code': 'INTERNAL_ERROR',
                                    'message': 'Regeneration failed due to an '
                                               'internal error.',
                                    'stage': 'server'}]}), 500


def _run_upload_buku_job(job_id, tmp_path, db_path, nama_asli, judul,
                         size):
    """Background upload-buku worker; progres via ingest_buku lapor."""
    def lapor(progress, tahap):
        _job_update(job_id, progress=progress, tahap=tahap)
    try:
        from buku_ajar import ingest_buku
        hasil = ingest_buku(db_path, tmp_path, nama_asli, judul,
                            lapor=lapor)
        _job_set(job_id, {
            'status': 'success', 'kind': 'upload_buku',
            'progress': 100, 'tahap': 'Selesai.',
            'result': hasil,
        })
    except ValueError as exc:
        _job_set(job_id, {
            'status': 'error', 'kind': 'upload_buku',
            'result': {'errors': [{'code': 'UPLOAD_INVALID',
                                   'message': str(exc),
                                   'stage': 'input'}]},
        })
    except Exception:  # noqa: BLE001
        logger.exception('Async upload buku error')
        _job_set(job_id, {
            'status': 'error', 'kind': 'upload_buku',
            'result': {'errors': [{'code': 'INTERNAL_ERROR',
                                   'message': 'Upload buku gagal.',
                                   'stage': 'server'}]},
        })
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_regenerate_job(job_id, generation_id, data):
    """Background regenerate worker; result remains draft-only."""
    try:
        with app.test_request_context(
                f'/api/module/{generation_id}/regenerate',
                method='POST', json={**data, 'draft': True}):
            response = regenerate_section(generation_id)
        body = response[0] if isinstance(response, tuple) else response
        status_code = response[1] if isinstance(response, tuple) else 200
        payload = body.get_json() if hasattr(body, 'get_json') else body
        _job_set(job_id, {
            'status': 'success' if status_code < 400 else 'error',
            'kind': 'regenerate',
            'result': payload or {},
        })
    except Exception:
        logger.exception('Async regeneration error')
        _job_set(job_id, {
            'status': 'error',
            'kind': 'regenerate',
            'result': {'errors': [{'code': 'INTERNAL_ERROR',
                                   'message': 'Regeneration failed.',
                                   'stage': 'regenerate'}]},
        })


@app.route('/api/generation/status/<job_id>', methods=['GET'])
def generation_status(job_id):
    """Poll an async generation job (used by the UI progress panel).

    If the module was persisted (and possibly edited via PUT since), the
    STORED version is the source of truth - the in-memory job result is
    only the original generation output.
    """
    job = _job_get(job_id)
    if job is None or not _valid_generation_id(job_id):
        return jsonify({
            'status': 'error',
            'errors': [{'code': 'NOT_FOUND', 'message': 'Unknown generation job.', 'stage': 'poll'}]
        }), 404
    payload = {'status': job['status']}
    if job.get('kind') == 'regenerate':
        payload.update(job.get('result') or {})
        return jsonify(payload), 200
    if job['status'] == 'success':
        result_gen_id = (job.get('result') or {}).get('generation_id')
        # Prefer the persisted (possibly edited) module over the original.
        # Storage is keyed by the MODULE generation_id (which PUT uses), not
        # by the polling job_id - load with the right key.
        stored = None
        try:
            if result_gen_id:
                stored = ModuleStore(get_generation_pipeline().db_path).load(result_gen_id)
        except Exception:
            logger.exception("Failed loading stored module; falling back to job result")
        if stored is not None:
            payload.update({
                'generation_id': result_gen_id,
                'module': stored['module'],
                'validation': stored['module'].get('validation_results', {}),
            })
            return jsonify(payload), 200
        payload.update({
            'generation_id': result_gen_id,
            'module': job['result'].get('module'),
            'validation': job['result'].get('validation', {})
        })
    elif job['status'] in ('warning', 'error'):
        payload.update(job.get('result') or {})
        if job['status'] == 'error':
            payload.setdefault('generation_id',
                              (job.get('result') or {}).get('generation_id'))
    if job.get('timing'):
        payload['timing'] = dict(job['timing'])
    return jsonify(payload), 200


def _run_generation_job(job_id, params, gate_data=None):
    """Background worker: run relevance gate, pipeline, and persistence."""
    worker_started = time.perf_counter()
    job = _job_get(job_id)
    timing = (job or {}).setdefault('timing', {})
    accepted_mono = (job or {}).get('_accepted_mono')
    timing['worker_started_at'] = utc_now_iso()
    if accepted_mono is not None:
        timing['queue_wait_ms'] = round(
            (worker_started - accepted_mono) * 1000, 1)
    try:
        gate_payload = dict(gate_data or params or {})
        if not _is_skip_relevance(gate_payload):
            relevance_started = time.perf_counter()
            relevance = _check_topic_relevance(gate_payload)
            timing['relevance_duration_ms'] = round(
                (time.perf_counter() - relevance_started) * 1000, 1)
            if relevance is not None and relevance.get('perlu_warning'):
                _job_set(job_id, {
                    'status': 'warning',
                    'result': {
                        'code': 'RELEVANCE_WARNING',
                        'message': ('Topik kurang relevan dengan elemen yang '
                                    'dipilih.'),
                        'relevansi': relevance.get('relevansi', []),
                        'saran': relevance.get('saran', ''),
                        'perlu_warning': True,
                    },
                    'timing': {
                        **timing,
                        'worker_total_ms': round(
                            (time.perf_counter() - worker_started) * 1000, 1),
                    },
                })
                return

        pipeline_started = time.perf_counter()
        lock_started = time.perf_counter()
        generation_lock.acquire()
        timing['lock_wait_ms'] = round(
            (time.perf_counter() - lock_started) * 1000, 1)
        try:
            pipeline = get_generation_pipeline()
            result = pipeline.generate(params)
            # Snapshot shared validator state before releasing generation_lock.
            # Another worker may start immediately after release.
            ctx_obj = getattr(pipeline.curriculum_validator, 'last_context', None)
        finally:
            generation_lock.release()
        timing['pipeline_worker_ms'] = round(
            (time.perf_counter() - pipeline_started) * 1000, 1)
        timing.update(result.get('generation_timing') or {})
        if result.get('status') == 'success' and result.get('module'):
            generation_context['module'] = result['module']
            # Persistent storage: final module + authoritative context
            # (module JSON + context JSON; the live context object is kept
            # in-process for edit re-validation). A failed save fails the
            # job, so success never claims persistence it did not do.
            persist_started = time.perf_counter()
            try:
                store = ModuleStore(pipeline.db_path)
                ctx_dict = dict(result['module'].get('curriculum_context') or {})
                if not ctx_dict:
                    raise ValueError("Generated module has no curriculum_context")
                store.save(result.get('generation_id'), result['module'], ctx_dict)
                if ctx_obj is not None:
                    try:
                        _context_objects[result.get('generation_id')] = ctx_obj
                    except Exception:
                        pass
            except Exception:
                timing['persistence_duration_ms'] = round(
                    (time.perf_counter() - persist_started) * 1000, 1)
                timing['worker_total_ms'] = round(
                    (time.perf_counter() - worker_started) * 1000, 1)
                logger.exception("Failed storing generated module")
                _job_set(job_id, {
                    'status': 'error',
                    'result': {
                        'generation_id': result.get('generation_id'),
                        'errors': [{'code': 'STORAGE_ERROR',
                                    'message': 'Generation succeeded but persistence failed.',
                                    'stage': 'storage'}],
                    },
                    'timing': timing,
                })
                return
            timing['persistence_duration_ms'] = round(
                (time.perf_counter() - persist_started) * 1000, 1)
            timing['worker_total_ms'] = round(
                (time.perf_counter() - worker_started) * 1000, 1)
            _job_set(job_id, {
                'status': 'success',
                'result': {
                    'generation_id': result.get('generation_id'),
                    'module': result['module'],
                    'validation': result.get('validation', {}),
                    'generation_timing': result.get('generation_timing', {}),
                },
                'timing': timing,
            })
        else:
            errors = []
            for err in result.get('errors', []):
                if isinstance(err, dict):
                    errors.append(err)
                else:
                    errors.append({'code': 'VALIDATION_FAILED', 'message': str(err), 'stage': 'pipeline'})
            if not errors:
                errors = [{'code': 'GENERATION_FAILED', 'message': 'Module generation did not pass validation.', 'stage': 'pipeline'}]
            _job_set(job_id, {
                'status': 'error',
                'result': {'generation_id': result.get('generation_id'), 'errors': errors},
                'timing': timing,
            })
    except Exception as e:
        timing['worker_total_ms'] = round(
            (time.perf_counter() - worker_started) * 1000, 1)
        logger.error("Module generation error: %s", e)
        _job_set(job_id, {
            'status': 'error',
            'result': {'errors': [{'code': 'INTERNAL_ERROR', 'message': 'Module generation failed due to an internal error.', 'stage': 'pipeline'}]},
            'timing': timing,
        })
    finally:
        timing['worker_total_ms'] = round(
            (time.perf_counter() - worker_started) * 1000, 1)
        _job_update(job_id, timing=timing)


def _recover_persisted_jobs(db_path: Optional[str] = None) -> int:
    """Requeue unfinished jobs after Flask process restart."""
    store = _async_store(db_path)
    recovered = 0
    for row in store.list_unfinished():
        job_id = row['job_id']
        if generation_jobs.get(job_id) is not None:
            continue
        generation_jobs[job_id] = _memory_job(row)
        payload = row.get('payload') or {}
        kind = row.get('kind')
        submitted = False
        if kind == 'generate':
            params = payload.get('params')
            gate_data = payload.get('gate_data') or params
            if isinstance(params, dict):
                submitted = _submit_background_job(
                    _run_generation_job, job_id, params, gate_data)
        elif kind == 'regenerate':
            generation_id = payload.get('generation_id')
            data = payload.get('data')
            if isinstance(generation_id, str) and isinstance(data, dict):
                submitted = _submit_background_job(
                    _run_regenerate_job, job_id, generation_id, data)
        elif kind == 'upload_buku':
            path = payload.get('tmp_path')
            if isinstance(path, str) and os.path.isfile(path):
                submitted = _submit_background_job(
                    _run_upload_buku_job, job_id, path,
                    payload.get('db_path') or str(DB_PATH),
                    payload.get('nama_asli') or 'upload',
                    payload.get('judul'), payload.get('size') or 0)
            else:
                _job_set(job_id, {
                    'status': 'error',
                    'result': {'errors': [{
                        'code': 'JOB_INPUT_LOST',
                        'message': 'Berkas upload tidak ditemukan setelah restart.',
                        'stage': 'restart'}]},
                })
        if submitted:
            recovered += 1
        else:
            current = _job_get(job_id, db_path)
            if kind == 'upload_buku' and current is not None and current.get('status') != 'running':
                continue
            _job_set(job_id, {
                'status': 'error',
                'result': {'errors': [{
                    'code': 'JOB_RECOVERY_FAILED',
                    'message': 'Pekerjaan tidak dapat dilanjutkan setelah restart.',
                    'stage': 'restart'}]},
            })
    return recovered


@app.route('/api/module/generate', methods=['POST'])
def generate_module():
    """Generate learning module via the real AI generation pipeline."""
    data = request.get_json(silent=True) or {}

    # Async mode: the UI polls /api/generation/status/<job_id> instead of
    # holding the HTTP request open for minutes.
    if data.get('async'):
        request_started = time.perf_counter()
        job_id = str(uuid.uuid4())
        params = _generation_params_from_request(data)
        meetings_err = _validate_meetings_input(
            data.get('jumlah_pertemuan'), data.get('jp_per_pertemuan'))
        if meetings_err:
            return jsonify({
                'status': 'error',
                'errors': [{'code': 'INVALID_PARAMS', 'message': meetings_err,
                            'stage': 'input'}]
            }), 400
        _counts, _counts_err = ModuleGenerationPipeline.resolve_assessment_counts(
            data.get('assessment_counts'))
        if _counts_err:
            return jsonify({
                'status': 'error',
                'errors': [{'code': 'INVALID_PARAMS', 'message': _counts_err,
                            'stage': 'input'}]
            }), 400
        limit_errors = validate_generate_body(data, data)
        if limit_errors:
            return jsonify({
                'status': 'error',
                'errors': limit_errors
            }), 400
        # Relevance gate berjalan di worker, bukan sebelum HTTP 202.
        # Warning tetap dikembalikan melalui status polling sehingga request
        # awal tidak menunggu AI advisory call.
        accepted_mono = time.perf_counter()
        _job_create(
            job_id, 'generate', {
                'params': params,
                'gate_data': dict(data),
            },
            accepted_mono=accepted_mono,
            timing={
                'request_validation_ms': round(
                    (accepted_mono - request_started) * 1000, 1),
                'accepted_at': utc_now_iso(),
            },
        )
        if not _submit_background_job(
                _run_generation_job, job_id, params, dict(data)):
            _job_remove(job_id)
            return jsonify({'status': 'error', 'errors': [{
                'code': 'JOB_QUEUE_FULL',
                'message': 'Antrean pekerjaan penuh. Coba lagi.',
                'stage': 'queue'}]}), 429
        return jsonify({'status': 'accepted', 'job_id': job_id}), 202

    try:
        data = request.get_json(silent=True) or {}
        params = _generation_params_from_request(data)
        meetings_err = _validate_meetings_input(
            data.get('jumlah_pertemuan'), data.get('jp_per_pertemuan'))
        if meetings_err:
            return jsonify({
                'status': 'error',
                'errors': [{'code': 'INVALID_PARAMS', 'message': meetings_err,
                            'stage': 'input'}]
            }), 400
        _counts, _counts_err = ModuleGenerationPipeline.resolve_assessment_counts(
            data.get('assessment_counts'))
        if _counts_err:
            return jsonify({
                'status': 'error',
                'errors': [{'code': 'INVALID_PARAMS', 'message': _counts_err,
                            'stage': 'input'}]
            }), 400
        limit_errors = validate_generate_body(data, data)
        if limit_errors:
            return jsonify({
                'status': 'error',
                'errors': limit_errors
            }), 400

        # Soft gate relevansi (sama seperti mode async di atas).
        gate = _relevance_gate_response(data)
        if gate is not None:
            return gate

        # R-43: buku wajib dipilih di UI (validasi form); endpoint
        # menerima tanpa buku agar kompatibel.

        # Pipeline and its validator hold mutable per-generation state.
        # Serialize the whole generate + context snapshot, not only AI calls.
        with generation_lock:
            pipeline = get_generation_pipeline()
            result = pipeline.generate(params)
            ctx_obj = getattr(
                pipeline.curriculum_validator, 'last_context', None)

        if result.get('status') == 'success' and result.get('module'):
            # Store module for download endpoint + persistent ModuleStore
            # (GET/PUT/export read storage, not memory).
            generation_context['module'] = result['module']
            try:
                store = ModuleStore(pipeline.db_path)
                ctx_dict = dict(
                    result['module'].get('curriculum_context') or {})
                if not ctx_dict:
                    raise ValueError(
                        "Generated module has no curriculum_context")
                store.save(
                    result.get('generation_id'), result['module'], ctx_dict)
                if ctx_obj is not None:
                    try:
                        _context_objects[result.get('generation_id')] = ctx_obj
                    except Exception:
                        pass
            except Exception:
                logger.exception("Failed storing generated module")
                return jsonify({
                    'status': 'error',
                    'generation_id': result.get('generation_id'),
                    'errors': [{'code': 'STORAGE_ERROR',
                                'message': 'Generation succeeded but persistence failed.',
                                'stage': 'storage'}],
                }), 500
            return jsonify({
                'status': 'success',
                'generation_id': result.get('generation_id'),
                'module': result['module'],
                'validation': result.get('validation', {})
            }), 200

        # Validation failure: structured errors, generation FAILS.
        # Pipeline errors are strings; map them onto the structured contract.
        errors = []
        for err in result.get('errors', []):
            if isinstance(err, dict):
                errors.append(err)
            else:
                errors.append({
                    'code': 'VALIDATION_FAILED',
                    'message': str(err),
                    'stage': 'pipeline'
                })
        if not errors:
            errors = [{
                'code': 'GENERATION_FAILED',
                'message': 'Module generation did not pass validation.',
                'stage': 'pipeline'
            }]
        return jsonify({
            'status': 'error',
            'generation_id': result.get('generation_id'),
            'errors': errors
        }), 422
    except Exception as e:
        # Never leak internals (stack traces, credentials, file paths)
        logger.error("Module generation error: %s", e)
        return jsonify({
            'status': 'error',
            'errors': [{
                'code': 'INTERNAL_ERROR',
                'message': 'Module generation failed due to an internal error.',
                'stage': 'pipeline'
            }]
        }), 500


@app.route('/api/module/download', methods=['GET'])
def download_module():
    """Download generated module as JSON.

    Single-operator legacy route: serves the last in-memory module of this
    process. A ``generation_id`` query param never selects a different
    module silently — a mismatch is a 409 instead of the wrong file.
    """
    try:
        requested = request.args.get('generation_id')
        if requested is not None and not _valid_generation_id(requested):
            return jsonify({
                'status': 'error',
                'message': 'Invalid generation_id.'
            }), 400

        # Requested ID selects persisted content, including after restart or
        # memory cleanup. No request may silently receive another module.
        module = None
        if requested is not None:
            stored = _resolve_app_store().load(requested)
            if stored is not None:
                module = stored.get('module')
        else:
            module = generation_context.get('module')
            if not module:
                summaries = _resolve_app_store().list_summaries()
                if summaries:
                    latest_id = summaries[0].get('generation_id')
                    if isinstance(latest_id, str):
                        stored = _resolve_app_store().load(latest_id)
                        module = (stored or {}).get('module')
        if not isinstance(module, dict):
            return jsonify({
                'status': 'error',
                'message': 'No module generated yet. Generate a module first.'
            }), 404

        output_path = PROJECT_ROOT / 'db' / 'downloaded_module.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(module, f, indent=2, ensure_ascii=False)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"module_{module.get('id', 'module')}.json"
        )
    except Exception:
        logger.exception("Module download failed")
        return jsonify({
            'status': 'error',
            'message': 'Module download failed due to an internal error.'
        }), 500


DOCX_MIMETYPE = ('application/vnd.openxmlformats-officedocument.'
                 'wordprocessingml.document')


def _safe_docx_filename(module: Dict, generation_id: str) -> str:
    """Nama file aman dari judul/ID modul (tanpa path traversal)."""
    base = str(module.get('title') or module.get('id') or generation_id)
    slug = re.sub(r'[^A-Za-z0-9-_]+', '-', base).strip('-')[:60]
    if not slug:
        slug = 'rpm-' + re.sub(r'[^A-Za-z0-9-_]+', '',
                               str(generation_id))[:8]
    return f"{slug}.docx"


@app.route('/api/module/<generation_id>/export-docx', methods=['GET'])
def export_module_docx(generation_id):
    """Export FINAL VALIDATED RPM sebagai file .docx.

    Sumber: modul tersimpan (ModuleStore) atau modul in-memory milik
    generation yang sama. Hard gate final validation ditegakkan oleh
    renderer — tanpa bypass. Draft/gagal/tidak ditemukan ditolak
    dengan status HTTP yang sesuai.
    """
    # Load DOCX dependencies only for export. API startup and generation do
    # not need python-docx or template rendering.
    from docx_renderer import ExportError, render_final_rpm_docx

    if not generation_id or '..' in generation_id or '/' in generation_id:
        return jsonify({
            'status': 'error',
            'message': 'Invalid generation_id.'
        }), 400
    if not _valid_generation_id(generation_id):
        return jsonify({
            'status': 'error',
            'message': 'Invalid generation_id.'
        }), 400
    # Batch 5 §12: export memakai version yang dipilih user (default
    # latest). Baris lama tanpa version rows memakai perilaku legacy.
    requested_version = request.args.get('version', type=int)
    try:
        vstore = VersionStore(get_generation_pipeline().db_path)
        version_row = None
        if requested_version is not None:
            version_row = vstore.get(generation_id, requested_version)
            if version_row is None:
                return jsonify({
                    'status': 'error',
                    'message': f'Version {requested_version} tidak ada.'
                }), 404
        else:
            version_row = vstore.latest(generation_id)
        if version_row is not None:
            if version_row['status'] == 'draft':
                return jsonify({
                    'status': 'error',
                    'message': 'Version masih draft (Needs review). '
                               'Perbaiki hingga validated sebelum export.'
                }), 422
            module = version_row['module']
            result = {
                'status': 'success',
                'generation_id': generation_id,
                'module': module,
                'validation': version_row.get('validation') or {},
            }
            tmp = tempfile.NamedTemporaryFile(
                suffix='.docx', delete=False)
            tmp.close()
            try:
                out_path = render_final_rpm_docx(result, tmp.name)
            except ExportError as e:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 422

            @after_this_request
            def _cleanup(response):
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
                return response

            return send_file(
                out_path,
                mimetype=DOCX_MIMETYPE,
                as_attachment=True,
                download_name=_safe_docx_filename(module, generation_id)
            )
        stored = None
        try:
            stored = _resolve_app_store().load(generation_id)
        except Exception:
            logger.exception("Failed loading stored module for DOCX export")
        module = (stored or {}).get('module') if stored else None
        if module is None:
            mem = generation_context.get('module') or {}
            if mem.get('generation_id') == generation_id:
                module = mem
        if not isinstance(module, dict):
            return jsonify({
                'status': 'error',
                'message': 'No module generated yet. Generate a module first.'
            }), 404
        result = {
            'status': 'success',
            'generation_id': generation_id,
            'module': module,
            'validation': module.get('validation_results', {}),
        }
        tmp = tempfile.NamedTemporaryFile(
            suffix='.docx', delete=False)
        tmp.close()
        try:
            out_path = render_final_rpm_docx(result, tmp.name)
        except ExportError as e:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 422

        @after_this_request
        def _cleanup(response):
            try:
                os.unlink(out_path)
            except OSError:
                pass
            return response

        return send_file(
            out_path,
            mimetype=DOCX_MIMETYPE,
            as_attachment=True,
            download_name=_safe_docx_filename(module, generation_id)
        )
    except Exception as e:
        logger.error("DOCX export error: %s", e)
        return jsonify({
            'status': 'error',
            'message': 'Module export failed due to an internal error.'
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM source_fragments")
        fragments = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM learning_outcomes")
        cp_count = cursor.fetchone()[0]
        cp_by_subject = None
        if request.args.get('summary') != '1':
            cursor.execute("""
                SELECT subject, COUNT(*) as count
                FROM learning_outcomes
                GROUP BY subject
            """)
            cp_by_subject = {row['subject']: row['count'] for row in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) FROM source_documents")
        documents = cursor.fetchone()[0]
        return jsonify({
            'status': 'success',
            'statistics': {
                'total_fragments': fragments,
                'total_cp_entries': cp_count,
                **({'cp_by_subject': cp_by_subject} if cp_by_subject is not None else {}),
                'total_documents': documents,
                'database_status': 'operational'
            }
        })
    except Exception:
        logger.exception("Stats lookup failed")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load statistics'
        }), 500
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors (including malformed JSON)."""
    return jsonify({
        'status': 'error',
        'message': 'Bad request - malformed JSON or missing required fields'
    }), 400


@app.errorhandler(413)
def request_too_large(error):
    """Handle 413: JSON generate >2MB, upload/impor file >10MB (R-35)."""
    if (request.endpoint in ('import_modules', 'upload_buku')
            or request.path in ('/api/modules/import', '/api/buku/upload')):
        errors = [{'code': 'UPLOAD_TOO_LARGE',
                   'message': 'File melebihi 10MB.',
                   'stage': 'input'}]
    else:
        errors = [{'code': 'BODY_TOO_LARGE',
                   'message': 'Request body melebihi 2MB.',
                   'stage': 'input'}]
    return jsonify({'status': 'error', 'errors': errors}), 413


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found',
        'hint': 'GET / for available endpoints'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.exception("Unhandled internal error")
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500


if __name__ == '__main__':
    print("\n" + "="*60)
    print("AI RPP/RPM PEMBELAJARAN MENDALAM GENERATOR - WEB SERVER")
    print("="*60)
    print("\nStarting Flask server...")
    print(f"Database: {DB_PATH}")
    print(f"Debug mode: False (Production)")
    print(f"CORS: Enabled")
    print("\nServer available at: http://localhost:5000")
    print("\nAPI Endpoints:")
    print("  GET  /api/health - Server health check")
    print("  GET  /api/systems - List education systems")
    print("  GET  /api/subjects/<system> - Get subjects")
    print("  GET  /api/cp/<subject>/<phase> - Get CP")
    print("  POST /api/context/generate - Generate context")
    print("  POST /api/module/generate - Generate RPP/RPM")
    print("  GET  /api/module/download - Download RPP/RPM")
    print("  GET  /api/stats - Database statistics")
    print("\n" + "="*60)
    _recover_persisted_jobs(str(DB_PATH))

    # Run server
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=False,
        use_reloader=False
    )
