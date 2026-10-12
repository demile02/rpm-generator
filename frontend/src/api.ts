/* Klien API Flask. Port setia ui/api.js: BASE relatif,
   error membawa .status/.data, upload via FormData, export via URL. */
import {
  ApiError,
  type BukuItem,
  type ContextResponse,
  type CurriculumElementsResponse,
  type CurriculumOptions,
  type CurriculumSubjectsResponse,
  type GenerateFormParams,
  type GenerationLogItem,
  type GenerationRecord,
  type GenStatusResponse,
  type ImportResponse,
  type ModuleResponse,
  type ModuleSummary,
  type RelevanceResponse,
  type StatsResponse,
  type VersionResponse,
  type VersionsResponse,
} from './types';
import { nextPollDelay, shouldAbortPolling, UPLOAD_POLL_MAX_ATTEMPTS } from './lib/uploadPolling';

const BASE = (import.meta.env.VITE_MODULE_API_BASE as string | undefined || '').replace(/\/$/, '');

async function parseJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const opts: RequestInit = { method, headers: { Accept: 'application/json' }, signal };
  if (body !== undefined) {
    (opts.headers as Record<string, string>)['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  const data = await parseJson(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

async function uploadFile<T>(
  path: string,
  file: File,
  onProgress?: (persen: number, tahap?: string) => void,
  signal?: AbortSignal,
): Promise<T> {
  /* Fetch tak mendukung progress upload, jadi pakai XHR agar persen
     kirim file tampil riil (0-100%). Untuk upload buku, server
     melanjutkan ekstraksi di background: setelah 100% terkirim,
     poll /api/buku/upload/status/<job_id> untuk persen ekstraksi. */
  const fd = new FormData();
  fd.append('file', file);
  const akhir = path === '/api/buku/upload' ? await kirimAsync(fd, path, onProgress, signal) : await kirimBiasa(fd, path, onProgress, signal);
  return akhir as T;
}

function kirimBiasa(
  fd: FormData,
  path: string,
  onProgress?: (persen: number, tahap?: string) => void,
  signal?: AbortSignal,
): Promise<unknown> {
  return new Promise<unknown>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', BASE + path);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)));
      }
    };
    xhr.onload = () => {
      let data: unknown = {};
      try {
        data = JSON.parse(xhr.responseText || '{}');
      } catch {
        /* abaikan, ditangani di bawah */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError(0, {}));
    xhr.onabort = () => reject(new DOMException('Upload dibatalkan.', 'AbortError'));
    const batalkan = (): void => xhr.abort();
    if (signal) {
      if (signal.aborted) {
        batalkan();
        return;
      }
      signal.addEventListener('abort', batalkan, { once: true });
      xhr.addEventListener('loadend', () => signal.removeEventListener('abort', batalkan), { once: true });
    }
    xhr.send(fd);
  });
}

async function kirimAsync(
  fd: FormData,
  path: string,
  onProgress?: (persen: number, tahap?: string) => void,
  signal?: AbortSignal,
): Promise<unknown> {
  /* Tahap 1: kirim file, 0-20% dari total tampilan. */
  fd.append('async', '1');
  const awal = await kirimBiasa(fd, path, (p) => {
    if (onProgress) onProgress(Math.round(p * 0.2));
  }, signal) as { status?: string; job_id?: string };
  const jobId = awal?.job_id || '';
  if (awal?.status !== 'accepted' || !jobId) return awal;
  /* Tahap 2: ekstraksi server, 20-100%. Poll berbatas waktu. */
  const startedAt = Date.now();
  let attempts = 0;
  for (;;) {
    if (signal?.aborted) throw new DOMException('Upload dibatalkan.', 'AbortError');
    if (shouldAbortPolling(startedAt) || attempts >= UPLOAD_POLL_MAX_ATTEMPTS) {
      throw new ApiError(408, { code: 'UPLOAD_POLL_TIMEOUT', message: 'Pemrosesan buku melewati batas waktu.' });
    }
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        signal?.removeEventListener('abort', batalkan);
        resolve();
      }, nextPollDelay(attempts));
      const batalkan = (): void => {
        window.clearTimeout(timer);
        reject(new DOMException('Upload dibatalkan.', 'AbortError'));
      };
      signal?.addEventListener('abort', batalkan, { once: true });
    });
    attempts += 1;
    const res = await fetch(BASE + path + '/status/' + encodeURIComponent(jobId), {
      headers: { Accept: 'application/json' },
      signal,
    });
    const data = await parseJson(res) as {
      status?: string; progress?: number; tahap?: string;
      errors?: unknown[];
    };
    if (!res.ok || data.status === 'error') {
      throw new ApiError(res.status, data);
    }
    if (data.status === 'success') {
      if (onProgress) onProgress(100, 'Selesai.');
      return data;
    }
    if (onProgress) {
      const p = Math.min(99, Math.max(0, Number(data.progress ?? 0)));
      onProgress(20 + Math.round(p * 0.8), data.tahap || 'Memproses…');
    }
  }
}

export const api = {
  getCurriculumOptions: (compact = false, signal?: AbortSignal) => request<CurriculumOptions>(
    'GET', compact ? '/api/curriculum/options?compact=1' : '/api/curriculum/options',
    undefined,
    signal,
  ),
  getCurriculumSubjects: (
    educationSystem: string,
    institutionType: string,
    grade: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      education_system: educationSystem,
      institution_type: institutionType,
      grade,
    });
    return request<CurriculumSubjectsResponse>('GET', `/api/curriculum/subjects?${query.toString()}`, undefined, signal);
  },
  getCurriculumElements: (
    subject: string,
    phase: string,
    educationSystem?: string,
    institutionType?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ subject, phase });
    if (educationSystem) query.set('education_system', educationSystem);
    if (institutionType) query.set('institution_type', institutionType);
    return request<CurriculumElementsResponse>('GET', `/api/curriculum/elements?${query.toString()}`, undefined, signal);
  },
  generateContext: (params: GenerateFormParams) =>
    request<ContextResponse>('POST', '/api/context/generate', params),
  cekRelevansi: (params: GenerateFormParams & { skip_relevance_check?: boolean }) =>
    request<RelevanceResponse>('POST', '/api/topic/relevance', params),
  generateModuleAsync: (params: GenerateFormParams) =>
    request<{ job_id: string }>('POST', '/api/module/generate', { async: true, ...params }),
  getGenerationStatus: (jobId: string) =>
    request<GenStatusResponse>('GET', '/api/generation/status/' + encodeURIComponent(jobId)),
  getModule: (generationId: string) =>
    request<ModuleResponse>('GET', '/api/module/' + encodeURIComponent(generationId)),
  listModules: () => request<{ modules?: ModuleSummary[] }>('GET', '/api/modules'),
  daftarBuku: () => request<{ buku?: BukuItem[] }>('GET', '/api/buku'),
  uploadBuku: (file: File, onProgress?: (persen: number, tahap?: string) => void, signal?: AbortSignal) =>
    uploadFile<{ document_id: string; judul?: string; halaman?: number; fragmen?: number }>(
      '/api/buku/upload',
      file,
      onProgress,
      signal,
    ),
  uploadModule: (file: File, onProgress?: (persen: number, tahap?: string) => void, signal?: AbortSignal) =>
    uploadFile<ImportResponse>('/api/modules/import', file, onProgress, signal),
  listGenerations: () =>
    request<{ generations?: GenerationLogItem[] }>('GET', '/api/generations'),
  getGenerationLog: (generationId: string) =>
    request<{ records?: GenerationRecord[] }>(
      'GET',
      '/api/generations/' + encodeURIComponent(generationId),
    ),
  deleteModule: (generationId: string) =>
    request<unknown>('DELETE', '/api/modules/' + encodeURIComponent(generationId)),
  deleteBuku: (documentId: string) =>
    request<{ deleted?: string }>('DELETE', '/api/buku/' + encodeURIComponent(documentId)),
  deleteGenerationLogs: (ids: string[]) =>
    request<{ deleted?: string[]; missing?: string[] }>('DELETE', '/api/generations', {
      generation_ids: ids,
    }),
  deleteVersion: (generationId: string, versionNo: number) =>
    request<{ latest_version?: number }>(
      'DELETE',
      '/api/module/' + encodeURIComponent(generationId) + '/versions/' + encodeURIComponent(versionNo),
    ),
  archiveModule: (generationId: string) =>
    request<unknown>('POST', '/api/modules/' + encodeURIComponent(generationId) + '/archive', {}),
  unarchiveModule: (generationId: string) =>
    request<unknown>(
      'POST',
      '/api/modules/' + encodeURIComponent(generationId) + '/unarchive',
      {},
    ),
  getStats: (summary = false) => request<StatsResponse>('GET', '/api/stats' + (summary ? '?summary=1' : '')),
  exportDocxUrl: (generationId: string) =>
    BASE + '/api/module/' + encodeURIComponent(generationId) + '/export-docx',
  listVersions: (generationId: string) =>
    request<VersionsResponse>(
      'GET',
      '/api/module/' + encodeURIComponent(generationId) + '/versions',
    ),
  getVersion: (generationId: string, versionNo: number) =>
    request<VersionResponse>(
      'GET',
      '/api/module/' + encodeURIComponent(generationId) + '/versions/' + encodeURIComponent(versionNo),
    ),
  saveVersion: (generationId: string, baseVersion: number, changes: Record<string, unknown>) =>
    request<VersionResponse>('POST', '/api/module/' + encodeURIComponent(generationId) + '/versions', {
      base_version: baseVersion,
      changes,
    }),
  saveCandidate: (
    generationId: string,
    baseVersion: number,
    candidate: unknown,
    changes: Record<string, unknown>,
  ) =>
    request<VersionResponse>('POST', '/api/module/' + encodeURIComponent(generationId) + '/versions', {
      base_version: baseVersion,
      candidate,
      changes,
    }),
  restoreVersion: (generationId: string, versionNo: number) =>
    request<VersionResponse>(
      'POST',
      '/api/module/' + encodeURIComponent(generationId) + '/versions/' + encodeURIComponent(versionNo) + '/restore',
      {},
    ),
  regenerateSection: async (
    generationId: string,
    baseVersion: number,
    target: string,
    counts?: Record<string, number>,
    extra?: Record<string, unknown>,
  ): Promise<GenStatusResponse> => {
    const body: Record<string, unknown> = {
      base_version: baseVersion,
      target,
      async: true,
      draft: true,
    };
    if (counts && typeof counts === 'object') body.counts = counts;
    if (extra && typeof extra === 'object') Object.assign(body, extra);
    const accepted = await request<{ job_id?: string } & GenStatusResponse>(
      'POST',
      '/api/module/' + encodeURIComponent(generationId) + '/regenerate',
      body,
    );
    if (!accepted.job_id) return accepted as GenStatusResponse;
    // Poll backoff 1s→5s seperti ui/api.js
    let tries = 0;
    for (;;) {
      const result = await request<GenStatusResponse>(
        'GET',
        '/api/generation/status/' + encodeURIComponent(accepted.job_id),
      );
      if (result.status === 'running') {
        tries += 1;
        await new Promise((r) => setTimeout(r, Math.min(1000 + tries * 500, 5000)));
        continue;
      }
      if (result.status === 'success') return result;
      throw new ApiError(422, result);
    }
  },
  finalizeVersion: (generationId: string) =>
    request<VersionResponse>(
      'POST',
      '/api/module/' + encodeURIComponent(generationId) + '/finalize',
      {},
    ),
};
