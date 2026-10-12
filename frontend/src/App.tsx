import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { AppProvider, PERNAH_BUKA_KEY, useAlerts } from './state/appContext';
import { SessionProvider, useSession, type Screen } from './state/session';
import { TopBar } from './components/TopBar';
import { Landing } from './components/Landing';
import { LogDialog } from './components/LogDialog';
import { Overlays } from './components/Overlays';
const Beranda = lazy(() => import('./screens/Beranda').then((m) => ({ default: m.Beranda })));
const Arsip = lazy(() => import('./screens/Arsip').then((m) => ({ default: m.Arsip })));
const Formulir = lazy(() => import('./screens/Formulir').then((m) => ({ default: m.Formulir })));
const Progres = lazy(() => import('./screens/Progres').then((m) => ({ default: m.Progres })));
const Hasil = lazy(() => import('./screens/Hasil').then((m) => ({ default: m.Hasil })));
const Editor = lazy(() => import('./screens/Editor').then((m) => ({ default: m.Editor })));

function hashKeScreen(hash: string): Screen {
  if (hash === '#layar-beranda') return 'beranda';
  if (hash === '#layar-arsip') return 'arsip';
  if (hash === '#layar-formulir') return 'formulir';
  if (hash === '#layar-progres') return 'progres';
  if (hash === '#layar-hasil') return 'hasil';
  return 'landing';
}

function bersihkanGenerationIdUntukTab(hash: string): void {
  if (!['#layar-beranda', '#layar-arsip', '#layar-formulir'].includes(hash)) return;
  if (!new URLSearchParams(window.location.search || '').has('generation_id')) return;
  try {
    window.history.replaceState(null, '', window.location.pathname + hash);
  } catch {
    /* URL opsional, navigasi hash tetap berjalan. */
  }
}

function Shell() {
  const { tampilAlert } = useAlerts();
  const session = useSession();
  const { module, mode, setMode, dirty } = session;
  const [screen, setScreen] = useState<Screen>(() => hashKeScreen(window.location.hash || ''));
  const [logOpen, setLogOpen] = useState(false);
  const hashTerakhirRef = useRef(window.location.hash || '');
  // Ref sesi terbaru untuk router hash (hindari closure basi):
  // handler terdaftar sekali, tapi baca module/openSession terkini.
  const sesiRef = useRef(session);
  sesiRef.current = session;

  /* Router hash — warisi route() legacy: ?generation_id= menang,
     returning user (rpm_pernah_buka) ke Beranda, anchor #a- biarkan. */
  useEffect(() => {
    let lepas = false;
    const bukaSesi = async (cb?: (ok: boolean) => void): Promise<void> => {
      const gid = new URLSearchParams(window.location.search || '').get('generation_id');
      if (!gid) {
        cb?.(false);
        return;
      }
      const ok = await sesiRef.current.openSession(gid);
      if (lepas) return;
      if (ok) {
        setScreen('hasil');
        cb?.(true);
      } else {
        cb?.(false);
      }
    };
    const route = (): void => {
      const hash = window.location.hash || '';
      bersihkanGenerationIdUntukTab(hash);
      const sesi = sesiRef.current;
      const bolehTinggalkan = (): boolean => {
        if (!sesi.dirty) {
          hashTerakhirRef.current = hash;
          return true;
        }
        try {
          const boleh = window.confirm('Perubahan belum disimpan. Tinggalkan halaman dan buang perubahan?');
          if (boleh) {
            hashTerakhirRef.current = hash;
            return true;
          }
          const kembali = hashTerakhirRef.current || '#layar-hasil';
          window.history.replaceState(null, '', window.location.pathname + window.location.search + kembali);
          return false;
        } catch {
          return false;
        }
      };
      if (hash === '#layar-formulir') {
        if (!bolehTinggalkan()) return;
        setScreen('formulir');
      }
      else if (hash === '#layar-beranda') {
        if (!bolehTinggalkan()) return;
        setScreen('beranda');
      }
      else if (hash === '#layar-arsip') {
        if (!bolehTinggalkan()) return;
        setScreen('arsip');
      }
      else if (hash === '#layar-hasil') {
        if (sesi.module) setScreen('hasil');
        else void bukaSesi((ok) => {
          if (!ok) {
            tampilAlert('Sesi tidak ditemukan', 'Sesi tidak ditemukan di penyimpanan server.');
            setScreen('beranda');
          }
        });
      } else if (hash === '' || hash === '#' || hash === '#layar-landing') {
        const q = new URLSearchParams(window.location.search || '').get('generation_id');
        if (q) {
          void bukaSesi((ok) => {
            if (!ok) {
              tampilAlert('Sesi tidak ditemukan', 'Sesi tidak ditemukan di penyimpanan server.');
              setScreen('beranda');
            }
          });
          return;
        }
        let pernah = false;
        try {
          pernah = !!window.localStorage?.getItem(PERNAH_BUKA_KEY);
        } catch {
          /* abaikan */
        }
        if ((hash === '' || hash === '#') && pernah) {
          setScreen('beranda');
          return;
        }
        try {
          window.localStorage?.setItem(PERNAH_BUKA_KEY, '1');
        } catch {
          /* abaikan */
        }
        setScreen('landing');
      } else if (!sesi.module && hash.startsWith('#a-')) {
        const q = new URLSearchParams(window.location.search || '').get('generation_id');
        if (q) void bukaSesi();
      }
      // Content shortcut anchors must keep browser/native scroll position.
      // Screen navigation still starts at top; otherwise first shortcut click
      // gets overwritten by the router and second click appears to work.
      if (
        hash === '' || hash === '#' ||
        ['#layar-landing', '#layar-beranda', '#layar-arsip', '#layar-formulir', '#layar-progres', '#layar-hasil'].includes(hash)
      ) {
        window.scrollTo(0, 0);
      }
    };
    window.addEventListener('hashchange', route);
    route();
    return () => {
      lepas = true;
      window.removeEventListener('hashchange', route);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const keluarSesi = useCallback(() => {
    try {
      const q = window.location.search || '';
      if (q.indexOf('generation_id') !== -1) {
        window.history.replaceState(null, '', window.location.pathname + (window.location.hash || ''));
      }
    } catch {
      /* abaikan */
    }
  }, []);

  /* Simpan global (topbar): klik tombol Simpan di Editor. */
  const simpanGlobal = useCallback(() => {
    const btn = document.getElementById('btn-simpan-versi');
    if (btn) {
      btn.click();
    } else {
      tampilAlert('Belum bisa menyimpan', 'Buka mode Edit dulu sebelum menyimpan.');
    }
  }, [tampilAlert]);

  const tinggalkan = useCallback((): boolean => {
    if (!dirty) return true;
    try {
      return window.confirm('Perubahan belum disimpan. Tinggalkan halaman dan buang perubahan?');
    } catch {
      return true;
    }
  }, [dirty]);

  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, [dirty]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && logOpen) setLogOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [logOpen]);

  /* Swipe pindah tab: konten ikut jari saat drag, lalu route baru
     mereset transform stage agar shell dan tabbar tetap stabil di mobile.
     Mati di desktop, layar non-tab, overlay/menu, dan field isian. */
  const screenRef = useRef(screen);
  screenRef.current = screen;
  useEffect(() => {
    const el = document.getElementById('swipe-stage');
    if (!el) return;
    const URUT: Screen[] = ['beranda', 'arsip', 'formulir'];
    // Karet di ujung: molor dikit dengan tahanan, tanpa bounce.
    const karet = (over: number): number => {
      const t = over < 0 ? -1 : 1;
      return t * Math.min(64, Math.abs(over) * 0.25);
    };
    const gerakHalus = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let x0 = 0, y0 = 0, geser = 0, lebar = 0;
    let arah: 'belum' | 'datar' | 'tegak' = 'belum';
    let gestureAktif = false;
    let timer: number | null = null;
    const setGeser = (px: number, animasi: boolean, cepat = false): void => {
      el.style.transition = animasi && !gerakHalus ? `transform ${cepat ? 0.16 : 0.3}s ease-out` : 'none';
      el.style.transform = px === 0 ? '' : `translateX(${px}px)`;
    };
    const mulai = (e: TouchEvent): void => {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
        setGeser(0, false);
      }
      arah = 'belum';
      gestureAktif = false;
      geser = 0;
      if (e.touches.length !== 1) return;
      if (!window.matchMedia('(max-width: 719px)').matches) return;
      if (screenRef.current === 'hasil') return;
      if (URUT.indexOf(screenRef.current) === -1) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest('#layar-hasil, .hasil-shortcut')) return;
      if (t?.closest('input, textarea, select, [contenteditable]')) return;
      if (document.querySelector('.overlay, .menu-pilih:not([hidden])')) return;
      const s = e.touches[0];
      x0 = s.clientX;
      y0 = s.clientY;
      lebar = el.getBoundingClientRect().width || window.innerWidth;
      gestureAktif = true;
    };
    const gerak = (e: TouchEvent): void => {
      if (!gestureAktif || arah === 'tegak') return;
      if (arah === 'belum' && e.touches.length !== 1) return;
      const s = e.touches[0];
      if (!s) return;
      const dx = s.clientX - x0;
      const dy = s.clientY - y0;
      if (arah === 'belum') {
        // Dead-zone 10px: gerakan kecil bukan swipe.
        if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
        // Vertikal dominan = scroll halaman, batalkan geser.
        if (Math.abs(dx) < Math.abs(dy) * 1.5) {
          arah = 'tegak';
          return;
        }
        arah = 'datar';
      }
      const i = URUT.indexOf(screenRef.current);
      const j = dx < 0 ? i + 1 : i - 1;
      geser = j < 0 || j >= URUT.length ? karet(dx) : Math.max(-lebar, Math.min(lebar, dx));
      setGeser(geser, false);
      if (e.cancelable) e.preventDefault();
    };
    const selesai = (e: TouchEvent): void => {
      const jadi = arah;
      arah = 'belum';
      gestureAktif = false;
      if (jadi !== 'datar') return;
      const s = e.changedTouches[0];
      const dx = s ? s.clientX - x0 : geser;
      const i = URUT.indexOf(screenRef.current);
      const j = dx < 0 ? i + 1 : i - 1;
      const ambang = Math.max(60, lebar * 0.2);
      if (s && Math.abs(dx) >= ambang && j >= 0 && j < URUT.length) {
        const dir = dx < 0 ? -1 : 1;
        const target = '#layar-' + URUT[j];
        if (gerakHalus) {
          window.location.hash = target;
          geser = 0;
          return;
        }
        // Commit: layarkan keluar searah, lalu pindah + masuk dari sisi datang.
        setGeser(dir * lebar, true, true);
        timer = window.setTimeout(() => {
          timer = null;
          window.location.hash = target;
        }, 170);
        geser = 0;
        return;
      }
      // Di bawah ambang / mentok ujung: snap kembali.
      geser = 0;
      setGeser(0, true);
    };
    const batal = (): void => {
      if (timer !== null) return;
      arah = 'belum';
      gestureAktif = false;
      geser = 0;
      setGeser(0, true);
    };
    el.addEventListener('touchstart', mulai, { passive: true });
    el.addEventListener('touchmove', gerak, { passive: false });
    el.addEventListener('touchend', selesai, { passive: true });
    el.addEventListener('touchcancel', batal, { passive: true });
    return () => {
      if (timer !== null) window.clearTimeout(timer);
      el.removeEventListener('touchstart', mulai);
      el.removeEventListener('touchmove', gerak);
      el.removeEventListener('touchend', selesai);
      el.removeEventListener('touchcancel', batal);
    };
  }, []);

  // Route changes must clear swipe residue before new screen paints.
  useEffect(() => {
    const el = document.getElementById('swipe-stage');
    if (!el) return;
    el.style.transition = 'none';
    el.style.transform = '';
  }, [screen]);

  return (
    <>
      <div className="grain" aria-hidden="true" />
      {/* Blob global ala Cari Guru: ciri Softly di setiap layar. */}
      <div className="blob-global" aria-hidden="true">
        <span className="blob blob--coral" style={{ width: 288, height: 288, left: '-4rem', top: '5rem' }} />
        <span className="blob blob--lavender" style={{ width: 340, height: 340, right: '-5rem', top: '38%' }} />
      </div>
      <a className="lewati" href="#konten">
        Lewati ke konten
      </a>
      <TopBar screen={screen} onOpenLog={() => setLogOpen(true)} onSaveGlobal={simpanGlobal} />
      <main className="wrap" id="konten">
        <div id="swipe-stage" className="swipe-stage">
          <Suspense fallback={<section className="screen" aria-live="polite"><p className="meta">Memuat halaman…</p></section>}>
            {screen === 'landing' && <Landing />}
            {screen === 'beranda' && <Beranda />}
            {screen === 'arsip' && <Arsip />}
            {screen === 'formulir' && (
              <Formulir
                onDone={() => {
                  keluarSesi();
                  window.location.hash = '#layar-progres';
                  setScreen('progres');
                }}
              />
            )}
            {screen === 'progres' && (
              <Progres
                onBack={() => {
                  if (!tinggalkan()) return;
                  window.location.hash = '#layar-formulir';
                  setScreen('formulir');
                }}
                onSuccess={() => setScreen('hasil')}
              />
            )}
            {screen === 'hasil' &&
              (mode === 'edit' ? (
                <section id="layar-hasil" className="screen" aria-labelledby="judul-hasil">
                  <h4 className="kicker kicker--judul" id="judul-hasil">Pratinjau RPM</h4>
                  <div className="hasil-badan">
                    <div className="hasil-dokumen">
                      <Editor
                        onDone={() => {
                          setMode('review');
                        }}
                      />
                    </div>
                  </div>
                </section>
              ) : (
                <Hasil
                  onEdit={() => {
                    if (!module) return;
                    setMode('edit');
                  }}
                />
              ))}
          </Suspense>
        </div>
      </main>
      <footer className="app-footer">
        <p className="meta">Generator RPM: Rencana Pembelajaran Mendalam dari CP resmi.</p>
      </footer>
      <LogDialog open={logOpen} onClose={() => setLogOpen(false)} />
      <Overlays />
    </>
  );
}

export default function App() {
  return (
    <AppProvider>
      <SessionProvider>
        <Shell />
      </SessionProvider>
    </AppProvider>
  );
}
