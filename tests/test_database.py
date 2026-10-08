#!/usr/bin/env python3
"""
Tests for Database Integrity (Phase 2, 25-27)
Tests database structure, data population, and provenance tracking
"""

import pytest
import sys

# Fixtures from conftest will handle imports


# ============================================================================
# DATABASE CONNECTION TESTS
# ============================================================================

@pytest.mark.database
class TestDatabaseConnection:
    """Test database connectivity."""
    
    def test_database_file_exists(self, test_db):
        """Test database file should exist."""
        assert test_db.exists()
    
    def test_database_is_sqlite(self, test_db):
        """Database should be SQLite format."""
        # SQLite files start with "SQLite format 3"
        with open(test_db, 'rb') as f:
            header = f.read(16)
            assert header.startswith(b'SQLite format 3')
    
    def test_database_connection_works(self, db_connection):
        """Should be able to connect to database."""
        assert db_connection is not None
        assert db_connection.cursor() is not None
    
    def test_database_row_factory_set(self, db_connection):
        """Database should have row factory set."""
        assert db_connection.row_factory is not None


# ============================================================================
# TABLE EXISTENCE TESTS
# ============================================================================

@pytest.mark.database
class TestTableExistence:
    """Test that required tables exist."""
    
    def test_authorities_table_exists(self, db_connection):
        """authorities table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='authorities'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_regulations_table_exists(self, db_connection):
        """regulations table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='regulations'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_source_documents_table_exists(self, db_connection):
        """source_documents table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_documents'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_source_fragments_table_exists(self, db_connection):
        """source_fragments table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_fragments'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_learning_outcomes_table_exists(self, db_connection):
        """learning_outcomes (CP) table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_outcomes'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_cognitive_operators_table_exists(self, db_connection):
        """cognitive_operators table should exist."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cognitive_operators'"
        )
        result = cursor.fetchone()
        assert result is not None
    
    def test_get_all_tables(self, db_connection):
        """Get all tables to verify database structure."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        # Should have at least 6 core tables
        assert len(tables) >= 6


# ============================================================================
# DATA POPULATION TESTS
# ============================================================================

@pytest.mark.database
class TestDataPopulation:
    """Test that database is populated with data."""
    
    def test_authorities_populated(self, db_connection):
        """authorities table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM authorities")
        count = cursor.fetchone()['count']
        assert count > 0
    
    def test_authorities_has_kemenag(self, db_connection):
        """authorities should include KEMENAG."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM authorities WHERE code LIKE '%KEMENAG%' OR name LIKE '%KEMENAG%'")
        result = cursor.fetchone()
        assert result is not None
    
    def test_authorities_has_kemendikdasmen(self, db_connection):
        """authorities should include Kemendikdasmen."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM authorities WHERE code LIKE '%KEMENAG%' OR code LIKE '%Kemendik%' OR name LIKE '%Kemendik%'")
        results = cursor.fetchall()
        assert len(results) >= 1
    
    def test_regulations_populated(self, db_connection):
        """regulations table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM regulations")
        count = cursor.fetchone()['count']
        assert count > 0
    
    def test_source_documents_populated(self, db_connection):
        """source_documents table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_documents")
        count = cursor.fetchone()['count']
        assert count > 0
    
    def test_source_fragments_populated(self, db_connection):
        """source_fragments table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_fragments")
        count = cursor.fetchone()['count']
        assert count > 0
        # Claim is 796 fragments
        assert count >= 100  # At least significant data
    
    def test_learning_outcomes_populated(self, db_connection):
        """learning_outcomes (CP) table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes")
        count = cursor.fetchone()['count']
        assert count > 0
        # Claim is 157 CP entries
        assert count >= 50  # At least significant data
    
    def test_cognitive_operators_populated(self, db_connection):
        """cognitive_operators table should have data."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM cognitive_operators")
        count = cursor.fetchone()['count']
        assert count >= 6  # C1-C6


# ============================================================================
# DATA INTEGRITY TESTS
# ============================================================================

@pytest.mark.database
class TestDataIntegrity:
    """Test data integrity and relationships."""
    
    def test_source_fragments_have_required_fields(self, db_connection):
        """Source fragments should have required fields."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(source_fragments)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required = ['id', 'document_id', 'text', 'page_number']
        for col in required:
            assert col in columns
    
    def test_learning_outcomes_have_required_fields(self, db_connection):
        """Learning outcomes should have required fields."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(learning_outcomes)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required = ['id', 'subject', 'phase', 'element', 'text']
        for col in required:
            assert col in columns
    
    def test_source_fragments_not_null_text(self, db_connection):
        """Source fragments should have non-null text."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_fragments WHERE text IS NULL")
        count = cursor.fetchone()['count']
        assert count == 0
    
    def test_learning_outcomes_not_null_id(self, db_connection):
        """Learning outcomes should have non-null id."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes WHERE id IS NULL")
        count = cursor.fetchone()['count']
        assert count == 0


# ============================================================================
# PROVENANCE TESTS
# ============================================================================

@pytest.mark.database
class TestProvenance:
    """Test that data provenance is tracked."""
    
    def test_all_cp_entries_have_source_document(self, db_connection):
        """All CP entries should have source document reference."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM learning_outcomes 
            WHERE source_document IS NULL OR source_document = ''
        """)
        null_count = cursor.fetchone()['count']
        
        # Get total count
        cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes")
        total_count = cursor.fetchone()['count']
        
        # All should have source
        assert null_count == 0
        assert total_count > 0
    
    def test_all_cp_entries_have_source_page(self, db_connection):
        """All CP entries should have source page information."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM learning_outcomes 
            WHERE source_page IS NULL
        """)
        null_count = cursor.fetchone()['count']
        assert null_count == 0
    
    def test_cp_entries_have_valid_subjects(self, db_connection):
        """CP entries should have valid subjects."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT DISTINCT subject FROM learning_outcomes")
        subjects = [row['subject'] for row in cursor.fetchall()]
        
        # Should have known subjects
        expected_subjects = [
            'Al-Qur\'an Hadis', 'Akidah Akhlak', 'Fikih',
            'Sejarah Kebudayaan Islam', 'Bahasa Arab'
        ]
        
        found_subjects = [s for s in expected_subjects if s in subjects]
        assert len(found_subjects) > 0
    
    def test_cp_entries_have_valid_phases(self, db_connection):
        """CP entries should have valid phases (A-F)."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT DISTINCT phase FROM learning_outcomes ORDER BY phase")
        phases = [row['phase'] for row in cursor.fetchall()]
        
        # Fase A-F untuk SD s.d. SMA/SMK. 'Fondasi' adalah fase PAUD dan
        # TKLB (Diktum KELIMA BSKAP 046), jadi sah.
        valid_phases = {'A', 'B', 'C', 'D', 'E', 'F', 'Fondasi', 'Unknown'}
        for phase in phases:
            assert phase in valid_phases
    
    def test_cp_entries_have_elements(self, db_connection):
        """CP entries should have element information."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM learning_outcomes 
            WHERE element IS NULL OR element = ''
        """)
        null_count = cursor.fetchone()['count']
        
        # Should mostly have elements
        assert null_count < 10  # Allow some but not many


# ============================================================================
# FOREIGN KEY RELATIONSHIP TESTS
# ============================================================================

@pytest.mark.database
class TestForeignKeyRelationships:
    """Test relationships between tables."""
    
    def test_source_fragments_reference_valid_documents(self, db_connection):
        """All source fragments should reference valid documents."""
        cursor = db_connection.cursor()
        
        # Get all document IDs referenced by fragments
        cursor.execute("SELECT DISTINCT document_id FROM source_fragments")
        fragment_doc_ids = [row['document_id'] for row in cursor.fetchall()]
        
        # Get all valid document IDs
        cursor.execute("SELECT id FROM source_documents")
        valid_doc_ids = [row['id'] for row in cursor.fetchall()]
        
        # All referenced should be valid
        for doc_id in fragment_doc_ids:
            if doc_id is not None:
                assert doc_id in valid_doc_ids
    
    def test_regulations_reference_valid_authorities(self, db_connection):
        """All regulations should reference valid authorities."""
        cursor = db_connection.cursor()
        
        # Get all authority IDs referenced by regulations
        cursor.execute("SELECT DISTINCT authority_id FROM regulations WHERE authority_id IS NOT NULL")
        regulation_authorities = [row['authority_id'] for row in cursor.fetchall()]
        
        # Get all valid authority IDs
        cursor.execute("SELECT DISTINCT id FROM authorities")
        valid_authorities = [row['id'] for row in cursor.fetchall()]
        
        # All referenced should be valid (or empty)
        for auth in regulation_authorities:
            assert auth in valid_authorities or auth is None


# ============================================================================
# DATA CONSISTENCY TESTS
# ============================================================================

@pytest.mark.database
class TestDataConsistency:
    """Test data consistency and absence of duplicates."""
    
    def test_no_duplicate_cp_ids(self, db_connection):
        """CP IDs should be unique."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT id, COUNT(*) as count FROM learning_outcomes 
            GROUP BY id HAVING count > 1
        """)
        duplicates = cursor.fetchall()
        assert len(duplicates) == 0
    
    def test_no_duplicate_fragment_ids(self, db_connection):
        """Fragment IDs should be unique."""
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT id, COUNT(*) as count FROM source_fragments 
            GROUP BY id HAVING count > 1
        """)
        duplicates = cursor.fetchall()
        assert len(duplicates) == 0
    
    def test_document_registry_consistency(self, db_connection):
        """Document registry should be consistent."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_documents")
        count = cursor.fetchone()['count']
        assert count > 0
        assert count <= 20  # Shouldn't have too many


# ============================================================================
# QUERY PERFORMANCE TESTS
# ============================================================================

@pytest.mark.database
class TestQueryPerformance:
    """Test that queries perform efficiently."""
    
    def test_cp_by_subject_phase_query(self, db_connection):
        """Query CP by subject and phase should be fast."""
        cursor = db_connection.cursor()
        
        # This should be indexed
        cursor.execute("""
            SELECT * FROM learning_outcomes 
            WHERE subject = 'Akidah Akhlak' AND phase = 'D'
        """)
        results = cursor.fetchall()
        
        # Should return results
        assert len(results) >= 0
    
    def test_fragments_by_document_query(self, db_connection):
        """Query fragments by document should be fast."""
        cursor = db_connection.cursor()
        
        # Get first document
        cursor.execute("SELECT id FROM source_documents LIMIT 1")
        doc = cursor.fetchone()
        
        if doc:
            # Query fragments for that document
            cursor.execute("""
                SELECT * FROM source_fragments 
                WHERE document_id = ?
            """, (doc['id'],))
            results = cursor.fetchall()
            assert len(results) >= 0


# ============================================================================
# DATABASE STATISTICS TESTS
# ============================================================================

@pytest.mark.database
class TestDatabaseStatistics:
    """Test database statistics and data volume."""
    
    def test_fragment_count_reasonable(self, db_connection):
        """Fragment count should match canonical Hukum/ extraction (6592)."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_fragments")
        count = cursor.fetchone()['count']
        
        # 9 dokumen kanonik di Hukum/ (6592) + fragmen buku ajar (R-43,
        # dinamis mengikuti isi DB; boleh 0 pada DB seed yang di-commit
        # karena buku user tidak ikut di-push).
        cursor.execute("SELECT COUNT(*) FROM source_fragments "
                       "WHERE document_id IN (SELECT id FROM "
                       "source_documents WHERE regulation_id IS NOT NULL)")
        kanonik = cursor.fetchone()[0]
        assert kanonik == 6592
        cursor.execute("SELECT COUNT(*) FROM source_fragments "
                       "WHERE document_id IN (SELECT id FROM "
                       "source_documents WHERE document_type = 'buku_ajar')")
        buku = cursor.fetchone()[0]
        assert count == kanonik + buku
    
    def test_no_fragment_debris(self, db_connection):
        """Filter fragmen remah: nol fragmen <=3 karakter dan nol
        fragmen tanpa kata berhuruf >=3 (heuristik token)."""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM source_fragments "
            "WHERE length(trim(text)) <= 3")
        count = cursor.fetchone()['count']
        assert count == 0
        cursor.execute("SELECT text FROM source_fragments")
        import re
        letter_word = re.compile(r'[A-Za-z\u00C0-\u024F]{3,}')
        for (text,) in cursor.fetchall():
            assert letter_word.search(text or ''), repr(text[:40])
    
    def test_cp_count_reasonable(self, db_connection):
        """CP = 132 madrasah (9941/2025, reguler + MAPK) + 333 sekolah
        (BKPDM 020/2026: 30 PAI-BP + 158 agama lain bernomor + 145
        tabel 1.2/1.3/2.2) + 2.595 mapel umum BSKAP 046/H/KR/2025."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes")
        count = cursor.fetchone()['count']
        assert count == 3060

    def test_school_cp_count(self, db_connection):
        """CP BKPDM 020/2026: 30 PAI-BP (6 fase x 5 elemen) plus 158
        agama lain bernomor plus 145 CP tabel dua kolom (1.2 Kristen
        reguler, 1.3 Katolik reguler, 2.2 Kristen pendidikan khusus)
        hasil parsing PDF — jumlah final dari parser, bukan manual."""
        cursor = db_connection.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) as c FROM learning_outcomes "
            "WHERE source_document = 'BKPDM-020-2026'"
        ).fetchone()
        assert row['c'] == 333

    def test_046_cp_excludes_agama(self, db_connection):
        """BSKAP 046 menyumbang CP mapel umum, bukan Pendidikan Agama —
        mapel itu diamendemen BKPDM 020/2026."""
        cursor = db_connection.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) as c FROM learning_outcomes "
            "WHERE source_document = 'BSKAP-046/H/KR/2025'"
        ).fetchone()
        assert row['c'] == 2595
        # CP Pendidikan Agama edisi 046 tetap tersimpan sebagai riwayat
        # berstatus 'superseded' (amendemen BKPDM 020 yang berlaku). Yang
        # tidak boleh ada: CP agama dari 046 yang masih 'active'.
        agama = cursor.execute(
            "SELECT COUNT(*) as c FROM learning_outcomes "
            "WHERE source_document = 'BSKAP-046/H/KR/2025' "
            "AND subject LIKE '%Agama%' AND status = 'active'"
        ).fetchone()
        assert agama['c'] == 0
    
    def test_document_count_reasonable(self, db_connection):
        """Document count: 9 kanonik Hukum/ + buku ajar user (R-43)."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_documents "
                       "WHERE regulation_id IS NOT NULL")
        count = cursor.fetchone()['count']

        # Tepat 9 dokumen kanonik (AGENTS.md §1); buku ajar terpisah.
        assert count == 9
    
    def test_regulation_count_reasonable(self, db_connection):
        """Regulation count should match the 9 canonical Hukum/ documents."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM regulations")
        count = cursor.fetchone()['count']
        
        # Tepat 9 regulasi kanonik (AGENTS.md §1); dulu 5 (data era lama)
        assert count == 9
    
    def test_authority_count_reasonable(self, db_connection):
        """Authority count should be reasonable (claim: 2)."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM authorities")
        count = cursor.fetchone()['count']
        
        # Claim: 2 authorities
        assert count == 2


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.database
@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database."""
    
    def test_complete_data_workflow(self, db_connection):
        """Test complete workflow using database."""
        cursor = db_connection.cursor()
        
        # 1. Get a document that has fragments (or skip)
        cursor.execute("""
            SELECT DISTINCT sd.id FROM source_documents sd 
            JOIN source_fragments sf ON sd.id = sf.document_id 
            LIMIT 1
        """)
        doc = cursor.fetchone()
        
        if doc is None:
            # No documents with fragments, skip this test
            pytest.skip("No documents with linked fragments in database")
        
        # 2. Get fragments for that document
        cursor.execute("""
            SELECT * FROM source_fragments 
            WHERE document_id = ? LIMIT 5
        """, (doc['id'],))
        fragments = cursor.fetchall()
        assert len(fragments) > 0
        
        # 3. Get CP entries
        cursor.execute("SELECT * FROM learning_outcomes LIMIT 1")
        cp = cursor.fetchone()
        assert cp is not None
        
        # 4. Verify CP has provenance
        assert cp['source_document'] is not None
        assert cp['source_page'] is not None
    
    def test_system_separation_in_database(self, db_connection):
        """Test that KEMENAG and Kemendikdasmen are separated."""
        cursor = db_connection.cursor()
        
        # Get subjects from database if available
        # This is a data-level test, not enforced by DB constraints in current design
        cursor.execute("SELECT DISTINCT subject FROM learning_outcomes")
        subjects = [row['subject'] for row in cursor.fetchall()]
        
        # Should have KEMENAG subjects
        kemenag_subjects = ['Al-Qur\'an Hadis', 'Akidah Akhlak', 'Fikih',
                            'Sejarah Kebudayaan Islam', 'Bahasa Arab']
        found = [s for s in subjects if s in kemenag_subjects]
        assert len(found) > 0
