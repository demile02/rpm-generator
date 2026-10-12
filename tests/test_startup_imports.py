"""Startup import boundary regressions."""
import os
import subprocess
import sys


def test_app_import_does_not_load_docx_renderer():
    env = os.environ.copy()
    env['PYTHONPATH'] = 'src'
    probe = subprocess.run(
        [sys.executable, '-c',
         'import sys; import app; '
         "assert 'docx_renderer' not in sys.modules"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert probe.returncode == 0, probe.stderr
