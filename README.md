# RPM Generator — Rencana Pembelajaran Mendalam

Generator RPP/RPM (Rencana Pembelajaran Mendalam) berbasis AI untuk
sekolah dan madrasah Indonesia. AI hanya menyusun konten pedagogis;
seluruh data normatif (CP, fase, elemen, profil lulusan) berasal dari
database kurikulum hasil ingest 9 dokumen regulasi kanonik di `Hukum/`,
dan setiap RPM melewati validasi berlapis sebelum bisa diekspor DOCX.

Sumber kebenaran spesifikasi: `AGENTS.md`.

## Status data (terverifikasi 2026-10-08)

- 6592 fragmen sumber, 3060 CP, 9 dokumen regulasi
- pytest 1208 fungsi uji (51 file), frontend Node 163/163
- Backend Flask sehat (`/api/health`), UI di `/app`

## Menjalankan

```bash
pip install -r requirements.txt   # PyPDF2==3.0.1 (pin 4.0.0 tidak ada di PyPI)
python3 src/app.py                # http://localhost:5000/app
```

Generate AI butuh gateway 9Router lokal (lihat `.env.example`).
Tanpa gateway: riwayat, pratinjau, dan export DOCX tetap jalan.
Butuh binary `tesseract-ocr` untuk audit kualitas OCR.

## Alur utama

Landing → Beranda (profil, koleksi buku ajar, riwayat RPM, impor RPM,
arsip) → Formulir generate (konteks kurikulum + buku sumber materi +
asesmen opsional) → Progres → Hasil tervalidasi (edit, regen per
bagian, riwayat versi, export DOCX) → Log generate (popup audit).

## API (ringkasan)

- `GET /api/health`, `GET /api/stats`
- Kurikulum: `GET /api/systems`, `GET /api/subjects/<system>`,
  `GET /api/curriculum/options`, `GET /api/cp/<subject>/<phase>`,
  `POST /api/context/generate`
- Generate: `POST /api/module/generate`,
  `GET /api/generation/status/<job_id>`
- Modul: `GET /api/modules`, `GET/PUT/DELETE /api/module/<id>`,
  `POST /api/module/<id>/regenerate`,
  `POST /api/module/<id>/finalize`,
  `GET /api/module/<id>/export-docx` (hanya final tervalidasi)
- Versi: `GET/POST /api/module/<id>/versions`,
  `GET/DELETE /api/module/<id>/versions/<no>`,
  `POST .../restore`
- Arsip: `POST /api/modules/<id>/archive|unarchive`
- Impor RPM: `POST /api/modules/import` (DOCX/PDF, maks 10MB)
- Buku ajar: `GET /api/buku`, `POST /api/buku/upload`
- Log: `GET/DELETE /api/generations`, `GET/DELETE /api/generations/<id>`

## Struktur proyek

```text
Hukum/            9 PDF regulasi kanonik (jangan diubah)
db/               rpm_generator.db (data universal ikut git),
                  curriculum_mappings.json, document_registry.json,
                  extracted_fragments.json, tessdata/, source_documents/
templates/        Templatku.docx (acuan layout DOCX, ikut git)
src/              app.py, module_generation_pipeline.py,
                  curriculum_engine.py, curriculum_context.py,
                  rule_engine.py, pdf_extraction.py,
                  nine_router_client.py, module_store.py,
                  docx_renderer.py, db_initialization.py,
                  rpm_importer.py, buku_ajar.py
ui/               index.html, styles.css, app.js, api.js, render.js,
                  fonts/ + vendor-*.js lokal (offline-first),
                  tests/frontend.test.js
tests/            51 file pytest
AGENTS.md         spesifikasi dan aturan kerja
Design.md         token visual Atelier Glass
```

## Aturan penting

- Jangan ubah backend/API/database untuk tugas frontend; sebaliknya juga.
- CP tidak dibuat/diparafrase AI; TP utama minimal C3 (aturan aplikasi).
- `Templatku.docx` hanya acuan layout, bukan sumber fakta kurikulum.
- Jangan commit `.env`, kunci API, atau rahasia apa pun.
