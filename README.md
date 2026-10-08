# RPM Generator — Rencana Pembelajaran Mendalam

Aplikasi pembuat RPP/RPM (Rencana Pembelajaran Mendalam) berbasis AI
untuk sekolah dan madrasah Indonesia. AI hanya menyusun konten
pedagogis; seluruh data normatif (CP, fase, elemen, profil lulusan)
berasal dari basis data kurikulum yang diekstrak dari 9 dokumen
regulasi kanonik di `Hukum/`. Setiap RPM melewati validasi berlapis
sebelum dapat diekspor ke DOCX.

Acuan spesifikasi: `AGENTS.md`.

## Pratinjau

![Beranda](docs/screenshots/beranda.png)
![Hasil generate yang tervalidasi](docs/screenshots/hasil-generate.png)

## Status data (terverifikasi 2026-10-08)

- 6592 fragmen sumber, 3060 CP, 9 dokumen regulasi
- 1208 test pytest (51 berkas), uji frontend Node 163/163
- Backend Flask berjalan normal (`/api/health`), antarmuka web di `/app`

## Persyaratan

- Python 3.10 atau lebih baru (periksa dengan `python3 --version`)
- Git
- Gateway 9Router yang berjalan di `http://localhost:20128` — hanya
  diperlukan untuk pembuatan RPM baru. Tanpa gateway, aplikasi tetap
  dapat dibuka dan dipakai untuk melihat riwayat, pratinjau, serta
  ekspor DOCX.
- (Opsional) `tesseract-ocr` untuk audit kualitas OCR
- Pustaka Python yang tercantum di `requirements.txt`

## Pemasangan

### 1. Unduh repositori

```bash
git clone https://github.com/demile02/rpm-generator.git
cd rpm-generator
```

### 2. Pasang 9Router

Ikuti panduan pemasangan pada https://github.com/decolua/9router
hingga gateway berjalan di `http://localhost:20128`.

### 3. Pasang dependensi Python

```bash
python3 -m pip install -r requirements.txt
```

Catatan: versi `PyPDF2==4.0.0` tidak tersedia di PyPI, sehingga
repositori ini memakai `PyPDF2==3.0.1` (versi terakhir yang tersedia;
pustaka ini tidak dipanggil langsung oleh kode).

### 4. Isi berkas `.env`

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

Buka berkas `.env` dengan editor teks, lalu isi:

| Variabel | Keterangan |
|---|---|
| `NINE_ROUTER_API_KEY` | Kunci API 9Router. Wajib diisi jika gateway mengaktifkan pemeriksaan kunci; boleh dikosongkan jika tidak. |
| `NINE_ROUTER_BASE_URL` | Alamat gateway. Biarkan `http://localhost:20128` jika gateway berjalan di komputer yang sama. |
| `NINE_ROUTER_COMBO` | Jangan diubah, tetap `rpm`. |
| `NINE_ROUTER_TIMEOUT` | Batas waktu tiap percobaan AI dalam detik. Biarkan `120`. |
| `NINE_ROUTER_MAX_RETRIES` | Jumlah percobaan ulang. Biarkan `2`. |

Berkas `.env` tidak boleh diunggah ke GitHub (sudah tercantum di
`.gitignore`).

## Penggunaan

Jalankan perintah berikut satu per satu di terminal, dari dalam folder
proyek. Setiap blok kode di bawah siap disalin-tempel.

### 1. Jalankan server

```bash
python3 src/app.py
```

Biarkan terminal ini tetap terbuka selama aplikasi dipakai.

### 2. Pastikan server menyala

Buka terminal kedua, lalu jalankan:

```bash
curl http://localhost:5000/api/health
```

Hasil yang benar:

```json
{"status":"healthy","database":"connected","fragments":6592}
```

Jika hasilnya seperti itu, lanjut ke langkah 3. Jika terminal
menjawab `Failed to connect`, berarti server langkah 1 belum jalan.

### 3. Buka aplikasi

Buka tautan berikut di peramban:

```text
http://localhost:5000/app
```

### 4. Isi profil (pertama kali saja)

1. Pada halaman Beranda, isi kartu Profil (nama penyusun, satuan
   pendidikan, semester, tahun pelajaran).
2. Klik `Simpan Profil`.

Profil tersimpan di peramban, tidak perlu diisi ulang setiap kali
membuka aplikasi.

### 5. Unggah buku ajar

1. Pada kartu `Koleksi Buku Ajar` di Beranda, klik `Pilih file`,
   pilih PDF/DOCX buku (maks. 10 MB).
2. Klik `Upload buku`.
3. Jadikan buku utama dengan tombol `Jadikan default` agar otomatis
   terpilih saat membuat RPM.

### 6. Buat RPM pertama

1. Klik menu `Buat RPM`.
2. Pilih sistem pendidikan, jenjang, kelas, mata pelajaran, dan elemen.
   Fase terisi otomatis dari kelas.
3. Pilih buku sumber materi dan atur jumlah asesmen bila perlu.
4. Klik `Generate RPM`, tunggu hingga layar hasil tampil.
5. Periksa isi, lalu klik `Simpan perubahan` untuk menyimpan versi
   final.

### 7. Unduh sebagai DOCX

Pada layar hasil, klik `Export DOCX`. Berkas hanya dapat diunduh
setelah hasil lolos validasi.

### 8. Memeriksa pemasangan (opsional)

```bash
python3 -m pytest tests/ -q
node ui/tests/frontend.test.js
```

## API (ringkasan)

- `GET /api/health`, `GET /api/stats`
- Kurikulum: `GET /api/systems`, `GET /api/subjects/<system>`,
  `GET /api/curriculum/options`, `GET /api/cp/<subject>/<phase>`,
  `POST /api/context/generate`
- Pembuatan: `POST /api/module/generate`,
  `GET /api/generation/status/<job_id>`
- Modul: `GET /api/modules`, `GET/PUT/DELETE /api/module/<id>`,
  `POST /api/module/<id>/regenerate`,
  `POST /api/module/<id>/finalize`,
  `GET /api/module/<id>/export-docx` (hanya untuk hasil final yang
  tervalidasi)
- Versi: `GET/POST /api/module/<id>/versions`,
  `GET/DELETE /api/module/<id>/versions/<no>`,
  `POST .../restore`
- Arsip: `POST /api/modules/<id>/archive|unarchive`
- Impor RPM: `POST /api/modules/import` (DOCX/PDF, maks. 10 MB)
- Buku ajar: `GET /api/buku`, `POST /api/buku/upload`
- Log: `GET/DELETE /api/generations`, `GET/DELETE /api/generations/<id>`

## Struktur proyek

```text
Hukum/            9 PDF regulasi kanonik (jangan diubah)
db/               rpm_generator.db (data universal disertakan di Git),
                  curriculum_mappings.json, document_registry.json,
                  extracted_fragments.json, tessdata/, source_documents/
templates/        Templatku.docx (acuan tata letak DOCX, ikut di Git)
src/              app.py, module_generation_pipeline.py,
                  curriculum_engine.py, curriculum_context.py,
                  rule_engine.py, pdf_extraction.py,
                  nine_router_client.py, module_store.py,
                  docx_renderer.py, db_initialization.py,
                  rpm_importer.py, buku_ajar.py
ui/               index.html, styles.css, app.js, api.js, render.js,
                  fonts/ + vendor-*.js lokal (offline-first),
                  tests/frontend.test.js
tests/            51 berkas pytest
AGENTS.md         spesifikasi dan aturan kerja
Design.md         token visual Atelier Glass
```

## Aturan penting

- Jangan mengubah backend/API/basis data untuk tugas frontend;
  demikian pula sebaliknya.
- CP tidak dibuat maupun diparafrasa oleh AI; TP utama minimal C3
  (aturan aplikasi).
- `Templatku.docx` hanya acuan tata letak, bukan sumber fakta
  kurikulum.
- Jangan mengunggah `.env`, kunci API, atau informasi rahasia apa pun.
