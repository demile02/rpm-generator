"""Preview/demo server: Flask app with a DETERMINISTIC fake AI (mock).

Uses the exact same fake router responses as the test suite
(test_phase_c_module_generation.fake_router_response) so the UI can be
walked end-to-end without a live 9Router. DB is a throwaway copy
(RPM_GENERATOR_DB env var). Not for production.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT / 'tests'))

# Throwaway DB copy (created by the launcher command).
os.environ.setdefault('RPM_GENERATOR_DB', str(PROJECT_ROOT / 'db' / 'mock_rpm.db'))

import app as app_module  # noqa: E402
from module_generation_pipeline import ModuleGenerationPipeline  # noqa: E402
from test_phase_c_module_generation import (  # noqa: E402
    fake_router_response,
    patch_pipeline_ai,
)

pipeline = ModuleGenerationPipeline(db_path=str(app_module.DB_PATH))
app_module._generation_pipeline = pipeline

# Wrap the REAL client method so the mock intercepts generate_json calls
# only; everything else (validators, storage, provenance) stays
# production code.
_original = pipeline.ai_client.generate_json


def _mocked(prompt, system_instruction=None, **kwargs):
    return fake_router_response(str(prompt), system_instruction, **kwargs)


pipeline.ai_client.generate_json = _mocked  # demo mock; not production

print("MOCK AI ENABLED - responses are deterministic (test-suite fake).")
print(f"DB (throwaway copy): {app_module.DB_PATH}")

if __name__ == '__main__':
    app_module.app.run(host='127.0.0.1', port=5000, debug=False,
                       use_reloader=False)
