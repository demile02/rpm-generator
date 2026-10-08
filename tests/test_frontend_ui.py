#!/usr/bin/env python3
"""Frontend UI tests (Node harness di ui/tests/frontend.test.js).

 dijalankan via node; skip bila node tidak tersedia. Menguji logika
alur nyata (bukan snapshot): options, validasi form, CP, polling,
gating export, download, dan render aman.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / 'ui' / 'tests' / 'frontend.test.js'


@pytest.mark.skipif(shutil.which('node') is None,
                    reason='node tidak tersedia')
def test_frontend_flow():
    proc = subprocess.run(
        ['node', str(SCRIPT)],
        capture_output=True, text=True, timeout=120,
        cwd=str(PROJECT_ROOT))
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert 'FRONTEND TESTS PASS (163/163)' in proc.stdout
