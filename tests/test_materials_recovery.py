#!/usr/bin/env python3
"""Batch 2 §5: materials reliability — deteksi terpotong deterministik +
bounded recovery yang sudah ada. Tidak ada retry tanpa batas, tidak ada
fake success, tidak ada pelonggaran validasi."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import ModuleGenerationPipeline

PARAMS = {
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
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


def _router_for(pipeline, materials_impl):
    from test_phase_c_module_generation import fake_router_response

    def side_effect(prompt, system_instruction=None, **kwargs):
        if '"activities"' in prompt:
            from test_phase_c_module_generation import (
                mock_meeting_principles)
            return {'activities': [
                _act(f'A{i + 1}', dur, tp, exp, stage, meeting)
                for i, (meeting, stage, dur, tp, exp) in enumerate(ROWS_D)],
                'meeting_principles': mock_meeting_principles(2)}
        if 'essential_understanding' in prompt or '"introduction"' in prompt:
            return materials_impl(prompt)
        return fake_router_response(prompt, system_instruction, **kwargs)

    return patch.object(
        pipeline.ai_client, 'generate_json', side_effect=side_effect)


def _good_materials(prompt):
    from test_phase_c_module_generation import (
        fake_router_response as real_fake)
    return real_fake(prompt)


class TestMaterialsTruncatedRecovery:
    def test_truncated_then_valid_recovers(self, pipeline):
        """Respons terpotong terdeteksi -> recovery bounded -> sukses."""
        from nine_router_client import ValidationError
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                pipeline.ai_client.last_response_meta = {
                    'response_chars': 3596, 'empty': False, 'truncated': True}
                raise ValidationError(
                    'AI response is not valid JSON: Unterminated string')
            pipeline.ai_client.last_response_meta = {
                'response_chars': 1200, 'empty': False, 'truncated': False}
            return _good_materials(prompt)

        with _router_for(pipeline, flaky):
            result = pipeline.generate(dict(PARAMS))
        assert result['status'] == 'success', result['errors']
        mat_records = [r for r in result['generation_log']
                       if r['stage'] == 'materials']
        assert [r['status'] for r in mat_records] == ['failed', 'success']
        assert mat_records[0]['error_category'] == 'format'
        assert 'truncated' in (mat_records[0]['error'] or '').lower()
        assert mat_records[0]['truncated_flag'] == 1

    def test_persistently_truncated_fails_bounded(self, pipeline):
        """Selalu terpotong -> gagal jujur tepat 3 attempt (bounded)."""
        from nine_router_client import ValidationError

        def always_cut(prompt):
            pipeline.ai_client.last_response_meta = {
                'response_chars': 3596, 'empty': False, 'truncated': True}
            raise ValidationError(
                'AI response is not valid JSON: Unterminated string')

        with _router_for(pipeline, always_cut):
            result = pipeline.generate(dict(PARAMS))
        assert result['status'] == 'failed'
        assert result['module'] is None
        mat_records = [r for r in result['generation_log']
                       if r['stage'] == 'materials']
        assert len(mat_records) == 3
        assert all(r['status'] == 'failed' for r in mat_records)
        assert all('truncated' in (r['error'] or '').lower()
                   for r in mat_records)

    def test_retry_bound_unchanged(self):
        assert ModuleGenerationPipeline.AI_STAGE_MAX_ATTEMPTS == 3
