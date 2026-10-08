# RPP/RPM Generator — Pembelajaran Mendalam

Generator **RPP/RPM (Rencana Pembelajaran Mendalam)** berbasis AI untuk
sekolah dan madrasah Indonesia. Sistem memisahkan penuh dua jalur
pendidikan — **Kemendikdasmen (sekolah umum)** dan **Kemenag
(madrasah)** — dan menghasilkan dokumen yang mengikuti struktur RPM
resmi dengan provenance data kurikulum yang dapat ditelusuri.

> **Sumber kebenaran (source of truth):** `AGENTS.md`. Semua struktur,
> istilah, dan aturan validasi mengikuti spesifikasi di sana.

## ✨ Karakteristik Produk

- **Output utama = RPP/RPM Pembelajaran Mendalam** — bukan Modul Ajar.
- **Kerangka Pembelajaran Mendalam** (Permendikdasmen No. 13/2025):
  praktik pedagogis, kemitraan, lingkungan pembelajaran, pemanfaatan
  digital; pengalaman belajar **memahami / mengaplikasi / merefleksi**
  (bukan tahap awal-inti-penutup); prinsip berkesadaran, bermakna,
  menggembirakan sebagai *prinsip*, bukan tahap.
- **8 Dimensi Profil Lulusan** (Permendikdasmen No. 10/2025) untuk
  **kedua** sistem: Keimanan & Ketakwaan, Kewargaan, Penalaran Kritis,
  Kreativitas, Kolaborasi, Kemandirian, Kesehatan, Komunikasi.
- **KBC (Kurikulum Berbasis Cinta) hanya untuk madrasah** — layer
  *tambahan* (tema Panca Cinta + materi insersi), **bukan** pengganti
  8 Dimensi (Kepdirjen Pendis No. 6077/2025).
- **Kesatuan pembelajaran = unit pembelajaran**, bukan 1 bab = 1 dokumen.
- **AI hanya menyusun konten pedagogis**; seluruh data normatif (CP,
  TP, fase, elemen, dimensi profil, versi kurikulum) berasal dari DB
  yang teregestrasi dan divalidasi multi-layer sebelum disimpan.

## 🗂️ Sumber Regulasi Kanonik (`Hukum/`)

Sembilan dokumen di folder `Hukum/` adalah **satu-satunya** sumber
regulasi (terekam di `db/document_registry.json` dengan hash + provenance):

| ID | Dokumen | Cakupan |
|---|---|---|
| `REG-KEMENDIKDASMEN-010-2025` | Permendikdasmen No. 10/2025 — 8 Dimensi Profil Lulusan | Sekolah umum |
| `REG-KEMENDIKDASMEN-012-2025` | Permendikdasmen No. 12/2025 | Sekolah umum |
| `REG-KEMENDIKDASMEN-013-2025` | Permendikdasmen No. 13/2025 — Pembelajaran Mendalam | Sekolah umum |
| `REG-KEMENDIKDASMEN-001-2026` | Permendikdasmen No. 1/2026 | Sekolah umum |
| `REG-KEMENDIKDASMEN-BSKAP-046-2025` | Kepka BSKAP No. 046/H/KR/2025 — PPA | Sekolah umum |
| `REG-KEMENDIKDASMEN-BKPDM-020-2026` | BKPDM No. 020/2026 — **mengubah CP Pendidikan Agama dan Budi Pekerti** dalam 046/H/KR/2025 | SD/SMP/SMA |
| `REG-KEMENAG-1503-2025` | KMA No. 1503/2025 — Kurikulum madrasah (versi `KMA-1503-2025`) | Madrasah |
| `REG-KEMENAG-PENDIS-9941-2025` | Kepdirjen Pendis No. 9941/2025 — CP madrasah | Madrasah |
| `GUIDE-KEMENAG-KBC-6077-2025` | Kepdirjen Pendis No. 6077/2025 — Panduan KBC | Madrasah |

Relasi amendemen (`046/2025 ← 020/2026`) terekam pada kolom
`supersedes_id` dan `supersedes_kind=amends`: 046 tetap menjadi dasar CP
mata pelajaran lain. Dokumen scan (BKPDM 020/2026, KMA 1503/2025) ditangani
pipeline ingest dengan **fallback OCR/vision** per halaman — halaman
scan tidak pernah dianggap "kosong" secara diam-diam; method ekstraksi
per halaman (`text_layer` / `ocr` / `vision`) dicatat sebagai provenance.

## 🏫 Pemisahan School vs Madrasah

| Aspek | KEMENDIKDASMEN (sekolah umum) | KEMENAG (madrasah) |
|---|---|---|
| Versi kurikulum | `KEMENDIKDASMEN-2025` | `KMA-1503-2025` |
| Sumber CP | PPA / kurikulum nasional (DB kemendikdasmen) | Kepdirjen Pendis 9941/2025 |
| Dimensi profil | 8 Dimensi Profil Lulusan | 8 Dimensi Profil Lulusan |
| Layer tambahan | — | KBC (Panca Cinta) sebagai layer terpisah |
| Mapel | Mapel sekolah umum | Mapel madrasah (Akidah Akhlak, Fikih, Al-Qur'an Hadis, SKI, Bahasa Arab) |

Mapping CP, aturan, dan prompt **tidak pernah dicampur** antar sistem;
`education_system` divalidasi sejak request masuk dan menentukan versi
kurikulum, sumber CP, serta gating KBC secara deterministik.

## 🧭 Struktur Output RPM (Master Outline)

```
A. Identitas Modul     — satuan pendidikan, penyusun, mapel, kelas/fase/
                         semester, alokasi waktu, tahun ajaran
B. Identifikasi        — kesiapan murid (input guru apa adanya, atau status
                         data belum tersedia), karakteristik materi,
                         dimensi profil, layer KBC (madrasah)
C. Desain Pembelajaran — CP + provenance, TP + level, KKTP,
                         praktik pedagogis
D. Langkah dan         — per pertemuan: Pembuka → Inti → Penutup,
   Pengalaman Belajar    lalu Prinsip Pembelajaran Mendalam menutup
                         tiap pertemuan
E. Asesmen             — diagnostik (dengan Jawaban Benar), formatif,
                         sumatif (dengan TP/KKTP)
Lampiran               — glosarium (bila ada)
```

## 🚀 Menjalankan mandiri (self-host)

Kebutuhan: Python >=3.10 (teruji 3.14), dan akses gateway 9Router
untuk generate AI (opsional untuk preview/export).

```bash
python3 -m pip install -r requirements.txt
python3 src/app.py            # Flask API + UI di http://localhost:5000
```

Uji seluruh suite:

```bash
python3 -m pytest tests/
node ui/tests/frontend.test.js   # 116 uji frontend Node
```

### Gerbang manual (tanpa CI aktif)

Belum ada workflow CI otomatis; sebelum merge/pindah baseline,
jalankan gerbang ini dan pastikan hijau:

1. `python3 -m pytest tests/ -q`
2. `node ui/tests/frontend.test.js`
3. `python3 -m pytest tests/test_nine_router_client.py -q` (hermetik:
   tidak membaca/menulis `.env` repo)

### Environment (opsional)

| Variabel | Default | Fungsi |
|---|---|---|
| `NINE_ROUTER_API_KEY` | (kosong) | Kunci API 9Router bila gateway membutuhkannya |
| `NINE_ROUTER_BASE_URL` | `http://localhost:20128` | Alamat gateway 9Router |
| `NINE_ROUTER_COMBO` | `rpm` | Kombinasi model (jangan diubah) |
| `RPM_GENERATOR_DB` | `db/rpm_generator.db` | Lokasi database SQLite |

Tanpa gateway AI, aplikasi tetap berjalan: riwayat, pratinjau
RPM tersimpan, dan export DOCX tetap berfungsi. Generate RPM
baru membutuhkan gateway.


## 📁 Struktur Proyek

```
├── Hukum/                       # 9 dokumen regulasi kanonik (JANGAN diubah)
├── db/
│   ├── curriculum_mappings.json # Mapping grade→fase, subject per sistem
│   ├── document_registry.json   # Registry 9 dokumen + provenance + relasi
│   ├── extracted_fragments.json # Fragmen teks hasil ekstraksi PDF Hukum/ (turunan, bisa dibuat ulang)
│   └── rpm_generator.db         # DB kurikulum + modul/log runtime lokal (jangan commit perubahannya)
├── templates/
│   └── Templatku.docx           # Master layout DOCX (acuan visual)
├── src/
│   ├── app.py                   # Flask API + endpoint UI
│   ├── module_generation_pipeline.py  # Pipeline RPM + validator + outline
│   ├── curriculum_engine.py     # Retrieval CP/TP/ATP per sistem
│   ├── curriculum_context.py    # Konteks kurikulum + versi per sistem
│   ├── rule_engine.py           # Aturan pedagogis (C3+, fase, provenance)
│   ├── pdf_extraction.py        # Ingesti PDF + fallback OCR/vision
│   ├── nine_router_client.py    # Klien AI (9Router, combo=rpm)
│   ├── module_store.py          # Persistensi modul (restart-safe)
│   ├── docx_renderer.py         # Render DOCX final tervalidasi
│   └── db_initialization.py     # Bootstrap DB dari registry
├── ui/                          # UI RPM (vanilla JS)
├── tests/                       # Suite pytest
└── AGENTS.md                    # Source of truth spesifikasi
```

## 🔒 Garansi Integritas

- **Provenance penuh**: setiap CP membawa document/fragment/page asal;
  setiap halaman ingest membawa method ekstraksinya.
- **Konsultasi regulasi CP**: saat generate, fragmen resmi dokumen yang
  mengubah/menerangkan CP (BKPDM 020/2026 untuk School; KMA 1503/2025
  untuk Madrasah) diambil deterministik dari DB dengan provenance utuh,
  disuntikkan ke prompt AI, dan terekam di
  `regulatory_consultation` (ditampilkan di section C).
- **Field terlindungi**: CP, fase, elemen, subject, versi kurikulum,
  dimensi profil, dan `regulatory_consultation` tidak dapat diubah AI
  maupun klien (PUT revalidasi penuh).
- **AI tidak pernah mengarang normatif**: dimensi profil difilter ke
  daftar normatif; tema KBC hanya dari daftar Panca Cinta normatif.
- **KBC gating deterministik**: layer KBC wajib ada untuk madrasah dan
  *error* bila muncul di konteks sekolah umum.
