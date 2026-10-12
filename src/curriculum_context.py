#!/usr/bin/env python3
"""
Pembangkit Konteks Kurikulum - FASE 5
AI RPP/RPM Generator (Pembelajaran Mendalam)

Menyusun Konteks Kurikulum tervalidasi yang diterima AI.
Memastikan CP, fase, dan metadata ternormalisasi sebelum pembuatan AI.
"""

import json
import sys
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

# Paksa keluaran UTF-8
try:
    if 'pytest' not in sys.modules:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (AttributeError, ValueError):
    pass


@dataclass(frozen=True)
class CPEntry:
    """Entri Capaian Pembelajaran."""
    id: str
    text: str
    source_document_id: str
    source_fragment_id: str
    source_page: int
    phase: str
    element: str


@dataclass
class TPEntry:
    """Entri Tujuan Pembelajaran."""
    id: str
    text: str
    cognitive_level: str
    source_type: str  # teacher, school, imported, ai_generated
    derived_from_id: Optional[str] = None


@dataclass
class ATPEntry:
    """Entri Alur Tujuan Pembelajaran."""
    id: str
    tp_ids: List[str]  # Daftar ID TP yang berurutan


@dataclass
class CurriculumContext:
    """
    Konteks kurikulum lengkap untuk pembuatan AI.
    Memuat seluruh data normatif yang tidak boleh diubah oleh AI.
    Bidang singular ``cp``/``element`` tetap menjadi primer dan sama
    dengan entri pertama ``cp_entries``/``elements``.
    """
    # Identitas inti
    education_system: str
    institution_type: str
    grade: str
    phase: str
    subject: str
    element: str
    curriculum_version: str

    # Data normatif (tidak berubah)
    cp: CPEntry
    tp_list: List[TPEntry]
    atp: ATPEntry

    # Topik otoritatif dari pengguna (BLOCKER 1); nilai baku menjaga
    # kompatibilitas pemanggil konstruktor lama (uji, perkakas).
    topic: str = ''

    # Aturan
    rules: Dict = None

    # Metadata
    generated_at: str = None
    context_hash: str = None
    # Cara elemen CP diselesaikan terhadap permintaan pengguna (jejak audit;
    # tidak pernah diganti diam-diam). Diisi oleh tahap kurikulum pipeline.
    element_resolution_note: str = None
    # Daftar CP aditif untuk cakupan multi-elemen; entri pertama selalu
    # sama dengan bidang primer ``cp`` agar pemanggil lama tetap valid.
    cp_entries: List[CPEntry] = field(default_factory=list)
    # Daftar elemen sejajar ``cp_entries``; entri pertama selalu sama
    # dengan bidang primer ``element``.
    elements: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Selaraskan bidang aditif dengan bidang primer."""
        # Pemanggil lama hanya mengisi ``cp``/``element`` sehingga
        # daftar aditif diturunkan dari bidang primer tersebut.
        if not self.cp_entries and self.cp is not None:
            self.cp_entries = [self.cp]
        elif self.cp_entries and self.cp is not None:
            # Pertahankan primer sebagai entri pertama bila pemanggil
            # memberikan daftar yang tidak diawali bidang primer.
            if not self.cp_entries or self.cp_entries[0] != self.cp:
                sisa = [e for e in (self.cp_entries or [])
                        if e != self.cp]
                self.cp_entries = [self.cp] + sisa
        if not self.elements:
            if self.cp_entries:
                self.elements = [e.element for e in self.cp_entries]
            elif self.element:
                self.elements = [self.element]
        elif self.element and (not self.elements
                               or self.elements[0] != self.element):
            sisa_el = [e for e in (self.elements or [])
                       if e != self.element]
            self.elements = [self.element] + sisa_el
    
    def to_dict(self) -> Dict:
        """Ubah konteks menjadi kamus.

        Bidang ``cp``/``element`` tetap dipertahankan sebagai primer
        untuk kompatibilitas lama, sedangkan ``cps``/``elements``
        membawa seluruh cakupan multi-CP.
        """
        return {
            'education_system': self.education_system,
            'institution_type': self.institution_type,
            'grade': self.grade,
            'phase': self.phase,
            'subject': self.subject,
            'element': self.element,
            'elements': list(self.elements),
            'curriculum_version': self.curriculum_version,
            # Topik adalah masukan otoritatif pengguna yang dibawa melalui
            # seluruh pipeline (BLOCKER 1); diekspor agar JSON modul memuatnya.
            'topic': self.topic,
            'cp': asdict(self.cp),
            'cps': [asdict(entry) for entry in self.cp_entries],
            'tp': [asdict(tp) for tp in self.tp_list],
            'atp': asdict(self.atp),
            'rules': self.rules,
            'metadata': {
                'generated_at': self.generated_at,
                'context_hash': self.context_hash
            }
        }
    
    def to_json(self) -> str:
        """Ubah menjadi JSON."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def _cp_entry_from_dict(cls, cp_data: Dict) -> "CPEntry":
        """Bangun satu ``CPEntry`` dari kamus dengan toleransi kunci."""
        if not isinstance(cp_data, dict):
            raise ValueError('context payload cp must be an object')
        return CPEntry(**{k: cp_data[k] for k in
                          ('id', 'text', 'source_document_id',
                           'source_fragment_id', 'source_page',
                           'phase', 'element') if k in cp_data})

    @classmethod
    def from_dict(cls, data: Dict) -> "CurriculumContext":
        """Bangun ulang konteks dari keluaran ``to_dict()``.

        Digunakan untuk memulihkan konteks otoritatif dari
        ``generated_modules.context_json`` (module_store) agar validasi
        ulang tetap berjalan setelah server dimulai ulang, tanpa
        ketergantungan memori. Bidang aditif (topic, metadata, cps,
        elements) menoleransi ketidakhadiran untuk baris lama; bila
        ``cps`` tidak ada, daftar diturunkan dari ``cp`` singular.
        Bidang singular ``cp``/``element`` tetap menjadi primer.
        """
        if not isinstance(data, dict):
            raise ValueError('context payload must be a JSON object')
        required = ['education_system', 'institution_type', 'grade', 'phase',
                    'subject', 'element', 'curriculum_version', 'cp']
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError('context payload missing: ' + ', '.join(missing))
        cp_data = data['cp']
        if not isinstance(cp_data, dict):
            raise ValueError('context payload cp must be an object')
        metadata = data.get('metadata') or {}
        cp = cls._cp_entry_from_dict(cp_data)
        # Daftar aditif: baca ``cps`` bila ada, selain itu turunkan dari
        # bidang singular agar payload lama tetap terbaca.
        raw_cps = data.get('cps')
        if isinstance(raw_cps, list) and raw_cps:
            cp_entries = [cls._cp_entry_from_dict(item)
                          for item in raw_cps if isinstance(item, dict)]
            if not cp_entries:
                cp_entries = [cp]
        else:
            cp_entries = [cp]
        raw_elements = data.get('elements')
        if isinstance(raw_elements, list) and raw_elements:
            elements = [str(e) for e in raw_elements]
        else:
            elements = [e.element for e in cp_entries]
        return cls(
            education_system=data['education_system'],
            institution_type=data['institution_type'],
            grade=data['grade'],
            phase=data['phase'],
            subject=data['subject'],
            element=data['element'],
            curriculum_version=data['curriculum_version'],
            cp=cp,
            tp_list=[TPEntry(**{k: tp[k] for k in
                                ('id', 'text', 'cognitive_level', 'source_type',
                                 'derived_from_id') if k in tp})
                     for tp in (data.get('tp_list') or data.get('tp') or [])
                     if isinstance(tp, dict)],
            atp=(ATPEntry(**data['atp'])
                 if isinstance(data.get('atp'), dict) and 'tp_ids' in data['atp']
                 else ATPEntry(id='', tp_ids=[])),
            topic=data.get('topic', ''),
            rules=data.get('rules'),
            generated_at=metadata.get('generated_at'),
            context_hash=metadata.get('context_hash'),
            cp_entries=cp_entries,
            elements=elements,
        )


_VALID_SUBJECTS_CACHE = None


def _valid_subjects_from_mapping():
    """Nama mapel per sistem dari db/curriculum_mappings.json — sumber
    otoritatif yang SAMA dengan CurriculumEngine (bukan daftar hardcode
    yang membusuk saat mapping bertambah). Hasil di-cache per proses;
    deterministik untuk file mapping yang sama."""
    global _VALID_SUBJECTS_CACHE
    if _VALID_SUBJECTS_CACHE is None:
        path = (Path(__file__).resolve().parent.parent
                / 'db' / 'curriculum_mappings.json')
        with open(path, encoding='utf-8') as f:
            mappings = json.load(f)
        out = {}
        for system, levels in mappings.get('subjects', {}).items():
            names = set()
            for subs in (levels or {}).values():
                for subj in subs or []:
                    if subj.get('name'):
                        names.add(subj['name'])
            out[system] = names
        _VALID_SUBJECTS_CACHE = out
    return _VALID_SUBJECTS_CACHE


class CurriculumContextGenerator:
    """Menyusun konteks kurikulum tervalidasi."""
    
    def __init__(self):
        self.context = None
        self.validation_errors = []
    
    def generate(
        self,
        education_system: str,
        institution_type: str,
        grade: str,
        phase: str,
        subject: str,
        element: str,
        cp_text: str,
        cp_source_doc: str,
        cp_source_frag: str,
        cp_page: int,
        tp_list: List[Dict],
        atp_tp_ids: List[str],
        curriculum_version: Optional[str] = None,
        cp_rows: Optional[List[Any]] = None,
    ) -> Optional[CurriculumContext]:
        """
        Bangun konteks kurikulum.
        Bila ``cp_rows`` diberikan (daftar dict/CPEntry untuk cakupan
        multi-elemen), seluruh baris dipakai sebagai ``cp_entries`` dan
        entri pertama menjadi primer ``cp``/``element``. Bila tidak,
        jatuh kembali ke parameter singular lama (satu entri CP).
        Kembali: CurriculumContext bila valid, None bila tidak valid
        """
        self.validation_errors = []
        # Versi kurikulum deterministik per sistem pendidikan
        # (AGENTS.md §4): jangan bawa versi madrasah ke sekolah umum.
        if not curriculum_version:
            curriculum_version = {
                'KEMENAG': 'KMA-1503-2025',
                'KEMENDIKDASMEN': 'KEMENDIKDASMEN-2025',
            }.get(education_system or system, 'KEMENDIKDASMEN-2025')
        if not self._validate_inputs(
            education_system or system, institution_type, phase, subject
        ):
            return None

        # Susun daftar CP aditif. Bila ``cp_rows`` diberikan, ubah setiap
        # baris (dict atau CPEntry) menjadi CPEntry; entri pertama menjadi
        # primer. Bila tidak, gunakan parameter singular lama.
        cp_entries: List[CPEntry] = []
        if cp_rows:
            for i, row in enumerate(cp_rows, 1):
                if isinstance(row, CPEntry):
                    cp_entries.append(row)
                    continue
                if not isinstance(row, dict):
                    self.validation_errors.append(
                        f"Invalid cp_rows entry #{i}: must be dict/CPEntry")
                    return None
                cp_entries.append(CPEntry(
                    id=row.get('id')
                    or f"CP-{subject.replace(' ', '-')}-{phase}-{i}",
                    text=row.get('text', ''),
                    source_document_id=row.get('source_document_id', ''),
                    source_fragment_id=row.get('source_fragment_id', ''),
                    source_page=row.get('source_page', 0),
                    phase=row.get('phase', phase),
                    element=row.get('element', element),
                ))
        if not cp_entries:
            # Buat entri CP (tidak berubah)
            cp_entries = [CPEntry(
                id=f"CP-{subject.replace(' ', '-')}-{phase}",
                text=cp_text,
                source_document_id=cp_source_doc,
                source_fragment_id=cp_source_frag,
                source_page=cp_page,
                phase=phase,
                element=element
            )]
        # Primer tetap entri pertama agar pemanggil lama tidak berubah.
        cp = cp_entries[0]
        elements = [entry.element for entry in cp_entries]
        element = cp.element
        
        # Buat entri TP
        tp_entries = []
        for i, tp_data in enumerate(tp_list, 1):
            tp = TPEntry(
                id=f"TP-{subject.replace(' ', '-')}-{i}",
                text=tp_data.get('text', ''),
                cognitive_level=tp_data.get('cognitive_level', 'C3'),
                source_type=tp_data.get('source_type', 'ai_generated'),
                derived_from_id=tp_data.get('derived_from_id')
            )
            tp_entries.append(tp)
        
        # Buat entri ATP (urutan tidak berubah)
        atp = ATPEntry(
            id=f"ATP-{subject.replace(' ', '-')}-{phase}",
            tp_ids=atp_tp_ids
        )
        
        # Tetapkan aturan (tidak berubah)
        rules = {
            'minimum_tp_level': 'C3',
            'minimum_kktp_level': 'C3',
            'enforce_alignment': True,
            'allow_ai_tp_generation': True,
            'allow_ai_content_generation': True
        }
        
        # Buat konteks
        self.context = CurriculumContext(
            education_system=education_system,
            institution_type=institution_type,
            grade=grade,
            phase=phase,
            subject=subject,
            element=element,
            curriculum_version=curriculum_version,
            cp=cp,
            tp_list=tp_entries,
            atp=atp,
            rules=rules,
            generated_at=datetime.now().isoformat(),
            context_hash=self._generate_hash(cp, atp),
            cp_entries=cp_entries,
            elements=elements,
        )
        
        return self.context
    
    def _validate_inputs(
        self,
        system: str,
        institution: str,
        phase: str,
        subject: str
    ) -> bool:
        """Validasi masukan kurikulum."""
        
        # Validasi fase
        if phase not in ['A', 'B', 'C', 'D', 'E', 'F']:
            self.validation_errors.append(f"Invalid phase: {phase}")
            return False
        
        # Validasi sistem
        if system not in ['KEMENAG', 'KEMENDIKDASMEN']:
            self.validation_errors.append(f"Invalid system: {system}")
            return False
        
        # Validasi pasangan mapel-sistem
        # Nama mapel harus konsisten dengan db/curriculum_mappings.json
        # (sumber otoritatif yang dipakai CurriculumEngine): dibaca dari
        # file yang sama, bukan daftar hardcode.
        try:
            valid_subjects = _valid_subjects_from_mapping()
        except Exception as exc:
            self.validation_errors.append(
                f"Curriculum mapping unavailable: {exc}")
            return False

        if subject not in valid_subjects.get(system, set()):
            self.validation_errors.append(
                f"Subject '{subject}' not valid for system '{system}'"
            )
            return False

        return True
    
    def _generate_hash(self, cp: CPEntry, atp: ATPEntry) -> str:
        """Buat hash dari data yang tidak berubah."""
        import hashlib
        data = f"{cp.id}:{cp.text}:{atp.id}:{':'.join(atp.tp_ids)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def validate_context(self, context: CurriculumContext) -> Tuple[bool, List[str]]:
        """Validasi kelengkapan konteks.

        Seluruh entri ``cp_entries`` wajib memiliki teks dan dokumen
        sumber; bidang primer ``cp`` tetap diperiksa seperti semula agar
        perilaku lama tidak berubah.
        """
        errors = []

        entri = list(getattr(context, 'cp_entries', None) or [])
        if not entri and getattr(context, 'cp', None) is not None:
            entri = [context.cp]
        jamak = len(entri) > 1
        for nomor, cp_entry in enumerate(entri, 1):
            penanda = f" (entri #{nomor})" if jamak else ""
            if not cp_entry.text:
                errors.append(f"CP text is empty{penanda}")
            if not cp_entry.source_document_id:
                errors.append(f"CP missing source document{penanda}")
        
        if not context.tp_list:
            errors.append("No TP entries provided")
        
        if not context.atp.tp_ids:
            errors.append("ATP has no TP sequence")
        
        # Pastikan seluruh TP dalam ATP ada
        tp_ids = {tp.id for tp in context.tp_list}
        for atp_id in context.atp.tp_ids:
            if atp_id not in tp_ids:
                errors.append(f"ATP references non-existent TP: {atp_id}")
        
        return len(errors) == 0, errors


class ContextValidator:
    """Memvalidasi konteks kurikulum sebelum pembuatan AI."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
    
    def validate_context_completeness(self, context: CurriculumContext) -> Tuple[bool, str]:
        """
        Validasi kelengkapan konteks sebelum pembuatan AI.
        Seluruh entri CP wajib lengkap; entri pertama tetap primer.
        Kembali: (is_valid, error_message)
        """
        entri = list(getattr(context, 'cp_entries', None) or [])
        if not entri and getattr(context, 'cp', None) is not None:
            entri = [context.cp]
        for cp_entry in entri:
            if not cp_entry.text:
                return False, "Capaian Pembelajaran tidak lengkap"
            if not cp_entry.source_document_id:
                return False, "Capaian Pembelajaran tidak lengkap"
        
        if not context.tp_list:
            return False, "Tujuan Pembelajaran tidak ada"
        
        if not context.atp.tp_ids:
            return False, "Alur Tujuan Pembelajaran tidak valid"
        
        # Pastikan seluruh TP ada dalam ATP
        tp_ids = {tp.id for tp in context.tp_list}
        for atp_id in context.atp.tp_ids:
            if atp_id not in tp_ids:
                return False, f"ATP mereferensikan TP yang tidak ada: {atp_id}"
        
        # Validasi jenjang kognitif
        for tp in context.tp_list:
            level = tp.cognitive_level
            if level not in ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']:
                return False, f"Invalid cognitive level: {level}"
            
            # Periksa batas minimum C3 untuk validasi
            if level in ['C1', 'C2']:
                return False, f"TP '{tp.id}' menggunakan level {level}. Minimum C3 diperlukan."
        
        return True, ""
    
    def print_context(self, context: CurriculumContext):
        """Cetak konteks untuk verifikasi."""
        print("\n" + "="*60)
        print("CURRICULUM CONTEXT")
        print("="*60)
        print(f"\nIdentity:")
        print(f"  System: {context.education_system}")
        print(f"  Institution: {context.institution_type}")
        print(f"  Grade: {context.grade}")
        print(f"  Phase: {context.phase}")
        print(f"  Subject: {context.subject}")
        print(f"  Element: {context.element}")
        
        print(f"\nCapaian Pembelajaran (CP):")
        print(f"  ID: {context.cp.id}")
        print(f"  Text: {context.cp.text[:80]}...")
        print(f"  Source: {context.cp.source_document_id}")
        
        print(f"\nTujuan Pembelajaran (TP):")
        for tp in context.tp_list:
            print(f"  {tp.id} [{tp.cognitive_level}]: {tp.text[:50]}...")
        
        print(f"\nAlur TP (ATP):")
        print(f"  Sequence: {' -> '.join(context.atp.tp_ids)}")
        
        print(f"\nMetadata:")
        print(f"  Generated: {context.generated_at}")
        print(f"  Context Hash: {context.context_hash}")
        print()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("CURRICULUM CONTEXT GENERATOR - PHASE 5")
    print("="*60 + "\n")
    
    generator = CurriculumContextGenerator()
    
    # Buat contoh konteks
    tp_list = [
        {'text': 'Menerapkan konsep Akidah dalam kehidupan sehari-hari',
         'cognitive_level': 'C3', 'source_type': 'ai_generated'},
        {'text': 'Menganalisis dimensi Akhlak dalam nilai-nilai luhur',
         'cognitive_level': 'C4', 'source_type': 'ai_generated'},
    ]
    
    context = generator.generate(
        education_system='KEMENAG',
        institution_type='MTs',
        grade='MTs_7',
        phase='D',
        subject='Akidah Akhlak',
        element='Akhlak',
        cp_text='Peserta didik dapat memahami dan menerapkan akhlak Islamiah dalam kehidupan',
        cp_source_doc='DOC-SK-DIRJEN-9941',
        cp_source_frag='frag-001',
        cp_page=42,
        tp_list=tp_list,
        atp_tp_ids=['TP-Akidah-Akhlak-1', 'TP-Akidah-Akhlak-2'],
        curriculum_version='KMA-1503-2025'
    )
    
    if context:
        validator = ContextValidator('')
        is_valid, error = validator.validate_context_completeness(context)
        
        if is_valid:
            print("Context is valid and ready for AI generation")
            validator.print_context(context)
            
            # Simpan ke berkas
            output_path = Path(__file__).parent.parent / 'db' / 'sample_context.json'
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(context.to_json())
            print(f"Context saved to {output_path}")
        else:
            print(f"Context validation failed: {error}")
    else:
        print("Context generation failed")
        print(f"Errors: {generator.validation_errors}")
    
    print("\n✅ CURRICULUM CONTEXT PHASE 5 COMPLETE")
