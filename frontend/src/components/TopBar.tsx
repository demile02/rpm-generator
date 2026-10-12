import { useSession, type Screen } from '../state/session';

interface TopBarProps {
  screen: Screen;
  onOpenLog: () => void;
  onSaveGlobal: () => void;
}

const TAB_AKTIF: Record<Screen, string> = {
  landing: '',
  beranda: 'beranda',
  arsip: 'arsip',
  formulir: 'formulir',
  progres: '',
  hasil: '',
};

export function TopBar({ screen, onOpenLog, onSaveGlobal }: TopBarProps) {
  const { generationId, mode } = useSession();

  const diHasil = screen === 'hasil' && !!generationId;
  const tabAktif = TAB_AKTIF[screen];

  return (
    <>
      <header className="topbar">
        <div className="wrap topbar__inner">
          <div className="brand">
            <span className="brand__mark" aria-hidden="true"></span>
            <span className="brand__text">
              <strong>Generator RPM</strong>
              <small>Rencana Pembelajaran Mendalam</small>
            </span>
          </div>
          <nav
            className="topbar__nav"
            id="nav-utama"
            aria-label="Navigasi utama"
          >
            <a href="#layar-beranda" aria-current={tabAktif === 'beranda' ? 'page' : undefined}>Beranda</a>
            <a href="#layar-arsip" aria-current={tabAktif === 'arsip' ? 'page' : undefined}>Arsip</a>
            <button type="button" id="btn-buka-log" className="navlink" onClick={onOpenLog}>
              Log
            </button>
            <a href="#layar-formulir" id="link-buat-rpm" hidden={diHasil} aria-current={tabAktif === 'formulir' ? 'page' : undefined}>
              Buat RPM
            </a>
            <button
              type="button"
              id="btn-finalize"
              className="btn btn--aksi"
              hidden={!diHasil}
              title={mode === 'edit' ? 'Simpan perubahan editor' : 'Simpan perubahan'}
              onClick={onSaveGlobal}
            >
              Simpan perubahan
            </button>
          </nav>
        </div>
      </header>
      <nav className="tabbar" aria-label="Navigasi cepat">
        <a
          href="#layar-beranda"
          data-tab="beranda"
          className={tabAktif === 'beranda' ? 'aktif' : undefined}
          aria-current={tabAktif === 'beranda' ? 'page' : undefined}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M9 22V12h6v10" /></svg>
          <span>Beranda</span>
        </a>
        <a
          href="#layar-arsip"
          data-tab="arsip"
          className={tabAktif === 'arsip' ? 'aktif' : undefined}
          aria-current={tabAktif === 'arsip' ? 'page' : undefined}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /></svg>
          <span>Arsip</span>
        </a>
        <a
          href="#layar-formulir"
          data-tab="formulir"
          className={tabAktif === 'formulir' ? 'aktif' : undefined}
          aria-current={tabAktif === 'formulir' ? 'page' : undefined}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
          <span>Buat</span>
        </a>
        <button type="button" id="btn-tab-log" data-tab="log" onClick={onOpenLog}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M9 13h6M9 17h6" /></svg>
          <span>Log</span>
        </button>
      </nav>
    </>
  );
}
