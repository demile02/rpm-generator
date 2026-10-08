#!/usr/bin/env python3
"""
PDF Extraction Pipeline
AI RPP/RPM Pembelajaran Mendalam Generator - Regulation Ingestion

Extracts text from PDFs, creates source fragments, and generates hashes.

AGENTS.md §2: pipeline WAJIB menangani PDF text-layer DAN PDF scan.
PDF scan (mis. BKPDM 020/2026, KMA 1503/2025) TIDAK boleh dianggap
"kosong" hanya karena ekstraksi teks biasa menghasilkan sedikit teks —
fallback render halaman + OCR/vision harus dijalankan.
"""

import pdfplumber
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Ekstraksi method yang dicatat per fragment (provenance, AGENTS.md §2):
EXTRACTION_METHOD_TEXT_LAYER = 'text_layer'
EXTRACTION_METHOD_OCR = 'ocr'
EXTRACTION_METHOD_VISION = 'vision'

# Ambang "text cukup": di bawah ini halaman dianggap butuh OCR fallback
# (halaman scan biasanya < 50 karakter teks nyata).
MIN_TEXT_CHARS_PER_PAGE = 50

# Ambang fragmen remah: di bawah ini chunk dibuang saat create_fragments
# (sisa linearisasi tabel/ornamen OCR, bukan konten).
MIN_FRAGMENT_CHARS = 3

# Pola fragmen remah berbasis token: fragmen tanpa KATA BERHURUF >= 3
# dianggap bukan konten — sisa penomoran ("1.2."), digit ("63177"),
# header nomor halaman ("-10 -"), garis/ornamen ("|", "-"). Kata dalam
# bahasa Indonesia maupun Inggris hampir selalu punya minimal 3 huruf.
_LETTER_WORD_RE = re.compile(r'[A-Za-z\u00C0-\u024F]{3,}')


def _is_fragment_debris(text: str) -> bool:
    """True bila chunk bukan konten: kosong/terlalu pendek, atau tanpa
    kata berhuruf >= 3 karakter. Digunakan create_fragments agar remah
    linearisasi OCR tidak pernah masuk korpus."""
    t = (text or '').strip()
    if len(t) <= MIN_FRAGMENT_CHARS:
        return True
    return not _LETTER_WORD_RE.search(t)


class PDFExtractor:
    """Extracts and processes PDF documents."""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.document_name = self.pdf_path.stem
        self.content = {}
        self.fragments = []
        self.document_hash = None
        self.metadata = {}
        # Diinisialisasi sejak konstruksi agar _ocr_pages aman dipanggil
        # mandiri (tanpa extract_text_with_pages) — audit OCR 2026-09.
        self.page_methods = {}
        
    def extract_text_with_pages(self) -> Dict[int, str]:
        """Extract text from PDF with page tracking.

        Fallback OCR (AGENTS.md §2): halaman dengan text layer tipis
        di-render lalu di-OCR via PyMuPDF+Tesseract bila tersedia.
        Method ekstraksi tiap halaman dicatat di self.page_methods.
        """
        print(f"📖 Extracting text from {self.pdf_path.name}...")
        
        pages_content = {}
        self.page_methods = {}
        needs_ocr_pages = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                self.metadata['total_pages'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    if len(text.strip()) >= MIN_TEXT_CHARS_PER_PAGE:
                        pages_content[page_num] = text
                        self.page_methods[page_num] = \
                            EXTRACTION_METHOD_TEXT_LAYER
                    else:
                        needs_ocr_pages.append(page_num)
                        print(f"   Page {page_num}: text layer tipis/kosong "
                              f"({len(text.strip())} chars) -> antrian OCR")
            print(f"   ✅ {len(pages_content)} pages via text layer, "
                  f"{len(needs_ocr_pages)} pages perlu OCR fallback")
            
            # Fallback OCR/vision untuk halaman scan (AGENTS.md §2).
            if needs_ocr_pages:
                ocr_pages = self._ocr_pages(needs_ocr_pages)
                for page_num, text in ocr_pages.items():
                    if text.strip():
                        pages_content[page_num] = text
                
            self.content = pages_content
            return pages_content
            
        except Exception as e:
            print(f"   ❌ Error extracting from {self.pdf_path.name}: {e}")
            return {}
    
    def _ocr_pages(self, page_numbers: List[int]) -> Dict[int, str]:
        """Render halaman lalu OCR via PyMuPDF + Tesseract (jika ada).

        Teks hasil OCR disimpan apa adanya (tidak "diperbaiki" diam-diam);
        nomor halaman dipertahankan; method dicatat sebagai 'ocr'.
        Bila Tesseract tidak terpasang, halaman tetap dilaporkan kosong
        dengan peringatan eksplisit (bukan dianggap PDF kosong).
        """
        result: Dict[int, str] = {}
        try:
            import fitz  # PyMuPDF - already a project dependency
        except ImportError:
            print("   ⚠️  PyMuPDF tidak tersedia; OCR fallback dilewati")
            return result
        try:
            import pytesseract
            from PIL import Image
            import io as _io
        except ImportError:
            print("   ⚠️  pytesseract/Pillow tidak terpasang - halaman "
                  f"{page_numbers[:5]}... terdeteksi SCAN tetapi tidak "
                  "dapat di-OCR; tandai missing source secara jujur")
            return result
        # Lokasi binary Tesseract: UB-Mannheim installer tidak selalu
        # menambah dirinya ke PATH.
        tesseract_cmd = shutil.which('tesseract')
        for candidate in (
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            '/usr/bin/tesseract', '/usr/local/bin/tesseract',
        ):
            if tesseract_cmd is None and Path(candidate).exists():
                tesseract_cmd = candidate
        if not tesseract_cmd:
            print("   ⚠️  Binary Tesseract tidak ditemukan; OCR fallback "
                  "dilewati (halaman scan tetap dilaporkan jujur)")
            return result
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        # Tessdata proyek memuat traineddata Indonesia (ind) yang tidak
        # dibawa installer bawaan; dipakai bila tersedia.
        tessdata_local = Path(__file__).resolve().parent.parent / 'db' / 'tessdata'
        if (tessdata_local / 'ind.traineddata').exists():
            os.environ['TESSDATA_PREFIX'] = str(tessdata_local)
        try:
            doc = fitz.open(self.pdf_path)
            for page_num in page_numbers:
                if page_num - 1 >= len(doc):
                    continue
                pix = doc[page_num - 1].get_pixmap(dpi=200)
                img = Image.open(_io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang="ind+eng")
                text = text.strip()
                if text:
                    result[page_num] = text
                    self.page_methods[page_num] = EXTRACTION_METHOD_OCR
            doc.close()
            print(f"   🔎 OCR fallback selesai: {len(result)} halaman "
                  f"terekstraksi")
        except Exception as e:
            print(f"   ⚠️  OCR fallback error: {e}")
        return result
    
    def calculate_hash(self) -> str:
        """Calculate SHA256 hash of the PDF file."""
        print(f"🔐 Calculating hash for {self.pdf_path.name}...")
        sha256_hash = hashlib.sha256()
        
        try:
            with open(self.pdf_path, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b''):
                    sha256_hash.update(byte_block)
            
            hash_value = sha256_hash.hexdigest()
            self.document_hash = hash_value
            print(f"   Hash: {hash_value}")
            return hash_value
            
        except Exception as e:
            print(f"   ❌ Error calculating hash: {e}")
            return None
    
    def create_fragments(self, max_chars_per_fragment: int = 1000) -> List[Dict]:
        """
        Create source fragments from extracted text.
        Each fragment is tagged with page number and section.

        Fragmen remah (≤ MIN_FRAGMENT_CHARS karakter setelah trim)
        dibuang: sisa linearisasi kolom tabel/ornamen halaman hasil OCR
        (mis. "|", "B.", "9") yang bukan konten dan hanya menjadi noise
        retrieval. Audit OCR 2026-09: 64 fragmen dari 6.958 (0,9%).
        """
        print(f"✂️  Creating fragments from {self.pdf_path.name}...")
        fragments = []
        fragment_id = 0
        dropped = 0
        
        for page_num, text in self.content.items():
            # Split page into sections (paragraphs)
            paragraphs = text.split('\n\n')
            
            for para_idx, paragraph in enumerate(paragraphs):
                if not paragraph.strip():
                    continue
                
                # Split long paragraphs into smaller fragments
                for chunk_idx in range(0, len(paragraph), max_chars_per_fragment):
                    chunk = paragraph[chunk_idx:chunk_idx + max_chars_per_fragment]
                    
                    # Filter fragmen remah (panjang + heuristik token):
                    # bukan konten, hanya noise layout hasil OCR — jangan
                    # dihitung sebagai fragmen.
                    if _is_fragment_debris(chunk):
                        dropped += 1
                        continue
                    
                    # Hash dihitung dari teks yang BENAR-BENAR tersimpan
                    # (chunk.strip()), bukan slice mentah — agar verifikasi
                    # text_hash == sha256(text) selalu konsisten. Encode
                    # eksplisit UTF-8 agar deterministik antar-platform.
                    stored_text = chunk.strip()
                    fragment_hash = hashlib.sha256(
                        stored_text.encode('utf-8')).hexdigest()
                    
                    fragment = {
                        'fragment_id': f"{self.document_name}_page{page_num}_para{para_idx}_chunk{chunk_idx // max_chars_per_fragment}",
                        'page_number': page_num,
                        'section': self._detect_section(text, chunk),
                        'paragraph': para_idx,
                        'text': stored_text,
                        'text_hash': fragment_hash,
                        'char_count': len(stored_text),
                        # Provenance per fragment (AGENTS.md §2): jalur
                        # ekstraksi halaman sumber (text_layer/ocr/vision).
                        'extraction_method': self.page_methods.get(
                            page_num, EXTRACTION_METHOD_TEXT_LAYER),
                    }
                    fragments.append(fragment)
                    fragment_id += 1
        
        if dropped:
            print(f"   🧹 Dropped {dropped} fragment remah "
                  f"(<= {MIN_FRAGMENT_CHARS} karakter / tanpa kata berhuruf >=3)")
        print(f"   ✅ Created {len(fragments)} fragments")
        self.fragments = fragments
        return fragments
    
    def _detect_section(self, full_text: str, chunk: str) -> str:
        """
        Attempt to detect section/heading for the chunk.
        Looks for heading patterns in the text.
        """
        lines = full_text.split('\n')
        
        # Find common section headers (simplified)
        headers = [
            'CAPAIAN PEMBELAJARAN', 'CP', 'TUJUAN PEMBELAJARAN', 'TP',
            'PENDAHULUAN', 'LAMPIRAN', 'DAFTAR PUSTAKA', 'GLOSARIUM',
            'AKIDAH', 'AKHLAK', 'FIKIH', 'SKI', 'BAHASA ARAB',
            'FASE A', 'FASE B', 'FASE C', 'FASE D', 'FASE E', 'FASE F'
        ]
        
        for line in lines:
            upper_line = line.upper().strip()
            if any(header in upper_line for header in headers):
                return upper_line[:100]
        
        return "General"
    
    def get_extraction_metadata(self) -> Dict:
        """Return extraction metadata."""
        methods = sorted(set(getattr(self, 'page_methods', {}).values())) or \
            ['text_layer']
        return {
            'document_id': self.document_name,
            'file_path': str(self.pdf_path),
            'file_size_bytes': self.pdf_path.stat().st_size,
            'document_hash': self.document_hash,
            'extracted_at': datetime.now().isoformat(),
            'total_pages': self.metadata.get('total_pages', 0),
            'total_fragments': len(self.fragments),
            'character_count': sum(f['char_count'] for f in self.fragments),
            # Provenance ekstraksi (AGENTS.md §2): method yang dipakai.
            'extraction_methods': methods,
        }


class PDFExtractionPipeline:
    """Orchestrates extraction for multiple PDFs."""
    
    def __init__(self, pdf_directory: str):
        self.pdf_directory = Path(pdf_directory)
        self.results = []
        self.all_fragments = []
        
    def find_pdfs(self) -> List[Path]:
        """Find all PDF files in directory."""
        pdfs = list(self.pdf_directory.rglob('*.pdf'))
        print(f"📂 Found {len(pdfs)} PDF files")
        for pdf in pdfs:
            print(f"   • {pdf.name}")
        return pdfs
    
    def extract_all(self) -> Dict:
        """Extract all PDFs in the directory."""
        pdfs = self.find_pdfs()
        results = {
            'extraction_timestamp': datetime.now().isoformat(),
            'documents': [],
            'total_documents': len(pdfs),
            'total_fragments': 0
        }
        
        for pdf_path in pdfs:
            print(f"\n{'='*60}")
            print(f"Processing: {pdf_path.name}")
            print(f"{'='*60}")
            
            extractor = PDFExtractor(str(pdf_path))
            
            # Extract text
            extractor.extract_text_with_pages()
            
            # Calculate hash
            extractor.calculate_hash()
            
            # Create fragments
            extractor.create_fragments()
            
            # Collect results
            doc_result = {
                'metadata': extractor.get_extraction_metadata(),
                'fragments': extractor.fragments
            }
            results['documents'].append(doc_result)
            self.all_fragments.extend(extractor.fragments)
        
        results['total_fragments'] = len(self.all_fragments)
        return results
    
    def save_results(self, output_file: str):
        """Save extraction results to JSON."""
        results = self.extract_all()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Results saved to {output_path}")
        print(f"   Documents: {results['total_documents']}")
        print(f"   Total fragments: {results['total_fragments']}")
        
        return results


if __name__ == '__main__':
    # Sumber kanonik: Hukum/ di ROOT proyek (AGENTS.md §1).
    # Ekstraksi adalah TURUNAN; PDF kanonik tidak boleh diganti.
    PROJECT_ROOT = Path(__file__).parent.parent
    PDF_DIRECTORY = PROJECT_ROOT / 'Hukum'
    OUTPUT_FILE = PROJECT_ROOT / 'db' / 'extracted_fragments.json'
    
    # Run extraction pipeline
    pipeline = PDFExtractionPipeline(str(PDF_DIRECTORY))
    results = pipeline.save_results(str(OUTPUT_FILE))
    
    print("\n" + "="*60)
    print("✨ PDF EXTRACTION COMPLETE")
    print("="*60)
