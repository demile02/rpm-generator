#!/usr/bin/env python3
"""
Curriculum Context Generator - PHASE 5
AI RPP/RPM Generator (Pembelajaran Mendalam)

Generates validated Curriculum Context that AI receives.
Ensures CP, phase, and metadata are normalized before AI generation.
"""

import json
import sys
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

# Force UTF-8 output
try:
    if 'pytest' not in sys.modules:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (AttributeError, ValueError):
    pass


@dataclass(frozen=True)
class CPEntry:
    """Capaian Pembelajaran entry."""
    id: str
    text: str
    source_document_id: str
    source_fragment_id: str
    source_page: int
    phase: str
    element: str


@dataclass
class TPEntry:
    """Tujuan Pembelajaran entry."""
    id: str
    text: str
    cognitive_level: str
    source_type: str  # teacher, school, imported, ai_generated
    derived_from_id: Optional[str] = None


@dataclass
class ATPEntry:
    """Alur Tujuan Pembelajaran entry."""
    id: str
    tp_ids: List[str]  # Ordered list of TP IDs


@dataclass
class CurriculumContext:
    """
    Complete curriculum context for AI generation.
    Contains all normative data that must not be changed by AI.
    """
    # Core identifiers
    education_system: str
    institution_type: str
    grade: str
    phase: str
    subject: str
    element: str
    curriculum_version: str
    
    # Normative data (immutable)
    cp: CPEntry
    tp_list: List[TPEntry]
    atp: ATPEntry

    # Authoritative user topic (BLOCKER 1); default keeps legacy
    # constructor call-sites (tests, tools) working unchanged.
    topic: str = ''
    
    # Rules
    rules: Dict = None
    
    # Metadata
    generated_at: str = None
    context_hash: str = None
    # How the CP element was resolved vs the user request (audit trail;
    # never silently overridden). Set by the pipeline's curriculum stage.
    element_resolution_note: str = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'education_system': self.education_system,
            'institution_type': self.institution_type,
            'grade': self.grade,
            'phase': self.phase,
            'subject': self.subject,
            'element': self.element,
            'curriculum_version': self.curriculum_version,
            # Topic is authoritative user input carried through the whole
            # pipeline (BLOCKER 1); exported so the module JSON shows it.
            'topic': self.topic,
            'cp': asdict(self.cp),
            'tp': [asdict(tp) for tp in self.tp_list],
            'atp': asdict(self.atp),
            'rules': self.rules,
            'metadata': {
                'generated_at': self.generated_at,
                'context_hash': self.context_hash
            }
        }
    
    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict) -> "CurriculumContext":
        """Rebuild a typed context from ``to_dict()`` output.

        Used to restore the authoritative context from persisted
        ``generated_modules.context_json`` (module_store) so edit
        re-validation keeps working after a server restart, without any
        in-memory dependency. Additive fields (topic, metadata) tolerate
        absence for rows written by older versions.
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
        return cls(
            education_system=data['education_system'],
            institution_type=data['institution_type'],
            grade=data['grade'],
            phase=data['phase'],
            subject=data['subject'],
            element=data['element'],
            curriculum_version=data['curriculum_version'],
            cp=CPEntry(**{k: cp_data[k] for k in
                          ('id', 'text', 'source_document_id',
                           'source_fragment_id', 'source_page',
                           'phase', 'element') if k in cp_data}),
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
    """Generates validated curriculum context."""
    
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
    ) -> Optional[CurriculumContext]:
        """
        Generate curriculum context.
        Returns: CurriculumContext if valid, None if invalid
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
        
        # Create CP entry (IMMUTABLE)
        cp = CPEntry(
            id=f"CP-{subject.replace(' ', '-')}-{phase}",
            text=cp_text,
            source_document_id=cp_source_doc,
            source_fragment_id=cp_source_frag,
            source_page=cp_page,
            phase=phase,
            element=element
        )
        
        # Create TP entries
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
        
        # Create ATP entry (IMMUTABLE ORDER)
        atp = ATPEntry(
            id=f"ATP-{subject.replace(' ', '-')}-{phase}",
            tp_ids=atp_tp_ids
        )
        
        # Define rules (IMMUTABLE)
        rules = {
            'minimum_tp_level': 'C3',
            'minimum_kktp_level': 'C3',
            'enforce_alignment': True,
            'allow_ai_tp_generation': True,
            'allow_ai_content_generation': True
        }
        
        # Create context
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
            context_hash=self._generate_hash(cp, atp)
        )
        
        return self.context
    
    def _validate_inputs(
        self,
        system: str,
        institution: str,
        phase: str,
        subject: str
    ) -> bool:
        """Validate curriculum inputs."""
        
        # Validate phase
        if phase not in ['A', 'B', 'C', 'D', 'E', 'F']:
            self.validation_errors.append(f"Invalid phase: {phase}")
            return False
        
        # Validate system
        if system not in ['KEMENAG', 'KEMENDIKDASMEN']:
            self.validation_errors.append(f"Invalid system: {system}")
            return False
        
        # Validate subject-system
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
        """Generate hash of immutable data."""
        import hashlib
        data = f"{cp.id}:{cp.text}:{atp.id}:{':'.join(atp.tp_ids)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def validate_context(self, context: CurriculumContext) -> Tuple[bool, List[str]]:
        """Validate context completeness."""
        errors = []
        
        if not context.cp.text:
            errors.append("CP text is empty")
        
        if not context.cp.source_document_id:
            errors.append("CP missing source document")
        
        if not context.tp_list:
            errors.append("No TP entries provided")
        
        if not context.atp.tp_ids:
            errors.append("ATP has no TP sequence")
        
        # Check all TPs in ATP exist
        tp_ids = {tp.id for tp in context.tp_list}
        for atp_id in context.atp.tp_ids:
            if atp_id not in tp_ids:
                errors.append(f"ATP references non-existent TP: {atp_id}")
        
        return len(errors) == 0, errors


class ContextValidator:
    """Validates curriculum context before AI generation."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
    
    def validate_context_completeness(self, context: CurriculumContext) -> Tuple[bool, str]:
        """
        Validate context is complete and valid.
        Returns: (is_valid, error_message)
        """
        if not context.cp.text:
            return False, "Capaian Pembelajaran tidak lengkap"
        
        if not context.tp_list:
            return False, "Tujuan Pembelajaran tidak ada"
        
        if not context.atp.tp_ids:
            return False, "Alur Tujuan Pembelajaran tidak valid"
        
        # Validate all TPs are in ATP
        tp_ids = {tp.id for tp in context.tp_list}
        for atp_id in context.atp.tp_ids:
            if atp_id not in tp_ids:
                return False, f"ATP mereferensikan TP yang tidak ada: {atp_id}"
        
        # Validate cognitive levels
        for tp in context.tp_list:
            level = tp.cognitive_level
            if level not in ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']:
                return False, f"Invalid cognitive level: {level}"
            
            # Check minimum C3 for validation
            if level in ['C1', 'C2']:
                return False, f"TP '{tp.id}' menggunakan level {level}. Minimum C3 diperlukan."
        
        return True, ""
    
    def print_context(self, context: CurriculumContext):
        """Print context for verification."""
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
    
    # Create sample context
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
            
            # Save to file
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
