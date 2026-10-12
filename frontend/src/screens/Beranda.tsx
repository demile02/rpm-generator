import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { pesanError } from '../types';
import type { BukuItem, ModuleSummary } from '../types';
import { bacaBukuDefault, tulisBukuDefault, useAlerts, useLoading, useProfile } from '../state/appContext';
import { useSession } from '../state/session';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ProfileDialog } from '../components/ProfileDialog';

const STATUS_RPM: Record<string, string> = { validated: 'Tervalidasi', finalized: 'Final', draft: 'Draf' };

function metaRpm(m: ModuleSummary): string {
  const kelasFase = [m.grade, m.phase].filter((v) => v).join('/');
  return [m.subject, kelasFase, m.updated_at, STATUS_RPM[m.status || ''] || m.status]
    .filter((v) => v)
    .join(' · ');
}

function metaBuku(b: BukuItem): string {
  const idn = b.identitas || {};
  const kepengarangan = [idn.pengarang, idn.tahun ? '(' + idn.tahun + ')' : '', idn.penerbit ? '· ' + idn.penerbit : '']
    .filter((v) => v)
    .join(' ');
  return [(b.fragmen || 0) + ' fragmen', b.ukuran ? Math.round(b.ukuran / 1024) + ' KB' : '', kepengarangan]
    .filter((v) => v)
    .join(' · ');
}

function judulBuku(b: BukuItem): string {
  /* Judul asli dari identitas buku; fallback nama file bila tak ada. */
  const idn = b.identitas || {};
  return idn.judul || b.judul || b.document_id || '(tanpa judul)';
}

const BATAS_UPLOAD_BYTE = 10 * 1024 * 1024;

function formatUkuran(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
  if (n >= 1024) return Math.round(n / 1024) + ' KB';
  return n + ' B';
}

function kodeErrorUpload(data: unknown): string {
  const d = data as { errors?: Array<{ code?: string }> } | null;
  return ((d && d.errors) || []).map((e) => e.code || '').join(' ');
}

/* Pesan gagal upload jujur: 413 BODY_TOO_LARGE = server menolak body >2MB,
   UPLOAD_TOO_LARGE = cek 10MB lolos tapi file kebesaran. Sertakan ukuran
   file aktual agar user paham kenapa gagal. */
function pesanGagalUpload(err: unknown, file: File, prefix: string, suffixUmum: string): string {
  const data = (err as { data?: unknown } | null)?.data;
  const status = (err as { status?: unknown } | null)?.status;
  const kode = kodeErrorUpload(data);
  const nama = '"' + file.name + '" (' + formatUkuran(file.size) + ')';
  if (kode.includes('BODY_TOO_LARGE') || (status === 413 && !kode.includes('UPLOAD_TOO_LARGE'))) {
    return prefix + ' gagal: file ' + nama + ' ditolak server (batas request 2MB terlampaui). Kecilkan/kompres file lalu coba lagi.';
  }
  if (kode.includes('UPLOAD_TOO_LARGE') || status === 413) {
    return prefix + ' gagal: file ' + nama + ' melebihi 10MB. Kecilkan/kompres file lalu coba lagi.';
  }
  return prefix + ' gagal: ' + pesanError(data) + ' ' + nama + ' ' + suffixUmum;
}

export function Beranda() {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, perbaruiLoading, sembunyiLoading } = useLoading();
  const { profile } = useProfile();
  const { openSession } = useSession();

  const [profilOpen, setProfilOpen] = useState(false);
  const [buku, setBuku] = useState<BukuItem[]>([]);
  const [bukuDefault, setBukuDefault] = useState<string>(() => bacaBukuDefault());
  const [bukuError, setBukuError] = useState('');
  const [bukuHasil, setBukuHasil] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadHasil, setUploadHasil] = useState('');
  const [riwayat, setRiwayat] = useState<ModuleSummary[]>([]);
  const [riwayatError, setRiwayatError] = useState('');
  const [bukaError, setBukaError] = useState('');
  const [pilihan, setPilihan] = useState<Record<string, boolean>>({});
  const [menuBuka, setMenuBuka] = useState<string | null>(null);
  const [hapusOpen, setHapusOpen] = useState(false);
  const [hapusSibuk, setHapusSibuk] = useState(false);
  const [hapusBukuId, setHapusBukuId] = useState('');
  const [hapusBukuJudul, setHapusBukuJudul] = useState('');
  const [hapusBukuSibuk, setHapusBukuSibuk] = useState(false);
  const [arsipOpen, setArsipOpen] = useState(false);
  const [arsipSibuk, setArsipSibuk] = useState(false);

  const fileBukuRef = useRef<HTMLInputElement | null>(null);
  const fileRpmRef = useRef<HTMLInputElement | null>(null);
  const pilihSemuaRef = useRef<HTMLInputElement | null>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => {
    uploadAbortRef.current?.abort();
    sembunyiLoading();
  }, [sembunyiLoading]);

  async function muatKoleksi(): Promise<void> {
    try {
      const res = await api.daftarBuku();
      const daftar = res.buku || [];
      let def = bacaBukuDefault();
      if (def && !daftar.some((b) => b.document_id === def)) {
        tulisBukuDefault('');
        def = '';
      }
      setBukuDefault(def);
      setBuku(daftar);
    } catch {
      setBuku([]);
    }
  }

  async function muatRiwayat(): Promise<void> {
    setRiwayatError('');
    try {
      const res = await api.listModules();
      setRiwayat((res.modules || []).filter((m) => !m.archived));
    } catch {
      const p = 'Gagal memuat riwayat RPM. Periksa server lalu muat ulang halaman.';
      setRiwayatError(p);
      tampilAlert('Gagal memuat riwayat', p);
    }
  }

  useEffect(() => {
    void muatKoleksi();
    void muatRiwayat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuBuka(null);
    };
    /* Tap di mana saja menutup menu titik-tiga yang terbuka. */
    const onTap = (e: Event) => {
      const t = e.target as HTMLElement | null;
      if (t && t.closest && t.closest('.menu-pilih,.titik')) return;
      setMenuBuka(null);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onTap, true);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onTap, true);
    };
  }, []);

  const gidTerlihat = riwayat.map((m) => m.generation_id).filter((g) => g);
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

  function onToggleDefault(id: string): void {
    const lama = bacaBukuDefault();
    const baru = lama === id ? '' : id;
    tulisBukuDefault(baru);
    setBukuDefault(baru);
    tampilAlert(
      baru ? 'Buku default dipilih' : 'Buku default dibatalkan',
      baru ? 'Menu generate otomatis memilih buku ini.' : 'Menu generate tidak lagi memilih otomatis.',
    );
    void muatKoleksi();
  }

  async function onFileBuku(e: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const input = e.currentTarget;
    const file = input.files?.[0];
    setBukuError('');
    setBukuHasil('');
    if (!file) {
      setBukuError('Pilih file PDF/DOCX dulu.');
      return;
    }
    if (file.size > BATAS_UPLOAD_BYTE) {
      input.value = '';
      const pesanBesar = 'Upload buku gagal: file "' + file.name + '" (' + formatUkuran(file.size) + ') melebihi 10MB. Kecilkan/kompres file lalu coba lagi.';
      setBukuError(pesanBesar);
      tampilAlert('Upload buku gagal', pesanBesar);
      return;
    }
    uploadAbortRef.current?.abort();
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    tampilLoading('Mengupload buku', '0% dari ' + file.name + '…');
    try {
      /* Persen riil dua tahap: kirim file, lalu ekstraksi server. */
      const res = await api.uploadBuku(file, (p, tahap) => {
        perbaruiLoading(p + '% dari ' + file.name + (tahap ? ' (' + tahap + ')' : '…'));
      }, controller.signal);
      sembunyiLoading();
      if (uploadAbortRef.current === controller) uploadAbortRef.current = null;
      input.value = '';
      const pesan = 'Buku "' + (res.judul || res.document_id) + '" masuk: ' + res.fragmen + ' fragmen dari ' + res.halaman + ' halaman.';
      setBukuHasil(pesan);
      tampilAlert('Buku diupload', pesan);
      await muatKoleksi();
    } catch (err) {
      if (uploadAbortRef.current !== controller || (err instanceof DOMException && err.name === 'AbortError')) return;
      uploadAbortRef.current = null;
      sembunyiLoading();
      const pesan = pesanGagalUpload(err, file, 'Upload buku', '(PDF/DOCX, maks 10MB).');
      setBukuError(pesan);
      tampilAlert('Upload buku gagal', pesan);
    }
  }

  async function onFileRpm(e: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    setUploadError('');
    setUploadHasil('');
    if (file.size > BATAS_UPLOAD_BYTE) {
      const pesanBesar = 'Upload gagal: file "' + file.name + '" (' + formatUkuran(file.size) + ') melebihi 10MB. Kecilkan/kompres file lalu coba lagi.';
      setUploadError(pesanBesar);
      tampilAlert('Upload gagal', pesanBesar);
      return;
    }
    uploadAbortRef.current?.abort();
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    tampilLoading('Mengupload RPM', '0% dari ' + file.name + '…');
    try {
      const res = await api.uploadModule(file, (p) => {
        if (p < 100) perbaruiLoading(p + '% dari ' + file.name + '…');
        else perbaruiLoading('100% terkirim, memproses ' + file.name + '…');
      }, controller.signal);
      sembunyiLoading();
      if (uploadAbortRef.current === controller) uploadAbortRef.current = null;
      const masuk = res.imported || [];
      const tolak = res.rejected || [];
      const draf = masuk.filter((r) => r.status === 'draft').length;
      let pesan = masuk.length + ' RPM masuk Beranda' + (draf ? ' (' + draf + ' draf, perlu perbaikan)' : '') + (tolak.length ? ', ' + tolak.length + ' ditolak' : '') + '.';
      const autoArsip = masuk.reduce((n, r) => n + (r.archived_lama || []).length, 0);
      if (autoArsip) {
        pesan += ' ' + autoArsip + ' RPM lama berjudul sama dipindah ke Arsip.';
      }
      if (tolak.length) {
        const pesanTolak = tolak.map((r) => (r.title || '(tanpa judul)') + ': ' + pesanError({ errors: r.errors })).join(' ');
        setUploadError(pesanTolak);
        if (!masuk.length) {
          tampilAlert('Upload ditolak', pesanTolak);
        }
      }
      if (masuk.length) {
        setUploadHasil(pesan);
        tampilAlert(
          tolak.length ? 'Upload sebagian masuk' : 'Upload berhasil',
          pesan + (tolak.length ? ' Yang ditolak: ' + tolak.map((r) => (r.title || '(tanpa judul)') + ': ' + pesanError({ errors: r.errors })).join(' ') : ''),
        );
        await muatRiwayat();
      } else if (!tolak.length) {
        const pesanNihil = 'Tidak ada RPM yang masuk. ' + pesanError(res);
        setUploadError(pesanNihil);
        tampilAlert('Upload gagal', pesanNihil);
      }
    } catch (err) {
      if (uploadAbortRef.current !== controller || (err instanceof DOMException && err.name === 'AbortError')) return;
      uploadAbortRef.current = null;
      sembunyiLoading();
      const pesan = pesanGagalUpload(err, file, 'Upload', '(hanya DOCX/PDF hasil generate aplikasi, maks 10MB).');
      setUploadError(pesan);
      tampilAlert('Upload gagal', pesan);
    }
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

  async function hapusBuku(): Promise<void> {
    const id = hapusBukuId;
    if (!id) {
      setHapusBukuId('');
      return;
    }
    setHapusBukuSibuk(true);
    tampilLoading('Menghapus buku', 'Menghapus "' + hapusBukuJudul + '"…');
    try {
      await api.deleteBuku(id);
      sembunyiLoading();
      if (bacaBukuDefault() === id) tulisBukuDefault('');
      await muatKoleksi();
      tampilAlert('Buku dihapus', '"' + hapusBukuJudul + '" dihapus permanen dari koleksi.');
    } catch {
      sembunyiLoading();
      const p = 'Gagal menghapus "' + hapusBukuJudul + '". Silakan coba lagi.';
      setBukuError(p);
      tampilAlert('Hapus buku gagal', p);
    }
    setHapusBukuSibuk(false);
    setHapusBukuId('');
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
    await muatRiwayat();
    if (gagal.length) {
      const p = gagal.length + ' dari ' + daftar.length + ' RPM gagal dihapus. Pilihan yang gagal dipertahankan, silakan coba lagi.';
      setRiwayatError(p);
      tampilAlert('Hapus sebagian gagal', p);
    } else {
      tampilAlert('RPM dihapus', daftar.length + ' RPM dihapus dari riwayat.');
    }
  }

  async function arsipTerpilih(): Promise<void> {
    const daftar = gidTerlihat.filter((g) => pilihan[g]);
    if (!daftar.length) {
      setArsipOpen(false);
      return;
    }
    setArsipSibuk(true);
    const gagal: string[] = [];
    tampilLoading('Mengarsipkan RPM', 'Mengarsipkan 1 dari ' + daftar.length + '…');
    for (let i = 0; i < daftar.length; i++) {
      perbaruiLoading('Mengarsipkan ' + (i + 1) + ' dari ' + daftar.length + '…');
      try {
        await api.archiveModule(daftar[i]);
      } catch {
        gagal.push(daftar[i]);
      }
    }
    setArsipSibuk(false);
    sembunyiLoading();
    setArsipOpen(false);
    setPilihan((prev) => {
      const nx = { ...prev };
      daftar.forEach((g) => {
        if (!gagal.includes(g)) delete nx[g];
      });
      return nx;
    });
    setMenuBuka(null);
    await muatRiwayat();
    if (gagal.length) {
      tampilAlert('Arsip sebagian gagal', gagal.length + ' dari ' + daftar.length + ' RPM gagal diarsipkan. Silakan coba lagi.');
    } else {
      tampilAlert('RPM diarsipkan', daftar.length + ' RPM dipindah ke Arsip.');
    }
  }

  const barisProfil: Array<[string, string]> = [
    ['Nama Penyusun', profile.penyusun],
    ['Satuan Pendidikan', profile.satuan_pendidikan],
    ['Semester', profile.semester],
    ['Tahun Pelajaran', profile.tahun_ajaran],
  ];
  const profilAda = barisProfil.some((r) => r[1]);

  return (
    <section id="layar-beranda" className="screen" aria-labelledby="kicker-beranda">
      <h4 className="kicker kicker--judul" id="kicker-beranda">RPM Anda</h4>
      <div className="profil" aria-labelledby="judul-profil-beranda">
        <div className="profil__identitas">
          <h2 id="judul-profil-beranda">Profil</h2>
          {profilAda ? (
            <dl className="identitas profil__data" id="profil-ringkas">
              {barisProfil
                .filter((r) => r[1])
                .map((r) => (
                  <div key={r[0]}>
                    <dt>{r[0]}</dt>
                    <dd>{r[1]}</dd>
                  </div>
                ))}
            </dl>
          ) : (
            <p className="meta" id="profil-ringkas-kosong">Belum diatur.</p>
          )}
        </div>
        <div className="form__actions profil__aksi">
          <button type="button" id="btn-ubah-profil" className="btn" onClick={() => setProfilOpen(true)}>
            Ubah Profil
          </button>
        </div>
      </div>

      <div className="kepala-bagian">
        {/* Batas koleksi: maksimal 5 buku (komentar pengguna). */}
        <h2>Koleksi Buku Ajar {buku.length > 0 ? '(' + buku.length + '/5)' : '(maksimal 5 buku)'}</h2>
        {buku.length > 0 && buku.length < 5 && (
          <div className="form__actions profil__aksi">
            <button type="button" id="btn-upload-buku" className="btn" onClick={() => fileBukuRef.current?.click()}>
              Tambah buku
            </button>
          </div>
        )}
      </div>
      <div className="kartu-bagian" aria-label="Koleksi buku ajar">
        <input ref={fileBukuRef} id="f-buku-file" type="file" accept=".pdf,.docx" hidden onChange={(e) => void onFileBuku(e)} />
        <p id="buku-error" className="error error--tutup" role="alert" hidden={!bukuError}>
          <span>{bukuError}</span>
          <button type="button" className="btn" onClick={() => setBukuError('')}>
            Oke, paham
          </button>
        </p>
        <p id="buku-hasil" className="meta" role="status" hidden={!bukuHasil}>
          {bukuHasil}
        </p>
        <ul id="koleksi-buku" className="riwayat">
          {buku.map((b) => {
            const judul = judulBuku(b);
            const aktif = bukuDefault !== '' && bukuDefault === b.document_id;
            return (
              <li key={b.document_id} className="rpm-card bg-white border border-bord rounded-xl p-4 flex items-start gap-3">
                <div className="rpm-card__isi flex-1">
                  <strong className="font-display text-text1">
                    {judul}
                    {aktif && (
                      <>
                        {' '}
                        <span className="badge-valid badge--sage inline-block text-xs font-medium rounded px-2 py-0.5 text-text1 border border-bord">
                          Default
                        </span>
                      </>
                    )}
                  </strong>
                  <p className="meta text-sm text-text2 mt-1">{metaBuku(b)}</p>
                </div>
                <div className="form__actions flex gap-2">
                  {/* Buku default: tombol coral menonjol agar status jelas. */}
                  <button
                    type="button"
                    className={aktif ? 'btn btn--aksi' : 'btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1'}
                    data-buku-default={b.document_id}
                    onClick={() => onToggleDefault(b.document_id)}
                  >
                    {aktif ? 'Batalkan default' : 'Jadikan default'}
                  </button>
                  {/* Buku default tak bisa dihapus: titik-tiga disembunyikan. */}
                  {!aktif && (
                    <button
                      type="button"
                      className="titik"
                      data-titik-buku={b.document_id}
                      aria-label={'Opsi untuk ' + judul}
                      aria-expanded={menuBuka === 'buku:' + b.document_id}
                      onClick={() => setMenuBuka(menuBuka === 'buku:' + b.document_id ? null : 'buku:' + b.document_id)}
                    >
                      ⋮
                    </button>
                  )}
                  <div className="menu-pilih" hidden={menuBuka !== 'buku:' + b.document_id} role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMenuBuka(null);
                        setHapusBukuId(b.document_id);
                        setHapusBukuJudul(judul);
                      }}
                    >
                      Hapus permanen
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
        <div id="koleksi-buku-kosong" className="kosong" hidden={buku.length > 0}>
          <span className="kosong__ikon kosong__ikon--sage" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
          </span>
          <strong>Belum ada buku ajar</strong>
          <p>Upload PDF atau DOCX agar generate punya sumber materi.</p>
          <p className="form__actions">
            <button type="button" className="btn btn--aksi" onClick={() => fileBukuRef.current?.click()}>
              Upload buku pertama
            </button>
          </p>
        </div>
      </div>

      <div className="kepala-bagian">
        <h2>Riwayat RPM</h2>
        <div className="form__actions profil__aksi">
          <button type="button" id="btn-buka-upload" className="btn" onClick={() => fileRpmRef.current?.click()}>
            Impor RPM
          </button>
          <input ref={fileRpmRef} id="upload-file" type="file" accept=".docx,.pdf" hidden onChange={(e) => void onFileRpm(e)} />
        </div>
      </div>
      <div id="upload-error" className="error error--tutup" role="alert" hidden={!uploadError}>
        <span>{uploadError}</span>
        <button type="button" className="btn" onClick={() => setUploadError('')}>
          Oke, paham
        </button>
      </div>
      <div id="upload-hasil" className="meta" role="status" hidden={!uploadHasil}>
        {uploadHasil}
      </div>
      <div className="kartu-bagian" aria-label="Daftar riwayat RPM">
        <div id="riwayat-error" className="error" role="alert" hidden={!riwayatError}>
          {riwayatError}
        </div>
        <div id="riwayat-kosong" className="kosong" hidden={riwayat.length > 0}>
          <span className="kosong__ikon kosong__ikon--lavender" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M9 13h6M9 17h6" /></svg>
          </span>
          <strong>Belum ada RPM tersimpan</strong>
          <p>Susun RPM pertama dari CP resmi dalam beberapa menit.</p>
          <p className="form__actions">
            <a className="btn btn--aksi" href="#layar-formulir">
              Buat RPM pertama
            </a>
          </p>
        </div>
        {riwayat.length > 0 && (
          <div className="bulk" id="bulk-kontrol" hidden={nDipilih === 0}>
            <label className="bulk__pilih">
              <input
                ref={pilihSemuaRef}
                type="checkbox"
                id="bulk-pilih"
                checked={nDipilih > 0 && nDipilih === gidTerlihat.length}
                onChange={onPilihSemua}
                disabled={gidTerlihat.length === 0}
              />
              <span>Pilih semua</span>
            </label>
            <div className="bulk__bilah" id="bulk-bilah" hidden={nDipilih === 0}>
              <span id="bulk-jumlah" role="status">
                {nDipilih + ' dipilih'}
              </span>
              <button type="button" id="btn-hapus-pilih" className="btn btn--hapus" onClick={() => setHapusOpen(true)}>
                Hapus
              </button>
              <button type="button" id="btn-arsip-pilih" className="btn" onClick={() => setArsipOpen(true)}>
                Arsipkan
              </button>
            </div>
          </div>
        )}
        <ul id="riwayat-rpm" className={'riwayat' + (nDipilih > 0 ? ' mode-pilih' : '')}>
          {riwayat.map((m) => {
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
      </div>

      <ProfileDialog open={profilOpen} onClose={() => setProfilOpen(false)} />
      <ConfirmDialog
        open={hapusBukuId !== ''}
        judul={'Hapus "' + hapusBukuJudul + '"?'}
        pesan="Buku dihapus permanen dari koleksi beserta hasil ekstraksinya. Tindakan ini tidak dapat dibatalkan."
        error=""
        confirmLabel="Hapus permanen"
        cancelLabel="Batal"
        confirmClass="btn btn--hapus"
        busy={hapusBukuSibuk}
        onClose={() => {
          if (!hapusBukuSibuk) setHapusBukuId('');
        }}
        onConfirm={() => void hapusBuku()}
      />
      <ConfirmDialog
        open={hapusOpen}
        judul={'Hapus ' + nDipilih + ' RPM?'}
        pesan="RPM yang dipilih akan dihapus dari riwayat. Tindakan ini tidak dapat dibatalkan."
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
      <ConfirmDialog
        open={arsipOpen}
        judul={'Arsipkan ' + nDipilih + ' RPM?'}
        pesan={nDipilih + ' RPM dipindah ke Arsip (data utuh, tetap bisa dibuka). Upload judul sama tidak akan nabrak lagi.'}
        error=""
        confirmLabel="Arsipkan"
        cancelLabel="Batal"
        confirmClass="btn btn--aksi"
        busy={arsipSibuk}
        onClose={() => {
          if (!arsipSibuk) setArsipOpen(false);
        }}
        onConfirm={() => void arsipTerpilih()}
      />
    </section>
  );
}

export default Beranda;
