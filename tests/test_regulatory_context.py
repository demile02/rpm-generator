#!/usr/bin/env python3
"""Konsultasi regulasi CP di pipeline RPM.

Memastikan fragmen dokumen yang MENGUBAH/menerangkan CP (BKPDM
020/2026 untuk KEMENDIKDASMEN; KMA 1503/2025 untuk KEMENAG) benar-benar
terkonsultasi saat generate: seleksi deterministik dari DB dengan
provenance utuh, injeksi ke prompt AI, tersimpan di module JSON, dan
dilindungi dari edit klien (PUT).
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (  # noqa: E402
    ModuleGenerationPipeline,
    build_regulatory_context,
    format_regulatory_context_for_prompt,
)
from test_phase_c_module_generation import (  # noqa: E402
    VALID_PARAMS,
    fake_router_response,
    patch_pipeline_ai,
)

BKPDM_DOC = 'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026'
KMA_DOC = 'DOC-REG-KEMENAG-1503-2025'

# Klausul kunci yang WAJIB terkonsultasi per dokumen (klausul yang
# mengubah/mendefinisikan CP) — dijamin lewat slot anchor
# (KEY_CLAUSE_ANCHORS), query terpisah dari scoring kata-kunci.
KEY_CLAUSES = {
    BKPDM_DOC: [
        'Mengubah ketentuan mengenai Capaian Pembelajaran',
        'Pendidikan Agama dan Budi Pekerti',
    ],
    KMA_DOC: [
        # Definisi CP (p19) — bukan hanya fragmen kaya kata kunci.
        'Capaian Pembelajaran adalah',
        'Pembelajaran Mendalam',
    ],
}


# ---------------------------------------------------------------------------
# 1. Seleksi deterministik + provenance
# ---------------------------------------------------------------------------

class TestBuildRegulatoryContext:
    def test_kemenag_gets_kma_1503(self, test_db):
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        assert rc['enabled'] is True
        assert [s['document_id'] for s in rc['sources']] == [KMA_DOC]
        frags = rc['sources'][0]['fragments']
        assert frags, 'KMA 1503 harus punya fragmen terpilih'
        for f in frags:
            assert f['source_document_id'] == KMA_DOC
            assert isinstance(f['page'], int) and f['page'] >= 1
            assert f['fragment_id']
            assert len(f['text']) >= 80  # fragmen substantif, bukan remah

    def test_kemendikdasmen_gets_bkpdm_020(self, test_db):
        rc = build_regulatory_context(
            'KEMENDIKDASMEN', 'Pendidikan Agama dan Budi Pekerti', 'D',
            db_path=str(test_db))
        assert rc['enabled'] is True
        assert [s['document_id'] for s in rc['sources']] == [BKPDM_DOC]
        # Amandemen CP PAI harus muncul di fragmen terpilih.
        texts = ' '.join(f['text'].lower()
                         for f in rc['sources'][0]['fragments'])
        assert 'capaian pembelajaran' in texts

    def test_key_clauses_locked_for_both_systems(self, test_db):
        """Pengunci klausul kunci BKPDM & KMA: fragmen yang memuat
        klausul yang MENGUBAH/MENDFINISIKAN CP harus terpilih — klausul
        ini tidak boleh terpotong LIMIT kandidat maupun kalah skor dari
        fragmen lain (slot anchor, query terpisah)."""
        for system, subject, doc_id in [
            ('KEMENDIKDASMEN', 'Pendidikan Agama dan Budi Pekerti', BKPDM_DOC),
            ('KEMENAG', 'Akidah Akhlak', KMA_DOC),
        ]:
            rc = build_regulatory_context(
                system, subject, 'D', db_path=str(test_db))
            assert rc['enabled'] is True
            src = rc['sources'][0]
            assert src['document_id'] == doc_id
            all_text = ' '.join(f['text'] for f in src['fragments'])
            for clause in KEY_CLAUSES[doc_id]:
                assert clause in all_text, (
                    f'Klausul kunci "{clause}" hilang dari konteks '
                    f'regulasi {doc_id}')

    def test_key_clause_fragment_comes_first(self, test_db):
        """Anchor diberi posisi awal (deterministik) sehingga klausul
        inti selalu bagian dari prompt, bahkan bila budget lain ketat."""
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        first = rc['sources'][0]['fragments'][0]['text'].lower()
        assert first.startswith('capaian pembelajaran adalah')

    def test_school_and_madrasah_never_mixed(self, test_db):
        """KBC-style isolation: dokumen amandemen School tidak boleh
        bocor ke madrasah dan sebaliknya."""
        rc_kemenag = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        rc_kemdik = build_regulatory_context(
            'KEMENDIKDASMEN', 'Pendidikan Agama dan Budi Pekerti', 'D',
            db_path=str(test_db))
        assert BKPDM_DOC not in [s['document_id'] for s in rc_kemenag['sources']]
        assert KMA_DOC not in [s['document_id'] for s in rc_kemdik['sources']]

    def test_unknown_system_disabled(self, test_db):
        rc = build_regulatory_context('', 'X', 'A', db_path=str(test_db))
        assert rc['enabled'] is False
        assert rc['sources'] == []

    def test_missing_db_degrades_not_fatal(self, tmp_path):
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D',
            db_path=str(tmp_path / 'nope.db'))
        assert rc['enabled'] is False
        assert rc['sources'] == []
        assert 'error' in rc  # kegagalan dicatat, tidak dipendam

    def test_deterministic_selection(self, test_db):
        """Dua pemanggilan dengan input sama hasil identik."""
        a = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        b = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_fragment_budget_respected(self, test_db):
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db),
            max_fragments_per_doc=2, max_chars_per_doc=600)
        frags = rc['sources'][0]['fragments']
        assert len(frags) <= 2
        assert sum(len(f['text']) for f in frags) <= 600


# ---------------------------------------------------------------------------
# 2. Format prompt: provenance eksplisit, siap dikonsultasikan
# ---------------------------------------------------------------------------

class TestPromptFormatting:
    def test_provenance_visible_in_prompt_block(self, test_db):
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D', db_path=str(test_db))
        block = format_regulatory_context_for_prompt(rc)
        assert 'KONTEKS REGULASI' in block
        assert KMA_DOC in block
        assert '· hal.' in block
        # Instruksi anti-pengubahan ikut terbawa.
        assert 'DILARANG mengubah CP' in block

    def test_empty_context_gives_empty_block(self):
        assert format_regulatory_context_for_prompt(None) == ''
        assert format_regulatory_context_for_prompt(
            {'enabled': False, 'sources': []}) == ''


# ---------------------------------------------------------------------------
# 3. Integrasi pipeline end-to-end (fake 9Router, DB nyata)
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    @pytest.fixture
    def pipeline(self, test_db):
        return ModuleGenerationPipeline(db_path=str(test_db))

    def test_full_generation_carries_consultation(self, pipeline):
        """Generate penuh: field regulatory_consultation terisi, prompt
        TP & outline menerima blok konteks regulasi, JSON module
        menampilkannya di master_outline.design."""
        seen_prompts = []
        real_fake = fake_router_response

        def spy(prompt, system_instruction=None, **kw):
            seen_prompts.append(prompt)
            return real_fake(prompt, system_instruction, **kw)

        with patch_pipeline_ai(pipeline, spy):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success', result.get('errors')
        module = result['module']

        rc = module['regulatory_consultation']
        assert rc['enabled'] is True
        assert rc['sources'][0]['document_id'] == KMA_DOC
        assert rc['sources'][0]['fragments']

        # Provenance tampil di master outline (section C DESAIN).
        mo_rc = module['master_outline']['design']['regulatory_consultation']
        assert mo_rc['enabled'] is True
        assert mo_rc['sources'][0]['fragments'][0]['fragment_id']

        # Prompt TP dan prompt outline sama-sama menerima blok.
        tp_prompt = next(p for p in seen_prompts if 'tp_list' in p)
        assert 'KONTEKS REGULASI' in tp_prompt
        assert KMA_DOC in tp_prompt
        outline_prompt = next(
            p for p in seen_prompts if 'triggering_questions' in p)
        assert 'KONTEKS REGULASI' in outline_prompt

    def test_put_rejects_client_edit_of_regulatory_consultation(self, pipeline,
                                                                test_db):
        """regulatory_consultation adalah provenance deterministik —
        klien tidak boleh mengubahnya lewat PUT."""
        from module_store import ModuleStore
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'

        store = ModuleStore(str(test_db))
        store.save(result['generation_id'], result['module'],
                   result['module'].get('curriculum_context'))

        stored = store.load(result['generation_id'])
        assert stored and stored.get('module')

        tampered = json.loads(json.dumps(stored['module']))
        tampered['regulatory_consultation'] = {
            'enabled': True,
            'sources': [{
                'document_id': 'FAKE-DOC',
                'document_title': 'Dokumen karangan',
                'role': 'x',
                'fragments': [{'fragment_id': 'f1',
                               'source_document_id': 'FAKE-DOC',
                               'page': 1, 'text': 'karangan'}],
            }],
            'note': 'fake',
        }

        # Bandingkan perilaku protected-key seperti app.py PUT: key yang
        # berbeda dari stored wajib terdeteksi.
        from app import PUT_PROTECTED_TOP_KEYS
        incoming = tampered
        touched = [k for k in PUT_PROTECTED_TOP_KEYS
                   if k in incoming
                   and incoming.get(k) != stored['module'].get(k)]
        assert 'regulatory_consultation' in touched


# ---------------------------------------------------------------------------
# 4. Fallback ketika DB tidak berisi dokumen amandemen (edge)
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_subject_without_keyword_match_still_fills(self, test_db):
        """Mapel di luar map PAI tetap dapat fragmen via kata-kunci
        dasar (capaian pembelajaran, kurikulum, ...)."""
        rc = build_regulatory_context(
            'KEMENAG', 'Matematika', 'D', db_path=str(test_db))
        # Tidak wajib ada, tapi bila ada harus valid strukturnya.
        if rc['enabled']:
            for s in rc['sources']:
                assert s['fragments']

    def test_pipeline_helper_uses_params(self, test_db):
        pipeline = ModuleGenerationPipeline(db_path=str(test_db))
        rc = pipeline.build_regulatory_context_for_generate(
            dict(VALID_PARAMS))
        assert rc['enabled'] is True
        assert rc['sources'][0]['document_id'] == KMA_DOC
