#!/usr/bin/env python3
"""Batch 2 §4: AI reliability observability — metadata ringan
(response_chars/empty_flag/truncated_flag) tanpa raw prompt/response."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from nine_router_client import (
    NineRouterClient, NineRouterConfig, detect_truncated_response,
)
from module_store import GenerationLogStore


class TestTruncationDetector:
    def test_complete_json_not_truncated(self):
        assert detect_truncated_response('{"a": 1}') is False
        assert detect_truncated_response(
            '{"a": {"b": [1, 2]}, "c": "x"}') is False
        assert detect_truncated_response('[1, 2, 3]') is False
        assert detect_truncated_response(
            '{"a": "kutip \\"aman\\" dan unicode é"}') is False

    def test_empty_not_truncated(self):
        assert detect_truncated_response('') is False
        assert detect_truncated_response('   ') is False
        assert detect_truncated_response(None) is False

    def test_cut_mid_string_truncated(self):
        assert detect_truncated_response('{"a": "terpotong') is True
        assert detect_truncated_response('{"introduction": "Al-Qur') is True

    def test_unbalanced_braces_truncated(self):
        assert detect_truncated_response('{"a": 1, "b": {"c": 2}') is True
        assert detect_truncated_response('{"a": [1, 2') is True

    def test_trailing_comma_colon_truncated(self):
        assert detect_truncated_response('{"a": 1,') is True
        assert detect_truncated_response('{"a":') is True

    def test_extra_text_not_truncated(self):
        """Teks tambahan bukan potongan: flag terpisah (parse tetap
        gagal downstream sebagai format — klasifikasi jujur)."""
        assert detect_truncated_response(
            '{"a": 1} catatan tambahan') is False


class TestClientResponseMeta:
    def _client_with(self, envelope=None, exc=None):
        client = NineRouterClient(NineRouterConfig(
            base_url='http://127.0.0.1:9', backoff_base=0))
        if exc is not None:
            def boom(*a, **k):
                raise exc
            client._make_request = boom
        else:
            client._make_request = lambda *a, **k: envelope
        return client

    @staticmethod
    def _envelope(content):
        return {'choices': [{'message': {'content': content}}]}

    def test_truncated_meta(self):
        client = self._client_with(self._envelope('{"a": "terpotong'))
        try:
            client.generate_text('p', temperature=0.1, max_tokens=2000)
        except Exception:
            pass
        meta = client.last_response_meta
        assert meta['response_chars'] == len('{"a": "terpotong')
        assert meta['empty'] is False
        assert meta['truncated'] is True
        assert meta['output_tokens'] is None

    def test_empty_meta(self):
        client = self._client_with(self._envelope(''))
        with pytest.raises(Exception):
            client.generate_text('p', temperature=0.1, max_tokens=2000)
        assert client.last_response_meta == {
            'response_chars': 0, 'empty': True, 'truncated': False,
            'output_tokens': None}

    def test_transport_meta(self):
        from nine_router_client import NetworkError
        client = self._client_with(exc=NetworkError('down'))
        with pytest.raises(Exception):
            client.generate_text('p', temperature=0.1, max_tokens=2000)
        assert client.last_response_meta['empty'] is True
        assert client.last_response_meta['response_chars'] == 0

    def test_complete_meta(self):
        client = self._client_with(self._envelope('{"a": 1}'))
        assert client.generate_text('p') == '{"a": 1}'
        assert client.last_response_meta == {
            'response_chars': 8, 'empty': False, 'truncated': False,
            'output_tokens': None}

    def test_usage_tokens_recorded_when_provided(self):
        envelope = self._envelope('{"a": 1}')
        envelope['usage'] = {'prompt_tokens': 100, 'completion_tokens': 42,
                             'total_tokens': 142}
        client = self._client_with(envelope)
        assert client.generate_text('p') == '{"a": 1}'
        assert client.last_response_meta['output_tokens'] == 42


class TestLogSchemaMigration:
    def test_old_table_migrated_additively(self, tmp_path):
        db = str(tmp_path / 'old.db')
        conn = sqlite3.connect(db)
        conn.execute(
            'CREATE TABLE generation_logs (id INTEGER PRIMARY KEY '
            'AUTOINCREMENT, generation_id VARCHAR(64) NOT NULL, '
            'stage VARCHAR(32) NOT NULL, attempt INTEGER NOT NULL DEFAULT 1, '
            'prompt_version VARCHAR(16), prompt_hash VARCHAR(64), '
            'model VARCHAR(64), provider VARCHAR(32), '
            'status VARCHAR(16) NOT NULL, error_category VARCHAR(16), '
            'error TEXT, duration_ms REAL, '
            'created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        conn.execute(
            "INSERT INTO generation_logs (generation_id, stage, status) "
            "VALUES ('g-old', 'tp', 'success')")
        conn.commit()
        conn.close()
        store = GenerationLogStore(db)
        cols = {r[1] for r in sqlite3.connect(db).execute(
            'PRAGMA table_info(generation_logs)').fetchall()}
        assert {'response_chars', 'empty_flag', 'truncated_flag'} <= cols
        rows = store.fetch('g-old')
        assert len(rows) == 1
        assert rows[0]['response_chars'] is None

    def test_roundtrip_new_fields(self, test_db):
        store = GenerationLogStore(str(test_db))
        rec = {'generation_id': 'g-obs', 'stage': 'materials', 'attempt': 1,
               'prompt_version': '1.0', 'prompt_hash': 'h', 'model': 'rpm',
               'provider': '9router', 'status': 'failed',
               'error_category': 'format', 'error': 'truncated',
               'duration_ms': 12.5, 'response_chars': 3596,
               'empty_flag': 0, 'truncated_flag': 1}
        assert store.save_records([rec]) == 1
        rows = store.fetch('g-obs')
        assert rows[0]['response_chars'] == 3596
        assert rows[0]['empty_flag'] == 0
        assert rows[0]['truncated_flag'] == 1


@pytest.fixture
def pipeline(test_db):
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


class TestAttemptRecordsCarryMeta:
    def test_records_have_meta_keys_and_no_raw(self, pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        params = {'education_system': 'KEMENAG', 'institution_type': 'MTs',
                  'grade': 'MTs_7', 'subject': 'Akidah Akhlak',
                  'element': 'Pemahaman Konsep', 'topic': 'Taubat',
                  'requested_tp_count': 3}
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(params)
        assert result['status'] == 'success', result['errors']
        records = result['generation_log']
        assert records
        blob = json.dumps(records, ensure_ascii=False, default=str)
        assert 'Pengenalan materi taubat' not in blob
        for record in records:
            assert 'response_chars' in record
            assert 'empty_flag' in record
            assert 'truncated_flag' in record
            assert 'output_tokens' in record
            assert 'is_retry' in record
