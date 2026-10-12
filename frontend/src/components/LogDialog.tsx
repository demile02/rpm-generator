import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useDialogFocus } from '../lib/dialogFocus';
import { useAlerts, useLoading } from '../state/appContext';
import { pesanError, type GenerationLogItem, type GenerationRecord } from '../types';
import { ConfirmDialog } from './ConfirmDialog';

interface LogDialogProps {
  open: boolean;
  onClose: () => void;
}

const STATUS_LOG: Record<string, string> = {
  success: 'Sukses',
  failed: 'Gagal',
  partial: 'Sebagian gagal',
  running: 'Berjalan',
};

function idPendek(gid: string): string {
  return gid.length > 8 ? gid.slice(0, 8) : gid;
}

function metaLog(g: GenerationLogItem): string {
  const bagian: string[] = [];
  const status = STATUS_LOG[g.status ?? ''] ?? g.status;
  if (status) bagian.push(status);
  bagian.push((g.attempts ?? 0) + ' tahap');
  if (g.error_categories && g.error_categories.length) bagian.push(g.error_categories.join(', '));
  if (g.updated_at) bagian.push(g.updated_at);
  return bagian.join(' · ');
}

function barisRecord(r: GenerationRecord): string {
  const bagian: string[] = [];
  if (r.stage) bagian.push(r.stage);
  if (r.attempt != null) bagian.push('percobaan ' + r.attempt);
  if (r.status) bagian.push(r.status);
  const galat = r.error_category || r.error || '';
  if (galat) bagian.push(galat);
  return bagian.join(' · ');
}

export function LogDialog({ open, onClose }: LogDialogProps) {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, sembunyiLoading } = useLoading();
  const [items, setItems] = useState<GenerationLogItem[]>([]);
  const [memuat, setMemuat] = useState(false);
  const [error, setError] = useState('');
  const [pilihan, setPilihan] = useState<Record<string, boolean>>({});
  const [menuBuka, setMenuBuka] = useState<string | null>(null);
  const [detailGid, setDetailGid] = useState<string | null>(null);
  const [detail, setDetail] = useState<GenerationRecord[]>([]);
  const [detailMemuat, setDetailMemuat] = useState(false);
  const [konfirmHapus, setKonfirmHapus] = useState(false);
  const [menghapus, setMenghapus] = useState(false);
  const [hapusError, setHapusError] = useState('');
  const detailRequestRef = useRef(0);
  const dialogRef = useDialogFocus(open, onClose);

  const muatLog = () => {
    setMemuat(true);
    setError('');
    setDetailGid(null);
    setDetail([]);
    api
      .listGenerations()
      .then((res) => {
        setItems(res.generations ?? []);
        setMemuat(false);
      })
      .catch(() => {
        const pesan = 'Gagal memuat log generate. Periksa server lalu muat ulang halaman.';
        setError(pesan);
        setMemuat(false);
        tampilAlert('Gagal memuat log', pesan);
      });
  };

  useEffect(() => {
    if (open) {
      setPilihan({});
      setMenuBuka(null);
      setKonfirmHapus(false);
      setHapusError('');
      muatLog();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open ]);

  if (!open) return null;

  const gidTerlihat = items.map((g) => g.generation_id).filter((g) => g);
  const nDipilih = gidTerlihat.filter((g) => pilihan[g]).length;
  const semuaDipilih = gidTerlihat.length > 0 && nDipilih === gidTerlihat.length;
  const sebagianDipilih = nDipilih > 0 && nDipilih < gidTerlihat.length;

  const aturPilih = (gid: string, nyala: boolean) => {
    setPilihan((p) => {
      const next = { ...p };
      if (nyala) next[gid] = true;
      else delete next[gid];
      return next;
    });
  };

  const pilihSemua = (nyala: boolean) => {
    setPilihan((p) => {
      const next = { ...p };
      gidTerlihat.forEach((g) => {
        if (nyala) next[g] = true;
        else delete next[g];
      });
      return next;
    });
  };

  const pilihViaMenu = (gid: string) => {
    aturPilih(gid, true);
    setMenuBuka(null);
  };

  const bukaDetail = (gid: string) => {
    const requestId = ++detailRequestRef.current;
    setDetailGid(gid);
    setDetail([]);
    setDetailMemuat(true);
    api
      .getGenerationLog(gid)
      .then((res) => {
        if (requestId !== detailRequestRef.current) return;
        setDetail(res.records ?? []);
        setDetailMemuat(false);
      })
      .catch(() => {
        if (requestId !== detailRequestRef.current) return;
        const pesan = 'Gagal memuat detail generate.';
        setError(pesan);
        setDetailMemuat(false);
        tampilAlert('Gagal memuat detail log', pesan);
      });
  };

  const bukaHapus = () => {
    if (!nDipilih) return;
    setHapusError('');
    setKonfirmHapus(true);
  };

  const hapusTerpilih = () => {
    const daftar = gidTerlihat.filter((g) => pilihan[g]);
    if (!daftar.length) {
      setKonfirmHapus(false);
      return;
    }
    setMenghapus(true);
    setHapusError('');
    tampilLoading('Menghapus log', 'Menghapus 1 dari ' + daftar.length + '…');
    api
      .deleteGenerationLogs(daftar)
      .then((res) => {
        setMenghapus(false);
        sembunyiLoading();
        setKonfirmHapus(false);
        const sudah = (res.deleted ?? []).length;
        const hilang = (res.missing ?? []).length;
        setPilihan((p) => {
          const next = { ...p };
          daftar.forEach((g) => {
            delete next[g];
          });
          return next;
        });
        muatLog();
        tampilAlert(
          hilang && !sudah ? 'Sebagian log gagal dihapus' : 'Log dihapus',
          sudah + ' log dihapus permanen' + (hilang ? ', ' + hilang + ' sudah tidak ada' : '') + '.',
        );
      })
      .catch((err) => {
        setMenghapus(false);
        sembunyiLoading();
        const data = (err as { data?: unknown } | null)?.data ?? {};
        const pesan = 'Gagal menghapus log. ' + pesanError(data);
        setHapusError(pesan);
        tampilAlert('Gagal menghapus log', pesan);
      });
  };

  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="dialog dialog--lebar" role="dialog" aria-modal="true" aria-labelledby="judul-log" tabIndex={-1}>
        <h2 id="judul-log">Log</h2>
        <p className="lede dialog__sub">Riwayat proses generate beserta status dan error tiap tahap.</p>
        {error && (
          <div id="log-error" className="error" role="alert">{error}</div>
        )}
        {!memuat && !items.length && !error && (
          <div id="log-kosong">
            <p className="lede">Belum ada proses generate tercatat.</p>
          </div>
        )}
        {nDipilih > 0 && (
          <div className="bulk" id="log-bulk-kontrol">
            <label className="bulk__pilih">
              <input
                type="checkbox"
                id="log-bulk-pilih"
                checked={semuaDipilih}
                ref={(el) => {
                  if (el) el.indeterminate = sebagianDipilih;
                }}
                onChange={(e) => pilihSemua(e.target.checked)}
              />
              <span>Pilih semua</span>
            </label>
            <div className="bulk__bilah" id="log-bulk-bilah">
              <span id="log-bulk-jumlah" role="status">{nDipilih} dipilih</span>
              <button
                type="button"
                id="btn-hapus-log-pilih"
                className="btn btn--hapus"
                onClick={bukaHapus}
              >
                Hapus permanen
              </button>
            </div>
          </div>
        )}
        <ul id="daftar-log" className={nDipilih > 0 ? 'riwayat mode-pilih' : 'riwayat'}>
          {memuat && (
            <li className="meta" role="status">Memuat log…</li>
          )}
          {items.map((g) => {
            const gid = g.generation_id;
            const pendek = idPendek(gid);
            const menuId = 'menulog-' + gid;
            const terbuka = menuBuka === gid;
            return (
              <li className="rpm-card" key={gid}>
                <label className="pilih">
                  <input
                    type="checkbox"
                    className="pilih__box"
                    data-gidlog={gid}
                    aria-label={'Pilih log ' + pendek}
                    checked={!!pilihan[gid]}
                    onChange={(e) => aturPilih(gid, e.target.checked)}
                  />
                </label>
                <div className="rpm-card__isi">
                  <strong>{pendek || '(tanpa id)'}</strong>
                  <p className="meta">{metaLog(g)}</p>
                  <button
                    type="button"
                    className="titik"
                    data-titiklog={gid}
                    aria-label={'Opsi untuk log ' + pendek}
                    aria-expanded={terbuka ? 'true' : 'false'}
                    aria-controls={menuId}
                    onClick={() => setMenuBuka((m) => (m === gid ? null : gid))}
                  >
                    ⋮
                  </button>
                  <div className="menu-pilih" id={menuId} hidden={!terbuka} role="menu">
                    <button type="button" data-aksi-pilihlog={gid} role="menuitem" onClick={() => pilihViaMenu(gid)}>
                      Pilih
                    </button>
                  </div>
                </div>
                <div className="form__actions">
                  <button type="button" className="btn" data-log={gid} onClick={() => bukaDetail(gid)}>
                    Detail
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
        {detailGid !== null && (
          <div id="log-detail" className="panel-cp">
            <h3 id="log-detail-judul">Detail {idPendek(detailGid)}</h3>
            <p id="log-detail-meta" className="meta">
              {detailMemuat ? 'Memuat detail…' : detail.length + ' tahap tercatat.'}
            </p>
            <div id="log-detail-isi">
              {!detailMemuat &&
                (detail.length ? (
                  <ul className="toc">
                    {detail.map((r, i) => (
                      <li key={(r.stage ?? '') + '-' + (r.attempt ?? i) + '-' + i}>
                        {barisRecord(r)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="meta">Tidak ada tahap tercatat untuk generate ini.</p>
                ))}
            </div>
            <div className="form__actions">
              <button type="button" id="btn-tutup-log" className="btn" onClick={() => setDetailGid(null)}>
                Tutup detail
              </button>
            </div>
          </div>
        )}
        <div className="form__actions">
          <button type="button" id="btn-tutup-log-overlay" className="btn btn--aksi" onClick={onClose}>
            Tutup
          </button>
        </div>
      </div>
      <ConfirmDialog
        open={konfirmHapus}
        judul={'Hapus ' + nDipilih + ' log permanen?'}
        pesan={nDipilih + ' baris audit log akan dihapus permanen. RPM di Beranda TIDAK ikut terhapus.'}
        error={hapusError}
        confirmLabel="Hapus permanen"
        cancelLabel="Batal"
        busy={menghapus}
        onConfirm={hapusTerpilih}
        onClose={() => {
          if (!menghapus) setKonfirmHapus(false);
        }}
      />
    </div>
  );
}
