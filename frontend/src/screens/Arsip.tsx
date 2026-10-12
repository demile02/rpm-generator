import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ModuleSummary } from '../types';
import { useAlerts, useLoading } from '../state/appContext';
import { useSession } from '../state/session';
import { ConfirmDialog } from '../components/ConfirmDialog';

const STATUS_RPM: Record<string, string> = { validated: 'Tervalidasi', finalized: 'Final', draft: 'Draf' };

function metaRpm(m: ModuleSummary): string {
  const kelasFase = [m.grade, m.phase].filter((v) => v).join('/');
  return [m.subject, kelasFase, m.updated_at, STATUS_RPM[m.status || ''] || m.status]
    .filter((v) => v)
    .join(' · ');
}

export function Arsip() {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, perbaruiLoading, sembunyiLoading } = useLoading();
  const { openSession } = useSession();

  const [arsip, setArsip] = useState<ModuleSummary[]>([]);
  const [arsipError, setArsipError] = useState('');
  const [bukaError, setBukaError] = useState('');
  const [pilihan, setPilihan] = useState<Record<string, boolean>>({});
  const [menuBuka, setMenuBuka] = useState<string | null>(null);
  const [hapusOpen, setHapusOpen] = useState(false);
  const [hapusSibuk, setHapusSibuk] = useState(false);
  const [kembaliOpen, setKembaliOpen] = useState(false);
  const [kembaliSibuk, setKembaliSibuk] = useState(false);

  const pilihSemuaRef = useRef<HTMLInputElement | null>(null);

  async function muatArsip(): Promise<void> {
    setArsipError('');
    try {
      const res = await api.listModules();
      setArsip((res.modules || []).filter((m) => m.archived));
    } catch {
      const p = 'Gagal memuat arsip. Periksa server lalu muat ulang.';
      setArsipError(p);
      tampilAlert('Gagal memuat arsip', p);
    }
  }

  useEffect(() => {
    void muatArsip();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuBuka(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const gidTerlihat = arsip.map((m) => m.generation_id).filter((g) => g);
  const nDipilih = gidTerlihat.filter((g) => pilihan[g]).length;

  useEffect(() => {
    if (pilihSemuaRef.current) {
      pilihSemuaRef.current.indeterminate = nDipilih > 0 && nDipilih < gidTerlihat.length;
    }
  });

  function onPilihItem(gid: string, nyala: boolean): void {
    setPilihan((prev) => {
      const nx = { ...prev };
      if (nyala) nx[gid] = true;
      else delete nx[gid];
      return nx;
    });
  }

  function onPilihSemua(e: React.ChangeEvent<HTMLInputElement>): void {
    const nyala = e.target.checked;
    setPilihan(() => {
      if (!nyala) return {};
      const nx: Record<string, boolean> = {};
      gidTerlihat.forEach((g) => {
        nx[g] = true;
      });
      return nx;
    });
  }

  function pilihKartu(gid: string): void {
    setPilihan((prev) => ({ ...prev, [gid]: true }));
    setMenuBuka(null);
  }

  async function bukaRpm(gid: string): Promise<void> {
    if (!gid) return;
    setBukaError('');
    tampilLoading('Membuka sesi', 'Membuka sesi tersimpan…');
    const ok = await openSession(gid);
    sembunyiLoading();
    if (!ok) {
      const p = 'Sesi tidak ditemukan di penyimpanan server.';
      setBukaError(p);
      tampilAlert('Sesi tidak ditemukan', p);
      return;
    }
    try {
      window.history.replaceState(null, '', window.location.pathname + '?generation_id=' + encodeURIComponent(gid) + '#layar-hasil');
    } catch {
      /* URL opsional, abaikan */
    }
    if ((window.location.hash || '') !== '#layar-hasil') {
      window.location.hash = '#layar-hasil';
    } else {
      window.dispatchEvent(new Event('hashchange'));
    }
  }

  async function hapusTerpilih(): Promise<void> {
    const daftar = gidTerlihat.filter((g) => pilihan[g]);
    if (!daftar.length) {
      setHapusOpen(false);
      return;
    }
    setHapusSibuk(true);
    const gagal: string[] = [];
    tampilLoading('Menghapus RPM', 'Menghapus 1 dari ' + daftar.length + '…');
    for (let i = 0; i < daftar.length; i++) {
      perbaruiLoading('Menghapus ' + (i + 1) + ' dari ' + daftar.length + '…');
      try {
        await api.deleteModule(daftar[i]);
      } catch {
        gagal.push(daftar[i]);
      }
    }
    setHapusSibuk(false);
    sembunyiLoading();
    setHapusOpen(false);
    setPilihan((prev) => {
      const nx = { ...prev };
      daftar.forEach((g) => {
        if (!gagal.includes(g)) delete nx[g];
      });
      return nx;
    });
    setMenuBuka(null);
    await muatArsip();
    if (gagal.length) {
      const p = gagal.length + ' dari ' + daftar.length + ' RPM gagal dihapus. Pilihan yang gagal dipertahankan, silakan coba lagi.';
      setArsipError(p);
      tampilAlert('Hapus sebagian gagal', p);
    } else {
      tampilAlert('RPM dihapus', daftar.length + ' RPM dihapus dari riwayat.');
    }
  }

  async function kembalikanTerpilih(): Promise<void> {
    const daftar = gidTerlihat.filter((g) => pilihan[g]);
    if (!daftar.length) {
      setKembaliOpen(false);
      return;
    }
    setKembaliSibuk(true);
    const gagal: string[] = [];
    tampilLoading('Mengembalikan RPM', 'Mengembalikan 1 dari ' + daftar.length + '…');
    for (let i = 0; i < daftar.length; i++) {
      perbaruiLoading('Mengembalikan ' + (i + 1) + ' dari ' + daftar.length + '…');
      try {
        await api.unarchiveModule(daftar[i]);
      } catch {
        gagal.push(daftar[i]);
      }
    }
    setKembaliSibuk(false);
    sembunyiLoading();
    setKembaliOpen(false);
    setPilihan((prev) => {
      const nx = { ...prev };
      daftar.forEach((g) => {
        if (!gagal.includes(g)) delete nx[g];
      });
      return nx;
    });
    setMenuBuka(null);
    await muatArsip();
    if (gagal.length) {
      tampilAlert('Kembalikan sebagian gagal', gagal.length + ' dari ' + daftar.length + ' RPM gagal dikembalikan.');
    } else {
      tampilAlert('RPM dikembalikan', daftar.length + ' RPM kembali aktif di Beranda.');
    }
  }

  return (
    <section id="layar-arsip" className="screen" aria-labelledby="kicker-arsip">
      <h4 className="kicker kicker--judul" id="kicker-arsip">Arsip RPM</h4>
      <p className="lede">RPM yang diarsipkan tetap utuh dan tetap bisa dibuka, diedit, diregenerasi, dan diekspor.</p>
      <div id="arsip-error" className="error" role="alert" hidden={!arsipError}>
        {arsipError}
      </div>
      <div id="arsip-kosong" className="kosong" hidden={arsip.length > 0}>
        <span className="kosong__ikon kosong__ikon--coral" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /></svg>
        </span>
        <strong>Arsip masih kosong</strong>
        <p>RPM yang diarsipkan tersimpan di sini, tetap utuh dan bisa dibuka lagi.</p>
        <p className="form__actions">
          <a className="btn btn--aksi" href="#layar-formulir">
            Buat RPM
          </a>
        </p>
      </div>
      {arsip.length > 0 && (
        <div className="bulk" id="arsip-bulk-kontrol" hidden={nDipilih === 0}>
          <label className="bulk__pilih">
            <input
              ref={pilihSemuaRef}
              type="checkbox"
              id="arsip-bulk-pilih"
              checked={nDipilih > 0 && nDipilih === gidTerlihat.length}
              onChange={onPilihSemua}
              disabled={gidTerlihat.length === 0}
            />
            <span>Pilih semua</span>
          </label>
          <div className="bulk__bilah" id="arsip-bulk-bilah" hidden={nDipilih === 0}>
            <span id="arsip-bulk-jumlah" role="status">
              {nDipilih + ' dipilih'}
            </span>
            <button type="button" id="btn-kembalikan-pilih" className="btn" onClick={() => setKembaliOpen(true)}>
              Kembalikan
            </button>
            <button type="button" id="btn-hapus-arsip-pilih" className="btn btn--hapus" onClick={() => setHapusOpen(true)}>
              Hapus
            </button>
          </div>
        </div>
      )}
      <ul id="riwayat-arsip" className={'riwayat' + (nDipilih > 0 ? ' mode-pilih' : '')}>
        {arsip.map((m) => {
          const gid = m.generation_id || '';
          const judul = m.title || '(tanpa judul)';
          const menuId = 'menu-' + gid;
          const bukaHref = window.location.pathname + '?generation_id=' + encodeURIComponent(gid) + '#layar-hasil';
          return (
            <li key={gid} className="rpm-card bg-white border border-bord rounded-xl p-4 flex items-start gap-3">
              <label className="pilih mt-1">
                <input
                  type="checkbox"
                  className="pilih__box w-5 h-5 accent-primary"
                  data-gid={gid}
                  aria-label={'Pilih ' + judul}
                  checked={!!pilihan[gid]}
                  onChange={(e) => onPilihItem(gid, e.target.checked)}
                />
              </label>
              <div className="rpm-card__isi flex-1">
                <strong className="font-display text-text1">
                  {judul}
                  {m.origin === 'import' && (
                    <>
                      {' '}
                      <span className="badge-valid badge--lavender inline-block text-xs font-medium rounded px-2 py-0.5 text-text1 border border-bord">
                        Hasil upload
                      </span>
                    </>
                  )}
                  {m.archived && (
                    <>
                      {' '}
                      <span className="badge-valid badge--lavender inline-block text-xs font-medium rounded px-2 py-0.5 text-text1 border border-bord">
                        Arsip
                      </span>
                    </>
                  )}
                  {m.status === 'draft' && (
                    <>
                      {' '}
                      <span className="badge-valid is-gagal inline-block text-xs font-medium rounded px-2 py-0.5 bg-red-50 text-galat border border-galat">
                        Draf
                      </span>
                    </>
                  )}
                </strong>
                <p className="meta text-sm text-text2 mt-1">{metaRpm(m)}</p>
                <button
                  type="button"
                  className="titik"
                  data-titik={gid}
                  aria-label={'Opsi untuk ' + judul}
                  aria-expanded={menuBuka === gid}
                  aria-controls={menuId}
                  onClick={() => setMenuBuka(menuBuka === gid ? null : gid)}
                >
                  ⋮
                </button>
                <div className="menu-pilih" id={menuId} hidden={menuBuka !== gid} role="menu">
                  <button type="button" data-aksi-pilih={gid} role="menuitem" onClick={() => pilihKartu(gid)}>
                    Pilih
                  </button>
                </div>
              </div>
              <div className="form__actions flex gap-2">
                <a
                  className="btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1 inline-flex items-center"
                  href={bukaHref}
                  onClick={(e) => {
                    e.preventDefault();
                    void bukaRpm(gid);
                  }}
                >
                  Buka
                </a>
                {m.status && m.status !== 'draft' && (
                  <>
                    {' '}
                    <a
                      className="btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1 inline-flex items-center"
                      href={api.exportDocxUrl(gid)}
                    >
                      Export DOCX
                    </a>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <p id="buka-error" className="error" role="alert" hidden={!bukaError}>
        {bukaError}
      </p>

      <ConfirmDialog
        open={kembaliOpen}
        judul={'Kembalikan ' + nDipilih + ' RPM?'}
        pesan={nDipilih + ' RPM kembali aktif di Beranda.'}
        error=""
        confirmLabel="Kembalikan"
        cancelLabel="Batal"
        confirmClass="btn btn--aksi"
        busy={kembaliSibuk}
        onClose={() => {
          if (!kembaliSibuk) setKembaliOpen(false);
        }}
        onConfirm={() => void kembalikanTerpilih()}
      />
      <ConfirmDialog
        open={hapusOpen}
        judul={'Hapus ' + nDipilih + ' RPM arsip permanen?'}
        pesan={nDipilih + ' RPM arsip akan dihapus permanen dari riwayat. Tindakan ini tidak dapat dibatalkan.'}
        error=""
        confirmLabel="Hapus"
        cancelLabel="Batal"
        confirmClass="btn btn--hapus"
        busy={hapusSibuk}
        onClose={() => {
          if (!hapusSibuk) setHapusOpen(false);
        }}
        onConfirm={() => void hapusTerpilih()}
      />
    </section>
  );
}
