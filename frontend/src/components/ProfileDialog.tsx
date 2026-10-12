import { useEffect, useState, type ChangeEvent } from 'react';
import { useDialogFocus } from '../lib/dialogFocus';
import { bacaProfil, tulisProfil, useAlerts, useProfile } from '../state/appContext';
import type { ProfileData } from '../types';

interface ProfileDialogProps {
  open: boolean;
  onClose: () => void;
}

function profilKosong(): ProfileData {
  return { penyusun: '', satuan_pendidikan: '', semester: '', tahun_ajaran: '' };
}

export function ProfileDialog({ open, onClose }: ProfileDialogProps) {
  const { refreshProfile } = useProfile();
  const { tampilAlert } = useAlerts();
  const [form, setForm] = useState<ProfileData>(profilKosong);
  const [status, setStatus] = useState('');

  useEffect(() => {
    if (open) {
      setForm(bacaProfil());
      setStatus('');
    }
  }, [open ]);

  const dialogRef = useDialogFocus(open, onClose);
  if (!open) return null;

  const ubah =
    (k: keyof ProfileData) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setForm((f) => ({ ...f, [k]: e.target.value }));
    };

  const simpan = () => {
    const profil: ProfileData = {
      penyusun: form.penyusun.trim(),
      satuan_pendidikan: form.satuan_pendidikan.trim(),
      semester: form.semester,
      tahun_ajaran: form.tahun_ajaran.trim(),
    };
    if (tulisProfil(profil)) {
      refreshProfile();
      onClose();
      tampilAlert('Profil tersimpan', 'Data default penyusun tersimpan di browser ini.');
    } else {
      const pesan = 'Gagal menyimpan profil di browser ini.';
      setStatus(pesan);
      tampilAlert('Profil gagal tersimpan', pesan);
    }
  };

  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="judul-profil" tabIndex={-1}>
        <h2 id="judul-profil">Profil Pengguna</h2>
        <p className="lede">
          Atur data default yang akan digunakan saat membuat RPM. Data tetap dapat diedit pada formulir.
        </p>
        <label className="field">
          Nama Penyusun
          <input
            id="p-penyusun"
            type="text"
            maxLength={100}
            placeholder="Mis. Nama Guru"
            value={form.penyusun}
            onChange={ubah('penyusun')}
            autoFocus
          />
        </label>
        <label className="field">
          Satuan Pendidikan
          <input
            id="p-satuan"
            type="text"
            maxLength={120}
            placeholder="Mis. MTs Negeri 1"
            value={form.satuan_pendidikan}
            onChange={ubah('satuan_pendidikan')}
          />
        </label>
        <label className="field">
          Semester
          <select id="p-semester" value={form.semester} onChange={ubah('semester')}>
            <option value="">Kosongkan</option>
            <option value="Ganjil">Ganjil</option>
            <option value="Genap">Genap</option>
          </select>
        </label>
        <label className="field">
          Tahun Pelajaran
          <input
            id="p-tahun"
            type="text"
            maxLength={20}
            placeholder="mis. 2026/2027"
            value={form.tahun_ajaran}
            onChange={ubah('tahun_ajaran')}
          />
        </label>
        <p id="profil-status" className="meta" role="status">{status}</p>
        <div className="form__actions">
          <button type="button" id="btn-simpan-profil" className="btn btn--aksi" onClick={simpan}>
            Simpan Profil
          </button>
          <button type="button" id="btn-batal-profil" className="btn" onClick={onClose}>
            Batal
          </button>
        </div>
      </div>
    </div>
  );
}
