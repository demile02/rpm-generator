import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import type { ProfileData } from '../types';

export interface AlertData {
  judul: string;
  pesan: string;
}

interface LoadingContextValue {
  loadingJudul: string | null;
  loadingStatus: string;
  tampilLoading: (judul: string, status?: string) => void;
  perbaruiLoading: (status: string) => void;
  sembunyiLoading: () => void;
}

interface AlertContextValue {
  alert: AlertData | null;
  tampilAlert: (judul: string, pesan: string) => void;
  tutupAlert: () => void;
}

interface ProfileContextValue {
  profile: ProfileData;
  refreshProfile: () => void;
}

interface AppContextValue extends LoadingContextValue, AlertContextValue, ProfileContextValue {}

export const PROFIL_KEY = 'rpm_profile';
export const BUKU_DEFAULT_KEY = 'rpm_buku_default';
export const PERNAH_BUKA_KEY = 'rpm_pernah_buka';

export function bacaProfil(): ProfileData {
  const profil: ProfileData = { penyusun: '', satuan_pendidikan: '', semester: '', tahun_ajaran: '' };
  try {
    const stored = window.localStorage?.getItem(PROFIL_KEY);
    if (!stored) return profil;
    const data = JSON.parse(stored) as Partial<ProfileData>;
    (['penyusun', 'satuan_pendidikan', 'semester', 'tahun_ajaran'] as const).forEach((k) => {
      if (typeof data[k] === 'string') profil[k] = data[k] as string;
    });
  } catch {
    /* profil rusak: pakai kosong */
  }
  return profil;
}

export function tulisProfil(profil: ProfileData): boolean {
  try {
    window.localStorage?.setItem(PROFIL_KEY, JSON.stringify(profil));
    return true;
  } catch {
    return false;
  }
}

export function bacaBukuDefault(): string {
  try {
    return window.localStorage?.getItem(BUKU_DEFAULT_KEY) || '';
  } catch {
    return '';
  }
}

export function tulisBukuDefault(id: string): boolean {
  try {
    if (id) window.localStorage?.setItem(BUKU_DEFAULT_KEY, id);
    else window.localStorage?.removeItem(BUKU_DEFAULT_KEY);
    return true;
  } catch {
    return false;
  }
}

const LoadingContext = createContext<LoadingContextValue | null>(null);
const AlertContext = createContext<AlertContextValue | null>(null);
const ProfileContext = createContext<ProfileContextValue | null>(null);

function requireContext<T>(ctx: T | null, name: string): T {
  if (!ctx) throw new Error(name + ' di luar AppProvider');
  return ctx;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [loadingJudul, setLoadingJudul] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState('');
  const [alert, setAlert] = useState<AlertData | null>(null);
  const [profile, setProfile] = useState<ProfileData>(() => bacaProfil());

  const tampilLoading = useCallback((judul: string, status = '') => {
    setLoadingJudul(judul);
    setLoadingStatus(status);
  }, []);
  const perbaruiLoading = useCallback((status: string) => {
    setLoadingStatus(status);
  }, []);
  const sembunyiLoading = useCallback(() => setLoadingJudul(null), []);
  const tampilAlert = useCallback((judul: string, pesan: string) => {
    setAlert({ judul, pesan });
  }, []);
  const tutupAlert = useCallback(() => setAlert(null), []);
  const refreshProfile = useCallback(() => setProfile(bacaProfil()), []);

  const loadingValue = useMemo(
    () => ({ loadingJudul, loadingStatus, tampilLoading, perbaruiLoading, sembunyiLoading }),
    [loadingJudul, loadingStatus, tampilLoading, perbaruiLoading, sembunyiLoading],
  );
  const alertValue = useMemo(
    () => ({ alert, tampilAlert, tutupAlert }),
    [alert, tampilAlert, tutupAlert],
  );
  const profileValue = useMemo(() => ({ profile, refreshProfile }), [profile, refreshProfile]);

  return (
    <LoadingContext.Provider value={loadingValue}>
      <AlertContext.Provider value={alertValue}>
        <ProfileContext.Provider value={profileValue}>
          {children}
        </ProfileContext.Provider>
      </AlertContext.Provider>
    </LoadingContext.Provider>
  );
}

export function useLoading(): LoadingContextValue {
  return requireContext(useContext(LoadingContext), 'useLoading');
}

export function useAlerts(): AlertContextValue {
  return requireContext(useContext(AlertContext), 'useAlerts');
}

export function useProfile(): ProfileContextValue {
  return requireContext(useContext(ProfileContext), 'useProfile');
}

/* Compatibility hook for callers not yet split by concern. */
export function useApp(): AppContextValue {
  const loading = useLoading();
  const alerts = useAlerts();
  const profile = useProfile();
  return useMemo(() => ({ ...loading, ...alerts, ...profile }), [loading, alerts, profile]);
}
