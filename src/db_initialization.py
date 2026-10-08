#!/usr/bin/env python3
"""
Database Initialization & Population Script
AI RPP/RPM Generator (Pembelajaran Mendalam) - Phase 2

Initializes PostgreSQL/SQLite database and populates with:
- Authorities
- Regulations
- Source Documents
- Source Fragments
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime


class DatabaseInitializer:
    """Initializes and populates the database."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """Connect to SQLite database (auto-creates)."""
        print(f"📊 Connecting to database: {self.db_path}")
        self.connection = sqlite3.connect(str(self.db_path))
        self.cursor = self.connection.cursor()
        print("   ✅ Connected")
        
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("   ✅ Connection closed")
    
    @staticmethod
    def _split_sql_statements(schema_sql: str):
        """Split skrip SQL multi-statement pada ';' DI LUAR komentar.

        Baris '-- ...' dibuang sebelum split: komentar bisa memuat
        ';' atau tanda kutip yang membuat naive split(str.split(';'))
        menghasilkan fragmen statement rusak (syntax error), sehingga
        CREATE/ALTER penting (mis. kolom provenance learning_outcomes)
        diam-diam gagal.
        """
        lines = []
        for line in schema_sql.split('\n'):
            if line.lstrip().startswith('--'):
                continue
            lines.append(line)
        cleaned = '\n'.join(lines)
        return [s.strip() for s in cleaned.split(';') if s.strip()]

    def create_schema(self, schema_sql: str):
        """Create database schema from SQL."""
        print("🏗️  Creating database schema...")
        
        try:
            # Parse SQL statements (comment-aware, lihat helper di atas)
            statements = self._split_sql_statements(schema_sql)
            
            for i, statement in enumerate(statements, 1):
                try:
                    self.cursor.execute(statement)
                    print(f"   ✅ Statement {i} executed")
                except Exception as e:
                    print(f"   ⚠️  Statement {i} error (may be expected): {str(e)[:80]}")
            
            self.connection.commit()
            print("✅ Schema created successfully")
            
        except Exception as e:
            print(f"❌ Error creating schema: {e}")
            self.connection.rollback()
    
    def create_simplified_schema(self):
        """Create simplified schema suitable for SQLite."""
        print("🏗️  Creating simplified database schema...")
        
        schema_sql = """
        -- Authorities
        CREATE TABLE IF NOT EXISTS authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            full_name TEXT,
            description TEXT
        );
        
        -- Regulations
        CREATE TABLE IF NOT EXISTS regulations (
            id TEXT PRIMARY KEY,
            authority_id INTEGER NOT NULL REFERENCES authorities(id),
            regulation_type TEXT,
            regulation_number TEXT,
            title TEXT NOT NULL,
            year INTEGER,
            effective_date TEXT,
            status TEXT CHECK (status IN ('draft', 'active', 'superseded', 'revoked')),
            supersedes_id TEXT REFERENCES regulations(id),
            description TEXT,
            source_url TEXT,
            local_file TEXT,
            document_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Kolom tambahan hasil migrasi metadata (AMENDEMEN + bukti tanggal).
        -- Dibuat terpisah agar re-run schema aman pada DB lama.
        ALTER TABLE regulations ADD COLUMN supersedes_kind TEXT;
        
        -- Source Documents
        CREATE TABLE IF NOT EXISTS source_documents (
            id TEXT PRIMARY KEY,
            regulation_id TEXT REFERENCES regulations(id),
            title TEXT NOT NULL,
            document_type TEXT,
            local_path TEXT UNIQUE NOT NULL,
            file_size_bytes INTEGER,
            document_hash TEXT,
            extracted_at TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Source Fragments
        CREATE TABLE IF NOT EXISTS source_fragments (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES source_documents(id),
            page_number INTEGER,
            section TEXT,
            paragraph INTEGER,
            text TEXT,
            text_hash TEXT,
            char_count INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Provenance per fragment (AGENTS.md §2): jalur ekstraksi halaman
        -- sumber (text_layer / ocr / vision).
        ALTER TABLE source_fragments ADD COLUMN extraction_method TEXT;
        
        -- Learning Outcomes (CP) - kolom provenance penuh (AGENTS.md
        -- §9/§27). Tabel inti dibuat oleh curriculum_engine, kolom
        -- tambahan dijamin di sini agar ingestion menghasilkan skema
        -- yang lengkap. CATATAN: jangan pakai ';' di komentar schema -
        -- statement splitter memotong pada ';'.
        CREATE TABLE IF NOT EXISTS learning_outcomes (
            id TEXT PRIMARY KEY,
            subject TEXT,
            phase TEXT,
            element TEXT,
            text TEXT,
            source_page INTEGER,
            source_document TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE learning_outcomes ADD COLUMN curriculum_version_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN education_system TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN institution_type TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN education_level TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN subject_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN phase_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN element_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN sub_element TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN program_type TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN track TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN source_document_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN source_fragment_id TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN source_section TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN version TEXT;
        ALTER TABLE learning_outcomes ADD COLUMN status TEXT;
        
        -- Cognitive Operators (Bloom's Taxonomy)
        CREATE TABLE IF NOT EXISTS cognitive_operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT UNIQUE NOT NULL,
            level_name TEXT,
            order_number INTEGER,
            examples TEXT,
            description TEXT
        );
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_regulations_authority ON regulations(authority_id);
        CREATE INDEX IF NOT EXISTS idx_regulations_status ON regulations(status);
        CREATE INDEX IF NOT EXISTS idx_source_documents_regulation ON source_documents(regulation_id);
        CREATE INDEX IF NOT EXISTS idx_source_fragments_document ON source_fragments(document_id);
        """
        
        try:
            # Parse SQL statements (comment-aware - komentar schema bisa
            # memuat ';' dan kutip tanpa memecah statement).
            statements = self._split_sql_statements(schema_sql)
            
            for i, statement in enumerate(statements, 1):
                try:
                    self.cursor.execute(statement)
                except Exception as e:
                    # Ignore "already exists" errors
                    if "already exists" not in str(e):
                        print(f"   ⚠️  {str(e)[:80]}")
            
            self.connection.commit()
            print("✅ Schema created successfully")
            
        except Exception as e:
            print(f"❌ Error creating schema: {e}")
            self.connection.rollback()
    
    def populate_authorities(self):
        """Populate authorities table."""
        print("📋 Populating authorities...")
        
        authorities = [
            ('KEMENAG', 'Kementerian Agama', 'Kementerian Agama Republik Indonesia', 
             'Otoritas kurikulum untuk institusi pendidikan Islam (RA, MI, MTs, MA, MAK)'),
            # Nama resmi sesuai kop dokumen kanonik (Kepka BSKAP 046/H/KR/2025
            # hal. 3: "Kementerian Pendidikan Dasar dan Menengah"). Nama lama
            # "Kebudayaan, Riset, dan Teknologi" adalah kementerian sebelum
            # pemisahan dan tidak dipakai dokumen Hukum/.
            ('KEMENDIKDASMEN', 'Kemendikdasmen', 'Kementerian Pendidikan Dasar dan Menengah',
             'Otoritas kurikulum untuk institusi pendidikan umum (TK, SD, SMP, SMA, SMK)')
        ]
        
        try:
            for code, name, full_name, description in authorities:
                self.cursor.execute('''
                    INSERT OR IGNORE INTO authorities (code, name, full_name, description)
                    VALUES (?, ?, ?, ?)
                ''', (code, name, full_name, description))
                # INSERT OR IGNORE tidak menimpa baris yang sudah ada, jadi
                # koreksi nama (mis. nama kementerian yang diperbaiki) tidak
                # akan pernah sampai ke DB lama tanpa UPDATE eksplisit.
                self.cursor.execute('''
                    UPDATE authorities
                    SET name = ?, full_name = ?, description = ?
                    WHERE code = ?
                ''', (name, full_name, description, code))
            
            self.connection.commit()
            print(f"   ✅ Inserted {len(authorities)} authorities")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.connection.rollback()
    
    def populate_cognitive_operators(self):
        """Populate Bloom's taxonomy.

        Daftar KKO per level adalah data normatif dari user (87 kata
        kerja operasional C1-C6). Seed memakai UPSERT agar daftar lama
        ikut terganti, bukan dipertahankan oleh INSERT OR IGNORE.
        """
        print("🧠 Populating cognitive operators...")

        operators = [
            ('C1', 'Remember', 1,
             'menemukenali, mengingat kembali, membaca, menyebutkan, '
             'melafalkan, menuliskan, menghafal, menyusun daftar, '
             'menggarisbawahi, menjodohkan, memilih, memberi definisi, '
             'menyatakan',
             'Mengingat kembali informasi yang telah dipelajari'),
            ('C2', 'Understand', 2,
             'menjelaskan, mengartikan, menginterpretasikan, menceritakan, '
             'menampilkan, memberi contoh, merangkum, menyimpulkan, '
             'membandingkan, mengklasifikasikan, menunjukkan, menguraikan, '
             'membedakan, menyadur, meramalkan, memperkirakan, menerangkan, '
             'menggantikan',
             'Memahami makna informasi yang telah dipelajari'),
            ('C3', 'Apply', 3,
             'melaksanakan, mengimplementasikan, menggunakan, mengonsepkan, '
             'menentukan, memproseskan, mendemonstrasikan, menghitung, '
             'menghubungkan, melakukan, membuktikan, menghasilkan, '
             'memperagakan, melengkapi, menyesuaikan, menemukan',
             'Menerapkan informasi dalam situasi baru'),
            ('C4', 'Analyze', 4,
             'mendiferensiasikan, mengorganisasikan, mengatribusikan, '
             'mendiagnosis, memerinci, menelaah, mendeteksi, mengaitkan, '
             'memecahkan, memisahkan, menyeleksi, mempertentangkan, membagi',
             'Menguraikan informasi menjadi bagian-bagian'),
            ('C5', 'Evaluate', 5,
             'mengecek, mengkritik, mempertahankan, memvalidasi, mendukung, '
             'memproyeksikan, memperbandingkan, menilai, mengevaluasi, '
             'memberi saran, memberi argumentasi, menafsirkan, merekomendasi',
             'Membuat penilaian berdasarkan kriteria'),
            ('C6', 'Create', 6,
             'membangun, merencanakan, memproduksi, mengkombinasikan, '
             'merancang, merekonstruksi, membuat, menciptakan, mengabstraksi, '
             'mengkategorikan, mengarang, mendesain, menyusun kembali, '
             'merangkaikan',
             'Menciptakan sesuatu yang baru')
        ]

        try:
            for level, name, order, examples, description in operators:
                self.cursor.execute('''
                    INSERT INTO cognitive_operators (level, level_name, order_number, examples, description)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(level) DO UPDATE SET
                        level_name=excluded.level_name,
                        order_number=excluded.order_number,
                        examples=excluded.examples,
                        description=excluded.description
                ''', (level, name, order, examples, description))
            
            self.connection.commit()
            print(f"   ✅ Inserted {len(operators)} cognitive operators")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.connection.rollback()
    
    def populate_regulations_from_registry(self, registry_path: str):
        """Populate regulations and source documents from registry."""
        print("📜 Populating regulations and source documents...")
        
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
            
            # Get authority IDs
            self.cursor.execute("SELECT id, code FROM authorities")
            authority_map = {row[1]: row[0] for row in self.cursor.fetchall()}
            
            docs_inserted = 0
            regs_inserted = 0
            
            for doc in registry.get('documents', []):
                # Map authority code to ID
                authority_code = doc.get('authority')
                authority_id = authority_map.get(authority_code)
                
                if not authority_id:
                    print(f"   ⚠️  Unknown authority: {authority_code}")
                    continue
                
                # Create regulation entry
                reg_id = doc.get('id')
                
                self.cursor.execute('''
                    INSERT OR IGNORE INTO regulations
                    (id, authority_id, regulation_type, regulation_number, title, year, 
                     effective_date, status, supersedes_id, description, source_url, local_file, document_hash,
                     supersedes_kind)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    reg_id,
                    authority_id,
                    doc.get('regulation_type'),
                    doc.get('regulation_number'),
                    doc.get('title'),
                    doc.get('year'),
                    doc.get('effective_date'),
                    doc.get('status', 'active'),
                    # Relasi antar-regulasi (mis. BKPDM 020/2026
                    # MENGUBAH bagian CP PAI-BP dari BSKAP 046/H/KR/2025 —
                    # amendemen, bukan penggantian total).
                    doc.get('supersedes_id'),
                    doc.get('description'),
                    doc.get('source_url'),
                    doc.get('local_path'),
                    doc.get('document_hash'),
                    # NULL bila tidak ada relasi: 'replaces' tanpa
                    # supersedes_id adalah relasi palsu.
                    doc.get('supersedes_kind'),
                ))
                regs_inserted += 1
                
                # Create source document entry (hash langsung dari registry
                # yang dihitung dari PDF aktual).
                self.cursor.execute('''
                    INSERT OR IGNORE INTO source_documents
                    (id, regulation_id, title, document_type, local_path,
                     file_size_bytes, document_hash, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    f"DOC-{reg_id}",
                    reg_id,
                    doc.get('title'),
                    doc.get('document_type'),
                    doc.get('local_path'),
                    doc.get('file_size_bytes'),
                    doc.get('document_hash'),
                    doc.get('notes')
                ))
                docs_inserted += 1
            
            self.connection.commit()
            print(f"   ✅ Inserted {regs_inserted} regulations and {docs_inserted} source documents")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.connection.rollback()
    
    def populate_fragments_from_extraction(self, extraction_path: str):
        """Populate source fragments from extraction results."""
        print("✂️  Populating source fragments...")
        
        try:
            with open(extraction_path, 'r', encoding='utf-8') as f:
                extraction_results = json.load(f)
            
            fragments_inserted = 0
            
            # Peta nama file -> doc_id kanonik. Ekstraksi hanya boleh
            # menempel pada source_documents dari registry (PDF di Hukum/,
            # AGENTS.md §1). Dokumen di luar registry DILEWATI, bukan
            # dibuatkan baris baru dengan path lama.
            self.cursor.execute("SELECT id, local_path FROM source_documents")
            by_basename = {
                Path(local_path).name.lower(): doc_id
                for doc_id, local_path in self.cursor.fetchall()
            }
            
            for doc in extraction_results.get('documents', []):
                metadata = doc.get('metadata', {})
                basename = Path(metadata.get('file_path', '')).name.lower()
                match = by_basename.get(basename)
                
                if not match:
                    print(
                        f"   ⚠️  Skipped (not in canonical registry): "
                        f"{metadata.get('document_id')}"
                    )
                    continue
                doc_id = match
                
                # Update document hash from canonical extraction
                self.cursor.execute(
                    "UPDATE source_documents SET document_hash = ? WHERE id = ?",
                    (metadata.get('document_hash'), doc_id)
                )
                
                # Insert fragments (dengan provenance method per fragment).
                for fragment in doc.get('fragments', []):
                    self.cursor.execute('''
                        INSERT OR IGNORE INTO source_fragments
                        (id, document_id, page_number, section, paragraph,
                         text, text_hash, char_count, extraction_method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        fragment.get('fragment_id'),
                        doc_id,
                        fragment.get('page_number'),
                        fragment.get('section'),
                        fragment.get('paragraph'),
                        fragment.get('text'),
                        fragment.get('text_hash'),
                        fragment.get('char_count', 0),
                        fragment.get('extraction_method', 'text_layer'),
                    ))
                    fragments_inserted += 1
            
            self.connection.commit()
            print(f"   ✅ Inserted {fragments_inserted} source fragments")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print(f"   Exception type: {type(e).__name__}")
            self.connection.rollback()
    
    def verify_data_integrity(self):
        """Verify data integrity."""
        print("\n🔍 Verifying data integrity...")
        
        try:
            # Count records
            queries = [
                ("authorities", "SELECT COUNT(*) FROM authorities"),
                ("regulations", "SELECT COUNT(*) FROM regulations"),
                ("source_documents", "SELECT COUNT(*) FROM source_documents"),
                ("source_fragments", "SELECT COUNT(*) FROM source_fragments"),
                ("cognitive_operators", "SELECT COUNT(*) FROM cognitive_operators")
            ]
            
            for name, query in queries:
                self.cursor.execute(query)
                count = self.cursor.fetchone()[0]
                print(f"   {name}: {count} records")
            
            # Check for orphaned fragments
            self.cursor.execute('''
                SELECT COUNT(*) FROM source_fragments sf
                WHERE NOT EXISTS (SELECT 1 FROM source_documents sd WHERE sd.id = sf.document_id)
            ''')
            orphaned = self.cursor.fetchone()[0]
            if orphaned > 0:
                print(f"   ⚠️  Warning: {orphaned} orphaned fragments found")
            else:
                print(f"   ✅ No orphaned fragments")
            
            # Check for documents without hashes
            self.cursor.execute('''
                SELECT COUNT(*) FROM source_documents WHERE document_hash IS NULL OR document_hash = ''
            ''')
            no_hash = self.cursor.fetchone()[0]
            if no_hash > 0:
                print(f"   ⚠️  Warning: {no_hash} documents without hash")
            else:
                print(f"   ✅ All documents have hashes")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    def initialize_and_populate(self, registry_path: str, extraction_path: str):
        """Full initialization and population workflow."""
        print("\n" + "="*60)
        print("🗄️  DATABASE INITIALIZATION & POPULATION")
        print("="*60 + "\n")
        
        try:
            self.connect()
            self.create_simplified_schema()
            self.populate_authorities()
            self.populate_cognitive_operators()
            self.populate_regulations_from_registry(registry_path)
            self.populate_fragments_from_extraction(extraction_path)
            self.verify_data_integrity()
            
            print("\n✅ DATABASE INITIALIZATION COMPLETE")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            self.close()


if __name__ == '__main__':
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'
    REGISTRY_PATH = PROJECT_ROOT / 'db' / 'document_registry.json'
    # Sumber kanonik: PDF di Hukum/ (AGENTS.md §1). Ekstraksi turunan
    # boleh dibuang dan dibuat ulang; PDF kanonik tidak.
    EXTRACTION_PATH = PROJECT_ROOT / 'db' / 'extracted_fragments.json'
    
    initializer = DatabaseInitializer(str(DB_PATH))
    initializer.initialize_and_populate(str(REGISTRY_PATH), str(EXTRACTION_PATH))
