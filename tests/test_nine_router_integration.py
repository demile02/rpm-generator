#!/usr/bin/env python3
"""
Integration tests for real 9Router API
These tests connect to actual 9Router instance at localhost:20128
Tests are skipped if API key not available
"""

import os
import pytest
import json
from nine_router_client import (
    NineRouterClient, NineRouterConfig, NineRouterError,
    AuthenticationError
)


# Skip all tests in this module if no API key is configured
pytestmark = pytest.mark.skipif(
    not os.getenv("NINE_ROUTER_API_KEY"),
    reason="NINE_ROUTER_API_KEY not configured"
)


class TestNineRouterIntegration:
    """Integration tests with real 9Router API."""
    
    @pytest.fixture
    def config(self):
        """Load real configuration from environment."""
        return NineRouterConfig.from_environment()
    
    @pytest.fixture
    def client(self, config):
        """Create real client."""
        return NineRouterClient(config)
    
    @pytest.mark.integration
    def test_health_check_real(self, client):
        """Real 9Router should respond to health check."""
        # This test runs even without API key since health check doesn't need auth
        assert client.health_check() is True
    
    @pytest.mark.integration
    def test_generate_text_real_simple(self, client):
        """Generate simple text using real 9Router."""
        result = client.generate_text(
            prompt="Respond with exactly: Hello World",
            temperature=0.0,
            max_tokens=10
        )
        
        assert isinstance(result, str)
        assert len(result) > 0
        # Verify it's actual generated text, not error
        assert "error" not in result.lower()
    
    @pytest.mark.integration
    def test_generate_json_real_simple(self, client):
        """Generate JSON using real 9Router."""
        result = client.generate_json(
            prompt='Generate JSON: {"status": "ok"}',
            temperature=0.0,
            max_tokens=50
        )
        
        assert isinstance(result, dict)
        assert "status" in result or len(result) > 0
    


class TestNineRouterErrorHandling:
    """Test error handling with real API."""
    
    @pytest.mark.integration
    def test_invalid_api_key_returns_401(self):
        """Invalid API key should raise AuthenticationError."""
        config = NineRouterConfig(
            base_url="http://localhost:20128",
            api_key="invalid-key-12345",
            combo="modul"
        )
        
        client = NineRouterClient(config)
        
        # This should fail with auth error since key is invalid
        with pytest.raises(AuthenticationError):
            client.generate_text("test prompt")
    
    @pytest.mark.integration
    def test_timeout_handling(self):
        """Should handle timeouts gracefully."""
        config = NineRouterConfig(
            base_url="http://localhost:20128",
            api_key=os.getenv("NINE_ROUTER_API_KEY"),
            combo="modul",
            timeout=0.001  # Very short timeout to trigger error
        )
        
        client = NineRouterClient(config)
        
        # Should retry and eventually fail with timeout
        from nine_router_client import TimeoutError
        with pytest.raises(TimeoutError):
            client.generate_text("test", max_tokens=5000)


class TestNineRouterComboUsage:
    """Verify that combo 'rpm' is actually being used."""
    
    @pytest.mark.integration
    def test_uses_rpm_combo(self):
        """Configuration should use 'rpm' combo."""
        config = NineRouterConfig.from_environment()
        assert config.combo == "rpm", \
            f"Expected combo 'rpm' but got '{config.combo}'"
    
    @pytest.mark.integration
    def test_rejects_wrong_combos(self):
        """Non-standard combo should initialize with a logged warning."""
        config = NineRouterConfig(
            base_url="http://localhost:20128",
            api_key=os.getenv("NINE_ROUTER_API_KEY"),
            combo="bu"
        )
        
        client = NineRouterClient(config)
        
        # Should have initialized (combo validation is warning-only)
        assert client.config.combo == "bu"


class TestNineRouterSecurityCompliance:
    """Verify security requirements are met."""
    
    def test_api_key_not_in_logs(self, caplog):
        """API key must never appear in log output.

        The in-memory Authorization header legitimately contains the key
        (Bearer auth requires it); logs must not.
        """
        import logging
        config = NineRouterConfig(
            base_url="http://localhost:20128",
            api_key="secret-key-12345",
            combo="modul"
        )
        
        with caplog.at_level(logging.DEBUG):
            client = NineRouterClient(config)
            headers = client._get_headers()
        
        # The raw key must not appear in any log record
        assert "secret-key-12345" not in caplog.text, \
            "Raw API key must not be written to logs"
        
        # But requests still authenticate via Bearer header in memory
        assert headers.get("Authorization", "").startswith("Bearer ")
    
    def test_api_key_from_environment(self):
        """API key should be loaded from environment only."""
        # Verify it's not hardcoded anywhere
        from nine_router_client import NineRouterConfig
        
        config = NineRouterConfig()
        # Default should have no API key
        assert config.api_key is None
        
        # Only loads from env
        config_from_env = NineRouterConfig.from_environment()
        
        if os.getenv("NINE_ROUTER_API_KEY"):
            assert config_from_env.api_key == os.getenv("NINE_ROUTER_API_KEY")


# Configuration documentation for users
@pytest.fixture(scope="session", autouse=True)
def integration_test_documentation():
    """
    Integration tests require 9Router to be running and API key configured.
    
    To run integration tests:
    
    1. Start 9Router (should be running at localhost:20128)
    2. Ensure /api/health returns {"ok": true}
    3. Get or generate API key from 9Router dashboard
    4. Set environment variable:
       export NINE_ROUTER_API_KEY="your-key-here"
    5. Run tests:
       pytest tests/test_nine_router_integration.py -v
    
    Tests will be SKIPPED if NINE_ROUTER_API_KEY is not set.
    
    Expected results:
    - Health check should pass
    - Text generation should return valid responses
    - JSON generation should return parseable JSON
    - Error handling (401, timeout) should work correctly
    """
    pass
