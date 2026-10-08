#!/usr/bin/env python3
"""
Unit tests for 9Router client with mocked HTTP responses
"""

import pytest
import json
from unittest.mock import patch, MagicMock
import requests

from nine_router_client import (
    NineRouterClient, NineRouterConfig, NineRouterError,
    AuthenticationError, TimeoutError, RateLimitError,
    ServerError, ValidationError
)


class TestNineRouterConfig:
    """Test configuration loading."""

    @pytest.fixture(autouse=True)
    def _tanpa_dotenv_lokal(self, tmp_path, monkeypatch):
        """Netralkan .env repo agar tes hermetik.

        `_load_dotenv` sudah no-op di bawah pytest kecuali path
        eksplisit; fixture ini sabuk-pengaman bila guard berubah.
        """
        import nine_router_client as nrc
        monkeypatch.setattr(nrc, '_DOTENV_PATH',
                            str(tmp_path / '.env.tidak-ada'))

    def test_config_default_values(self):
        """Config should have sensible defaults. Timeout 120s: real `rpm`
        calls with large structured JSON legitimately run longer than 30s
        (observed in production smoke tests)."""
        config = NineRouterConfig()
        assert config.base_url == "http://localhost:20128"
        assert config.combo == "rpm"
        assert config.timeout == 120
        assert config.max_retries == 2
    
    def test_config_from_environment(self):
        """Config should load from environment variables."""
        with patch.dict('os.environ', {
            'NINE_ROUTER_API_KEY': 'test-key-123',
            'NINE_ROUTER_BASE_URL': 'http://test:9000',
            'NINE_ROUTER_COMBO': 'automation',
            'NINE_ROUTER_TIMEOUT': '60',
            'NINE_ROUTER_MAX_RETRIES': '3'
        }):
            config = NineRouterConfig.from_environment()
            assert config.api_key == 'test-key-123'
            assert config.base_url == 'http://test:9000'
            assert config.combo == 'automation'
            assert config.timeout == 60
            assert config.max_retries == 3
    
    def test_config_environment_defaults(self):
        """Config should use defaults when env vars not set."""
        with patch.dict('os.environ', {}, clear=True):
            config = NineRouterConfig.from_environment()
            assert config.api_key is None
            assert config.base_url == "http://localhost:20128"
            assert config.combo == "rpm"

    def test_dotenv_file_loads_key(self, tmp_path, monkeypatch):
        """File .env proyek dibaca bila variabel belum di-set (terisolasi)."""
        import nine_router_client as nrc
        env_file = tmp_path / '.env'
        env_file.write_text('NINE_ROUTER_API_KEY=kunci-dotenv-uji\n',
                            encoding='utf-8')
        monkeypatch.setattr(nrc, '_DOTENV_PATH', str(env_file))
        with patch.dict('os.environ', {}, clear=True):
            config = NineRouterConfig.from_environment()
            assert config.api_key == 'kunci-dotenv-uji'

    def test_dotenv_example_documents_keys(self):
        """Contoh .env mendokumentasikan semua kunci yang didukung."""
        import pathlib
        example = (pathlib.Path(__file__).resolve().parents[1] /
                   '.env.example')
        assert example.exists(), '.env.example wajib ada'
        text = example.read_text(encoding='utf-8')
        for key in ('NINE_ROUTER_API_KEY', 'NINE_ROUTER_BASE_URL',
                    'NINE_ROUTER_COMBO', 'NINE_ROUTER_TIMEOUT',
                    'NINE_ROUTER_MAX_RETRIES', 'NINE_ROUTER_BACKOFF_BASE'):
            assert key in text, key


class TestNineRouterClient:
    """Test NineRouter client."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return NineRouterConfig(
            base_url="http://localhost:20128",
            api_key="test-key",
            combo="rpm",
            timeout=10,
            max_retries=1
        )
    
    @pytest.fixture
    def client(self, config):
        """Create client with test config."""
        with patch.object(NineRouterClient, 'health_check', return_value=True):
            return NineRouterClient(config)
    
    def test_client_initialization(self, config):
        """Client should initialize with config."""
        with patch.object(NineRouterClient, 'health_check', return_value=True):
            client = NineRouterClient(config)
            assert client.config == config
    
    def test_headers_with_api_key(self, client):
        """Headers should include Authorization if API key present."""
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"
    
    def test_headers_without_api_key(self, config):
        """Headers should work without API key."""
        config.api_key = None
        with patch.object(NineRouterClient, 'health_check', return_value=True):
            client = NineRouterClient(config)
            headers = client._get_headers()
            assert "Authorization" not in headers
    
    def test_health_check_success(self, client):
        """Health check should return True on 200."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_get.return_value = mock_response
            
            result = client.health_check()
            assert result is True
            mock_get.assert_called_once()
    
    def test_health_check_failure(self, client):
        """Health check should return False on error."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")
            result = client.health_check()
            assert result is False
    
    @patch('requests.post')
    def test_generate_text_success(self, mock_post, client):
        """Generate text should return content from API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Generated text"}
            }]
        }
        mock_post.return_value = mock_response
        
        result = client.generate_text("test prompt")
        assert result == "Generated text"
    
    @patch('requests.post')
    def test_generate_text_with_system_instruction(self, mock_post, client):
        """Generate text should include system instruction."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_post.return_value = mock_response
        
        client.generate_text("user prompt", system_instruction="system msg")
        
        call_args = mock_post.call_args
        data = call_args[1]['json']
        messages = data['messages']
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == 'system msg'
        assert messages[1]['role'] == 'user'
    
    @patch('requests.post')
    def test_generate_json_success(self, mock_post, client):
        """Generate JSON should parse and return dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": '{"key": "value"}'}
            }]
        }
        mock_post.return_value = mock_response
        
        result = client.generate_json("generate json")
        assert result == {"key": "value"}
    
    @patch('requests.post')
    def test_generate_json_invalid_json(self, mock_post, client):
        """Generate JSON should raise ValidationError on invalid JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "not valid json"}
            }]
        }
        mock_post.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.generate_json("generate json")
    
    @patch('requests.post')
    def test_authentication_error_401(self, mock_post, client):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_post.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_rate_limit_error_429(self, mock_post, client):
        """Should raise RateLimitError on 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response
        
        with pytest.raises(RateLimitError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_server_error_500(self, mock_post, client):
        """Should raise ServerError on 500."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        with pytest.raises(ServerError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_timeout_error(self, mock_post, client):
        """Should raise TimeoutError on timeout."""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        with pytest.raises(TimeoutError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_retry_on_timeout(self, mock_post, client):
        """Should retry on timeout up to max_retries."""
        client.config.max_retries = 2
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "success"}}]
        }
        
        # First call times out, second succeeds
        mock_post.side_effect = [
            requests.exceptions.Timeout(),
            mock_response
        ]
        
        result = client.generate_text("prompt")
        assert result == "success"
        assert mock_post.call_count == 2
    
    @patch('requests.post')
    def test_no_retry_on_auth_error(self, mock_post, client):
        """Should not retry on authentication error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        with pytest.raises(AuthenticationError):
            client.generate_text("prompt")
        
        # Should only try once (no retries on auth error)
        assert mock_post.call_count == 1
    
    @patch('requests.post')
    def test_response_missing_choices(self, mock_post, client):
        """Should raise ValidationError if response missing choices."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "invalid"}
        mock_post.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_response_empty_choices(self, mock_post, client):
        """Should raise ValidationError if choices is empty."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        mock_post.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_response_missing_message(self, mock_post, client):
        """Should raise ValidationError if choice missing message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"data": "invalid"}]}
        mock_post.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.generate_text("prompt")
    
    @patch('requests.post')
    def test_response_empty_content(self, mock_post, client):
        """Should raise ValidationError if content is empty."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        mock_post.return_value = mock_response
        
        with pytest.raises(ValidationError):
            client.generate_text("prompt")



# ============================================================================
# RELIABILITY HARDENING TESTS (malformed-JSON bounded retry + extraction)
# ============================================================================

def _ok_response(content):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"choices": [{"message": {"content": content}}]}
    return m


@pytest.mark.api
class TestJSONReliability:
    """Bounded retry for transient malformed/empty model JSON; honest
    failure after the last attempt; no semantic drift on retries."""

    def _client(self, max_retries=2):
        config = NineRouterConfig(
            base_url="http://localhost:20128", api_key="k", combo="rpm",
            timeout=10, max_retries=max_retries, backoff_base=0.0,
        )
        return NineRouterClient(config)

    @patch('requests.post')
    def test_malformed_json_retries_then_succeeds(self, mock_post):
        """The real-E2E finding: 'Expecting , delimiter' on attempt 1 must
        not fail the generation — bounded retry returns the valid JSON."""
        client = self._client()
        bad = '{"tp_list": ["a", "b"'  # truncated -> malformed
        mock_post.side_effect = [
            _ok_response(bad),
            _ok_response('{"tp_list": ["a", "b"]}'),
        ]
        result = client.generate_json("hasilkan TP")
        assert result == {"tp_list": ["a", "b"]}
        assert mock_post.call_count == 2

    @patch('requests.post')
    def test_persistent_malformed_json_fails_honestly(self, mock_post):
        """After max_retries+1 attempts the client raises — no fake success,
        no unbounded retrying."""
        client = self._client(max_retries=2)
        mock_post.return_value = _ok_response('{"broken": [1, 2')
        with pytest.raises(ValidationError):
            client.generate_json("prompt")
        assert mock_post.call_count == 3  # 1 initial + 2 retries, bounded

    @patch('requests.post')
    def test_recovery_note_added_once_and_base_prompt_preserved(self, mock_post):
        """Retry uses the SAME task prompt + a single format-recovery note;
        no semantic drift, no duplicated notes."""
        client = self._client()
        mock_post.side_effect = [
            _ok_response("garbage not json"),
            _ok_response('{"ok": true}'),
        ]
        client.generate_json("Tugas utama: hasilkan JSON taubat")
        payloads = [c[1]['json'] for c in mock_post.call_args_list]
        first_user = payloads[0]['messages'][-1]['content']
        second_user = payloads[1]['messages'][-1]['content']
        BASE = "Tugas utama: hasilkan JSON taubat"
        MARK = "PERHATIAN (percobaan ulang)"
        # generate_text(json_format=True) adds its own format instruction at
        # the end; the retry must keep the SAME task body with exactly one
        # recovery note inserted - no semantic drift, no duplicated notes.
        assert first_user.startswith(BASE)
        assert MARK not in first_user
        assert second_user.startswith(BASE)
        assert second_user.count(MARK) == 1
        assert second_user.split(MARK)[0].rstrip() == BASE  # only the note
        # Same messages count (system untouched) and same model/combo.
        assert len(payloads[0]['messages']) == len(payloads[1]['messages'])
        assert payloads[0]['model'] == payloads[1]['model'] == 'rpm'

    @patch('requests.post')
    def test_fence_wrapped_json_extracted_without_retry(self, mock_post):
        """```json fences are legitimate formatting — extracted directly,
        no retry burned."""
        client = self._client()
        fenced = '```json\n{"criteria": ["a"]}\n```'
        mock_post.return_value = _ok_response(fenced)
        result = client.generate_json("p")
        assert result == {"criteria": ["a"]}
        assert mock_post.call_count == 1

    @patch('requests.post')
    def test_commentary_wrapped_json_extracted(self, mock_post):
        client = self._client()
        wrapped = 'Berikut hasilnya:\n{"topic": "Taubat"}\nSemoga membantu.'
        mock_post.return_value = _ok_response(wrapped)
        assert client.generate_json("p") == {"topic": "Taubat"}

    @patch('requests.post')
    def test_array_json_extracted(self, mock_post):
        client = self._client()
        mock_post.return_value = _ok_response('```json\n["a", "b"]\n```')
        assert client.generate_json("p") == ["a", "b"]

    @patch('requests.post')
    def test_empty_content_retried_then_succeeds(self, mock_post):
        client = self._client()
        mock_post.side_effect = [
            _ok_response(""),
            _ok_response('{"filled": true}'),
        ]
        assert client.generate_json("p") == {"filled": True}
        assert mock_post.call_count == 2

    @patch('requests.post')
    def test_broken_envelope_retried_then_succeeds(self, mock_post):
        """Malformed OpenAI envelope (missing choices) is a provider
        transient — retried, then honest failure if persistent."""
        client = self._client()
        bad_env = MagicMock()
        bad_env.status_code = 200
        bad_env.json.return_value = {"data": "invalid"}
        mock_post.side_effect = [bad_env, _ok_response('{"ok": 1}')]
        assert client.generate_json("p") == {"ok": 1}
        assert mock_post.call_count == 2

    @patch('requests.post')
    def test_non_json_content_never_repaired(self, mock_post):
        """Prose that contains no JSON must fail honestly (no regex repair
        inventing data)."""
        client = self._client()
        mock_post.return_value = _ok_response("saya tidak bisa menjawab.")
        with pytest.raises(ValidationError):
            client.generate_json("p")

    @patch('requests.post')
    def test_auth_error_not_retried_from_json_loop(self, mock_post):
        client = self._client()
        resp = MagicMock()
        resp.status_code = 401
        mock_post.return_value = resp
        with pytest.raises(AuthenticationError):
            client.generate_json("p")
        assert mock_post.call_count == 1


@pytest.mark.api
class TestHTTPRetryHardening:
    """Backoff schedule, Retry-After, connection errors."""

    def _client(self, max_retries=2):
        config = NineRouterConfig(
            base_url="http://localhost:20128", api_key="k", combo="rpm",
            timeout=10, max_retries=max_retries, backoff_base=1.0,
        )
        return NineRouterClient(config)

    @patch('nine_router_client.time.sleep')
    @patch('requests.post')
    def test_backoff_delays_grow_and_are_capped(self, mock_post, mock_sleep):
        client = self._client()
        mock_post.return_value = _ok_response('{"a": 1}')
        client.generate_json("p")  # first-attempt success: no sleep at all
        mock_sleep.assert_not_called()

        # Force two HTTP-level failures then success; capture delays.
        mock_post.side_effect = [
            requests.exceptions.Timeout(),          # attempt 1 -> 1s
            requests.exceptions.ConnectionError(),  # attempt 2 -> 3s
            _ok_response('{"a": 1}'),
        ]
        assert client.generate_json("p") == {"a": 1}
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert delays == [1.0, 3.0]

    @patch('nine_router_client.time.sleep')
    @patch('requests.post')
    def test_retry_after_429_honored_with_cap(self, mock_post, mock_sleep):
        client = self._client()
        limited = MagicMock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "2"}
        ok = _ok_response('{"a": 1}')
        mock_post.side_effect = [limited, ok]
        assert client.generate_json("p") == {"a": 1}
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert delays and delays[0] == 2.0  # Retry-After honored

        # Absurd Retry-After is capped at MAX_BACKOFF_SECONDS.
        limited2 = MagicMock()
        limited2.status_code = 429
        limited2.headers = {"Retry-After": "600"}
        mock_post.side_effect = [limited2, ok]
        client.generate_json("p")
        delays2 = [c[0][0] for c in mock_sleep.call_args_list]
        assert delays2[-1] == 10.0

    @patch('requests.post')
    def test_connection_error_classified_and_retried(self, mock_post):
        client = self._client()
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("reset"),
            _ok_response('{"a": 1}'),
        ]
        # generate_json (ValidationError-only loop) still surfaces honest
        # failure for persistent NetworkError; here first retry succeeds.
        assert client.generate_json("p") == {"a": 1}
        assert mock_post.call_count == 2

    @patch('requests.post')
    def test_persistent_connection_error_raises_networkerror(self, mock_post):
        client = self._client()
        mock_post.side_effect = requests.exceptions.ConnectionError("reset")
        with pytest.raises(Exception) as ei:
            client.generate_text("p")
        assert not isinstance(ei.value, requests.exceptions.RequestException)

    @patch('requests.post')
    def test_4xx_invalid_request_not_retried(self, mock_post):
        client = self._client()
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"error": {"message": "bad request"}}
        mock_post.return_value = resp
        with pytest.raises(NineRouterError):
            client.generate_text("p")
        assert mock_post.call_count == 1
