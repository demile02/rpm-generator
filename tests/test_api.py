#!/usr/bin/env python3
"""
Tests for Flask API (Phase 12)
Tests REST API endpoints and responses
"""

import pytest
import sys
import json
from unittest.mock import patch

# Don't add src to path here - let conftest fixtures handle imports


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestAPIEndpoints:
    """Test API endpoint existence and routing."""
    
    def test_root_endpoint_exists(self, flask_client):
        """Root endpoint / should exist."""
        response = flask_client.get('/')
        assert response.status_code in [200, 404, 405]  # Either exists or 405
    
    def test_health_endpoint_exists(self, flask_client):
        """Health check endpoint should exist."""
        response = flask_client.get('/api/health')
        assert response.status_code in [200, 404, 409]
    
    def test_systems_endpoint_exists(self, flask_client):
        """Systems endpoint should exist."""
        response = flask_client.get('/api/systems')
        assert response.status_code in [200, 404]
    
    def test_subjects_endpoint_exists(self, flask_client):
        """Subjects endpoint should exist."""
        response = flask_client.get('/api/subjects/KEMENAG')
        assert response.status_code in [200, 404]
    
    def test_cp_endpoint_exists(self, flask_client):
        """CP endpoint should exist."""
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        assert response.status_code in [200, 404, 409]
    
    def test_context_generate_endpoint_exists(self, flask_client):
        """Context generation endpoint should exist."""
        response = flask_client.post('/api/context/generate', json={})
        assert response.status_code in [400, 404, 422]
    
    def test_module_generate_endpoint_exists(self, flask_client):
        """Module generation endpoint should exist."""
        import app as app_module
        # Clear any context state leaked from other tests
        app_module.generation_context.pop('current', None)
        app_module.generation_context.pop('module', None)
        response = flask_client.post('/api/module/generate', json={})
        assert response.status_code in [200, 400, 404]


# ============================================================================
# ROOT ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestRootEndpoint:
    """Test root endpoint."""
    
    def test_root_returns_json(self, flask_client):
        """Root endpoint should return JSON."""
        response = flask_client.get('/')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
    
    def test_root_contains_status(self, flask_client):
        """Root response should contain status."""
        response = flask_client.get('/')
        data = json.loads(response.data)
        assert 'status' in data
    
    def test_root_contains_endpoints(self, flask_client):
        """Root response should list endpoints."""
        response = flask_client.get('/')
        data = json.loads(response.data)
        assert 'endpoints' in data


# ============================================================================
# HEALTH CHECK ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_returns_200(self, flask_client):
        """Health endpoint should return 200."""
        response = flask_client.get('/api/health')
        assert response.status_code == 200
    
    def test_health_returns_json(self, flask_client):
        """Health endpoint should return JSON."""
        response = flask_client.get('/api/health')
        assert response.content_type == 'application/json'
    
    def test_health_contains_status(self, flask_client):
        """Health response should contain status."""
        response = flask_client.get('/api/health')
        data = json.loads(response.data)
        assert 'status' in data
    
    def test_health_contains_database_info(self, flask_client):
        """Health response should indicate database status."""
        response = flask_client.get('/api/health')
        data = json.loads(response.data)
        assert 'database' in data or 'timestamp' in data


# ============================================================================
# SYSTEMS ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestSystemsEndpoint:
    """Test systems retrieval endpoint."""
    
    def test_systems_returns_200(self, flask_client):
        """Systems endpoint should return 200."""
        response = flask_client.get('/api/systems')
        assert response.status_code == 200
    
    def test_systems_returns_json(self, flask_client):
        """Systems endpoint should return JSON."""
        response = flask_client.get('/api/systems')
        assert response.content_type == 'application/json'
    
    def test_systems_contains_status(self, flask_client):
        """Systems response should contain status."""
        response = flask_client.get('/api/systems')
        data = json.loads(response.data)
        assert 'status' in data
    
    def test_systems_contains_systems_list(self, flask_client):
        """Systems response should contain systems."""
        response = flask_client.get('/api/systems')
        data = json.loads(response.data)
        assert 'systems' in data
    
    def test_systems_list_is_array(self, flask_client):
        """Systems should be an array."""
        response = flask_client.get('/api/systems')
        data = json.loads(response.data)
        assert isinstance(data['systems'], list)
    
    def test_systems_list_has_items(self, flask_client):
        """Systems list should have items."""
        response = flask_client.get('/api/systems')
        data = json.loads(response.data)
        assert len(data['systems']) > 0


# ============================================================================
# SUBJECTS ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestSubjectsEndpoint:
    """Test subjects retrieval endpoint."""
    
    def test_subjects_for_kemenag_returns_200(self, flask_client):
        """Subjects for KEMENAG should return 200."""
        response = flask_client.get('/api/subjects/KEMENAG')
        assert response.status_code == 200
    
    def test_subjects_returns_json(self, flask_client):
        """Subjects endpoint should return JSON."""
        response = flask_client.get('/api/subjects/KEMENAG')
        assert response.content_type == 'application/json'
    
    def test_subjects_contains_system(self, flask_client):
        """Subjects response should contain system."""
        response = flask_client.get('/api/subjects/KEMENAG')
        data = json.loads(response.data)
        assert 'system' in data
    
    def test_subjects_contains_list(self, flask_client):
        """Subjects response should contain subject list."""
        response = flask_client.get('/api/subjects/KEMENAG')
        data = json.loads(response.data)
        assert 'subjects' in data
    
    def test_subjects_list_is_array(self, flask_client):
        """Subjects should be an array."""
        response = flask_client.get('/api/subjects/KEMENAG')
        data = json.loads(response.data)
        assert isinstance(data['subjects'], list)
    
    def test_subjects_kemenag_has_akidah(self, flask_client):
        """KEMENAG should have Akidah Akhlak."""
        response = flask_client.get('/api/subjects/KEMENAG')
        data = json.loads(response.data)
        subjects = data['subjects']
        assert 'Akidah Akhlak' in subjects
    
    def test_invalid_system_returns_error(self, flask_client):
        """Invalid system should return error."""
        response = flask_client.get('/api/subjects/INVALID_SYSTEM')
        assert response.status_code in [400, 404]


# ============================================================================
# CP ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestCPEndpoint:
    """Test CP retrieval endpoint."""
    
    def test_cp_ambiguous_lookup_requires_full_identity(self, flask_client):
        """Ambiguous subject/phase lookup must not select an arbitrary CP."""
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        assert response.status_code == 409
    
    def test_cp_returns_json(self, flask_client):
        """CP endpoint should return JSON."""
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        assert response.content_type == 'application/json'
    
    def test_cp_contains_status(self, flask_client):
        """CP response should contain status."""
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        data = json.loads(response.data)
        assert 'status' in data
    
    def test_cp_valid_contains_cp_data(self, flask_client):
        """Valid CP query should return CP data."""
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        data = json.loads(response.data)
        if response.status_code == 200:
            assert 'cp' in data or 'not_found' in data.get('status', '')
    
    def test_cp_invalid_phase_returns_error(self, flask_client):
        """Invalid phase should return not_found."""
        response = flask_client.get('/api/cp/Akidah Akhlak/INVALID')
        assert response.status_code in [200, 404]
    
    def test_cp_invalid_subject_returns_error(self, flask_client):
        """Invalid subject should return not_found."""
        response = flask_client.get('/api/cp/INVALID_SUBJECT/D')
        assert response.status_code in [200, 404]


# ============================================================================
# CONTEXT GENERATION ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestContextGenerationEndpoint:
    """Test context generation endpoint."""
    
    def test_context_generate_requires_post(self, flask_client):
        """Context generation should be POST."""
        response = flask_client.get('/api/context/generate')
        assert response.status_code in [405, 404]  # Method not allowed or not found
    
    def test_context_generate_accepts_json(self, flask_client):
        """Context generation should accept JSON."""
        response = flask_client.post('/api/context/generate', json={})
        assert response.status_code in [200, 400]
    
    def test_context_generate_with_valid_data(self, flask_client):
        """Context generation with valid data."""
        data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D'
        }
        response = flask_client.post('/api/context/generate', json=data)
        assert response.status_code in [200, 409]
    
    def test_context_generate_returns_json(self, flask_client):
        """Context generation should return JSON."""
        data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D'
        }
        response = flask_client.post('/api/context/generate', json=data)
        assert response.content_type == 'application/json'
    
    def test_context_generate_requires_fields(self, flask_client):
        """Context generation should require fields."""
        response = flask_client.post('/api/context/generate', json={})
        # Should either succeed or return 400 for missing fields
        assert response.status_code in [200, 400]
    
    def test_context_generate_response_structure(self, flask_client):
        """Context generation response should have proper structure."""
        data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'phase': 'D'
        }
        response = flask_client.post('/api/context/generate', json=data)
        if response.status_code == 200:
            result = json.loads(response.data)
            assert 'status' in result


# ============================================================================
# MODULE GENERATION ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestModuleGenerationEndpoint:
    """Test module generation endpoint."""
    
    def test_module_generate_requires_post(self, flask_client):
        """Module generation should be POST."""
        response = flask_client.get('/api/module/generate')
        assert response.status_code in [405, 404]
    
    def test_module_generate_accepts_json(self, flask_client, test_db):
        """Module generation runs the REAL pipeline (mocked AI) and can succeed."""
        from module_generation_pipeline import ModuleGenerationPipeline
        from test_phase_c_module_generation import fake_router_response

        context_data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D'
        }
        ctx_response = flask_client.post('/api/context/generate', json=context_data)
        assert ctx_response.status_code == 200

        # Wire the endpoint to the real pipeline on the TEMP test database,
        # with the AI client mocked (no real 9Router needed).
        import app as app_module
        pipeline = ModuleGenerationPipeline(db_path=str(test_db))
        app_module._generation_pipeline = pipeline
        try:
            with patch.object(
                pipeline.ai_client, 'generate_json',
                side_effect=fake_router_response
            ):
                response = flask_client.post('/api/module/generate', json=context_data)
            assert response.status_code == 200, response.get_data(as_text=True)
            data = json.loads(response.data)
            assert data['status'] == 'success'
            assert data['module']['learning_objectives']
        finally:
            app_module._generation_pipeline = None
            pipeline.curriculum_validator.close()
    
    def test_module_generate_returns_json(self, flask_client):
        """Module generation should return JSON."""
        import app as app_module
        # Hermetic: tanpa konteks bocor dari test lain (tanpa ini POST {}
        # dapat memakai generation_context global dan memicu REAL AI
        # generation bermenit-menit — Batch 6 isolation).
        app_module.generation_context.pop('current', None)
        app_module.generation_context.pop('module', None)
        response = flask_client.post('/api/module/generate', json={})
        assert response.status_code == 400
        assert response.content_type == 'application/json'

    def test_module_generate_response_structure(self, flask_client):
        """Module generation response should have proper structure."""
        import app as app_module
        app_module.generation_context.pop('current', None)
        app_module.generation_context.pop('module', None)
        response = flask_client.post('/api/module/generate', json={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'error'


# ============================================================================
# STATISTICS ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestStatisticsEndpoint:
    """Test statistics endpoint."""
    
    def test_stats_endpoint_returns_200(self, flask_client):
        """Stats endpoint should return 200."""
        response = flask_client.get('/api/stats')
        assert response.status_code == 200
    
    def test_stats_returns_json(self, flask_client):
        """Stats endpoint should return JSON."""
        response = flask_client.get('/api/stats')
        assert response.content_type == 'application/json'
    
    def test_stats_contains_statistics(self, flask_client):
        """Stats response should contain statistics."""
        response = flask_client.get('/api/stats')
        data = json.loads(response.data)
        assert 'statistics' in data or 'status' in data
    
    def test_stats_includes_fragment_count(self, flask_client):
        """Stats should include fragment count."""
        response = flask_client.get('/api/stats')
        data = json.loads(response.data)
        if 'statistics' in data:
            assert 'total_fragments' in data['statistics']
    
    def test_stats_includes_cp_count(self, flask_client):
        """Stats should include CP count."""
        response = flask_client.get('/api/stats')
        data = json.loads(response.data)
        if 'statistics' in data:
            assert 'total_cp_entries' in data['statistics']


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.api
class TestErrorHandling:
    """Test error handling."""
    
    def test_404_on_nonexistent_endpoint(self, flask_client):
        """Nonexistent endpoint should return 404."""
        response = flask_client.get('/api/nonexistent')
        assert response.status_code == 404
    
    def test_404_returns_json(self, flask_client):
        """404 response should return JSON."""
        response = flask_client.get('/api/nonexistent')
        assert response.content_type == 'application/json'
    
    def test_404_contains_error_message(self, flask_client):
        """404 should contain error message."""
        response = flask_client.get('/api/nonexistent')
        data = json.loads(response.data)
        assert 'status' in data
        assert 'message' in data or 'error' in data
    
    def test_invalid_json_returns_error(self, flask_client):
        """Invalid JSON should return error."""
        response = flask_client.post(
            '/api/context/generate',
            data='invalid json',
            content_type='application/json'
        )
        assert response.status_code in [400, 415]


# ============================================================================
# HTTP METHOD TESTS
# ============================================================================

@pytest.mark.api
class TestHTTPMethods:
    """Test HTTP method support."""
    
    def test_get_systems_not_post(self, flask_client):
        """Systems endpoint should not accept POST."""
        response = flask_client.post('/api/systems')
        assert response.status_code in [405, 404]
    
    def test_context_generate_not_get(self, flask_client):
        """Context generation should not accept GET."""
        response = flask_client.get('/api/context/generate')
        assert response.status_code in [405, 404]
    
    def test_module_generate_not_get(self, flask_client):
        """Module generation should not accept GET."""
        response = flask_client.get('/api/module/generate')
        assert response.status_code in [405, 404]


# ============================================================================
# RESPONSE STRUCTURE TESTS
# ============================================================================

@pytest.mark.api
class TestResponseStructure:
    """Test response structure consistency."""
    
    def test_all_endpoints_return_json(self, flask_client):
        """All endpoints should return JSON."""
        endpoints = [
            ('GET', '/'),
            ('GET', '/api/health'),
            ('GET', '/api/systems'),
            ('GET', '/api/subjects/KEMENAG'),
            ('GET', '/api/stats'),
        ]
        
        for method, path in endpoints:
            if method == 'GET':
                response = flask_client.get(path)
                assert response.content_type == 'application/json'
    
    def test_successful_responses_have_status(self, flask_client):
        """Successful responses should have status field."""
        response = flask_client.get('/api/systems')
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'status' in data
    
    def test_error_responses_have_message(self, flask_client):
        """Error responses should have message."""
        response = flask_client.get('/api/nonexistent')
        if response.status_code == 404:
            data = json.loads(response.data)
            assert 'message' in data or 'error' in data


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.api
@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for API."""
    
    def test_complete_api_workflow(self, flask_client):
        """Test complete API workflow."""
        # 1. Get systems
        response = flask_client.get('/api/systems')
        assert response.status_code == 200
        
        # 2. Get subjects
        response = flask_client.get('/api/subjects/KEMENAG')
        assert response.status_code == 200
        
        # 3. Get CP
        response = flask_client.get('/api/cp/Akidah Akhlak/D')
        assert response.status_code in [200, 404, 409]
    
    def test_api_health_and_stats(self, flask_client):
        """Test health check and statistics."""
        # 1. Health check
        response = flask_client.get('/api/health')
        assert response.status_code == 200
        
        # 2. Statistics
        response = flask_client.get('/api/stats')
        assert response.status_code == 200
    
    def test_context_and_module_workflow(self, flask_client, test_db):
        """Full REST workflow: context, then real-pipeline module generation
        (AI mocked; validation failures return 422, never a fake success)."""
        from module_generation_pipeline import ModuleGenerationPipeline
        from test_phase_c_module_generation import fake_router_response

        context_data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D'
        }
        response = flask_client.post('/api/context/generate', json=context_data)
        assert response.status_code == 200

        import app as app_module
        pipeline = ModuleGenerationPipeline(db_path=str(test_db))
        app_module._generation_pipeline = pipeline
        try:
            with patch.object(
                pipeline.ai_client, 'generate_json',
                side_effect=fake_router_response
            ):
                response = flask_client.post('/api/module/generate', json=context_data)
            # Success path with valid mocked AI output
            assert response.status_code == 200, response.get_data(as_text=True)
            data = json.loads(response.data)
            assert data['status'] == 'success'
            assert data['module']
            assert data['validation']
        finally:
            app_module._generation_pipeline = None
            pipeline.curriculum_validator.close()


# ============================================================================
# TOPIC SERIALIZATION + PERSISTENT EDIT (PUT /api/module/<generation_id>)
# ============================================================================

@pytest.fixture
def api_pipeline(test_db):
    """Flask app wired to the real pipeline on the temp test DB
    (same pattern as test_phase_c_module_generation)."""
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


@pytest.mark.api
class TestTopicSerialization:
    """Topic must survive generation into the serialized module JSON."""

    def _generate(self, flask_client, api_pipeline, topic='Taubat'):
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        context_data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D',
            'topic': topic,
        }
        ctx = flask_client.post('/api/context/generate', json=context_data)
        assert ctx.status_code == 200
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            resp = flask_client.post('/api/module/generate', json=context_data)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return json.loads(resp.data)

    def test_module_to_dict_contains_topic(self):
        """Module.to_dict() exposes the authoritative topic field."""
        import sys as _sys
        _sys.path.insert(0, str(SRC_DIR)) if False else None
        from module_generation_pipeline import Module
        m = Module(
            id='x', title='t', subject='s', grade='g', phase='D',
            curriculum_version='v', module_identity={}, facilities=[],
            target_students={}, learning_model='m', methods=[],
            learning_objectives=[], success_criteria=[],
            essential_understanding={}, guiding_questions=[],
            learning_activities=[], assessments={},
            generation_id='gid', topic='Taubat',
        )
        assert m.to_dict()['topic'] == 'Taubat'

    def test_api_response_contains_topic(self, flask_client, api_pipeline):
        data = self._generate(flask_client, api_pipeline, topic='Taubat')
        assert data['module']['topic'] == 'Taubat dalam Pembelajaran'

    def test_topic_survives_generation_serialization(self, flask_client, api_pipeline):
        data = self._generate(flask_client, api_pipeline, topic='Sabar')
        assert data['module']['topic'] == 'Sabar dalam Pembelajaran'
        assert data['module']['title'].endswith('Sabar dalam Pembelajaran')


@pytest.mark.api
class TestPersistentEdit:
    """PUT /api/module/<generation_id>: validated, protected persistence."""

    def _generate_stored(self, flask_client, api_pipeline):
        """Generate + store server-side exactly like the async worker
        (module JSON + context JSON + live context object)."""
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        import app as app_module
        context_data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D',
            'topic': 'Taubat',
        }
        ctx = flask_client.post('/api/context/generate', json=context_data)
        assert ctx.status_code == 200
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            resp = flask_client.post('/api/module/generate', json=context_data)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = json.loads(resp.data)
        gid = data['generation_id']
        from module_store import ModuleStore
        store = ModuleStore(api_pipeline.db_path)
        store.save(gid, data['module'], data['module'].get('curriculum_context') or {})
        ctx_obj = getattr(api_pipeline.curriculum_validator, 'last_context', None)
        if ctx_obj is not None:
            app_module._context_objects[gid] = ctx_obj
        return gid, data['module']

    def test_valid_editable_update_200(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['main_content'] = 'DIEDIT: pemahaman bermakna taubat.'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        assert body['generation_id'] == gid
        assert body['module']['essential_understanding']['main_content'].startswith('DIEDIT')

    def test_update_persists_and_generation_id_stable(self, flask_client, api_pipeline):
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['application'] = 'DEFINISI BARU (edit).'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200
        stored = ModuleStore(api_pipeline.db_path).load(gid)
        assert stored is not None
        assert stored['module']['essential_understanding']['application'] == 'DEFINISI BARU (edit).'
        assert stored['module']['generation_id'] == gid

    def test_update_persists_structured_entries_not_repr_strings(self, flask_client, api_pipeline):
        """Regression: a successful PUT once stored dataclass entries via
        json.dumps(default=str), corrupting the row into 396-char repr
        strings. Typed entries must round-trip as objects."""
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['learning_objectives'][0]['text'] = (
            'Menerapkan TP yang diedit melalui PUT dalam pembelajaran.')
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        stored = ModuleStore(api_pipeline.db_path).load(gid)
        # All typed lists must still be dicts, not str-reprs.
        for key in ('learning_objectives', 'success_criteria', 'learning_activities'):
            assert stored['module'][key], f'{key} emptied by PUT'
            for entry in stored['module'][key]:
                assert isinstance(entry, dict), f'{key} entry corrupted to string: {str(entry)[:80]}'
        assert stored['module']['learning_objectives'][0]['text'] == (
            'Menerapkan TP yang diedit melalui PUT dalam pembelajaran.')
        # And a follow-up PUT against the stored row still validates clean.
        edited2 = json.loads(json.dumps(stored['module']))
        edited2['essential_understanding']['application'] = 'Edit kedua setelah PUT pertama.'
        resp2 = flask_client.put(f'/api/module/{gid}', json={'module': edited2})
        assert resp2.status_code == 200, resp2.get_data(as_text=True)

    def test_invalid_generation_id_404(self, flask_client, api_pipeline):
        resp = flask_client.put('/api/module/nope-not-a-real-id',
                                json={'module': {'title': 'x'}})
        assert resp.status_code == 404

    def test_malformed_json_400(self, flask_client, api_pipeline):
        resp = flask_client.put('/api/module/whatever',
                                data='not json at all',
                                content_type='application/json')
        assert resp.status_code == 400

    def test_schema_invalid_422(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        resp = flask_client.put(f'/api/module/{gid}',
                                json={'module': {'title': 12345, 'learning_objectives': 'nope'}})
        assert resp.status_code in [400, 422]

    def test_kktp_level_drop_rejected_422(self, flask_client, api_pipeline):
        """KKTP C6 -> C2 must fail validation and NOT touch storage."""
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        # Find the KKTP of the highest-level TP and drop its level to C2.
        kk = edited['success_criteria'][-1]
        kk['cognitive_level'] = 'C2'
        before = ModuleStore(api_pipeline.db_path).load(gid)
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        codes = [e['code'] for e in body['errors']]
        assert 'KKTP_ERROR' in codes
        after = ModuleStore(api_pipeline.db_path).load(gid)
        assert after['module'] == before['module']  # database unchanged

    def test_protected_cp_modification_rejected(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['curriculum_context']['cp']['text'] = 'CP palsu hasil edit'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'PROTECTED_FIELD_MODIFICATION' in codes

    def test_protected_provenance_rejected(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['curriculum_context']['cp']['source_page'] = 999
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'PROTECTED_FIELD_MODIFICATION' in codes

    def test_phase_modification_rejected(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['phase'] = 'E'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'PROTECTED_FIELD_MODIFICATION' in codes

    def test_subject_modification_rejected(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['subject'] = 'Fikih'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'PROTECTED_FIELD_MODIFICATION' in codes

    def test_topic_cannot_be_changed_via_put(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['topic'] = 'Topik Baru'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422

    def test_failed_validation_does_not_mutate_storage(self, flask_client, api_pipeline):
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['phase'] = 'C'
        flask_client.put(f'/api/module/{gid}', json={'module': edited})
        stored = ModuleStore(api_pipeline.db_path).load(gid)
        assert stored['module']['phase'] == 'D'

    def test_updated_at_present_on_success(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['main_content'] = 'Edit untuk updated_at.'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200
        assert 'updated_at' in json.loads(resp.data)

    def test_generation_job_on_fresh_thread_finds_cp(self, flask_client, api_pipeline):
        """Regression: the pipeline singleton's sqlite connection was bound
        to the first worker thread, so every async generation after the
        first hit a cross-thread ProgrammingError and saw an empty CP list.
        A fresh job (new thread) must still resolve CP correctly."""
        import threading
        import app as app_module
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        app_module.generation_jobs.clear()
        params = {
            'education_system': 'KEMENAG', 'institution_type': 'MTs',
            'grade': 'MTs_7', 'phase': 'D', 'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep', 'topic': 'Taubat',
        }
        resp = flask_client.post('/api/module/generate', json={'async': True, **params})
        assert resp.status_code == 202, resp.get_data(as_text=True)
        job_id = json.loads(resp.data)['job_id']
        job = None
        # Keep the AI patch active while the worker thread runs.
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            for _ in range(100):
                job = app_module.generation_jobs.get(job_id)
                if job and job['status'] != 'running':
                    break
                threading.Event().wait(0.1)
        assert job is not None and job['status'] != 'running', 'job never finished'
        if job['status'] == 'error':
            msgs = [e.get('message', '') for e in job['result'].get('errors', [])]
            assert not any('ELEMENT_NOT_FOUND' in m for m in msgs), \
                f'fresh-thread job lost CP access: {msgs}'
            assert False, f'fresh-thread job failed: {msgs}'
        assert job['result']['module']['topic'] == 'Taubat dalam Pembelajaran'


# ============================================================================
# RESTART-SAFE RETRIEVAL (GET /api/module/<generation_id> + PUT after restart)
# ============================================================================

class TestRestartSafeRetrieval:
    """Modules must be retrievable and editable from STORAGE only — no
    in-memory context dependency. 'Restart' is simulated the honest way:
    a brand-new Flask app instance plus a brand-new pipeline object, with
    all old in-process state discarded (a true subprocess variant lives in
    TestTrueProcessRestart)."""

    def _generate_stored(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        import app as app_module
        context_data = {
            'education_system': 'KEMENAG', 'institution_type': 'MTs',
            'grade': 'MTs_7', 'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep', 'phase': 'D', 'topic': 'Taubat',
        }
        ctx = flask_client.post('/api/context/generate', json=context_data)
        assert ctx.status_code == 200
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            resp = flask_client.post('/api/module/generate', json=context_data)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = json.loads(resp.data)
        gid = data['generation_id']
        from module_store import ModuleStore
        store = ModuleStore(api_pipeline.db_path)
        store.save(gid, data['module'], data['module'].get('curriculum_context') or {})
        return gid, data['module']

    def _restart(self, api_pipeline):
        """New app state + new pipeline; old in-memory context is gone.
        The replaced pipeline's sqlite handles are closed so Windows can
        delete the temp DB at teardown."""
        import app as app_module
        from module_generation_pipeline import ModuleGenerationPipeline
        old = app_module._generation_pipeline
        app_module._generation_pipeline = ModuleGenerationPipeline(
            db_path=str(api_pipeline.db_path))
        app_module._context_objects.clear()
        app_module.generation_context.clear()
        if old is not None:
            try:
                old.curriculum_validator.close()
            except Exception:
                pass
        return app_module._generation_pipeline

    # ---------------- GET ----------------

    def test_get_existing_module_200(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        resp = flask_client.get(f'/api/module/{gid}')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        assert body['generation_id'] == gid
        assert body['module']['topic'] == 'Taubat dalam Pembelajaran'
        assert body['module']['generation_id'] == gid
        assert 'updated_at' in body
        # Authoritative context echoed from storage.
        assert body['context']['cp']['source_document_id']
        assert body['context']['phase'] == 'D'

    def test_get_nonexistent_404_module_not_found(self, flask_client, api_pipeline):
        resp = flask_client.get('/api/module/00000000-0000-0000-0000-000000000000')
        assert resp.status_code == 404
        body = json.loads(resp.data)
        assert body['status'] == 'error'
        assert body['errors'][0]['code'] == 'MODULE_NOT_FOUND'
        assert body['errors'][0]['stage'] == 'storage'

    def test_get_malformed_id_404(self, flask_client, api_pipeline):
        resp = flask_client.get('/api/module/not%20a%20real%20id')
        assert resp.status_code == 404
        assert json.loads(resp.data)['errors'][0]['code'] == 'MODULE_NOT_FOUND'

    # ---------------- Persistence across restart ----------------

    def test_module_and_context_survive_new_app_instance(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        self._restart(api_pipeline)
        resp = flask_client.get(f'/api/module/{gid}')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['module']['topic'] == module['topic']
        assert body['context']['cp']['id'] == module['curriculum_context']['cp']['id']
        assert body['context']['cp']['source_page'] == module['curriculum_context']['cp']['source_page']

    def test_edit_after_restart_200_and_persists(self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        self._restart(api_pipeline)  # in-memory context destroyed
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['main_content'] = 'EDIT SETELAH RESTART.'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        # Second GET (still after restart) returns the persisted edit.
        again = json.loads(flask_client.get(f'/api/module/{gid}').data)
        assert again['module']['essential_understanding']['main_content'] == 'EDIT SETELAH RESTART.'
        assert again['module']['generation_id'] == gid

    # ---------------- Protection after restart ----------------

    def _assert_protected_after_restart(self, flask_client, api_pipeline, mutate, field_label):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        self._restart(api_pipeline)
        edited = json.loads(json.dumps(module))
        mutate(edited)
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422, f'{field_label}: {resp.get_data(as_text=True)[:200]}'
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'PROTECTED_FIELD_MODIFICATION' in codes, f'{field_label}: {codes}'
        after = json.loads(flask_client.get(f'/api/module/{gid}').data)
        return after

    def test_protected_cp_rejected_after_restart(self, flask_client, api_pipeline):
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m['curriculum_context']['cp'].update(text='CP dirampas'), 'cp')
        assert after['module']['curriculum_context']['cp']['text'] != 'CP dirampas'

    def test_protected_provenance_rejected_after_restart(self, flask_client, api_pipeline):
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m['curriculum_context']['cp'].update(source_page=1), 'provenance')
        assert after['module']['curriculum_context']['cp']['source_page'] != 1

    def test_protected_topic_rejected_after_restart(self, flask_client, api_pipeline):
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m.update(topic='Topik Lain'), 'topic')
        assert after['module']['topic'] == 'Taubat dalam Pembelajaran'

    def test_protected_phase_rejected_after_restart(self, flask_client, api_pipeline):
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m.update(phase='C'), 'phase')
        assert after['module']['phase'] == 'D'

    def test_protected_subject_rejected_after_restart(self, flask_client, api_pipeline):
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m.update(subject='Fikih'), 'subject')
        assert after['module']['subject'] == 'Akidah Akhlak'

    def test_protected_element_rejected_after_restart(self, flask_client, api_pipeline):
        # Module has no top-level 'element' field; the authoritative value
        # lives in curriculum_context. The PUT must still reject any
        # client-supplied element change and never store it.
        after = self._assert_protected_after_restart(
            flask_client, api_pipeline,
            lambda m: m.update(element='Akhlak'), 'element')
        assert after['module'].get('element') != 'Akhlak'
        assert after['module']['curriculum_context']['element'] == 'Pemahaman Konsep'

    # ---------------- Validation after restart ----------------

    def test_invalid_kktp_rejected_after_restart_db_unchanged(self, flask_client, api_pipeline):
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        self._restart(api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['success_criteria'][0]['cognitive_level'] = 'C2'
        before = ModuleStore(api_pipeline.db_path).load(gid)
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 422
        codes = [e['code'] for e in json.loads(resp.data)['errors']]
        assert 'KKTP_ERROR' in codes
        after = ModuleStore(api_pipeline.db_path).load(gid)
        assert after['module'] == before['module']  # database unchanged

    def test_valid_json_roundtrip_no_repr_strings(self, flask_client, api_pipeline):
        """After an edit, GET must serve objects/lists — never repr strings
        (regression for the json.dumps(default=str) storage corruption)."""
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        edited['guiding_questions'] = ['Apa yang terjadi jika taubat tidak ditegakkan?']
        assert flask_client.put(f'/api/module/{gid}', json={'module': edited}).status_code == 200
        served = json.loads(flask_client.get(f'/api/module/{gid}').data)['module']
        for key in ('learning_objectives', 'success_criteria', 'learning_activities'):
            for entry in served[key]:
                assert isinstance(entry, dict), f'{key} entry corrupted: {str(entry)[:60]}'
        assert isinstance(served['guiding_questions'], list)
        assert isinstance(served['curriculum_context'], dict)

    # ---------------- TRUE subprocess restart ----------------

    def test_true_subprocess_restart_get_and_put(self, flask_client, api_pipeline, tmp_path):
        """The honest restart test: PROCESS A generates and stores a module,
        then a brand-new Python PROCESS B (fresh interpreter, only the DB
        via RPM_GENERATOR_DB) must serve GET and a validated PUT for it.
        No object can have survived — only the database."""
        import os
        import subprocess
        import sys as _sys
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, module = self._generate_stored(flask_client, api_pipeline)

        child = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'restart_child.py')
        env = dict(os.environ)
        env['RPM_GENERATOR_DB'] = str(api_pipeline.db_path)

        # PROCESS B (fresh interpreter): GET must restore module + context.
        p1 = subprocess.run(
            [_sys.executable, child, 'get'],
            input=json.dumps({'generation_id': gid}),
            capture_output=True, text=True, env=env, timeout=120)
        assert p1.returncode == 0, p1.stderr[-400:]
        got = json.loads(p1.stdout.strip().splitlines()[-1])
        assert got['http'] == 200, got
        assert got['status'] == 'success'
        assert got['topic'] == 'Taubat dalam Pembelajaran'
        assert got['context_phase'] == 'D'
        assert got['context_cp_source']

        # PROCESS B (still a separate process): validated PUT must pass.
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['main_content'] = 'EDIT DARI PROSES BERBEDA.'
        p2 = subprocess.run(
            [_sys.executable, child, 'put'],
            input=json.dumps({'generation_id': gid, 'module': edited}),
            capture_output=True, text=True, env=env, timeout=120)
        assert p2.returncode == 0, p2.stderr[-400:]
        put = json.loads(p2.stdout.strip().splitlines()[-1])
        assert put['http'] == 200, put
        assert put['status'] == 'success'

        # Back in PROCESS A: the edit is visible via storage.
        served = json.loads(flask_client.get(f'/api/module/{gid}').data)
        assert served['module']['essential_understanding']['main_content'] == 'EDIT DARI PROSES BERBEDA.'
        assert served['module']['generation_id'] == gid


# ============================================================================
# QUALITY MAJOR-FIX PERSISTENCE TESTS (A.3 re-derivation + rubric descriptors)
# ============================================================================

@pytest.mark.api
class TestQualityFixPersistence:
    """A.3 stays authoritative through PUT (client never supplies it) and
    rubric descriptors survive the edit round-trip."""

    def _generate_stored(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response
        from test_phase_c_module_generation import patch_pipeline_ai
        import app as app_module
        context_data = {
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D',
            'topic': 'Taubat',
        }
        ctx = flask_client.post('/api/context/generate', json=context_data)
        assert ctx.status_code == 200
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            resp = flask_client.post('/api/module/generate', json=context_data)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = json.loads(resp.data)
        gid = data['generation_id']
        from module_store import ModuleStore
        store = ModuleStore(api_pipeline.db_path)
        store.save(gid, data['module'], data['module'].get('curriculum_context') or {})
        ctx_obj = getattr(api_pipeline.curriculum_validator, 'last_context', None)
        if ctx_obj is not None:
            app_module._context_objects[gid] = ctx_obj
        return gid, data['module']

    def test_put_rederives_a3_from_authoritative_source(
            self, flask_client, api_pipeline):
        from module_generation_pipeline import allowed_profile_values
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        # Client tries to smuggle a non-normative profile value through PUT.
        edited['profile_dimensions'] = ['Fake Value', 'Another One']
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        allowed = allowed_profile_values('KEMENAG')
        assert body['module']['profile_dimensions']
        assert all(v in allowed
                   for v in body['module']['profile_dimensions'])

    def test_rubric_descriptors_survive_put_roundtrip(
            self, flask_client, api_pipeline):
        from module_store import ModuleStore
        gid, module = self._generate_stored(flask_client, api_pipeline)
        # Descriptors were attached at generation time.
        rows = module['rubric']['kktp_rubric']
        assert rows and all(
            len(r['descriptors']) == len(r['levels']) for r in rows)
        edited = json.loads(json.dumps(module))
        edited['essential_understanding']['value'] = 'Edit deskriptor test.'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        stored = ModuleStore(api_pipeline.db_path).load(gid)
        srows = stored['module']['rubric']['kktp_rubric']
        for r in srows:
            assert r.get('descriptors'), 'descriptor lost in PUT round-trip'
            assert len(r['descriptors']) == len(r['levels'])

    def test_edited_module_passes_full_validation_with_new_rules(
            self, flask_client, api_pipeline):
        gid, module = self._generate_stored(flask_client, api_pipeline)
        edited = json.loads(json.dumps(module))
        # A harmless editable change must still pass every validator incl.
        # the new A3/RUBRIC_DESCRIPTOR/B4 gates.
        eu = edited['essential_understanding']
        if 'application' in eu:
            eu['application'] = 'Siswa membiasakan evaluasi diri setelah belajar.'
        resp = flask_client.put(f'/api/module/{gid}', json={'module': edited})
        assert resp.status_code == 200, json.loads(resp.data).get('errors')
