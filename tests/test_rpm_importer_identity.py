import json
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from rpm_importer import parse_identity, resolve_grade_phase


@pytest.fixture
def mappings():
    path = Path(__file__).resolve().parents[1] / 'db' / 'curriculum_mappings.json'
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


@pytest.mark.parametrize(
    ('name', 'kelas', 'expected_institution', 'expected_grade'),
    [
        ('SD Negeri 1', '1 / A / Ganjil', 'SD', 'SD_1'),
        ('SMP Negeri 1', '7 / D / Ganjil', 'SMP', 'SMP_7'),
        ('SMA Negeri 1', '10 / E / Ganjil', 'SMA', 'SMA_10'),
        ('SMK Negeri 1', '10 / E / Ganjil', 'SMK', 'SMK_10'),
    ],
)
def test_explicit_school_identity_selects_kemendikdasmen(
        mappings, name, kelas, expected_institution, expected_grade):
    identity = {
        'nama sekolah': name,
        'kelas / fase / semester': kelas,
    }

    resolved = resolve_grade_phase(identity, mappings)

    assert resolved == (
        'KEMENDIKDASMEN', expected_institution, expected_grade,
        kelas.split('/')[1].strip(),
    )


@pytest.mark.parametrize(
    ('label', 'name', 'kelas', 'expected_institution', 'expected_grade'),
    [
        ('Nama Madrasah', 'MI Negeri 1', '1 / A / Ganjil', 'MI', 'MI_1'),
        ('Nama Madrasah', 'MTs Negeri 1', '7 / D / Ganjil', 'MTs', 'MTs_7'),
        ('Nama Madrasah', 'MA Negeri 1', '10 / E / Ganjil', 'MA', 'MA_10'),
    ],
)
def test_valid_madrasah_identity_stays_on_kemenag(
        mappings, label, name, kelas, expected_institution, expected_grade):
    lines = [
        'A. IDENTITAS MODUL',
        f'{label}: {name} // Kelas / Fase / Semester: {kelas}',
        'B. IDENTIFIKASI',
    ]

    identity = parse_identity(lines)
    resolved = resolve_grade_phase(identity, mappings)

    assert resolved == (
        'KEMENAG', expected_institution, expected_grade,
        kelas.split('/')[1].strip(),
    )
