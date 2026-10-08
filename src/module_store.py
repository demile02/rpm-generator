"""Persistent storage for generated modules (additive, minimal).

One table, ``generated_modules``: the final editable module JSON plus the
authoritative generation context JSON, keyed by generation_id. The context
is stored so later edits can always be re-validated against the original
authoritative CP / provenance / phase / subject — the client is never
trusted for protected values.

The table is created lazily on the SAME database (no schema redesign, no
separate file). Test suites point the app/pipeline at a temp DB copy, so
production data is never mutated by tests.
"""
import dataclasses
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses (and containers holding them) into
    plain JSON-safe structures.

    Flask's jsonify serializes dataclasses fine, but ``json.dumps`` in the
    store does not — a raw ``json.dumps(..., default=str)`` of a dict holding
    dataclass entries silently stores their repr strings, corrupting the row.
    Everything persisted through ModuleStore goes through this helper.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generated_modules (
  generation_id VARCHAR(64) PRIMARY KEY,
  module_json   TEXT NOT NULL,
  context_json  TEXT NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# Audit trail AI generation: satu baris per stage-attempt (+ satu baris
# 'final' per generation). Hanya metadata — tanpa teks prompt/response,
# tanpa API key/header/secret. Tabel additif; tidak menyentuh tabel
# kurikulum maupun generated_modules.
#
# Batch 2: response_chars / empty_flag / truncated_flag membedakan
# empty vs malformed vs truncated vs transport tanpa menyimpan raw
# output (lihat detect_truncated_response di nine_router_client).
_SCHEMA_LOGS = """
CREATE TABLE IF NOT EXISTS generation_logs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  generation_id  VARCHAR(64) NOT NULL,
  stage          VARCHAR(32) NOT NULL,
  attempt        INTEGER NOT NULL DEFAULT 1,
  prompt_version VARCHAR(16),
  prompt_hash    VARCHAR(64),
  model          VARCHAR(64),
  provider       VARCHAR(32),
  status         VARCHAR(16) NOT NULL,
  error_category VARCHAR(16),
  error          TEXT,
  duration_ms    REAL,
  response_chars INTEGER,
  empty_flag     INTEGER,
  truncated_flag INTEGER,
  output_tokens  INTEGER,
  is_retry       INTEGER,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_generation_logs_gen
  ON generation_logs(generation_id);
"""

# Kolom observability Batch 2/8 (ditambah via migrasi additif bila tabel
# lama belum memilikinya — tidak ada hapus/ubah kolom existing).
_LOG_OBSERVABILITY_COLUMNS = (
    ('response_chars', 'INTEGER'),
    ('empty_flag', 'INTEGER'),
    ('truncated_flag', 'INTEGER'),
    ('output_tokens', 'INTEGER'),
    ('is_retry', 'INTEGER'),
)


class ModuleStore:
    """SQLite-backed store for final (validated) module JSON."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            # R-38: flag arsip per RPM (0 = aktif, 1 = arsip). Kolom baru
            # via ALTER additif agar DB lama tetap jalan tanpa migrasi.
            cols = {r[1] for r in
                    conn.execute('PRAGMA table_info(generated_modules)')}
            if 'archived' not in cols:
                conn.execute('ALTER TABLE generated_modules '
                             'ADD COLUMN archived INTEGER NOT NULL '
                             'DEFAULT 0')
            if 'archived_at' not in cols:
                conn.execute('ALTER TABLE generated_modules '
                             'ADD COLUMN archived_at TIMESTAMP')
            # KKO normatif user (87 kata): seed baru via UPSERT agar DB
            # lama (4 contoh/level) ikut terganti saat app boot.
            conn.executemany(
                'INSERT INTO cognitive_operators '
                '(level, level_name, order_number, examples, description) '
                'VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(level) DO UPDATE SET '
                'level_name=excluded.level_name, '
                'order_number=excluded.order_number, '
                'examples=excluded.examples, '
                'description=excluded.description',
                [
                    ('C1', 'Remember', 1,
                     'menemukenali, mengingat kembali, membaca, menyebutkan, '
                     'melafalkan, menuliskan, menghafal, menyusun daftar, '
                     'menggarisbawahi, menjodohkan, memilih, memberi definisi, '
                     'menyatakan',
                     'Mengingat kembali informasi yang telah dipelajari'),
                    ('C2', 'Understand', 2,
                     'menjelaskan, mengartikan, menginterpretasikan, '
                     'menceritakan, menampilkan, memberi contoh, merangkum, '
                     'menyimpulkan, membandingkan, mengklasifikasikan, '
                     'menunjukkan, menguraikan, membedakan, menyadur, '
                     'meramalkan, memperkirakan, menerangkan, menggantikan',
                     'Memahami makna informasi yang telah dipelajari'),
                    ('C3', 'Apply', 3,
                     'melaksanakan, mengimplementasikan, menggunakan, '
                     'mengonsepkan, menentukan, memproseskan, '
                     'mendemonstrasikan, menghitung, menghubungkan, '
                     'melakukan, membuktikan, menghasilkan, memperagakan, '
                     'melengkapi, menyesuaikan, menemukan',
                     'Menerapkan informasi dalam situasi baru'),
                    ('C4', 'Analyze', 4,
                     'mendiferensiasikan, mengorganisasikan, mengatribusikan, '
                     'mendiagnosis, memerinci, menelaah, mendeteksi, '
                     'mengaitkan, memecahkan, memisahkan, menyeleksi, '
                     'mempertentangkan, membagi',
                     'Menguraikan informasi menjadi bagian-bagian'),
                    ('C5', 'Evaluate', 5,
                     'mengecek, mengkritik, mempertahankan, memvalidasi, '
                     'mendukung, memproyeksikan, memperbandingkan, menilai, '
                     'mengevaluasi, memberi saran, memberi argumentasi, '
                     'menafsirkan, merekomendasi',
                     'Membuat penilaian berdasarkan kriteria'),
                    ('C6', 'Create', 6,
                     'membangun, merencanakan, memproduksi, mengkombinasikan, '
                     'merancang, merekonstruksi, membuat, menciptakan, '
                     'mengabstraksi, mengkategorikan, mengarang, mendesain, '
                     'menyusun kembali, merangkaikan',
                     'Menciptakan sesuatu yang baru'),
                ])
            conn.commit()
        finally:
            conn.close()

    def save(self, generation_id: str, module_dict: Dict, context_dict: Dict) -> None:
        """Insert or replace the stored module + authoritative context."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO generated_modules (generation_id, module_json, context_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(generation_id) DO UPDATE SET
                  module_json = excluded.module_json,
                  context_json = excluded.context_json,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    generation_id,
                    json.dumps(to_jsonable(module_dict), ensure_ascii=False),
                    json.dumps(to_jsonable(context_dict), ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, generation_id: str) -> Optional[Dict]:
        """Return {'module': dict, 'context': dict, 'updated_at': str} or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT module_json, context_json, updated_at FROM generated_modules WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {
            'module': json.loads(row['module_json']),
            'context': json.loads(row['context_json']),
            'updated_at': row['updated_at'],
        }

    def get_updated_at(self, generation_id: str) -> Optional[str]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT updated_at FROM generated_modules WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return row['updated_at']

    def delete(self, generation_id: str) -> bool:
        """Hapus satu RPM dari riwayat. True bila ada baris terhapus."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM generated_modules WHERE generation_id = ?",
                (generation_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def set_archived(self, generation_id: str,
                     archived: bool) -> bool:
        """Tandai arsip (True) / kembalikan aktif (False).

        R-38: baris + versi + log tetap utuh; hanya flag. Modul arsip
        tetap bisa dibuka/edit/regen/export. Return False bila ID
        tidak ada.
        """
        conn = self._connect()
        try:
            if archived:
                cur = conn.execute(
                    "UPDATE generated_modules SET archived = 1, "
                    "archived_at = CURRENT_TIMESTAMP "
                    "WHERE generation_id = ?",
                    (generation_id,),
                )
            else:
                cur = conn.execute(
                    "UPDATE generated_modules SET archived = 0, "
                    "archived_at = NULL WHERE generation_id = ?",
                    (generation_id,),
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def find_active_by_title(self, title: str, exclude_id: str = '',
                             subject: str = '', grade: str = '',
                             phase: str = '') -> list:
        """Cari RPM AKTIF (archived=0) berjudul sama persis.

        R-39: dipakai upload agar yang lama otomatis terarsip dan tidak
        nabrak. Banding judul case-insensitive setelah strip; bila
        subject/grade/phase diberikan harus cocok juga.
        """
        key = (title or '').strip().lower()
        if not key:
            return []
        conn = self._connect()
        try:
            try:
                rows = conn.execute(
                    "SELECT generation_id, module_json FROM "
                    "generated_modules WHERE archived = 0"
                ).fetchall()
            except Exception:
                # Kolom belum ada (DB sangat lama): anggap semua aktif.
                rows = conn.execute(
                    "SELECT generation_id, module_json FROM "
                    "generated_modules"
                ).fetchall()
        finally:
            conn.close()
        out = []
        for row in rows:
            gid = row['generation_id']
            if gid == exclude_id:
                continue
            try:
                module = json.loads(row['module_json'])
            except (ValueError, TypeError):
                continue
            if not isinstance(module, dict):
                continue
            if (module.get('title') or '').strip().lower() != key:
                continue
            if subject and (module.get('subject') or '') != subject:
                continue
            if grade and (module.get('grade') or '') != grade:
                continue
            if phase and (module.get('phase') or '') != phase:
                continue
            out.append(gid)
        return out

    def list_summaries(self) -> List[Dict]:
        """Read-only dashboard listing, newest first.

        Only rows in generated_modules appear here; that table is
        written solely on successful generation/save, so failed
        generations never enter history. No schema change.
        """
        conn = self._connect()
        try:
            try:
                rows = conn.execute(
                    "SELECT generation_id, module_json, updated_at, "
                    "archived, archived_at FROM generated_modules "
                    "ORDER BY updated_at DESC, rowid DESC"
                ).fetchall()
                has_archive_cols = True
            except Exception:
                rows = conn.execute(
                    "SELECT generation_id, module_json, updated_at "
                    "FROM generated_modules ORDER BY updated_at DESC, "
                    "rowid DESC"
                ).fetchall()
                has_archive_cols = False
        finally:
            conn.close()
        summaries = []
        for row in rows:
            try:
                module = json.loads(row['module_json'])
            except (ValueError, TypeError):
                continue
            if not isinstance(module, dict):
                continue
            validation = module.get('validation_results') or {}
            final = validation.get('final') or {}
            try:
                archived = bool(row['archived']) if has_archive_cols \
                    else False
            except (IndexError, KeyError):
                archived = False
            try:
                archived_at = row['archived_at'] \
                    if has_archive_cols else None
            except (IndexError, KeyError):
                archived_at = None
            summaries.append({
                'generation_id': row['generation_id'],
                'title': module.get('title') or '',
                'subject': module.get('subject') or '',
                'grade': module.get('grade') or '',
                'phase': module.get('phase') or '',
                'updated_at': row['updated_at'],
                'passed': final.get('passed') is True,
                'origin': module.get('origin') or 'generate',
                'archived': archived,
                'archived_at': archived_at,
            })
        return summaries


# Batch 5: versioning draft/edit/regen. Satu baris per version; version
# lama immutable (hanya INSERT, tidak ada UPDATE/DELETE dari endpoint).
# generated_modules tetap menjadi baseline v1 implisit untuk baris lama.
_SCHEMA_VERSIONS = """
CREATE TABLE IF NOT EXISTS module_versions (
  generation_id    VARCHAR(64) NOT NULL,
  version_no       INTEGER NOT NULL,
  parent_version_no INTEGER,
  status           VARCHAR(16) NOT NULL,
  alignment_status VARCHAR(16),
  changed_sections TEXT,
  warnings         TEXT,
  module_json      TEXT NOT NULL,
  validation_json  TEXT,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (generation_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_module_versions_gen
  ON module_versions(generation_id);
"""

# Status version yang diizinkan (Batch 5 §11).
VERSION_STATUSES = ('draft', 'validated', 'finalized')
ALIGNMENT_STATUSES = ('Aligned', 'Needs review')


class VersionStore:
    """Penyimpanan version draft/edit/regen (additive, immutable history).

    Tidak menyimpan API key, raw prompt, atau raw AI response — hanya
    payload module final per version + metadata status. Berbagi database
    dengan ModuleStore (tidak ada database terpisah).
    """

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_VERSIONS)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _encode(row: sqlite3.Row) -> Dict:
        return {
            'generation_id': row['generation_id'],
            'version_no': row['version_no'],
            'parent_version_no': row['parent_version_no'],
            'status': row['status'],
            'alignment_status': row['alignment_status'],
            'changed_sections': json.loads(row['changed_sections'] or '[]'),
            'warnings': json.loads(row['warnings'] or '[]'),
            'module': json.loads(row['module_json']),
            'validation': json.loads(row['validation_json'] or '{}'),
            'created_at': row['created_at'],
        }

    def history(self, generation_id: str) -> List[Dict]:
        """Semua version terurut menaik (tanpa payload module)."""
        self._ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT generation_id, version_no, parent_version_no, '
                'status, alignment_status, changed_sections, warnings, '
                "'{}' AS module_json, '{}' AS validation_json, created_at "
                'FROM module_versions WHERE generation_id = ? '
                'ORDER BY version_no',
                (generation_id,)).fetchall()
        finally:
            conn.close()
        return [self._encode(r) for r in rows]

    def get(self, generation_id: str, version_no: int) -> Optional[Dict]:
        """Satu version lengkap (+ payload module)."""
        self._ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT * FROM module_versions WHERE generation_id = ? '
                'AND version_no = ?', (generation_id, version_no)).fetchone()
        finally:
            conn.close()
        return self._encode(row) if row is not None else None

    def latest(self, generation_id: str) -> Optional[Dict]:
        """Version tertinggi (+ payload module)."""
        self._ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT * FROM module_versions WHERE generation_id = ? '
                'ORDER BY version_no DESC LIMIT 1',
                (generation_id,)).fetchone()
        finally:
            conn.close()
        return self._encode(row) if row is not None else None

    def delete_one(self, generation_id: str, version_no: int) -> bool:
        """Hapus satu baris version. True bila ada baris terhapus.

        Versi terakhir modul TIDAK boleh dihapus (modul tanpa versi
        = rusak): pemanggil menolak lebih dulu, ini pengaman lapis dua.
        """
        self._ensure_schema()
        conn = self._connect()
        try:
            cur = conn.execute(
                'SELECT COUNT(*) FROM module_versions '
                'WHERE generation_id = ?', (generation_id,)).fetchone()
            if (cur[0] or 0) <= 1:
                return False
            cur = conn.execute(
                'DELETE FROM module_versions WHERE generation_id = ? '
                'AND version_no = ?', (generation_id, version_no))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_all(self, generation_id: str) -> int:
        """Hapus seluruh version milik satu RPM. Kembalikan jumlah baris."""
        self._ensure_schema()
        conn = self._connect()
        try:
            cur = conn.execute(
                'DELETE FROM module_versions WHERE generation_id = ?',
                (generation_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def save_new(self, generation_id: str, expected_latest: int,
                 parent_version_no: int, status: str, module_dict: Dict,
                 validation_dict: Dict, alignment_status: Optional[str],
                 changed_sections: List[str],
                 warnings: List[str]) -> Dict:
        """INSERT version baru dengan optimistic concurrency: gagal
        (StaleVersionError) bila latest saat ini != expected_latest.
        Tidak pernah overwrite version lama."""
        if status not in VERSION_STATUSES:
            raise ValueError(f"Invalid version status {status!r}")
        self._ensure_schema()
        conn = self._connect()
        try:
            cur = conn.execute(
                'SELECT COALESCE(MAX(version_no), 0) FROM module_versions '
                'WHERE generation_id = ?', (generation_id,))
            current = cur.fetchone()[0]
            if current != expected_latest:
                raise StaleVersionError(
                    f"Version {expected_latest} sudah kedaluwarsa; "
                    f"versi terbaru adalah v{current}. Muat ulang sebelum "
                    f"menyimpan.")
            version_no = current + 1
            conn.execute(
                'INSERT INTO module_versions (generation_id, version_no, '
                'parent_version_no, status, alignment_status, '
                'changed_sections, warnings, module_json, validation_json) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (generation_id, version_no, parent_version_no, status,
                 alignment_status,
                 json.dumps(changed_sections or [], ensure_ascii=False),
                 json.dumps(warnings or [], ensure_ascii=False),
                 json.dumps(to_jsonable(module_dict), ensure_ascii=False),
                 json.dumps(to_jsonable(validation_dict or {}),
                            ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()
        saved = self.get(generation_id, version_no)
        assert saved is not None
        return saved


class StaleVersionError(Exception):
    """Optimistic concurrency: base version bukan latest (HTTP 409)."""


def reliability_summary(records: list) -> Dict:
    """Agregat metrik reliability dari generation-log records (Batch 8 §6).

    Murni komputasi metadata — tanpa raw prompt/response. Mengembalikan
    per-stage: generations, attempts, first_attempt_success_rate,
    final_success_rate, avg_attempts_per_success, recovered,
    fail_categories, truncated_count, output_tokens_total.
    """
    per_gen: Dict = {}
    for r in records or []:
        key = (r.get('stage') or '?', r.get('generation_id'))
        bucket = per_gen.setdefault(key, [])
        bucket.append(r)
    summary: Dict[str, Dict] = {}
    for (stage, _gid), rows in per_gen.items():
        entry = summary.setdefault(stage, {
            'generations': 0, 'attempts': 0, 'first_ok': 0,
            'final_ok': 0, 'success_attempt_sum': 0,
            'fail_categories': {}, 'truncated_count': 0,
            'output_tokens_total': 0,
        })
        entry['generations'] += 1
        entry['attempts'] += len(rows)
        first = min(rows, key=lambda r: (r.get('attempt') or 1))
        if first.get('status') == 'success':
            entry['first_ok'] += 1
        successes = [r for r in rows if r.get('status') == 'success']
        if successes:
            entry['final_ok'] += 1
            entry['success_attempt_sum'] += min(
                r.get('attempt') or 1 for r in successes)
        for r in rows:
            if r.get('status') != 'success':
                code = r.get('error_category') or 'unknown'
                entry['fail_categories'][code] = \
                    entry['fail_categories'].get(code, 0) + 1
            if r.get('truncated_flag'):
                entry['truncated_count'] += 1
            tokens = r.get('output_tokens')
            if isinstance(tokens, int):
                entry['output_tokens_total'] += tokens
    def _ordered(stage, gid):
        return sorted(per_gen[(stage, gid)],
                      key=lambda r: (r.get('attempt') or 1))

    def _was_recovered(stage, gid):
        rows = _ordered(stage, gid)
        return bool(rows) and rows[0].get('status') != 'success' \
            and any(r.get('status') == 'success' for r in rows)

    result = {}
    for stage, e in summary.items():
        n = e['generations']
        result[stage] = {
            'generations': n,
            'attempts': e['attempts'],
            'first_attempt_success_rate': (e['first_ok'] / n if n else 0.0),
            'final_success_rate': (e['final_ok'] / n if n else 0.0),
            'avg_attempts_per_success': (
                e['success_attempt_sum'] / e['final_ok']
                if e['final_ok'] else 0.0),
            'recovered': sum(
                1 for (st, gid) in per_gen
                if st == stage and _was_recovered(st, gid)),
            'fail_categories': e['fail_categories'],
            'truncated_count': e['truncated_count'],
            'output_tokens_total': e['output_tokens_total'],
        }
    return result


class GenerationLogStore:
    """SQLite-backed audit trail AI generation (additive, minimal).

    Satu baris per stage-attempt + satu baris ``stage='final'`` per
    generation. Kolom metadata saja: tanpa teks prompt/response (yang
    tersimpan hanya hash prompt), tanpa API key/header/secret.
    Persistence best-effort: kegagalan tulis TIDAK boleh menggagalkan
    generation (pemanggil membungkus try/except).
    """

    _COLUMNS = ('generation_id', 'stage', 'attempt', 'prompt_version',
                'prompt_hash', 'model', 'provider', 'status',
                'error_category', 'error', 'duration_ms',
                'response_chars', 'empty_flag', 'truncated_flag',
                'output_tokens', 'is_retry')

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_LOGS)
            existing = {
                row[1] for row in
                conn.execute('PRAGMA table_info(generation_logs)').fetchall()
            }
            for name, ddl in _LOG_OBSERVABILITY_COLUMNS:
                if name not in existing:
                    conn.execute(
                        f'ALTER TABLE generation_logs ADD COLUMN {name} {ddl}')
            conn.commit()
        finally:
            conn.close()

    def save_records(self, records: list) -> int:
        """Simpan banyak record sekaligus. Return jumlah baris."""
        if not records:
            return 0
        self._ensure_schema()
        columns = ', '.join(self._COLUMNS)
        placeholders = ', '.join(['?'] * len(self._COLUMNS))
        conn = self._connect()
        try:
            conn.executemany(
                f'INSERT INTO generation_logs ({columns}) '
                f'VALUES ({placeholders})',
                [tuple(r.get(c) for c in self._COLUMNS) for r in records],
            )
            conn.commit()
            return len(records)
        finally:
            conn.close()

    def fetch(self, generation_id: str) -> list:
        """Seluruh record satu generation terurut waktu (dict)."""
        self._ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT generation_id, stage, attempt, prompt_version, '
                'prompt_hash, model, provider, status, error_category, '
                'error, duration_ms, response_chars, empty_flag, '
                'truncated_flag, output_tokens, is_retry, created_at '
                'FROM generation_logs '
                'WHERE generation_id = ? ORDER BY id',
                (generation_id,),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def delete(self, generation_id: str) -> int:
        """Hapus seluruh baris audit satu generation_id.

        Hanya generation_logs; modul di generated_modules + versinya
        TIDAK ikut (keputusan: hapus log = hanya baris audit).
        Return jumlah baris terhapus (0 bila tak ada).
        """
        self._ensure_schema()
        conn = self._connect()
        try:
            cur = conn.execute(
                'DELETE FROM generation_logs WHERE generation_id = ?',
                (generation_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def delete_many(self, generation_ids: list) -> int:
        """Hapus audit banyak generation_id sekaligus. Return total baris."""
        ids = [g for g in (generation_ids or []) if g]
        if not ids:
            return 0
        total = 0
        for gid in ids:
            total += self.delete(gid)
        return total

    def list_generations(self, limit: int = 100) -> list:
        """Ringkasan satu baris per generation_id, terbaru dulu.

        Agregasi read-only dari generation_logs: status keseluruhan
        (sukses bila ada record final sukses, gagal bila ada record
        gagal tanpa sukses, berjalan bila belum ada keduanya),
        daftar stage yang dilewati, kategori error, dan rentang waktu.
        """
        self._ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT generation_id, stage, attempt, status, '
                'error_category, created_at '
                'FROM generation_logs ORDER BY id'
            ).fetchall()
        finally:
            conn.close()
        per_gen: Dict[str, list] = {}
        for r in rows:
            per_gen.setdefault(r['generation_id'], []).append(dict(r))
        items = []
        for gid, recs in per_gen.items():
            stages = []
            for r in recs:
                if r['stage'] not in stages:
                    stages.append(r['stage'])
            failed = [r for r in recs if r.get('status') != 'success']
            has_success = any(
                r.get('stage') == 'final' and r.get('status') == 'success'
                for r in recs)
            has_any_success = any(
                r.get('status') == 'success' for r in recs)
            if has_success:
                status = 'success'
            elif failed and not has_any_success:
                status = 'failed'
            elif failed:
                status = 'partial'
            else:
                status = 'running'
            errors = sorted({
                r.get('error_category') or 'unknown' for r in failed})
            items.append({
                'generation_id': gid,
                'status': status,
                'stages': stages,
                'attempts': len(recs),
                'error_categories': errors,
                'started_at': recs[0].get('created_at'),
                'updated_at': recs[-1].get('created_at'),
            })
        items.sort(key=lambda m: m.get('updated_at') or '', reverse=True)
        return items[:max(int(limit or 0), 0) or 100]


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'
