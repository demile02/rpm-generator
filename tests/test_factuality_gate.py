#!/usr/bin/env python3
"""Batch 2 §1: factuality & provenance gate (fail closed).

CP/provenance output harus cocok dengan baris aktif database; klaim
nomor regulasi dalam teks AI harus merujuk 9 dokumen kanonik terdaftar.
"""
import sys
from dataclasses import fields as dc_fields, replace as dc_replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (
    Module, TPEntry, KKTPEntry, ActivityEntry, FactualityValidator,
)
from curriculum_context import CurriculumContext

MEET_PARAMS = {
    'education_system': 'KEMENAG',
    'institution_type': 'MTs',
    'grade': 'MTs_7',
    'subject': 'Akidah Akhlak',
    'element': 'Pemahaman Konsep',
    'topic': 'Taubat',
    'requested_tp_count': 3,
    'jumlah_pertemuan': 2,
    'jp_per_pertemuan': 2,
}

ROWS_D = [
    (1, 'Pembuka', 15, 'TP-1', 'memahami'),
    (1, 'Inti', 35, 'TP-1', 'mengaplikasi'),
    (1, 'Inti', 30, 'TP-2', 'mengaplikasi'),
    (2, 'Pembuka', 15, 'TP-2', 'memahami'),
    (2, 'Inti', 35, 'TP-3', 'mengaplikasi'),
    (2, 'Penutup', 30, 'TP-3', 'merefleksi'),
]


def _act(name, duration, tp, exp, stage, meeting):
    return {'name': name, 'description': 'Deskripsi ' + name,
            'duration': duration, 'experience': exp, 'tp_linked': tp,
            'stage': stage, 'meeting': meeting}


@pytest.fixture
def pipeline(test_db):
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


def _generate(pipeline):
    from test_phase_c_module_generation import (
        fake_router_response, patch_pipeline_ai, mock_meeting_principles)

    def side_effect(prompt, system_instruction=None, **kwargs):
        if '"activities"' in prompt:
            return {'activities': [
                _act(f'A{i + 1}', dur, tp, exp, stage, meeting)
                for i, (meeting, stage, dur, tp, exp) in enumerate(ROWS_D)],
                'meeting_principles': mock_meeting_principles(2)}
        return fake_router_response(prompt, system_instruction, **kwargs)

    with patch_pipeline_ai(pipeline, side_effect):
        return pipeline.generate(dict(MEET_PARAMS))


def module_from_result(result):
    """Rebuild Module dataclass dari dict hasil (mirror PUT round-trip)."""
    d = dict(result['module'])
    d['curriculum_context'] = CurriculumContext.from_dict(
        d['curriculum_context'])
    tp_names = {f.name for f in dc_fields(TPEntry)}
    kk_names = {f.name for f in dc_fields(KKTPEntry)}
    act_names = {f.name for f in dc_fields(ActivityEntry)}
    d['learning_objectives'] = [
        TPEntry(**{k: t.get(k) for k in tp_names})
        for t in d.get('learning_objectives') or []]
    d['success_criteria'] = [
        KKTPEntry(**{k: k_.get(k) for k in kk_names})
        for k_ in d.get('success_criteria') or []]
    d['learning_activities'] = [
        ActivityEntry(**{k: a.get(k) for k in act_names})
        for a in d.get('learning_activities') or []]
    mod_names = {f.name for f in dc_fields(Module)}
    return Module(**{k: v for k, v in d.items() if k in mod_names})


class TestCpProvenanceGate:
    def test_faithful_output_passes(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        gate = FactualityValidator(pipeline.db_path)
        assert gate.validate(module_from_result(result)) == []

    def test_tampered_cp_text_rejected(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        cp = module.curriculum_context.cp
        module.curriculum_context.cp = dc_replace(
            cp, text=cp.text + ' (tambahan karangan)')
        errors = FactualityValidator(pipeline.db_path).validate_cp(module)
        assert any('CP_PROVENANCE_INVALID' in e for e in errors)

    def test_tampered_source_rejected(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        cp = module.curriculum_context.cp
        module.curriculum_context.cp = dc_replace(
            cp, source_document_id='DOC-PALSU-9999')
        errors = FactualityValidator(pipeline.db_path).validate_cp(module)
        assert any('CP_PROVENANCE_INVALID' in e for e in errors)

    def test_tampered_page_rejected(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        cp = module.curriculum_context.cp
        module.curriculum_context.cp = dc_replace(cp, source_page=9999)
        errors = FactualityValidator(pipeline.db_path).validate_cp(module)
        assert any('CP_PROVENANCE_INVALID' in e for e in errors)

    def test_wrong_system_context_rejected(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        module.curriculum_context.subject = 'Fisika Kuantum'
        errors = FactualityValidator(pipeline.db_path).validate_cp(module)
        assert any('CP_PROVENANCE_INVALID' in e for e in errors)

    def test_9941_outside_kemenag_rejected(self, pipeline):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        module.curriculum_context.education_system = 'KEMENDIKDASMEN'
        errors = FactualityValidator(pipeline.db_path).validate_cp(module)
        assert any('outside KEMENAG' in e for e in errors)

    def test_routing_invariants_in_data(self, test_db):
        """DB sendiri menjamin: 020 tidak dipakai non-PABP, 046 tidak
        dipakai mapel agama (distinction Batch 2 §1)."""
        import sqlite3
        conn = sqlite3.connect(str(test_db))
        try:
            bad020 = conn.execute(
                "SELECT COUNT(*) FROM learning_outcomes WHERE status='active'"
                " AND source_document_id LIKE '%020%'"
                " AND LOWER(subject) NOT LIKE '%agama%'").fetchone()[0]
            bad046 = conn.execute(
                "SELECT COUNT(*) FROM learning_outcomes WHERE status='active'"
                " AND source_document_id LIKE '%046%'"
                " AND LOWER(subject) LIKE '%agama%'").fetchone()[0]
        finally:
            conn.close()
        assert bad020 == 0
        assert bad046 == 0


class TestRegulatoryClaimsGate:
    def _module_with_claim(self, pipeline, claim):
        result = _generate(pipeline)
        assert result['status'] == 'success', result['errors']
        module = module_from_result(result)
        module.learning_activities[0].description += ' ' + claim
        return module

    def test_fabricated_regulation_rejected(self, pipeline):
        module = self._module_with_claim(
            pipeline, 'Sesuai PP No. 99 Tahun 2099 tentang khayalan.')
        errors = FactualityValidator(pipeline.db_path).validate_claims(module)
        assert any('REGULATORY_CLAIM_UNVERIFIED' in e for e in errors)

    def test_fabricated_code_rejected(self, pipeline):
        module = self._module_with_claim(
            pipeline, 'Lihat Kepdirjen Pendis No. 1234 Tahun 2030.')
        errors = FactualityValidator(pipeline.db_path).validate_claims(module)
        assert any('REGULATORY_CLAIM_UNVERIFIED' in e for e in errors)

    def test_canonical_citation_passes(self, pipeline):
        module = self._module_with_claim(
            pipeline, 'Dimensi Profil Lulusan merujuk Permendikdasmen '
                      'No. 10 Tahun 2025.')
        assert FactualityValidator(pipeline.db_path).validate_claims(
            module) == []

    def test_canonical_code_passes(self, pipeline):
        module = self._module_with_claim(
            pipeline, 'CP diambil dari 046/H/KR/2025 dan BKPDM 020/2026.')
        assert FactualityValidator(pipeline.db_path).validate_claims(
            module) == []

    def test_quran_reference_not_flagged(self, pipeline):
        module = self._module_with_claim(
            pipeline, 'Berdasarkan QS Az-Zumar ayat 53 dan hadis riwayat.')
        assert FactualityValidator(pipeline.db_path).validate_claims(
            module) == []

    def test_unregistered_real_regulation_fails_closed(self, pipeline):
        """Regulasi nyata di luar 9 dokumen kanonik tetap ditolak
        (tanpa provenance terdaftar = fail closed, sesuai §1)."""
        module = self._module_with_claim(
            pipeline, 'Sesuai UU No. 20 Tahun 2003 tentang Sisdiknas.')
        errors = FactualityValidator(pipeline.db_path).validate_claims(module)
        assert any('REGULATORY_CLAIM_UNVERIFIED' in e for e in errors)


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


class TestPutFactualityIntegration:
    def _stored(self, flask_client, api_pipeline):
        import json as _json
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        from module_store import ModuleStore
        ctx = flask_client.post('/api/context/generate', json={
            'education_system': 'KEMENAG', 'institution_type': 'MTs',
            'grade': 'MTs_7', 'subject': 'Akidah Akhlak', 'phase': 'D',
            'element': 'Pemahaman Konsep', 'topic': 'Taubat'})

        def side_effect(prompt, system_instruction=None, **kwargs):
            if '"activities"' in prompt:
                from test_phase_c_module_generation import (
                    mock_meeting_principles)
                return {'activities': [
                    _act(f'A{i + 1}', dur, tp, exp, stage, meeting)
                    for i, (meeting, stage, dur, tp, exp)
                    in enumerate(ROWS_D)],
                    'meeting_principles': mock_meeting_principles(2)}
            return fake_router_response(prompt, system_instruction, **kwargs)

        assert ctx.status_code == 200
        with patch_pipeline_ai(api_pipeline, side_effect):
            resp = flask_client.post('/api/module/generate', json={
                'education_system': 'KEMENAG', 'institution_type': 'MTs',
                'grade': 'MTs_7', 'subject': 'Akidah Akhlak',
                'element': 'Pemahaman Konsep', 'phase': 'D',
                'topic': 'Taubat',
                'jumlah_pertemuan': 2, 'jp_per_pertemuan': 2})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = _json.loads(resp.data)
        ModuleStore(api_pipeline.db_path).save(
            body['generation_id'], body['module'],
            body['module'].get('curriculum_context') or {})
        return body['generation_id'], body['module']

    def test_put_fabricated_claim_422(self, flask_client, api_pipeline):
        gid, module = self._stored(flask_client, api_pipeline)
        acts = [dict(a) for a in module['learning_activities']]
        acts[0]['description'] += ' Sesuai PP No. 99 Tahun 2099.'
        resp = flask_client.put(f'/api/module/{gid}',
                                json={'learning_activities': acts})
        assert resp.status_code == 422, resp.get_data(as_text=True)
        assert 'REGULATORY_CLAIM_UNVERIFIED' in resp.get_data(as_text=True)

    def test_put_canonical_claim_200(self, flask_client, api_pipeline):
        gid, module = self._stored(flask_client, api_pipeline)
        acts = [dict(a) for a in module['learning_activities']]
        acts[0]['description'] += (
            ' Merujuk Permendikdasmen No. 10 Tahun 2025.')
        resp = flask_client.put(f'/api/module/{gid}',
                                json={'learning_activities': acts})
        assert resp.status_code == 200, resp.get_data(as_text=True)
