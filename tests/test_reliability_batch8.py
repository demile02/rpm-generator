#!/usr/bin/env python3
"""Batch 8: AI reliability & token efficiency.

- Detector false-negative fix (bukti: real TP gagal) + guard C1/C2/UNKNOWN.
- _extract_json: hanya normalisasi deterministik yang terbukti.
- Feedback recovery berbeda per kategori.
- reliability_summary + kolom observability baru.
- Retry bound tetap 3; validasi tidak dilonggarkan.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import ModuleGenerationPipeline
from module_store import reliability_summary
from nine_router_client import (
    _extract_json, ValidationError, detect_truncated_response,
)


@pytest.fixture
def validator():
    from module_generation_pipeline import RuleValidator
    return RuleValidator()


class TestDetectorUserKKO:
    """Detektor ikut daftar KKO normatif user (87 kata C1-C6).

    + 'menganalisis' (C4) dan 'menerapkan' (C3): dipakai AI/test tapi
    tidak ada di daftar user.
    """

    def test_c1_membaca(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa membaca teks bacaan.') == 'C1'

    def test_c1_melafalkan(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa melafalkan bacaan dengan tajwid yang benar.') == 'C1'

    def test_c1_membaca_nyaring_ikut_membaca(self, validator):
        # 'membaca nyaring' tidak ada di daftar; cocok 'membaca' (C1).
        assert validator._extract_cognitive_level(
            'Peserta didik mampu membaca nyaring kata-kata berpola kombinasi '
            'huruf dalam teks narasi sederhana dengan lafal yang tepat.') == 'C1'

    def test_c2_menampilkan(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa menampilkan contoh perilaku terpuji.') == 'C2'

    def test_c2_membandingkan(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa membandingkan dua pendapat ulama.') == 'C2'

    def test_c3_menerapkan(self, validator):
        assert validator._extract_cognitive_level(
            'Menerapkan konsep taubat dalam kehidupan') == 'C3'

    def test_c3_melaksanakan(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa melaksanakan salat berjamaah dengan tertib.') == 'C3'

    def test_c4_menganalisis(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa menganalisis kasus taubat') == 'C4'

    def test_c4_memecahkan(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa memecahkan masalah waris dengan dalil.') == 'C4'

    def test_c5_mengevaluasi(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa mengevaluasi praktik taubat') == 'C5'

    def test_c6_merancang(self, validator):
        assert validator._extract_cognitive_level(
            'Siswa merancang program taubat') == 'C6'

    def test_validate_accepts_c3_plus(self, validator):
        for text in (
                'Menerapkan konsep taubat dalam kehidupan.',
                'Siswa melaksanakan salat berjamaah.',
                'Menganalisis perilaku taubat.',
                'Mengevaluasi kejujuran dalam taubat.',
                'Merancang program perbaikan diri.'):
            ok, level, _err = validator.validate_tp_cognitive_level(text)
            assert ok, text
            assert level in ('C3', 'C4', 'C5', 'C6')


class TestDetectorStillFailClosed:
    """Arah berbahaya (false positive C1/C2) tetap ditolak."""

    def test_menjelaskan_stays_c2(self, validator):
        ok, level, _err = validator.validate_tp_cognitive_level(
            'Peserta didik mampu menjelaskan konsep keautentikan Al-Quran.')
        assert (ok, level) == (False, 'C2')

    def test_memahami_unknown(self, validator):
        # 'memahami' tidak ada di daftar KKO user -> UNKNOWN (ditolak).
        ok, level, _err = validator.validate_tp_cognitive_level(
            'Siswa memahami tata cara taubat nasuha.')
        assert (ok, level) == (False, 'UNKNOWN')

    def test_menyebutkan_stays_c1(self, validator):
        ok, level, _err = validator.validate_tp_cognitive_level(
            'Menyebutkan pengertian taubat.')
        assert (ok, level) == (False, 'C1')

    def test_vague_presenting_stays_unknown(self, validator):
        ok, level, _err = validator.validate_tp_cognitive_level(
            'Peserta didik mampu menyajikan refleksi kritis tentang materi.')
        assert ok is False
        assert level == 'UNKNOWN'

    def test_bare_membaca_is_c1(self, validator):
        """'membaca' ada di daftar user sebagai C1."""
        ok, level, _err = validator.validate_tp_cognitive_level(
            'Siswa membaca teks bacaan.')
        assert (ok, level) == (False, 'C1')


class TestExtractJsonDeterministic:
    """Hanya normalisasi terbukti: plain, fence, single-wrap. Sisanya gagal."""

    def test_plain(self):
        assert _extract_json('{"a": 1}') == {'a': 1}

    def test_fenced(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {'a': 1}

    def test_single_prose_wrap(self):
        assert _extract_json(
            'Berikut hasilnya: {"a": 1} semoga membantu') == {'a': 1}

    def test_multiple_objects_rejected(self):
        with pytest.raises(ValidationError):
            _extract_json('{"a": 1}{"b": 2}')

    def test_broken_rejected(self):
        with pytest.raises(ValidationError):
            _extract_json('{"a": 1,')

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            _extract_json('   ')

    def test_no_json_rejected(self):
        with pytest.raises(ValidationError):
            _extract_json('halo dunia')


class TestRecoveryFeedbackDifferentiated:
    def test_categories_differ(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        t = P._recovery_feedback('transport', 'tp')
        f = P._recovery_feedback('format', 'tp')
        s = P._recovery_feedback('semantic', 'tp')
        assert len({t, f, s}) == 3

    def test_tp_stage_extra_present(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        assert 'C3' in P._recovery_feedback('semantic', 'tp')

    def test_retry_bound_unchanged(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        assert P.AI_STAGE_MAX_ATTEMPTS == 3

    def test_categorize_mapping(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        assert P._categorize_ai_error(
            ValueError('TP-1: Could not determine cognitive level')) == 'semantic'
        assert P._categorize_ai_error(
            ValueError('AI response is not valid JSON: Extra data')) == 'format'
        assert P._categorize_ai_error(
            ValueError('Empty content in response message')) == 'transport'


class TestReliabilitySummary:
    def _rec(self, stage, gid, attempt, status, **kw):
        rec = {'generation_id': gid, 'stage': stage, 'attempt': attempt,
               'prompt_version': '1.0', 'prompt_hash': 'h', 'model': 'rpm',
               'provider': '9router', 'status': status,
               'error_category': kw.get('error_category'),
               'error': kw.get('error'), 'duration_ms': 1.0,
               'response_chars': kw.get('response_chars'),
               'empty_flag': kw.get('empty_flag'),
               'truncated_flag': kw.get('truncated_flag'),
               'output_tokens': kw.get('output_tokens'),
               'is_retry': 1 if attempt > 1 else 0}
        return rec

    def test_rates_and_recovery(self):
        recs = [
            self._rec('tp', 'g1', 1, 'success'),
            self._rec('tp', 'g2', 1, 'failed', error_category='semantic',
                      error='TP-1: Could not determine cognitive level'),
            self._rec('tp', 'g2', 2, 'success'),
            self._rec('materials', 'g1', 1, 'failed',
                      error_category='format', truncated_flag=1,
                      response_chars=7000, output_tokens=1800),
            self._rec('materials', 'g1', 2, 'failed',
                      error_category='format'),
            self._rec('materials', 'g1', 3, 'failed',
                      error_category='format'),
        ]
        out = reliability_summary(recs)
        tp = out['tp']
        assert tp['generations'] == 2
        assert tp['attempts'] == 3
        assert tp['first_attempt_success_rate'] == 0.5
        assert tp['final_success_rate'] == 1.0
        assert tp['avg_attempts_per_success'] == 1.5
        assert tp['recovered'] == 1
        assert tp['fail_categories'] == {'semantic': 1}
        mat = out['materials']
        assert mat['final_success_rate'] == 0.0
        assert mat['truncated_count'] == 1
        assert mat['output_tokens_total'] == 1800
        assert mat['fail_categories'] == {'format': 3}

    def test_empty_records(self):
        assert reliability_summary([]) == {}
        assert reliability_summary(None) == {}

    def test_no_raw_content_in_summary(self):
        import json
        recs = [self._rec('tp', 'g1', 1, 'success')]
        blob = json.dumps(reliability_summary(recs))
        assert 'prompt' not in blob.replace('prompt_version', '')


class TestPromptVersionsUntouched:
    """§7: stage 100% (kktp/assessments) tak tersentuh; tp tak berubah."""

    def test_tp_kktp_assessments_still_10(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        assert P.PROMPT_VERSIONS['tp'] == '1.0'
        assert P.PROMPT_VERSIONS['kktp'] == '1.0'
        assert P.PROMPT_VERSIONS['assessments'] == '1.1'
