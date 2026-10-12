import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { api } from '../api';
import type { RpmModule, ValidationResult, VersionMeta } from '../types';

export type Screen = 'landing' | 'beranda' | 'arsip' | 'formulir' | 'progres' | 'hasil';

interface GenerateJob {
  jobId: string;
  pollStart: number;
  retryParams: Record<string, unknown> | null;
}

interface SessionValue {
  generationId: string | null;
  module: RpmModule | null;
  validation: ValidationResult | null;
  version: number | null;
  versions: VersionMeta[];
  hasVersions: boolean;
  mode: 'review' | 'edit';
  dirty: boolean;
  draftChanges: Record<string, boolean>;
  job: GenerateJob | null;
  setJob: (j: GenerateJob | null) => void;
  setMode: (m: 'review' | 'edit') => void;
  setDirty: (d: boolean) => void;
  setDraftChanges: (d: Record<string, boolean>) => void;
  tampilkanHasil: (module: RpmModule, validation: ValidationResult | null, gid: string) => void;
  terapkanVersi: (
    version: VersionMeta & { module: RpmModule; validation?: ValidationResult | null },
    onVersions?: () => void,
  ) => void;
  setVersionsState: (versions: VersionMeta[]) => void;
  setVersion: (v: number | null) => void;
  openSession: (gid: string) => Promise<boolean>;
  clearSession: () => void;
  exportUrl: () => string | null;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [module, setModule] = useState<RpmModule | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [versions, setVersions] = useState<VersionMeta[]>([]);
  const [hasVersions, setHasVersions] = useState(false);
  const [mode, setMode] = useState<'review' | 'edit'>('review');
  const [dirty, setDirty] = useState(false);
  const [draftChanges, setDraftChanges] = useState<Record<string, boolean>>({});
  const [job, setJob] = useState<GenerateJob | null>(null);

  const tampilkanHasil = useCallback(
    (m: RpmModule, v: ValidationResult | null, gid: string) => {
      setModule(m);
      setValidation(v);
      setGenerationId(gid || (m.generation_id as string) || null);
      setMode('review');
      setDirty(false);
      setDraftChanges({});
      setVersion(null);
      setVersions([]);
      setHasVersions(false);
    },
    [],
  );

  const terapkanVersi = useCallback(
    (
      ver: VersionMeta & { module: RpmModule; validation?: ValidationResult | null },
      onVersions?: () => void,
    ) => {
      if (!ver || !ver.module) return;
      setModule(ver.module);
      setValidation(ver.validation ?? null);
      setVersion(ver.version_no);
      setDirty(false);
      if (onVersions) onVersions();
    },
    [],
  );

  const setVersionsState = useCallback((list: VersionMeta[]) => {
    setVersions(list);
    setHasVersions(list.length > 0);
  }, []);

  const openSession = useCallback(async (gid: string): Promise<boolean> => {
    try {
      const res = await api.getModule(gid);
      if (res.status === 'success' && res.module) {
        tampilkanHasil(res.module, res.validation || null, res.generation_id || gid);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }, [tampilkanHasil]);

  const clearSession = useCallback(() => {
    setGenerationId(null);
    setModule(null);
    setValidation(null);
    setVersion(null);
    setVersions([]);
    setHasVersions(false);
    setMode('review');
    setDirty(false);
    setDraftChanges({});
    setJob(null);
  }, []);

  const exportUrl = useCallback((): string | null => {
    if (!generationId) return null;
    let url = api.exportDocxUrl(generationId);
    if (hasVersions && version != null) url += '?version=' + encodeURIComponent(version);
    return url;
  }, [generationId, hasVersions, version]);

  const value = useMemo(
    () => ({
      generationId,
      module,
      validation,
      version,
      versions,
      hasVersions,
      mode,
      dirty,
      draftChanges,
      job,
      setJob,
      setMode,
      setDirty,
      setDraftChanges,
      tampilkanHasil,
      terapkanVersi,
      setVersionsState,
      setVersion,
      openSession,
      clearSession,
      exportUrl,
    }),
    [
      generationId, module, validation, version, versions, hasVersions, mode,
      dirty, draftChanges, job, setJob, tampilkanHasil,
      terapkanVersi, setVersionsState, openSession, clearSession, exportUrl,
    ],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession di luar SessionProvider');
  return ctx;
}

export function finalPassed(validation: ValidationResult | null): boolean {
  return !!((validation || {}).final && (validation as { final: { passed?: boolean } }).final.passed);
}
