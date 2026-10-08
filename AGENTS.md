# AGENTS.md

## PROJECT: AI RPP / RPM PEMBELAJARAN MENDALAM

Aplikasi ini adalah generator perencanaan pembelajaran berbasis AI untuk sekolah dan madrasah Indonesia.

Terminologi kerja:
- **RPP/RPM** = dokumen perencanaan pembelajaran.
- **RPM (Rencana Pembelajaran Mendalam)** adalah istilah kerja untuk perencanaan pembelajaran yang menggunakan pendekatan Pembelajaran Mendalam; regulasi menetapkan komponen minimal perencanaan, bukan mewajibkan nomenklatur “RPM”.
- Produk utama sekarang **bukan Modul Ajar**.

Tujuan utama:
- Menghasilkan RPP/RPM yang sesuai kurikulum dan regulasi yang berlaku.
- Membedakan otoritas Kemendikdasmen dan Kemenag.
- Menjaga CP, fase, elemen, struktur kurikulum, dan data normatif agar tidak dihalusinasi AI.
- Menerapkan kerangka Pembelajaran Mendalam secara benar.
- Untuk madrasah, mengintegrasikan Kurikulum Berbasis Cinta (KBC) tanpa mengganti 8 Dimensi Profil Lulusan.
- Melakukan validasi kurikulum, pedagogis, dan alignment sebelum dokumen final dibuat.
- Menghasilkan DOCX yang siap digunakan atau diedit guru.

## CURRENT IMPLEMENTATION STATUS

Current repository is the working baseline.

### Verified status — 2026-09-27

The following areas are complete and must not be reopened without a
demonstrated regression, failing test, or explicit user request:

- Regulation ingestion, OCR/extraction, source fragments, and provenance.
- Curriculum parser, curriculum database, and curriculum mappings.
- BSKAP 046 active CP mapping and Kemenag CP handling.
- Curriculum/phase/subject validation.
- RPM generation pipeline and real 9Router `rpm` integration.
- Bounded stage regeneration/recovery and measured reliability work.
- Generation logs and prompt versioning.
- Final validation and protected-field/immutability checks.
- DOCX renderer and `Templatku.docx` layout fidelity.
- Web/DOCX content parity.
- DOCX export follows the active/latest RPM version, with explicit version override support.
- Version history, view/save cycle, immutable versions, and optimistic version handling.
- History UI no longer exposes per-row Restore controls.
- Regenerate/Finalize loading, success, failure, timeout, and anti-double-click states.
- Teacher-entered `Kesiapan Murid` is preserved verbatim and is never used as an AI diagnosis.
- Readiness is wired through Praktik Pedagogis, Aktivitas, and Asesmen generation.
- Real-AI readiness A/B test verified substantive, relevant adaptation while CP/TP/KKTP/topik remained fixed.
- Latest verified test checkpoint: pytest **1089 passed, 10 skipped**; frontend Node tests **74/74**.

Current limitations / next work:
- Repository-local Anti-Slop skills are available as agent guidance, but the runtime
  `AntiSlopProcessor` is currently an internal implementation and is not yet a
  direct execution of the Markdown skill rules. Runtime integration is a separate
  controlled task and must preserve protected/normative fields.
- The next product work is UI/UX redesign; existing RPM Web Preview A–E structure
  must not be changed unless explicitly requested.

Important:
- Real-AI reliability is measured, not guaranteed on every model attempt.
- Invalid model output must continue to be rejected; never weaken
  validation to increase the success rate.
- Do not reopen completed ingestion, OCR, parser, provenance, registry,
  or database work unless:
  - a test fails;
  - a regression is demonstrated; or
  - the user explicitly requests that area.

Do not fix unrelated technical debt.

Do not expand scope after the requested task is complete.

When acceptance criteria are satisfied, STOP.

==================================================
1. SOURCE OF TRUTH REGULASI
==================================================

Folder `Hukum/` pada ROOT PROJECT adalah **SOURCE OF TRUTH utama** untuk regulasi yang digunakan aplikasi.

Jangan lagi menganggap dokumen hukum lama yang pernah diproses sebagai sumber kanonik jika sudah digantikan oleh dokumen di `Hukum/`.

Dokumen turunan/cache/extracted lama boleh dibuang atau dibuat ulang bila diperlukan, tetapi:
- jangan menghapus PDF kanonik di `Hukum/`;
- jangan mengganti dokumen kanonik dengan hasil OCR/ekstraksi;
- jangan menganggap file lama lebih benar daripada dokumen di `Hukum/` tanpa verifikasi.

9 dokumen kanonik:

KEMENDIKDASMEN:
1. `Permendikdasmen No. 10 Tahun 2025.pdf`
2. `Permendikdasmen No. 12 Tahun 2025.pdf`
3. `Permendikdasmen No. 13 Tahun 2025.pdf`
4. `Permendikdasmen No. 1 Tahun 2026.pdf`
5. `Kepka BSKAP No.046_H_KR_2025.pdf`
6. `BKPDM No. 020 Tahun 2026.pdf`

KEMENAG:
7. `KMA No. 1503 Tahun 2025.pdf`
8. `Kepdirjen Pendis No. 9941 Tahun 2025.pdf`
9. `Kepdirjen Pendis No. 6077 Tahun 2025.pdf`

==================================================
2. PDF INGESTION DAN PDF SCAN
==================================================

Agent WAJIB mampu membaca PDF yang:
- memiliki text layer;
- merupakan hasil scan/gambar;
- campuran text layer + gambar.

Jangan menyimpulkan PDF “kosong” hanya karena ekstraksi teks biasa menghasilkan sedikit atau tidak ada teks.

Pipeline minimal:

PDF
 ↓
cek text layer
 ↓
text cukup?
 ├─ ya → ekstraksi teks
 └─ tidak → render halaman + OCR/vision
 ↓
normalisasi dan simpan source fragments

Untuk setiap fragment regulasi simpan minimal:
- document_id
- page_number
- section
- paragraph/locator bila tersedia
- text
- extraction_method (`text_layer`, `ocr`, atau `vision`)
- hash

Jika OCR/vision menghasilkan teks yang meragukan:
- jangan diam-diam memperbaiki isi normatif;
- simpan teks hasil ekstraksi;
- pertahankan nomor halaman;
- tandai confidence/quality bila pipeline mendukung.

==================================================
3. 9 DOKUMEN DAN FUNGSI REGULASINYA
==================================================

### Permendikdasmen No. 10 Tahun 2025

Fungsi:
- Standar Kompetensi Lulusan.
- dasar 8 Dimensi Profil Lulusan.

8 dimensi:
- keimanan dan ketakwaan terhadap Tuhan Yang Maha Esa
- kewargaan
- penalaran kritis
- kreativitas
- kolaborasi
- kemandirian
- kesehatan
- komunikasi

### Permendikdasmen No. 12 Tahun 2025

Fungsi:
- Standar Isi.
- ruang lingkup materi dan landasan isi pembelajaran.

Jangan menjadikan dokumen ini sebagai pengganti dokumen CP mata pelajaran.

### Permendikdasmen No. 13 Tahun 2025

Fungsi:
- perubahan atas regulasi kurikulum;
- kerangka dasar kurikulum;
- pendekatan Pembelajaran Mendalam.

### Permendikdasmen No. 1 Tahun 2026

Fungsi:
- Standar Proses;
- perencanaan pembelajaran;
- pelaksanaan pembelajaran;
- penilaian proses pembelajaran.

Komponen minimal dokumen perencanaan:
1. Tujuan pembelajaran
2. Langkah pembelajaran
3. Penilaian/asesmen pembelajaran

### Kepka BSKAP No. 046/H/KR/2025

Fungsi:
- sumber CP nasional untuk mata pelajaran yang berada di bawah Kemendikdasmen sesuai dokumen keputusan.
- berlaku sebagai dasar CP selain bagian yang kemudian diubah secara khusus oleh BKPDM 020/2026.

### BKPDM No. 020 Tahun 2026

Fungsi:
- perubahan CP **Pendidikan Agama dan Budi Pekerti** pada CP nasional.

PENTING:
- jangan memperlakukan 020/2026 sebagai pengganti total 046/H/KR/2025;
- 046/H/KR/2025 tetap digunakan untuk CP lain yang tidak diubah;
- gunakan 020/2026 hanya dalam konteks CP Agama dan Budi Pekerti Kemendikdasmen.

### KMA No. 1503 Tahun 2025

Fungsi:
- pedoman implementasi kurikulum madrasah;
- payung kurikulum untuk RA, MI, MTs, MA, MAK;
- konteks Pembelajaran Mendalam dan Kurikulum Berbasis Cinta di madrasah.

Jangan mengambil teks CP PAI/Bahasa Arab langsung dari KMA 1503 jika teks CP tersedia pada Kepdirjen Pendis 9941/2025.

### Kepdirjen Pendis No. 9941 Tahun 2025

Fungsi:
- sumber CP PAI dan Bahasa Arab pada madrasah.

Mencakup antara lain:
- Al-Qur'an Hadis
- Akidah Akhlak
- Fikih
- SKI
- Bahasa Arab

CP harus disimpan sebagai data normatif dengan provenance.

### Kepdirjen Pendis No. 6077 Tahun 2025

Fungsi:
- Panduan Kurikulum Berbasis Cinta.
- Panca Cinta / lima tema KBC.
- strategi dan contoh integrasi KBC ke pembelajaran madrasah.

Panduan ini adalah acuan pembelajaran KBC, tetapi contoh/format dalam panduan tidak boleh diperlakukan sebagai satu-satunya template wajib.

==================================================
4. SEKOLAH VS MADRASAH
==================================================

Aplikasi WAJIB membedakan:

1. `KEMENDIKDASMEN`
2. `KEMENAG`

Contoh:
- SMP → KEMENDIKDASMEN
- SMA → KEMENDIKDASMEN
- MI → KEMENAG
- MTs → KEMENAG
- MA → KEMENAG

Jangan mencampur jalur kurikulum.

### CP sekolah umum

Mapel umum:
- gunakan Kepka BSKAP 046/H/KR/2025.

Pendidikan Agama dan Budi Pekerti:
- gunakan CP yang berlaku setelah perubahan BKPDM 020/2026.

### CP madrasah

Mapel umum:
- gunakan CP nasional yang sesuai (BSKAP 046/H/KR/2025).

PAI dan Bahasa Arab:
- gunakan Kepdirjen Pendis 9941/2025.

Jangan menggunakan CP PAI-BP Kemendikdasmen untuk menggantikan CP Akidah Akhlak/Fikih/Al-Qur'an Hadis/SKI/Bahasa Arab madrasah.

==================================================
5. CURRICULUM ENGINE
==================================================

Curriculum Engine BUKAN AI.

Harus berupa:
- database
- aturan
- mapping
- versioning
- validasi
- provenance

AI tidak boleh menentukan sendiri:
- fase
- jenjang
- mata pelajaran
- elemen
- CP resmi
- versi kurikulum
- status regulasi

Pipeline konseptual:

Regulation Registry
        ↓
Curriculum Database
        ↓
Curriculum Engine
        ↓
Curriculum Context
        ↓
AI / Generation
        ↓
Pedagogical Validation
        ↓
Anti-Slop / Humanization
        ↓
Final Validation
        ↓
DOCX Renderer

==================================================
6. REGULATION REGISTRY
==================================================

Setiap regulasi memiliki versioning.

Minimal field:

regulations
- id
- authority
- regulation_type
- regulation_number
- title
- year
- effective_date
- status
- supersedes_id
- source_url
- local_file
- document_hash
- created_at
- updated_at

Status:
- draft
- active
- superseded
- revoked

Validitas harus ditentukan dari:
- nomor regulasi
- tanggal
- status
- hubungan dengan regulasi sebelumnya
- sumber resmi

Jangan menentukan validitas hanya dari nama file atau tanggal file.

==================================================
7. GRADE → PHASE
==================================================

Mapping fase dikontrol sistem.

Jangan menggunakan input free-text untuk fase jika fase dapat ditentukan dari kelas/jenjang.

Contoh mapping umum:

MI kelas 1–2 → Fase A
MI kelas 3–4 → Fase B
MI kelas 5–6 → Fase C
MTs kelas 7–9 → Fase D
MA kelas 10 → Fase E
MA kelas 11–12 → Fase F

SMP kelas 7–9 → Fase D
SMA kelas 10 → Fase E
SMA kelas 11–12 → Fase F

Gunakan pemetaan yang benar-benar sesuai regulasi/CP mata pelajaran jika dokumen sumber memberikan ketentuan khusus.

Jika grade tidak sesuai fase:
→ validation error.

AI tidak boleh mengganti fase secara bebas.

==================================================
8. SUBJECT IDENTITY
==================================================

Identitas mata pelajaran harus terikat pada:
- education_system
- institution_type
- education_level
- curriculum_version
- phase
- subject
- element

Tujuannya mencegah pencampuran:
- PAI sekolah
- Akidah Akhlak madrasah
- Fikih madrasah
- Al-Qur'an Hadis madrasah
- SKI madrasah
- Bahasa Arab madrasah
- dan padanan mata pelajaran lain.

==================================================
9. CP
==================================================

CP resmi adalah DATA NORMATIF.

Database minimal:

learning_outcomes
- id
- curriculum_version_id
- education_system
- institution_type
- education_level
- subject_id
- phase_id
- element_id
- text
- source_document_id
- source_fragment_id
- source_page
- source_section
- version
- status

Aturan:
- CP tidak dibuat AI.
- CP tidak diparafrasekan.
- CP tidak di-humanisasi.
- CP tidak diproses Anti-Slop.
- CP tidak digabung dari regulasi lama secara sembarangan.
- CP tidak boleh dipotong sehingga mengubah makna.

AI hanya menerima CP yang sudah dipilih Curriculum Engine sebagai context.

Setiap CP wajib memiliki provenance.

==================================================
10. TP
==================================================

TP dapat berasal dari:
- teacher
- school
- imported
- ai_generated

Gunakan `source_type`:
- teacher
- school
- imported
- ai_generated

TP harus berhubungan dengan:
- CP
- phase
- subject
- element
- unit pembelajaran / topik

### Quality rule aplikasi

TP generator minimum C3.

Ini adalah QUALITY RULE aplikasi, bukan klaim bahwa pemerintah menetapkan semua TP harus minimum C3.

Bloom revisi:
- C1 Remember
- C2 Understand
- C3 Apply
- C4 Analyze
- C5 Evaluate
- C6 Create

TP utama hasil generator:
- C3
- C4
- C5
- C6

TP C1/C2 tidak boleh menjadi TP utama generator.

Validator harus memahami konteks kalimat, bukan sekadar mencari satu kata.

==================================================
11. UNIT PEMBELAJARAN
==================================================

RPM tidak wajib dibuat satu bab = satu RPM.

Gunakan konsep **unit pembelajaran** sebagai satu kesatuan pembelajaran yang dirancang untuk mencapai tujuan tertentu.

Satu unit pembelajaran dapat berupa:
- satu subtopik;
- satu bab;
- beberapa subtopik;
- gabungan topik yang saling berkaitan;
- satu rangkaian projek;
- beberapa pertemuan dalam satu tujuan/rangkaian belajar.

Dasarnya adalah keterkaitan tujuan, langkah pembelajaran, dan asesmen, bukan batas halaman buku.

==================================================
12. MASTER OUTLINE RPM
==================================================

Master outline yang digunakan:

A. IDENTITAS
- satuan pendidikan
- mata pelajaran
- fase/kelas
- semester
- alokasi waktu
- tahun ajaran
- penyusun

B. IDENTIFIKASI
- kesiapan murid
- karakteristik materi
- Dimensi Profil Lulusan yang relevan

C. DESAIN PEMBELAJARAN
- CP
- Tujuan Pembelajaran
- topik/konteks
- praktik pedagogis
- kemitraan pembelajaran
- lingkungan pembelajaran
- pemanfaatan digital

D. PENGALAMAN BELAJAR / LANGKAH PEMBELAJARAN
- Memahami
- Mengaplikasi
- Merefleksi
- prinsip pembelajaran: berkesadaran, bermakna, menggembirakan

E. ASESMEN
- asesmen awal
- asesmen proses
- asesmen akhir

CATATAN:
- Ini adalah master outline kerja.
- Format visual dapat berubah sesuai kebutuhan sekolah/madrasah.
- Jangan menganggap seluruh field di atas sebagai komponen minimal Pasal 5.
- Komponen minimal dokumen perencanaan menurut Permendikdasmen No. 1 Tahun 2026 tetap: tujuan, langkah, asesmen.

==================================================
13. PEMBELAJARAN MENDALAM
==================================================

### Prinsip pembelajaran

Tiga prinsip:
1. Berkesadaran
2. Bermakna
3. Menggembirakan

Ketiganya adalah prinsip pembelajaran, bukan tiga tahap kegiatan yang wajib berurutan.

### Pengalaman belajar

Tiga pengalaman belajar:
1. Memahami
2. Mengaplikasi
3. Merefleksi

Jangan menyamakan:
- Berkesadaran = kegiatan awal
- Bermakna = kegiatan inti
- Menggembirakan = kegiatan penutup

Jangan memaksa format awal–inti–penutup jika tidak diperlukan.

==================================================
14. DIMENSI PROFIL LULUSAN
==================================================

8 Dimensi Profil Lulusan tetap menjadi sasaran profil lulusan dalam konteks Pembelajaran Mendalam.

Jangan mengganti 8 Dimensi Profil Lulusan dengan Panca Cinta.

Jangan membuat Panca Cinta sebagai “dimensi ke-9, ke-10, dst.”.

==================================================
15. KBC UNTUK MADRASAH
==================================================

KBC hanya berlaku sebagai integrasi khusus untuk madrasah.

Panca Cinta / lima tema KBC:
1. Cinta Allah dan Rasul-Nya
2. Cinta Ilmu
3. Cinta Lingkungan
4. Cinta Diri dan Sesama
5. Cinta Tanah Air

Posisi KBC:

8 Dimensi Profil Lulusan
        +
Tema KBC / Panca Cinta
        ↓
Pembelajaran madrasah

Panca Cinta BUKAN pengganti 8 Dimensi Profil Lulusan.

Dalam RPM madrasah, unsur KBC dapat ditampilkan sebagai:
- Tema KBC / Panca Cinta
- Materi Insersi
- integrasi nilai dalam tujuan/kegiatan/konteks yang relevan

Jangan memaksa semua tema Panca Cinta masuk ke satu unit pembelajaran.
Gunakan tema yang relevan dengan CP, tujuan, materi, dan konteks.

Jangan mengubah CP menjadi “CP berbasis cinta”.

Panduan KBC memuat contoh implementasi dan contoh rancangan pembelajaran. Contoh tersebut bukan satu-satunya format wajib.

==================================================
16. KERANGKA PEMBELAJARAN
==================================================

Dalam desain pembelajaran, pertimbangkan:

### Praktik pedagogis
Strategi/model/metode yang dipilih untuk mencapai tujuan.

### Kemitraan pembelajaran
Pihak yang terlibat bila relevan.

### Lingkungan pembelajaran
Lingkungan fisik, sosial-budaya, virtual, atau kombinasi yang mendukung pembelajaran.

### Pemanfaatan digital
Teknologi digital bila relevan dan tersedia.

Jangan memaksakan teknologi atau kemitraan yang tidak realistis terhadap konteks sekolah/madrasah.

==================================================
17. IDENTIFIKASI KESIAPAN MURID
==================================================

Identifikasi kesiapan murid harus relevan dengan pembelajaran.

Dapat mencakup:
- pengetahuan awal
- keterampilan awal
- motivasi
- kondisi emosional
- kondisi sosial
- informasi lain yang relevan

Tidak wajib selalu berupa angka atau sebaran nilai.

Jangan mengarang hasil asesmen awal.

Jika data aktual tidak tersedia:
→ nyatakan bahwa data kesiapan belum tersedia.

==================================================
18. ASESMEN
==================================================

Gunakan tiga posisi utama:
- asesmen awal
- asesmen proses
- asesmen akhir

Asesmen harus memberikan bukti ketercapaian tujuan pembelajaran.

Jangan menilai aktivitas semata-mata jika aktivitas tersebut bukan bukti yang sesuai dengan tujuan.

Jangan memaksakan asesmen sumatif di setiap pertemuan.

==================================================
19. ALIGNMENT
==================================================

Alignment minimal:

CP
 ↓
TP
 ↓
Pengalaman belajar / aktivitas
 ↓
Asesmen

Untuk setiap TP harus jelas:
- apa yang harus dicapai;
- pengalaman apa yang memungkinkan murid mencapainya;
- bukti apa yang menunjukkan ketercapaian.

Jika madrasah menggunakan KBC:

CP
 ↓
TP
 ↓
Panca Cinta / Materi Insersi yang relevan
 ↓
Pengalaman belajar
 ↓
Asesmen

KBC tidak boleh dipasang sebagai dekorasi tanpa hubungan dengan pembelajaran.

==================================================
20. RULE ENGINE
==================================================

Rule registry harus memisahkan:

A. RULE REGULASI
Aturan yang benar-benar berasal dari dokumen resmi.

B. QUALITY RULE APLIKASI
Aturan kualitas yang dipilih aplikasi dan tidak boleh diklaim sebagai kewajiban pemerintah.

Contoh quality rule:
- TP minimum C3.
- alignment TP–asesmen.
- konteks pembelajaran harus realistis.

Jangan menulis quality rule sebagai “wajib menurut peraturan” jika tidak ada dasar eksplisit.

==================================================
21. VALIDATION BEHAVIOR
==================================================

Jika ditemukan:
- CP tanpa sumber resmi
- fase tidak cocok
- subject tidak cocok dengan education_system
- TP tidak selaras dengan CP
- TP utama C1/C2
- aktivitas tidak mendukung TP
- asesmen tidak mengukur TP

→ REJECT / validation error.

Jika invalid:
1. tampilkan validation report;
2. kirim error terstruktur ke generator bila perlu;
3. perbaiki bagian invalid;
4. validasi ulang.

Jangan render dokumen invalid.

==================================================
22. CURRICULUM CONTEXT
==================================================

Sebelum memanggil AI, Curriculum Engine harus menghasilkan context terstruktur, minimal mencakup:

{
  "education_system": "KEMENAG",
  "institution_type": "MA",
  "grade": "XI",
  "phase": "F",
  "subject": "Akidah Akhlak",
  "element": "...",
  "curriculum_version": "KMA-1503-2025",
  "cp": {
    "id": "...",
    "text": "...",
    "source_document_id": "...",
    "source_fragment_id": "..."
  },
  "profile_dimensions": [],
  "kbc": {
    "enabled": true,
    "themes": [],
    "insertion_material": []
  }
}

AI tidak boleh menerima input kurikulum mentah tanpa context yang telah divalidasi.

==================================================
23. AI / 9ROUTER
==================================================

Gunakan 9router sebagai AI Gateway.

AI menerima:
- Curriculum Context
- input pengguna
- aturan generation
- output schema
- validation rules
- sumber bahan ajar user jika fitur sumber konten digunakan

AI TIDAK boleh menjadi sumber:
- CP
- regulasi
- fase
- elemen
- struktur kurikulum
- nomor regulasi
- KBC fact normatif
- bahan ajar yang tidak tersedia dalam sumber user

Jika data normatif tidak ditemukan:
→ jangan mengarang.

==================================================
24. SOURCE MATERIAL USER
==================================================

Sumber regulasi dan sumber bahan ajar adalah dua hal yang berbeda.

Sumber regulasi:
- berasal dari `Hukum/` dan registry.

Sumber bahan ajar:
- disediakan user melalui PDF/DOCX/TXT/MD bila fitur konten digunakan.

AI tidak melakukan browsing bebas untuk mencari bahan ajar jika aplikasi mengharuskan sumber user.

Jika sumber bahan ajar tidak tersedia:
→ tandai gap secara jujur.

==================================================
25. ANTI-SLOP / HUMANIZATION
==================================================

ANTI-SLOP HAS TWO DISTINCT LAYERS.

A. AGENT SKILL
- repository-local rules live under `skills/antislop/`;
- this skill applies to coding-agent output;
- it is not itself the RPM runtime processor.

B. RPM RUNTIME
- production RPM generation uses an Anti-Slop processor after pedagogical
  validation and before final validation;
- the runtime processor may use repository-local Anti-Slop rules as its policy
  source, but Markdown skill files must not be treated as executable code
  without an explicit adapter/implementation;
- do not silently replace the existing runtime processor without regression
  tests.

Runtime pipeline:

AI Generation
↓
Pedagogical Validation
↓
Anti-Slop / Humanization
↓
Final Validation

Anti-Slop runtime is allowed ONLY on AI-generated mutable/narrative content.

Allowed examples:
- activity descriptions;
- pedagogical narratives;
- trigger questions;
- reflection;
- remedial/enrichment narrative;
- other AI-generated prose that is explicitly classified as humanizable.

NEVER Anti-Slop: 
- CP;
- source/provenance;
- phase;
- grade;
- subject;
- element;
- curriculum version;
- regulation metadata;
- TP/KKTP protected metadata;
- KBC normative metadata;
- answer keys;
- scoring metadata;
- citations/reference metadata;
- normative numbers/dates;
- Qur'an/Hadith text or other protected quotations;
- teacher input that must remain verbatim, including `Kesiapan Murid`;
- database/source records themselves.

Database records are authoritative input, not Anti-Slop targets.

After Anti-Slop:
- final validation MUST run again;
- protected fields MUST remain unchanged;
- alignment and normative validation MUST still pass;
- if final validation fails, the result MUST NOT be rendered or returned as success.

The goal is humanized language without changing facts, targets, provenance,
meaning, cognitive metadata, assessment criteria, or regulatory content.

==================================================
26. FINAL VALIDATOR
==================================================

Setelah Anti-Slop:
- validasi ulang alignment;
- validasi CP;
- validasi provenance;
- validasi phase/subject;
- validasi cognitive level;
- validasi KBC bila madrasah.

Jika gagal:
→ jangan render.

==================================================
27. PROVENANCE
==================================================

Semua data kurikulum penting harus dapat ditelusuri minimal ke:
- document_id
- page
- section
- source_fragment_id

Contoh:

CP Akidah Akhlak Fase D
→ Kepdirjen Pendis 9941/2025
→ halaman X
→ section Akidah Akhlak
→ source_fragment_id

Untuk KBC:

Tema KBC
→ Kepdirjen Pendis 6077/2025
→ halaman/section terkait
→ source_fragment_id

==================================================
28. DATABASE
==================================================

Database aktual: SQLite (`db/rpm_generator.db` atau lokasi yang sudah dipakai project).

Jangan mengubah database backend hanya karena Agent.md berubah.

Minimal struktur kurikulum:
- curriculum_authorities
- regulations
- education_systems
- education_levels
- grades
- phases
- grade_phases
- curriculum_versions
- subjects
- subject_elements
- source_documents
- source_fragments
- learning_outcomes
- curriculum_materials
- learning_objectives
- learning_sequences
- learning_sequence_items
- curriculum_rules
- cognitive_operators

Struktur dokumen/hasil RPM dapat memakai tabel yang sudah ada atau dimodifikasi sesuai implementasi aktual.

Jangan menghapus migrasi/tabel lama sebelum melakukan repository inspection dan memastikan dependensinya.

==================================================
29. AUDIT LOG
==================================================

Generation logs are implemented through the generation log store.

Minimal traceability:
- generation_id
- stage
- attempt
- model
- provider
- prompt_version
- prompt_hash
- validation_result
- error category when applicable
- final_result
- duration
- created_at

Current implementation requirements:
- One generation ID per `generate()` call.
- Retries use distinct attempt numbers under the same generation ID.
- Prompt version and effective prompt hash are stored for each AI stage.
- Logs must not contain API keys, authorization headers, or secrets.
- Raw prompt/response content is not persisted by default.
- Validation and recovery outcomes remain traceable from the generation log.

Tujuan: setiap RPM dapat ditelusuri proses pembuatannya.

==================================================
30. SECURITY
==================================================

API key tidak boleh berada di frontend.

Gunakan environment variables.

Jangan commit:
- .env
- API key
- service role key
- secret token

==================================================
31. FRONTEND / USER FLOW
==================================================

Current product flow:

Landing Page
↓
Beranda
↓
Buat RPM
↓
Hasil RPM / Editor

Beranda responsibilities:
- show user profile;
- show saved RPM history;
- open/edit saved RPM versions;
- expose export actions where available.

Current profile fields:
- Nama Penyusun
- Satuan Pendidikan
- Semester
- Tahun Pelajaran

Generate flow must preserve the validated curriculum flow:

1. Pilih sistem pendidikan
2. Pilih jenjang/institusi
3. Pilih kelas
4. Sistem menentukan fase
5. Pilih mata pelajaran
6. Pilih elemen bila berlaku
7. Tentukan unit pembelajaran / topik
8. Sistem memuat CP dan context regulasi
9. Sistem menentukan context Profil Lulusan
10. Jika KEMENAG: tampilkan integrasi KBC/Panca Cinta bila relevan
11. Rancang/generate TP dan pengalaman belajar
12. Rancang asesmen
13. Validasi
14. Preview RPM
15. Save/version
16. Export DOCX

Do not make the user fill phase manually when the system can determine it.

WEB PREVIEW RULE
- The final A–E RPM Web Preview layout is currently established.
- Do not restructure A–E, reorder sections, or change document semantics
  during unrelated UI redesign.
- Styling may evolve according to `Design.md`; content/structure requires
  explicit user instruction.

==================================================
32. RENDERING DOCX
==================================================

Output final hanya DOCX.

Renderer menerima hasil FINAL VALIDATED RPM.

Jangan render:
- draft AI
- hasil sebelum validation
- hasil sebelum final validation

Dokumen harus memiliki:
- heading konsisten
- numbering konsisten
- tabel rapi
- page break yang masuk akal
- header/footer bila diperlukan
- lampiran jika dibutuhkan

==================================================
33. ANTI-HALLUCINATION
==================================================

Jika data tidak ditemukan dalam sumber resmi:

JANGAN MENGARANG.

Gunakan:
“Data belum tersedia dalam sumber kurikulum yang terdaftar.”

Jika sumber tambahan diperlukan:
- tandai missing source;
- jangan membuat nomor regulasi tebakan;
- jangan membuat CP tebakan;
- jangan mengarang metadata sumber.

==================================================
34. REFERENCES
==================================================

Jangan mengarang:
- buku
- jurnal
- DOI
- URL
- penulis
- tahun
- penerbit

Jika referensi dibuat dari sumber user:
→ simpan provenance.

Jika tidak dapat diverifikasi:
→ tandai unverified.

==================================================
35. DEVELOPMENT PRINCIPLE
==================================================

Prioritas:
1. Correctness
2. Curriculum compliance
3. Pedagogical alignment
4. Traceability
5. Natural language
6. Visual quality

Jangan mengorbankan correctness demi tampilan.
Jangan mengorbankan provenance demi kemudahan.
Jangan mengubah fakta normatif demi hasil AI yang terlihat lebih natural.

==================================================
36. IMPLEMENTATION ORDER
==================================================

PHASE 1 — Repository inspection
- baca project
- identifikasi stack
- identifikasi database
- identifikasi pipeline lama
- identifikasi dokumen lama

PHASE 2 — Regulation ingestion
- jadikan `Hukum/` source of truth
- ekstrak teks
- fallback OCR/vision untuk scan PDF
- metadata
- hashing
- source fragments

PHASE 3 — Regulation registry
- authority
- regulation
- version
- status
- relationship

PHASE 4 — Curriculum Engine
- education system
- institution
- level
- grade
- phase
- subject
- element
- CP
- KBC context

PHASE 5 — Rule & validation
- phase validation
- subject validation
- provenance
- TP C3+
- alignment

PHASE 6 — RPM context/schema
- identitas
- identifikasi
- desain
- pengalaman belajar
- asesmen
- KBC layer untuk madrasah

PHASE 7 — AI integration

PHASE 8 — RPM generation

PHASE 9 — Pedagogical validation

PHASE 10 — Anti-Slop

PHASE 11 — Final validation

PHASE 12 — DOCX rendering

PHASE 13 — UI/UX refinement

Jangan mengerjakan fase berikutnya dengan mengorbankan correctness fase sebelumnya.

==================================================
37. IMPORTANT AGENT RULES
==================================================

JANGAN:
- mengarang CP;
- mengarang regulasi;
- menganggap AI sebagai sumber kurikulum;
- mencampur Kemenag dan Kemendikdasmen;
- menganggap 046/H/KR/2025 sudah tidak berlaku seluruhnya;
- menggunakan 020/2026 sebagai pengganti seluruh 046/2025;
- menggunakan PAI-BP sekolah sebagai CP Akidah Akhlak/Fikih/Al-Qur'an Hadis/SKI/Bahasa Arab madrasah;
- menjadikan Panca Cinta sebagai dimensi Profil Lulusan baru;
- mengklaim quality rule aplikasi sebagai aturan pemerintah;
- menurunkan TP utama menjadi C1/C2;
- mengubah CP melalui Anti-Slop;
- membuat referensi palsu;
- bypass validation;
- render dokumen invalid;
- menganggap PDF scan tidak terbaca tanpa fallback OCR/vision;
- menghapus PDF kanonik dari `Hukum/`.

WAJIB:
- membaca dokumen sumber;
- menjaga provenance;
- melakukan versioning;
- memvalidasi fase;
- memvalidasi subject;
- memvalidasi CP;
- memvalidasi TP;
- memvalidasi alignment;
- menerapkan prinsip Pembelajaran Mendalam;
- menjaga 8 Dimensi Profil Lulusan;
- untuk madrasah, mengintegrasikan KBC/Panca Cinta secara relevan;
- melakukan final validation setelah Anti-Slop;
- menjaga data normatif tetap utuh.

==================================================
38. CURRENT DEFINITION OF DONE / VERIFIED STATE
==================================================

[x] `Hukum/` menjadi source of truth.
[x] 9 dokumen kanonik terdaftar.
[x] PDF text layer dan PDF scan dapat diproses.
[x] Source fragments memiliki provenance.
[x] Regulation registry tersedia.
[x] Curriculum Engine tidak menggunakan AI untuk data normatif.
[x] Kemenag dan Kemendikdasmen terpisah.
[x] Relasi 046/H/KR/2025 ↔ 020/2026 benar.
[x] CP madrasah PAI/Bahasa Arab berasal dari 9941/2025.
[x] KMA 1503/2025 digunakan sebagai payung kurikulum madrasah.
[x] 6077/2025 digunakan untuk KBC.
[x] Grade → phase tervalidasi.
[x] Subject → education system tervalidasi.
[x] TP minimum C3 sebagai quality rule aplikasi.
[x] TP/aktivitas/asesmen alignment tervalidasi.
[x] Master outline RPM terimplementasi.
[x] 8 Dimensi Profil Lulusan tidak tergantikan oleh KBC.
[x] KBC/Panca Cinta menjadi layer tambahan untuk madrasah.
[x] Teacher readiness handling tervalidasi.
[x] Readiness terhubung ke Praktik Pedagogis, Aktivitas, dan Asesmen.
[x] Anti-Slop menjaga data normatif tetap terlindungi.
[x] Final validation berjalan setelah Anti-Slop.
[x] DOCX dibuat hanya dari FINAL VALIDATED RPM.
[x] Generation logs tersimpan.
[x] Prompt versioning tersimpan dan dapat ditelusuri.
[x] Validation results tersimpan di generation logs.
[x] Tidak ada API secret di frontend/repository.
[x] Web/DOCX parity dan active-version export tervalidasi.
[x] Version history dan view/save cycle tervalidasi.
[x] Process loading/success/failure states tervalidasi.

Current engineering checkpoint:
- pytest: **1089 passed, 10 skipped**
- frontend Node tests: **74/74**

==================================================
39. GLOBAL SKILLS & DESIGN RULES
==================================================

## Skills (antislop - selalu aktif)
Muat & terapkan skill dari ~/skills/ sesuai kebutuhan task:
- UI/frontend → antislop + antislop-ui (+ antislop-layoutmobile bila responsive)
- Menulis/menulis ulang copy → antislop-copywriting
- Membersihkan komentar kode → antislop-code (kode tidak diubah)
- Aksesibilitas → antislop-human
- Sebelum deliver UI → jalankan Delivery Gate (PASS/FAIL) dari antislop core


### FRONTEND DESIGN SOURCE OF TRUTH

[`Design.md`](./Design.md) is the source of truth for the RPM Generator
visual/design system and product UI/UX.

Before delivering a UI task, report:
`UI DELIVERY GATE: PASS / FAIL`

### AGENT SKILL VS RPM RUNTIME

Repository-local skills are instructions/policies for coding agents. They are
not automatically executable production code.

The RPM generation pipeline has a separate runtime Anti-Slop processor.
Its runtime integration must use an explicit adapter/implementation and must
never treat Markdown files as executable code without such an adapter.

==================================================
40. CURRENT NEXT PRIORITY
==================================================

The completed generation, validation, readiness, versioning, and export
baseline must be preserved.

The next product priority is UI/UX redesign using `Design.md`.

### UI/UX SCOPE
- Landing Page.
- Beranda/dashboard.
- User profile moved into Beranda.
- Saved RPM history.
- Create RPM page.
- Existing RPM editor/review/versioning flow.
- Responsive mobile/tablet/desktop experience.

Do not treat the above as completed until implementation and UI verification
pass.

The final RPM Web Preview A–E structure is currently final and must not be
restructured during this redesign unless the user explicitly requests it.
Only its visual styling may be adjusted by the design system when the task
explicitly includes Web Preview styling.

Do not reopen completed curriculum/OCR/parser/provenance/mapping/generation
work unless a regression is demonstrated or the user explicitly requests it.

==================================================
41. MASTER LAYOUT SOURCE OF TRUTH
==================================================

`templates/Templatku.docx` is the MASTER LAYOUT reference for the DOCX output.

Important distinction:

A. REGULATORY SOURCE OF TRUTH
- `Hukum/` remains the source of truth for normative/regulatory content.

B. CONTENT SOURCE OF TRUTH
- the FINAL VALIDATED RPM result is the source of truth for generated content
  shown in Web and exported to DOCX.

C. DOCX LAYOUT SOURCE OF TRUTH
- `templates/Templatku.docx` is the source of truth for DOCX visual/document
  layout.

D. WEB UI/UX SOURCE OF TRUTH
- `Design.md` is the source of truth for application UI/UX.

`Templatku.docx` is NOT a source of curriculum facts or regulatory claims.
Treat it as read-only.

Expected path:
`templates/Templatku.docx`

If the file is missing during a DOCX layout task, STOP. Do not invent a
replacement template.

==================================================
42. WEB PREVIEW LAYOUT RULES
==================================================

The A–E Web Preview layout is currently established and should be treated as
product content/layout baseline.

Do not change during general UI redesign:
- A–E structure;
- section order;
- tables;
- field hierarchy;
- generated RPM semantics.

Only styling may change when explicitly requested.
The Web Preview must still consume the FINAL VALIDATED RPM result.

==================================================
43. DOCX ↔ WEB CONTENT PARITY
==================================================

Web Preview and DOCX MUST render the SAME FINAL VALIDATED RPM result.

Required flow:

FINAL VALIDATED RPM RESULT
        ├──> WEB RENDERER
        └──> DOCX RENDERER

DOCX renderer MUST NOT:
- call AI;
- regenerate sections;
- enrich content;
- infer missing content;
- silently add defaults;
- paraphrase generated text;
- create DOCX-only content.

Export DOCX defaults to the active/latest Web RPM version. Explicit version
override remains allowed where the existing API supports it.

==================================================
44. TEMPLATE-DRIVEN DOCX
==================================================

`templates/Templatku.docx` remains the primary DOCX layout reference.

Preserve where applicable:
- header;
- title placement;
- margins;
- typography;
- section hierarchy;
- table geometry;
- cell formatting;
- spacing;
- numbering;
- page structure;
- visual hierarchy.

Do not replace template fidelity with generic `python-docx` defaults.

==================================================
45. VERSIONING / SAVED RPM RULES
==================================================

Saved valid RPMs must remain retrievable and editable.

History behavior:
- newest → oldest;
- saved/validated RPMs only;
- history records remain immutable;
- editing creates a new version through existing versioning flow;
- viewing a version must not mutate its content;
- saving without edits must preserve content exactly;
- active version is explicit in the UI;
- no per-row Restore control is required by the current UI.

Export DOCX must use the active/latest Web RPM version by default.

Do not create a second versioning system.

==================================================
46. DEFINITION OF DONE — CURRENT PRODUCT
==================================================

A task is CLEAR only when its explicit acceptance criteria are satisfied,
relevant tests pass, and no regression is introduced.

For frontend tasks:
- read `Design.md`;
- load required local skills;
- verify actual interaction;
- verify responsive states where relevant;
- run UI Delivery Gate.

For generation tasks:
- preserve normative data and provenance;
- preserve readiness rules;
- preserve alignment validators;
- preserve Anti-Slop protected fields;
- final validation must pass before rendering.

For DOCX tasks:
- render only FINAL VALIDATED RPM;
- preserve Web/DOCX content parity;
- preserve `Templatku.docx` fidelity;
- verify output visually where possible.

When acceptance criteria are satisfied, STOP.

==================================================
END OF AGENTS.md
==================================================
