/* Kontrak tipe backend RPM Generator. Cermin JSON Flask src/app.py.
   Tanpa data palsu: semua field opsional sesuai respons nyata. */

export interface ApiErrorItem {
  code?: string;
  message?: string;
  stage?: string;
  section?: string;
  entity_id?: string;
  severity?: string;
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, data: unknown) {
    super('HTTP ' + status);
    this.status = status;
    this.data = data;
  }
}

export interface CurriculumOptions {
  status: string;
  systems: Record<
    string,
    {
      subjects: string[];
      institutions: Record<
        string,
        {
          grades: string[];
          grade_labels?: Record<string, string>;
          grade_phase?: Record<string, string>;
          phases?: string[];
        }
      >;
    }
  >;
  elements_by_subject?: Record<string, Record<string, string[]>>;
}

export interface CurriculumSubjectsResponse {
  status: string;
  education_system: string;
  institution_type: string;
  grade: string;
  phase: string;
  subjects: string[];
}

export interface CurriculumElementsResponse {
  status: string;
  subject: string;
  phase: string;
  elements: string[];
}

export interface CpInfo {
  id?: string;
  text?: string;
  phase?: string;
  element?: string;
  subject?: string;
  source_document_id?: string;
  source_fragment_id?: string;
  source_page?: string | number;
  [k: string]: unknown;
}

export interface ContextResponse {
  status: string;
  message?: string;
  context?: { cp?: CpInfo; [k: string]: unknown };
  errors?: ApiErrorItem[];
}

export interface BukuIdentitas {
  judul?: string;
  pengarang?: string;
  tahun?: string;
  penerbit?: string;
}

export interface BukuItem {
  document_id: string;
  judul?: string;
  nama_file?: string;
  ukuran?: number;
  diupload?: string;
  fragmen?: number;
  identitas?: BukuIdentitas;
}

export interface ModuleSummary {
  generation_id: string;
  title?: string;
  subject?: string;
  grade?: string;
  phase?: string;
  updated_at?: string;
  passed?: boolean;
  origin?: string;
  archived?: boolean;
  archived_at?: string | null;
  status?: string;
  latest_version?: number | null;
}

export interface VersionMeta {
  version_no: number;
  parent_version_no?: number | null;
  status?: string;
  alignment_status?: string;
  changed_sections?: string[];
  warnings?: string[];
  created_at?: string;
}

/* Modul RPM: struktur longgar — backend sumber kebenaran.
   Bagian yang disentuh editor diberi tipe di editor. */
export type RpmModule = Record<string, unknown> & {
  generation_id?: string;
  topic?: string;
  subject?: string;
  grade?: string;
  phase?: string;
};

export interface ValidationResult {
  final?: { passed?: boolean };
  [k: string]: unknown;
}

export interface ModuleResponse {
  status: string;
  generation_id?: string;
  module?: RpmModule;
  context?: unknown;
  validation?: ValidationResult | null;
  version_no?: number | null;
  updated_at?: string;
}

export interface VersionResponse {
  status: string;
  generation_id?: string;
  version: VersionMeta & {
    module: RpmModule;
    validation?: ValidationResult | null;
  };
}

export interface VersionsResponse {
  status: string;
  generation_id?: string;
  versions: VersionMeta[];
  latest_version?: number | null;
}

export interface GenStatusResponse {
  status: 'running' | 'warning' | 'success' | 'error';
  generation_id?: string;
  module?: RpmModule;
  validation?: ValidationResult | null;
  errors?: ApiErrorItem[];
  code?: string;
  message?: string;
  relevansi?: RelevanceItem[];
  saran?: string;
  perlu_warning?: boolean;
  timing?: Record<string, number | string | null>;
  version?: VersionMeta & { module: RpmModule; validation?: ValidationResult | null };
  regen_id?: string;
  draft?: boolean;
  [k: string]: unknown;
}

export interface GenerationLogItem {
  generation_id: string;
  status?: string;
  stages?: string[];
  attempts?: number;
  error_categories?: string[];
  started_at?: string;
  updated_at?: string;
}

export interface GenerationRecord {
  generation_id: string;
  stage?: string;
  attempt?: number;
  prompt_version?: string | null;
  prompt_hash?: string | null;
  model?: string;
  provider?: string;
  status?: string;
  error_category?: string | null;
  error?: string | null;
  duration_ms?: number | null;
  response_chars?: number | null;
  created_at?: string;
}

export interface StatsResponse {
  status: string;
  statistics?: {
    total_fragments?: number;
    total_cp_entries?: number;
    cp_by_subject?: Record<string, number>;
    total_documents?: number;
    database_status?: string;
  };
}

export interface ImportResponse {
  status: string;
  imported?: Array<{
    generation_id?: string;
    title?: string;
    subject?: string;
    grade?: string;
    phase?: string;
    version_no?: number;
    status?: string;
    draft_errors?: ApiErrorItem[];
    archived_lama?: string[];
  }>;
  rejected?: Array<{ title?: string; errors?: ApiErrorItem[] }>;
  errors?: ApiErrorItem[];
}

export interface GenerateFormParams {
  education_system: string;
  institution_type: string;
  grade: string;
  phase?: string;
  subject: string;
  element?: string;
  elements?: string[];
  topic: string;
  satuan_pendidikan?: string;
  semester?: string;
  tahun_ajaran?: string;
  penyusun?: string;
  jumlah_pertemuan?: string;
  jp_per_pertemuan?: string;
  assessment_counts?: {
    diagnostic?: string;
    formative?: string;
    summative?: string;
  };
  buku_document_id?: string;
  student_readiness?: string;
  skip_relevance_check?: boolean;
}

export interface RelevanceItem {
  elemen: string;
  nilai: string;
  alasan?: string;
}

export interface RelevanceResponse {
  status: string;
  relevansi?: RelevanceItem[];
  saran?: string;
  perlu_warning?: boolean;
  skipped?: boolean;
  fail_open?: boolean;
  code?: string;
  message?: string;
}

export interface ProfileData {
  penyusun: string;
  satuan_pendidikan: string;
  semester: string;
  tahun_ajaran: string;
}

export function pesanError(data: unknown): string {
  const d = data as { errors?: ApiErrorItem[] } | null;
  const errors = (d && d.errors) || [];
  if (!errors.length) return 'kesalahan tak dikenal';
  return errors
    .map((e) => (e.stage ? '[' + e.stage + '] ' : '') + (e.message || e.code))
    .join(' · ');
}
