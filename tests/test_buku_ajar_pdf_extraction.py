import sqlite3
from pathlib import Path

import pytest

import buku_ajar
from pdf_extraction import EXTRACTION_METHOD_OCR


@pytest.fixture
def buku_db(tmp_path):
    db_path = tmp_path / "buku.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE source_documents (
            id TEXT PRIMARY KEY,
            regulation_id TEXT,
            title TEXT,
            document_type TEXT,
            local_path TEXT,
            file_size_bytes INTEGER,
            document_hash TEXT,
            extracted_at TEXT,
            notes TEXT,
            book_title TEXT,
            book_author TEXT,
            book_year TEXT,
            book_publisher TEXT,
            book_identity_source TEXT
        );
        CREATE TABLE source_fragments (
            id TEXT PRIMARY KEY,
            document_id TEXT,
            page_number INTEGER,
            section TEXT,
            paragraph INTEGER,
            text TEXT,
            text_hash TEXT,
            char_count INTEGER,
            extraction_method TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _make_mixed_pdf(path: Path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    text_page = doc.new_page()
    text_page.insert_text(
        (72, 72),
        "Teks halaman dengan lapisan teks yang cukup untuk ekstraksi biasa. " * 3,
    )
    doc.new_page()
    doc.save(path)
    doc.close()


def test_ingest_pdf_uses_shared_ocr_fallback_for_scan_pages(
    buku_db, tmp_path, monkeypatch
):
    pdf_path = tmp_path / "scan-book.pdf"
    _make_mixed_pdf(pdf_path)

    def fake_ocr_pages(extractor, page_numbers):
        assert page_numbers == [2]
        extractor.page_methods[2] = EXTRACTION_METHOD_OCR
        return {2: "Teks halaman hasil OCR yang harus disimpan apa adanya."}

    from pdf_extraction import PDFExtractor

    monkeypatch.setattr(PDFExtractor, "_ocr_pages", fake_ocr_pages)

    result = buku_ajar.ingest_buku(
        str(buku_db), str(pdf_path), "scan-book.pdf"
    )

    assert result["fragmen"] == 2
    conn = sqlite3.connect(buku_db)
    rows = conn.execute(
        "SELECT page_number, text, extraction_method "
        "FROM source_fragments ORDER BY page_number"
    ).fetchall()
    conn.close()

    assert rows[0][0] == 1
    assert rows[0][2] == "text_layer"
    assert rows[1] == (
        2,
        "Teks halaman hasil OCR yang harus disimpan apa adanya.",
        "ocr",
    )
