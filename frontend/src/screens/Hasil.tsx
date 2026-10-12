import { useEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from 'react';
import { useDialogFocus } from '../lib/dialogFocus';
import { api } from '../api';
import { useAlerts, useLoading } from '../state/appContext';
import { finalPassed, useSession } from '../state/session';
import { pesanError, type RpmModule, type ValidationResult, type VersionMeta } from '../types';
import {
  renderModuleParts,
  type AssessItem,
} from '../lib/moduleRender';

/* NAMA_BAGIAN persis ui/app.js */
const NAMA_BAGIAN: Record<string, string> = {
  tp: 'TP',
  kktp: 'KKTP',
  materi: 'Materi',
  praktik_pedagogis: 'Praktik Pedagogis',
  aktivitas: 'Aktivitas',
  asesmen: 'Asesmen',
  diagnostik: 'Diagnostik',
  formatif: 'Formatif',
  sumatif: 'Sumatif',
};

function labelShortcut(banner: string): string {
  const match = banner.match(/^([A-Z])\.\s*(.*)$/);
  if (!match) return banner;
  const teks = match[2].toLocaleLowerCase('id-ID');
  return match[1] + '. ' + teks.charAt(0).toLocaleUpperCase('id-ID') + teks.slice(1);
}

interface ShortcutPosition {
  x: number;
  y: number;
}

function batasPosisiShortcut(posisi: ShortcutPosition, lebar: number, tinggi: number): ShortcutPosition {
  const radius = 26;
  return {
    x: Math.max(radius - 26, Math.min(lebar - radius + 26, posisi.x)),
    y: Math.max(radius, Math.min(tinggi - radius, posisi.y)),
  };
}

interface ShortcutDrag {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  moved: boolean;
}

interface StepperProps {
  awal: number;
  min: number;
  max: number;
  label: string;
  kurangLabel: string;
  tambahLabel: string;
  onChange: (n: number) => void;
  onKurang?: () => void;
  onTambah?: () => void;
}

function Stepper({ awal, min, max, label, kurangLabel, tambahLabel, onChange, onKurang, onTambah }: StepperProps) {
  const [n, setN] = useState(() => Math.max(min, Math.min(max, Number(awal) || min)));
  useEffect(() => {
    setN(Math.max(min, Math.min(max, Number(awal) || min)));
  }, [awal, min, max]);
  const atur = (arah: 'kurang' | 'tambah') => {
    const nx = Math.max(min, Math.min(max, n + (arah === 'tambah' ? 1 : -1)));
    setN(nx);
    onChange(nx);
    if (arah === 'kurang' && onKurang) onKurang();
    if (arah === 'tambah' && onTambah) onTambah();
  };
  return (
    <span className="stepper" role="group" aria-label={label}>
      <button
        type="button"
        className="btn btn--step"
        aria-label={kurangLabel}
        disabled={n <= min}
        onClick={() => atur('kurang')}
      >
        −
      </button>
      <span className="stepper__angka" aria-live="polite">
        {n}
      </span>
      <button
        type="button"
        className="btn btn--step"
        aria-label={tambahLabel}
        disabled={n >= max}
        onClick={() => atur('tambah')}
      >
        +
      </button>
    </span>
  );
}

function Table({
  headers,
  rows,
  cls,
  fracs,
}: {
  headers: string[];
  rows: React.ReactNode[][];
  cls?: string;
  fracs?: number[];
}) {
  if (!rows.length) return null;
  return (
    <div className="table-wrap">
      <table className={cls}>
        {fracs && fracs.length === headers.length && (
          <colgroup>
            {fracs.map((f, i) => (
              <col key={i} style={{ width: (f * 100).toFixed(1) + '%' }} />
            ))}
          </colgroup>
        )}
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface AssessBlockProps {
  judul: string;
  target: string;
  label: string;
  items: AssessItem[];
  diagnostik: boolean;
  regenBusy: boolean;
  versiMemuat: boolean;
  onCount: (target: string, n: number) => void;
  onRegen: (target: string) => void;
}

function AssessBlock({
  judul,
  target,
  label,
  items,
  diagnostik,
  regenBusy,
  versiMemuat,
  onCount,
  onRegen,
}: AssessBlockProps) {
  return (
    <>
      <div className="baris-aksi">
        <h4>{judul}</h4>
        <Stepper
          awal={items.length}
          min={1}
          max={30}
          label={'Jumlah soal ' + judul}
          kurangLabel="Kurangi"
          tambahLabel="Tambah"
          onChange={(n) => onCount(target, n)}
        />
        <button
          type="button"
          className={regenBusy ? 'btn btn--retry btn--busy' : 'btn btn--retry'}
          disabled={regenBusy || versiMemuat}
          onClick={() => onRegen(target)}
        >
          Regenerate {label}
        </button>
      </div>
      <Table
        headers={diagnostik ? ['Instrumen', 'Tipe', 'Jawaban Benar'] : ['Instrumen', 'Tipe', 'TP', 'KKTP']}
        rows={items.map((it) => {
          const soal = (
            <>
              {it.question}
              {diagnostik && it.options.length > 0 && (
                <>
                  <br />
                  {it.options.map((o) => (
                    <span key={o.label}>
                      {o.label}. {o.text}
                      <br />
                    </span>
                  ))}
                </>
              )}
            </>
          );
          return diagnostik
            ? [soal, it.type, it.answer]
            : [soal, it.type, it.tp, it.kktp];
        })}
        cls={diagnostik ? 'val-mid' : undefined}
      />
    </>
  );
}

interface HasilProps {
  onEdit: () => void;
}

export function Hasil({ onEdit }: HasilProps) {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, sembunyiLoading } = useLoading();
  const session = useSession();
  const {
    module,
    validation,
    generationId,
    version,
    versions,
    hasVersions,
    setVersion,
    setVersionsState,
    terapkanVersi,
    exportUrl,
  } = session;

  const [counts, setCounts] = useState<Record<string, number>>({});
  const [nPertemuan, setNPertemuan] = useState<number | null>(null);
  const [statusSimpan, setStatusSimpan] = useState('');
  const [regenBusy, setRegenBusy] = useState(false);
  const [versiMemuat, setVersiMemuat] = useState(true);
  const [peringatan, setPeringatan] = useState<string[]>([]);
  const [hapusTarget, setHapusTarget] = useState<number | null>(null);
  const [hapusSibuk, setHapusSibuk] = useState(false);
  const [hasilError, setHasilError] = useState('');
  const hapusDialogRef = useDialogFocus(hapusTarget != null, () => {
    if (!hapusSibuk) setHapusTarget(null);
  }, hapusSibuk);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [shortcutPosition, setShortcutPosition] = useState<ShortcutPosition>(() => {
    const bawaan = { x: 0, y: Math.max(26, window.innerHeight / 2) };
    try {
      const tersimpan = JSON.parse(window.localStorage.getItem('rpm_shortcut_position') || 'null') as Partial<ShortcutPosition> | null;
      if (typeof tersimpan?.x === 'number' && typeof tersimpan?.y === 'number') {
        return batasPosisiShortcut(
          { x: tersimpan.x, y: tersimpan.y },
          window.innerWidth,
          window.innerHeight,
        );
      }
    } catch {
      /* Posisi hanya preferensi tampilan. */
    }
    return bawaan;
  });
  const shortcutDragRef = useRef<ShortcutDrag | null>(null);
  const shortcutLivePositionRef = useRef<ShortcutPosition>(shortcutPosition);
  const shortcutElementRef = useRef<HTMLDivElement | null>(null);
  const shortcutPendingPositionRef = useRef<ShortcutPosition | null>(null);
  const shortcutSuppressClickRef = useRef(false);
  const shortcutAnchorHandledRef = useRef(false);

  useEffect(() => {
    shortcutLivePositionRef.current = shortcutPosition;
    const el = shortcutElementRef.current;
    if (el) {
      el.style.left = `${shortcutPosition.x}px`;
      el.style.top = `${shortcutPosition.y}px`;
    }
    try {
      window.localStorage.setItem('rpm_shortcut_position', JSON.stringify(shortcutPosition));
    } catch {
      /* Posisi hanya preferensi tampilan. */
    }
  }, [shortcutPosition]);

  useEffect(() => {
    return () => {
      shortcutDragRef.current = null;
    };
  }, []);

  useEffect(() => {
    const sesuaikanDenganViewport = (): void => {
      setShortcutPosition((sekarang) => batasPosisiShortcut(sekarang, window.innerWidth, window.innerHeight));
    };
    window.addEventListener('resize', sesuaikanDenganViewport);
    return () => window.removeEventListener('resize', sesuaikanDenganViewport);
  }, []);

  useEffect(() => {
    if (!shortcutOpen) return;
    const tutupSaatTapDiLuar = (event: globalThis.PointerEvent): void => {
      const target = event.target;
      const shortcut = document.querySelector('.hasil-shortcut');
      if (target instanceof Node && shortcut && !shortcut.contains(target)) {
        setShortcutOpen(false);
      }
    };
    document.addEventListener('pointerdown', tutupSaatTapDiLuar);
    return () => document.removeEventListener('pointerdown', tutupSaatTapDiLuar);
  }, [shortcutOpen]);

  const bukaBagianShortcut = (event: MouseEvent<HTMLAnchorElement>, id: string): void => {
    event.preventDefault();
    if (shortcutAnchorHandledRef.current) {
      shortcutAnchorHandledRef.current = false;
      return;
    }
    shortcutAnchorHandledRef.current = true;
    setShortcutOpen(false);
    try {
      window.history.pushState(null, '', '#' + id);
    } catch {
      /* URL hanya penanda posisi; scroll tetap dijalankan. */
    }
    const scrollKeTarget = (): void => {
      const target = document.getElementById(id);
      if (!target) return;
      const offsetAtas = 88;
      const posisi = target.getBoundingClientRect().top + window.scrollY - offsetAtas;
      window.scrollTo(0, Math.max(0, posisi));
    };
    scrollKeTarget();
    window.requestAnimationFrame(scrollKeTarget);
    window.setTimeout(() => {
      shortcutAnchorHandledRef.current = false;
    }, 0);
  };

  const tahanNavigasiShortcut = (event: PointerEvent<HTMLAnchorElement>): void => {
    event.preventDefault();
  };

  const mulaiGeserShortcut = (event: PointerEvent<HTMLButtonElement>): void => {
    if (!window.matchMedia('(max-width: 719px)').matches) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    shortcutDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: shortcutLivePositionRef.current.x,
      originY: shortcutLivePositionRef.current.y,
      moved: false,
    };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* Pointer capture opsional pada browser lama. */
    }
  };

  const geserShortcut = (event: PointerEvent<HTMLButtonElement>): void => {
    const drag = shortcutDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    event.preventDefault();
    const posisi = batasPosisiShortcut(
      { x: drag.originX + dx, y: drag.originY + dy },
      window.innerWidth,
      window.innerHeight,
    );
    shortcutLivePositionRef.current = posisi;
    shortcutPendingPositionRef.current = posisi;
    const el = shortcutElementRef.current;
    if (el) {
      el.style.left = `${posisi.x}px`;
      el.style.top = `${posisi.y}px`;
    }
  };

  const selesaiGeserShortcut = (event: PointerEvent<HTMLButtonElement>): void => {
    const drag = shortcutDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    shortcutSuppressClickRef.current = drag.moved;
    if (drag.moved && shortcutPendingPositionRef.current) {
      setShortcutPosition(shortcutPendingPositionRef.current);
    }
    shortcutPendingPositionRef.current = null;
    shortcutDragRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* Pointer capture opsional pada browser lama. */
    }
  };

  const gerakShortcutDenganKeyboard = (arah: 'atas' | 'bawah' | 'kiri' | 'kanan'): void => {
    const langkah = 16;
    const delta = {
      atas: { x: 0, y: -langkah },
      bawah: { x: 0, y: langkah },
      kiri: { x: -langkah, y: 0 },
      kanan: { x: langkah, y: 0 },
    }[arah];
    setShortcutPosition((sekarang) => batasPosisiShortcut(
      { x: sekarang.x + delta.x, y: sekarang.y + delta.y },
      window.innerWidth,
      window.innerHeight,
    ));
  };

  const m = (module || {}) as RpmModule;
  const parts = useMemo(() => (module ? renderModuleParts(module as RpmModule) : null), [module]);
  const ok = finalPassed(validation);
  const simpanPesan = statusSimpan;

  /* Muat riwayat saat sesi dibuka; draft regen yang sedang tampil
     tidak dimundurkan (warisi logika muatRiwayat legacy). */
  useEffect(() => {
    const anchor = window.location.hash;
    if (!anchor.startsWith('#a-')) return;
    const id = anchor.slice(1);
    const scrollKeTarget = (): void => {
      const target = document.getElementById(id);
      if (!target) return;
      window.scrollTo(0, Math.max(0, target.getBoundingClientRect().top + window.scrollY - 88));
    };
    const t1 = window.setTimeout(scrollKeTarget, 0);
    const t2 = window.setTimeout(scrollKeTarget, 200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [module]);

  useEffect(() => {
    const gid = generationId;
    if (!gid) return;
    let batal = false;
    setVersiMemuat(true);
    api
      .listVersions(gid)
      .then((res) => {
        if (batal) return;
        const list = res.versions || [];
        setVersionsState(list);
        if (list.length) {
          const latest = res.latest_version ?? null;
          if (latest != null && (version == null || latest >= version)) {
            setVersion(latest);
          }
        }
        setVersiMemuat(false);
      })
      .catch(() => {
        if (!batal) setVersiMemuat(false);
      });
    return () => {
      batal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationId]);

  if (!module || !parts) return null;

  const cur = versions.find((v) => v.version_no === version) || null;

  function hitungJumlah(target: string): Record<string, number> | undefined {
    const n = counts[target];
    if (n == null || n < 1 || n > 30) return undefined;
    return { [target]: n };
  }

  async function regenBagian(target: string, extra?: Record<string, unknown>) {
    if (!generationId || version == null || versiMemuat) {
      setStatusSimpan('Riwayat versi belum tersedia untuk sesi ini. Muat ulang halaman.');
      return;
    }
    if (regenBusy) return;
    const { dirty } = session;
    if (dirty) {
      const lanjut = window.confirm(
        'Ada perubahan belum disimpan. Regenerasi memakai versi tersimpan terakhir; perubahan tak tersimpan akan hilang. Lanjut?',
      );
      if (!lanjut) return;
    }
    const nama = NAMA_BAGIAN[target] || target;
    const c = target !== 'aktivitas' ? hitungJumlah(target) : undefined;
    let berapa = c && c[target] ? ' ' + c[target] + ' soal' : '';
    if (extra && typeof extra.n_meetings === 'number') {
      berapa += ' (' + (extra.n_meetings as number) + ' pertemuan)';
    }
    setRegenBusy(true);
    tampilLoading('Meregenerasi ' + nama, 'Meregenerasi ' + target + berapa + ' via AI…');
    setStatusSimpan('Meregenerasi ' + target + berapa + '…');
    try {
      const res = await api.regenerateSection(generationId, version, target, c, extra);
      setRegenBusy(false);
      sembunyiLoading();
      if (res.draft) {
        session.setDraftChanges({ ...session.draftChanges, [target]: true });
      }
      const ver = (res.version || res) as VersionMeta & {
        module: RpmModule;
        validation?: ValidationResult | null;
      };
      terapkanVersi(ver);
      await muatRiwayatUlang();
      setPeringatan(
        (res.warnings as string[] | undefined) ||
          ((ver as { warnings?: string[] }).warnings ?? []),
      );
      session.setDirty(true);
      const pesanDraft = nama + ' menjadi draft. Klik Simpan perubahan untuk menyimpan.';
      setStatusSimpan(pesanDraft);
      tampilAlert(nama + ' diregenerasi', pesanDraft);
    } catch (err) {
      setRegenBusy(false);
      sembunyiLoading();
      const data = (err as { data?: unknown })?.data || {};
      const rincian = pesanError(data);
      const pesanGagal =
        nama +
        ' gagal diperbarui. Coba lagi.' +
        (rincian && rincian !== 'kesalahan tak dikenal' ? ' Rincian: ' + rincian : '');
      setStatusSimpan(pesanGagal);
      tampilAlert(nama + ' gagal diregenerasi', pesanGagal);
    }
  }

  async function muatRiwayatUlang(pin?: number | null): Promise<void> {
    if (!generationId) return;
    try {
      const res = await api.listVersions(generationId);
      const list = res.versions || [];
      setVersionsState(list);
      if (pin != null) {
        setVersion(pin);
        return;
      }
      const latest = res.latest_version ?? null;
      if (latest != null && (version == null || latest >= version)) {
        setVersion(latest);
      }
    } catch {
      /* abaikan */
    }
  }

  async function lihatVersi(v: number) {
    if (!generationId) return;
    if (session.dirty) {
      const lanjut = window.confirm('Perubahan belum disimpan. Tinggalkan halaman dan buang perubahan?');
      if (!lanjut) return;
    }
    try {
      const res = await api.getVersion(generationId, v);
      const ver = res.version;
      terapkanVersi(ver);
      await muatRiwayatUlang(ver.version_no);
      setHasilError('');
    } catch (err) {
      const p = 'Gagal membuka versi: ' + pesanError((err as { data?: unknown })?.data);
      setHasilError(p);
      tampilAlert('Gagal membuka versi', p);
    }
  }

  async function hapusVersi() {
    if (hapusTarget == null || !generationId) return;
    if (versions.length <= 1) {
      tampilAlert(
        'Tidak bisa dihapus',
        'Versi terakhir tidak boleh dihapus; modul harus punya minimal 1 versi.',
      );
      setHapusTarget(null);
      return;
    }
    setHapusSibuk(true);
    tampilLoading('Menghapus versi', 'Menghapus v' + hapusTarget + '…');
    try {
      const res = await api.deleteVersion(generationId, hapusTarget);
      const latestNo = res.latest_version;
      if (latestNo != null) {
        const r = await api.getVersion(generationId, latestNo);
        terapkanVersi(r.version);
        await muatRiwayatUlang(r.version.version_no);
        tampilAlert('Versi dihapus', 'v' + hapusTarget + ' dihapus permanen. Menampilkan v' + r.version.version_no + '.');
      }
      setHapusSibuk(false);
      sembunyiLoading();
      setHapusTarget(null);
    } catch (err) {
      setHapusSibuk(false);
      sembunyiLoading();
      const p = 'Gagal menghapus versi. ' + pesanError((err as { data?: unknown })?.data);
      tampilAlert('Gagal menghapus versi', p);
    }
  }

  const url = exportUrl();
  const urutVersi = [...versions].sort((a, b) => b.version_no - a.version_no);

  return (
    <section id="layar-hasil" className="screen" aria-labelledby="judul-hasil">
      <h4 className="kicker kicker--judul" id="judul-hasil">Pratinjau RPM</h4>
      <p id="hasil-validasi" className={ok ? 'badge-valid' : 'badge-valid is-gagal'}>
        Final validation: {ok ? 'PASS' : 'BELUM LULUS'}
      </p>
      <p id="hasil-versi" className="meta">
        {hasVersions && cur
          ? 'Versi v' +
            cur.version_no +
            ' dari ' +
            versions.length +
            ' (' +
            (cur.status || '') +
            (cur.alignment_status ? ' / ' + cur.alignment_status : '') +
            ')'
          : ''}
      </p>
      <p id="hasil-alignment" className="meta">
        {cur && cur.alignment_status
          ? 'Keselarasan: ' +
            cur.alignment_status +
            ((cur.warnings || []).length ? ' (' + (cur.warnings || []).join(' ') + ')' : '')
          : ''}
      </p>
      <div className="form__actions" role="group" aria-label="Aksi RPM">
        <button type="button" id="btn-mode-edit" className="btn" onClick={onEdit}>
          Edit
        </button>
      </div>
      <p id="status-simpan" className="meta" role="status">
        {simpanPesan}
      </p>
      {peringatan.length > 0 && (
        <div id="peringatan-dependensi" className="panel-cp">
          <h3>Perhatian</h3>
          <ul>
            {peringatan.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="hasil-badan">
        <div
          ref={shortcutElementRef}
          className="hasil-shortcut"
          style={{ left: `${shortcutPosition.x}px`, top: `${shortcutPosition.y}px` }}
        >
          <button
            type="button"
            className="hasil-shortcut__toggle"
            aria-expanded={shortcutOpen}
            aria-controls="hasil-toc"
            aria-label="Buka shortcut bagian RPM"
            onPointerDown={mulaiGeserShortcut}
            onPointerMove={geserShortcut}
            onPointerUp={selesaiGeserShortcut}
            onPointerCancel={selesaiGeserShortcut}
            onKeyDown={(event) => {
              const arah = {
                ArrowUp: 'atas',
                ArrowDown: 'bawah',
                ArrowLeft: 'kiri',
                ArrowRight: 'kanan',
              }[event.key] as 'atas' | 'bawah' | 'kiri' | 'kanan' | undefined;
              if (!arah) return;
              event.preventDefault();
              gerakShortcutDenganKeyboard(arah);
            }}
            onClick={() => {
              if (shortcutSuppressClickRef.current) {
                shortcutSuppressClickRef.current = false;
                return;
              }
              setShortcutOpen((open) => !open);
            }}
          >
            Shortcut
          </button>
          <nav id="hasil-toc" className={'toc hasil-shortcut__panel' + (shortcutOpen ? ' is-open' : '')} aria-label="Shortcut bagian RPM">
            <h3 className="hasil-shortcut__label">Shortcut</h3>
            <ul>
              {parts.toc.map((t) => (
                <li key={t.id}>
                  <a
                    href={'#' + t.id}
                    onPointerDown={tahanNavigasiShortcut}
                    onClick={(event) => bukaBagianShortcut(event, t.id)}
                  >{labelShortcut(t.banner)}</a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
        <div className="hasil-dokumen">
          <article id="hasil-isi" className="dokumen">
            <p className="doc-title">PERENCANAAN PEMBELAJARAN MENDALAM</p>
            {parts.topic.trim() && <p className="doc-topic">&ldquo;{parts.topic.trim()}&rdquo;</p>}
            <section id="a-identitas">
              <h3 className="banner">A. IDENTITAS MODUL</h3>
              <dl className="identitas">
                {parts.identitas.map((r) => (
                  <div key={r.label}>
                    <dt>{r.label}</dt>
                    <dd>{r.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section id="b-identifikasi">
              <h3 className="banner">B. IDENTIFIKASI</h3>
              <h4>Kesiapan Murid</h4>
              <p>{parts.kesiapanSummary}</p>
              {parts.kesiapanAspects.length > 0 && (
                <ul>
                  {parts.kesiapanAspects.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
              <h4>Karakteristik materi</h4>
              <p>{parts.materiSummary}</p>
              {parts.dims.length > 0 && (
                <>
                  <h4>Dimensi Profil Lulusan</h4>
                  <ol className="rpm-numbered-list">
                    {parts.dims.map((d, i) => (
                      <li key={d.name}>
                        <div className="rpm-list-heading">
                          <span className="rpm-list-number" aria-hidden="true">{i + 1}.</span>{' '}
                          <strong>{d.name}</strong>
                        </div>
                        {d.note ? (
                          <div className="rpm-list-explanation">{d.note}</div>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {parts.kbcPairs.length > 0 && (
                <>
                  <h4>Kurikulum Berbasis Cinta &amp; Materi Insersi</h4>
                  <ol className="rpm-numbered-list">
                    {parts.kbcPairs.map((it, i) => (
                      <li key={i}>
                        <div className="rpm-list-heading">
                          <span className="rpm-list-number" aria-hidden="true">{i + 1}.</span>{' '}
                          <strong>{it.theme ? it.theme : 'Materi insersi'}</strong>
                        </div>
                        {it.text ? (
                          <div className="rpm-list-explanation">{it.text}</div>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </section>
            <section id="c-desain">
              <h3 className="banner">C. DESAIN PEMBELAJARAN</h3>
              <h4>Capaian Pembelajaran (CP)</h4>
              <blockquote className="cp">{parts.cp}</blockquote>
              {parts.sumberLine && <p className="meta">{parts.sumberLine}</p>}
              <div className="baris-aksi">
                <h4>Tujuan Pembelajaran</h4>
                <button
                  type="button"
                  className={regenBusy ? 'btn btn--retry btn--busy' : 'btn btn--retry'}
                  disabled={regenBusy || versiMemuat}
                  onClick={() => void regenBagian('tp')}
                >
                  Regenerate TP
                </button>
              </div>
              <Table
                headers={['Nomor', 'Tujuan Pembelajaran', 'Level']}
                rows={parts.tpRows.map((t) => [t.id, t.text, t.level])}
                fracs={[0.109, 0.782, 0.109]}
              />
              {parts.kktp.length > 0 && (
                <>
                  <div className="baris-aksi">
                    <h4>Kriteria Ketercapaian (KKTP)</h4>
                    <button
                      type="button"
                      className={regenBusy ? 'btn btn--retry btn--busy' : 'btn btn--retry'}
                      disabled={regenBusy || versiMemuat}
                      onClick={() => void regenBagian('kktp')}
                    >
                      Regenerate KKTP
                    </button>
                  </div>
                  {parts.kktp.map((k, i) => (
                    <div className="kktp-item" key={i}>
                      <p className="kktp-heading">
                        <strong>
                          {i + 1}. {k.id}
                        </strong>
                      </p>
                      {k.criteria.map((c, j) => (
                        <p className="kktp-explanation" key={j}>{c}</p>
                      ))}
                    </div>
                  ))}
                </>
              )}
              {parts.practices.length > 0 && (
                <>
                  <div className="baris-aksi">
                    <h4>Praktik Pedagogis</h4>
                    <button
                      type="button"
                      className={regenBusy ? 'btn btn--retry btn--busy' : 'btn btn--retry'}
                      disabled={regenBusy || versiMemuat}
                      onClick={() => void regenBagian('praktik_pedagogis')}
                    >
                      Regenerate Praktik Pedagogis
                    </button>
                  </div>
                  {parts.practices.map((p, i) => (
                    <p key={i}>
                      {i + 1}. {p}
                    </p>
                  ))}
                </>
              )}
            </section>
            <section id="d-pengalaman">
              <h3 className="banner">D. LANGKAH DAN PENGALAMAN PEMBELAJARAN</h3>
              {parts.meetings.length > 0 ? (
                <>
                  <div className="baris-aksi baris-aksi--tunggal">
                    <Stepper
                      awal={parts.meetings.length}
                      min={1}
                      max={16}
                      label="Jumlah pertemuan"
                      kurangLabel="Kurangi pertemuan"
                      tambahLabel="Tambah pertemuan"
                      onChange={(n) => {
                        setNPertemuan(n);
                        const cur = (m.meetings as unknown[])?.length;
                        setStatusSimpan(
                          n === cur
                            ? 'Jumlah pertemuan sama dengan versi tersimpan.'
                            : 'Jumlah pertemuan: ' +
                                n +
                                ' (pending, klik Regenerate Aktivitas untuk memecah/menggabung via AI).',
                        );
                      }}
                    />
                    <button
                      type="button"
                      className={regenBusy ? 'btn btn--retry btn--busy' : 'btn btn--retry'}
                      disabled={regenBusy || versiMemuat}
                      onClick={() => {
                        const curN = (m.meetings as unknown[])?.length;
                        const extra =
                          typeof nPertemuan === 'number' && nPertemuan !== curN
                            ? { n_meetings: nPertemuan }
                            : undefined;
                        void regenBagian('aktivitas', extra);
                      }}
                    >
                      Regenerate Aktivitas
                    </button>
                  </div>
                  {parts.meetings.map((mtg, i) => (
                    <div key={i}>
                      <h4>
                        Pertemuan {mtg.index}: {mtg.jp} JP ({mtg.minutes} menit)
                      </h4>
                      {(['Pembuka', 'Inti', 'Penutup'] as const).map((tahap) => (
                        <div key={tahap}>
                          <h4>{tahap}</h4>
                          <Table
                            headers={['Aktivitas', 'Deskripsi', 'Durasi', 'TP', 'Pengalaman']}
                            rows={(tahap === 'Pembuka' ? mtg.pembuka : tahap === 'Inti' ? mtg.inti : mtg.penutup).map(
                              (a) => [a.name, a.description, a.duration, a.tp, a.experience],
                            )}
                            fracs={[0.187, 0.422, 0.109, 0.094, 0.188]}
                          />
                        </div>
                      ))}
                      {mtg.principles.length > 0 && (
                        <>
                          <p>
                            <strong>Prinsip Pembelajaran Mendalam</strong>
                          </p>
                          <ol>
                            {mtg.principles.map((p) => (
                              <li key={p.label}>
                                <strong>{p.label}</strong>
                                <br />
                                {p.text}
                              </li>
                            ))}
                          </ol>
                        </>
                      )}
                    </div>
                  ))}
                </>
              ) : (
                parts.fallbackExperiences.map((fb) => (
                  <div key={fb.nama}>
                    <h4>Pengalaman {fb.nama}</h4>
                    <Table
                      headers={['Aktivitas', 'Deskripsi', 'Durasi', 'TP']}
                      rows={fb.rows.map((r) => [r.name, r.desc, r.dur, r.tp])}
                    />
                  </div>
                ))
              )}
            </section>
            <section id="e-asesmen">
              <h3 className="banner">E. ASESMEN</h3>
              <AssessBlock judul="Asesmen Diagnostik" target="diagnostik" label="Diagnostik" items={parts.diagnostik} diagnostik versiMemuat={versiMemuat} regenBusy={regenBusy} onCount={(t, n) => setCounts((c) => ({ ...c, [t]: n }))} onRegen={(t) => void regenBagian(t)} />
              <AssessBlock judul="Asesmen Formatif" target="formatif" label="Formatif" items={parts.formatif} diagnostik={false} versiMemuat={versiMemuat} regenBusy={regenBusy} onCount={(t, n) => setCounts((c) => ({ ...c, [t]: n }))} onRegen={(t) => void regenBagian(t)} />
              <AssessBlock judul="Asesmen Sumatif" target="sumatif" label="Sumatif" items={parts.sumatif} diagnostik={false} versiMemuat={versiMemuat} regenBusy={regenBusy} onCount={(t, n) => setCounts((c) => ({ ...c, [t]: n }))} onRegen={(t) => void regenBagian(t)} />
              {parts.diagnostik.length + parts.formatif.length + parts.sumatif.length === 0 && (
                <p className="meta">
                  Asesmen belum digenerate. Gunakan tombol Regenerate Diagnostik / Formatif / Sumatif di atas untuk
                  menambahkannya.
                </p>
              )}
            </section>
            {parts.glosarium.length > 0 && (
              <section id="glosarium">
                <h3 className="banner">G. Glosarium</h3>
                <Table
                  headers={['Istilah', 'Definisi']}
                  rows={parts.glosarium.map((g) => [g.istilah, g.definisi])}
                  fracs={[0.25, 0.75]}
                />
              </section>
            )}
          </article>
        </div>
      </div>
      <h2>Riwayat versi</h2>
      <ul id="riwayat-versi" className="toc">
        {urutVersi.map((v) => (
          <li key={v.version_no}>
            <strong>
              v{v.version_no}
              {v.version_no === version ? ' (AKTIF)' : ''}
            </strong>
            <br />
            {v.status || ''}
            {v.alignment_status ? ' / ' + v.alignment_status : ''}
            {v.changed_sections && v.changed_sections.length ? (
              <>
                <br />
                ubah: {v.changed_sections.join(', ')}
              </>
            ) : null}
            <br />
            <button type="button" onClick={() => void lihatVersi(v.version_no)}>
              Lihat
            </button>{' '}
            {versions.length > 1 && (
              <button type="button" className="btn btn--hapus" onClick={() => setHapusTarget(v.version_no)}>
                Hapus
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="form__actions">
        {ok && url && (
          <a id="btn-export-docx" className="btn btn--aksi" href={url}>
            Export DOCX
          </a>
        )}
        <a className="btn" href="#layar-formulir">
          Buat RPM baru
        </a>
      </div>
      {hasilError && (
        <div id="hasil-error" className="error" role="alert">
          {hasilError}
        </div>
      )}
      {hapusTarget != null && (
        <div className="overlay" onClick={(e) => {
          if (!hapusSibuk && e.target === e.currentTarget) setHapusTarget(null);
        }}>
          <div ref={hapusDialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="hapus-versi-judul" tabIndex={-1}>
            <h2 id="hapus-versi-judul">Hapus v{hapusTarget} permanen?</h2>
            <p className="lede">
              Riwayat v{hapusTarget} akan dihapus permanen dari modul ini. Versi lain tetap utuh.
            </p>
            <div className="form__actions">
              <button
                type="button"
                className={hapusSibuk ? 'btn btn--hapus btn--busy' : 'btn btn--hapus'}
                disabled={hapusSibuk}
                onClick={() => void hapusVersi()}
              >
                Hapus permanen
              </button>
              <button type="button" className="btn" disabled={hapusSibuk} onClick={() => setHapusTarget(null)}>
                Batal
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
