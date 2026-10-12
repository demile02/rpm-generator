import { useEffect, useState } from 'react';
import { useDialogFocus } from '../lib/dialogFocus';
import { api } from '../api';
import { useAlerts, useLoading } from '../state/appContext';
import { useSession } from '../state/session';
import type { GenerateFormParams } from '../types';

/* Delapan tahap persis ui/index.html layar-progres. */
const TAHAP: Array<[string, string]> = [
  ['Validasi kurikulum', 'CP resmi, fase, dan konteks dicek sebelum AI bekerja'],
  ['Topik', 'Topik pembelajaran dimatangkan dari konteks'],
  ['TP', 'Tujuan pembelajaran disusun dari CP'],
  ['KKTP', 'Kriteria ketercapaian dipasangkan ke tiap TP'],
  ['Materi', 'Bahan ajar diringkas dari sumber materi'],
  ['Aktivitas', 'Langkah per pertemuan disusun dari TP'],
  ['Asesmen', 'Instrumen awal, proses, dan akhir disusun dari TP dan KKTP'],
  ['Outline dan validasi final', 'Seluruh bagian dicek ulang sebelum hasil dibuka'],
];

interface TahapError {
  stage?: string;
  message?: string;
  code?: string;
}

/* Pesan tahap gagal persis ui/app.js tahapGagal. */
function pesanTahap(data: unknown): string {
  const errors = (data as { errors?: TahapError[] } | null)?.errors ?? [];
  return errors.length
    ? errors.map((e) => (e.stage ? '[' + e.stage + '] ' : '') + (e.message || e.code)).join(' · ')
    : 'Generation gagal tanpa pesan error.';
}

export function Progres({ onBack, onSuccess }: { onBack: () => void; onSuccess: () => void }) {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, perbaruiLoading, sembunyiLoading } = useLoading();
  const { job, setJob, tampilkanHasil } = useSession();

  const [teks, setTeks] = useState('Menghubungi backend…');
  const [waktu, setWaktu] = useState('0 mnt');
  const [galat, setGalat] = useState('');
  const [peringatan, setPeringatan] = useState<{
    relevansi: Array<{ elemen: string; nilai: string; alasan?: string }>;
    saran: string;
  } | null>(null);
  const peringatanDialogRef = useDialogFocus(peringatan != null, () => setPeringatan(null));
  const [bisaCoba, setBisaCoba] = useState(false);
  const [bisaPoll, setBisaPoll] = useState(false);
  const [ronde, setRonde] = useState(0);

  const jobId = job?.jobId ?? '';
  const retryParams = job?.retryParams ?? null;

  /* Poll tiap 5s seperti pollStatus legacy; sukses → hasil + URL + onSuccess. */
  useEffect(() => {
    const aktif = job;
    if (!aktif) {
      setGalat('Tidak ada job generate aktif. Kembali ke formulir lalu generate ulang.');
      return;
    }
    let batal = false;
    let timer = 0;
    setGalat('');
    setPeringatan(null);
    setBisaCoba(false);
    setBisaPoll(false);
    setTeks('Menghubungi backend…');
    setWaktu('0 mnt');
    if (ronde > 0) tampilLoading('Melanjutkan polling', 'Menghubungi backend…');
    else tampilLoading('Menyusun RPM', 'Menghubungi backend…');

    const gagal = (data: unknown): void => {
      if (batal) return;
      sembunyiLoading();
      const pesan = pesanTahap(data);
      setGalat(pesan);
      tampilAlert('Generate gagal', pesan);
      setBisaPoll(false);
      setBisaCoba(true);
      setTeks('Generation tidak berhasil.');
    };

    const poll = (): void => {
      api.getGenerationStatus(aktif.jobId).then((res) => {
        if (batal) return;
        if (res.status === 'running') {
          const menit = Math.floor((Date.now() - aktif.pollStart) / 60000);
          const t = 'Backend sedang menyusun RPM (menit ke-' + (menit + 1) + ')…';
          setTeks(t);
          setWaktu(menit + ' mnt');
          perbaruiLoading(t);
          timer = window.setTimeout(poll, 5000);
        } else if (res.status === 'warning') {
          sembunyiLoading();
          setPeringatan({
            relevansi: res.relevansi ?? [],
            saran: res.saran ?? '',
          });
          setTeks('Periksa relevansi topik dan elemen.');
          setBisaPoll(false);
          setBisaCoba(false);
        } else if (res.status === 'success' && res.module) {
          sembunyiLoading();
          tampilkanHasil(res.module, res.validation ?? null, res.generation_id ?? '');
          try {
            const gid = res.generation_id ?? '';
            window.history.replaceState(null, '', window.location.pathname + '?generation_id=' + encodeURIComponent(gid) + '#layar-hasil');
            if (window.location.hash !== '#layar-hasil') window.location.hash = '#layar-hasil';
          } catch {
            /* URL opsional, abaikan */
          }
          onSuccess();
        } else {
          gagal(res);
        }
      }).catch(() => {
        if (batal) return;
        sembunyiLoading();
        const pesan = 'Polling terputus. Koneksi bermasalah.';
        setGalat(pesan);
        tampilAlert('Koneksi terputus', pesan + ' Tekan Poll ulang untuk melanjutkan.');
        setBisaPoll(true);
      });
    };
    poll();
    return () => {
      batal = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.jobId, ronde]);

  /* Coba Lagi: kirim ulang retryParams seperti btn-coba-lagi legacy. */
  const onLanjutkanWarning = (): void => {
    if (!retryParams) return;
    setPeringatan(null);
    setGalat('');
    setTeks('Menghubungi backend…');
    tampilLoading('Menyusun RPM', 'Melanjutkan tanpa pemeriksaan relevansi…');
    api.generateModuleAsync({
      ...(retryParams as unknown as GenerateFormParams),
      skip_relevance_check: true,
    } as GenerateFormParams).then((res) => {
      setJob({
        jobId: res.job_id,
        pollStart: Date.now(),
        retryParams: { ...retryParams, skip_relevance_check: true },
      });
    }).catch((err: unknown) => {
      sembunyiLoading();
      const data = (err as { data?: unknown } | null)?.data;
      const pesan = pesanTahap(data);
      setGalat(pesan);
      tampilAlert('Generate gagal', pesan);
      setBisaCoba(true);
      setTeks('Generation tidak berhasil.');
    });
  };

  const onCobaLagi = (): void => {
    if (!retryParams) {
      const pesan = 'Tidak ada parameter generate untuk diulang. Kembali ke formulir.';
      setGalat(pesan);
      tampilAlert('Generate gagal', pesan);
      return;
    }
    setGalat('');
    setBisaCoba(false);
    setBisaPoll(false);
    setTeks('Menghubungi backend…');
    tampilLoading('Menyusun RPM', 'Menghubungi backend…');
    api.generateModuleAsync(retryParams as unknown as GenerateFormParams).then((res) => {
      setJob({ jobId: res.job_id, pollStart: Date.now(), retryParams });
    }).catch((err: unknown) => {
      sembunyiLoading();
      const data = (err as { data?: unknown } | null)?.data;
      const pesan = pesanTahap(data);
      setGalat(pesan);
      tampilAlert('Generate gagal', pesan);
      setBisaCoba(true);
      setTeks('Generation tidak berhasil.');
    });
  };

  const onPollUlang = (): void => {
    setGalat('');
    setBisaPoll(false);
    tampilLoading('Melanjutkan polling', 'Menghubungi backend…');
    setRonde((r) => r + 1);
  };

  const onKembali = (): void => {
    sembunyiLoading();
    onBack();
  };

  return (
    <section id="layar-progres" className="screen" aria-labelledby="judul-progres">
      <p className="kicker">Langkah 2 dari 2, Generation</p>
      <h1 id="judul-progres">Menyusun RPM</h1>
      <p className="lede">Backend menyusun delapan tahap di bawah ini. Anda bisa menunggu, halaman ini memberi kabar tiap menit.</p>
      <div className="progress" id="progres-bar" role="status" aria-live="polite">
        <div className="progress__bar" aria-hidden="true"><span></span></div>
        <p id="progres-teks">{teks}</p>
        <p className="meta">ID generation: <code id="progres-id">{jobId}</code> · <span id="progres-waktu">{waktu}</span></p>
      </div>
      <ol className="tahap" aria-label="Tahap penyusunan RPM">
        {TAHAP.map(([judul, ket]) => (
          <li key={judul}><div><strong>{judul}</strong><span>{ket}</span></div></li>
        ))}
      </ol>
      <div id="progres-error" className="error" role="alert" hidden={!galat}>{galat}</div>
      {peringatan && (
        <div
          className="overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPeringatan(null);
          }}
        >
          <div ref={peringatanDialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="judul-relevansi-progres" tabIndex={-1}>
            <h2 id="judul-relevansi-progres">Periksa kembali pilihan elemen</h2>
            <p className="lede dialog__sub">Topik kurang relevan dengan elemen berikut:</p>
            <ul>
              {peringatan.relevansi
                .filter((r) => r.nilai !== 'RELEVAN')
                .map((r) => (
                  <li key={r.elemen}>
                    <strong>{r.elemen}</strong>
                    {r.alasan ? ': ' + r.alasan : ''}
                  </li>
                ))}
            </ul>
            {peringatan.saran && <p className="lede">{peringatan.saran}</p>}
            <div className="form__actions">
              <button type="button" className="btn" onClick={onKembali}>Ubah pilihan</button>
              <button type="button" className="btn btn--aksi" onClick={onLanjutkanWarning}>Tetap lanjutkan</button>
            </div>
          </div>
        </div>
      )}
      <div className="form__actions">
        <button type="button" id="btn-coba-lagi" className="btn btn--aksi" hidden={!bisaCoba} onClick={onCobaLagi}>Coba Lagi</button>
        <button type="button" id="btn-poll-ulang" className="btn" hidden={!bisaPoll} onClick={onPollUlang}>Coba polling lagi</button>
        <button type="button" id="btn-ke-formulir" className="btn" onClick={onKembali}>Kembali ke formulir</button>
      </div>
    </section>
  );
}
