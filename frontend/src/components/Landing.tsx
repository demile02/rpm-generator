import { useEffect, useState } from 'react';
import { api } from '../api';

function formatRibuan(n: number | undefined): string {
  return Number(n || 0).toLocaleString('id-ID');
}

/* Ikon outline 1.8px, relevan dengan isi kartu (bukan dekorasi generik). */
function Ikon({ d }: { d: string }) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const FITUR: Array<{ judul: string; deskripsi: string; ikon: string; aksen: string }> = [
  { judul: 'CP resmi, bukan karangan', deskripsi: 'CP diambil dari dokumen regulasi yang terdaftar. AI tidak pernah mengarang CP.', ikon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h6', aksen: 'fitur__ikon--sage' },
  { judul: 'Diperiksa berlapis', deskripsi: 'Setiap RPM melewati pemeriksaan CP, struktur, aturan, pedagogis, dan final sebelum dapat diekspor.', ikon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4', aksen: 'fitur__ikon--lavender' },
  { judul: 'Ramah madrasah', deskripsi: 'Madrasah dapat mengintegrasikan Kurikulum Berbasis Cinta yang relevan dengan materi.', ikon: 'M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z', aksen: 'fitur__ikon--coral' },
  { judul: 'Tidak takut kehilangan', deskripsi: 'Semua versi tersimpan. Buka kembali, bandingkan, dan lanjutkan kapan saja.', ikon: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5M12 7v5l4 2', aksen: 'fitur__ikon--lavender' },
  { judul: 'Menjadi dokumen rapi', deskripsi: 'Unduh DOCX yang mengikuti templat sekolah atau madrasah dan siap disunting guru.', ikon: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3', aksen: 'fitur__ikon--sage' },
  { judul: 'Menghargai observasi Anda', deskripsi: 'Catatan kesiapan murid digunakan apa adanya, bukan sebagai diagnosis karangan.', ikon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75', aksen: 'fitur__ikon--coral' },
];

const LANGKAH: Array<{ judul: string; deskripsi: string }> = [
  { judul: 'Pilih konteks', deskripsi: 'Sistem, jenjang, kelas, mapel, dan topik' },
  { judul: 'Susun otomatis', deskripsi: 'AI menyusun TP, kegiatan, dan asesmen' },
  { judul: 'Periksa', deskripsi: 'Sistem memeriksa keselarasan sebelum hasil dibuka' },
  { judul: 'Unduh', deskripsi: 'DOCX siap dipakai, disunting, atau dibuatkan versi baru' },
];

export function Landing() {
  const [cp, setCp] = useState('');
  const [dokumen, setDokumen] = useState('');
  const [fragmen, setFragmen] = useState('');
  const [statsGagal, setStatsGagal] = useState(false);

  useEffect(() => {
    let batal = false;
    api
      .getStats(true)
      .then((res) => {
        if (batal) return;
        const s = res.statistics ?? {};
        setCp(formatRibuan(s.total_cp_entries));
        setDokumen(formatRibuan(s.total_documents));
        setFragmen(formatRibuan(s.total_fragments));
      })
      .catch(() => {
        if (!batal) setStatsGagal(true);
      });
    return () => {
      batal = true;
    };
  }, []);

  return (
    <section id="layar-landing" className="screen" aria-labelledby="judul-landing">
      <div className="hero">
        <span className="blob blob--coral" aria-hidden="true" style={{ width: 320, height: 320, left: '4%', top: '2%' }} />
        <span className="blob blob--lavender" aria-hidden="true" style={{ width: 300, height: 300, right: '5%', top: '12%', animationDelay: '2s' }} />
        <div className="hero__utama reveal">
          <p className="kicker">Untuk guru sekolah dan madrasah</p>
          <h1 id="judul-landing">
            Susun RPM dari CP resmi tanpa mulai dari nol.
          </h1>
          <p className="lede">
            Pilih sistem, jenjang, dan topik. Aplikasi mengambil CP resmi,
            menyusun tujuan, kegiatan, dan asesmen, lalu memvalidasinya
            berlapis sebelum diekspor sebagai DOCX siap pakai.
          </p>
          <div className="form__actions">
            <a className="btn btn--aksi" href="#layar-formulir">
              Buat RPM
            </a>
            <a className="btn" href="#layar-beranda">Beranda</a>
          </div>
        </div>
        {/* Stats hanya tampil bila data sudah ada: tanpa strip placeholder. */}
        {!statsGagal && cp && dokumen && fragmen && (
          <dl className="hero__stats" id="stat-kurikulum">
            <div className="hero__stats--coral"><dt>Entri CP resmi</dt><dd data-stat="cp">{cp}</dd></div>
            <div className="hero__stats--sage"><dt>Dokumen regulasi</dt><dd data-stat="dokumen">{dokumen}</dd></div>
            <div className="hero__stats--lavender"><dt>Fragmen sumber</dt><dd data-stat="fragmen">{fragmen}</dd></div>
          </dl>
        )}
      </div>
      <div className="fitur">
        <div className="fitur__kepala">
          <h2>
            Kenapa guru memakainya
          </h2>
          <p className="lede">
            Semua yang tertulis di bawah ini benar-benar dikerjakan aplikasi.
          </p>
        </div>
        <ul className="fitur__grid">
          {FITUR.map((f) => (
            <li key={f.judul}>
              <span className={'fitur__ikon ' + f.aksen} aria-hidden="true">
                <Ikon d={f.ikon} />
              </span>
              <strong>{f.judul}</strong>
              <span>{f.deskripsi}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="langkah">
        <h2>Alur kerja</h2>
        <ol className="alur alur--geser">
          {LANGKAH.map((l, i) => (
            <li key={l.judul}>
              <span className="alur__nomor" aria-hidden="true">{'0' + (i + 1)}</span>
              <strong>{l.judul}</strong>
              <span>{l.deskripsi}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="cta-akhir">
        <span className="cta-akhir__logo" aria-hidden="true"></span>
        <h2>Mulai RPM pertama Anda</h2>
        <p>Langsung mulai tanpa akun. Sistem memandu hingga dokumen DOCX.</p>
        <div className="form__actions">
          <a className="btn btn--aksi" href="#layar-formulir">Buat RPM</a>
          <a className="btn cta-akhir__sekunder" href="#layar-beranda">Beranda</a>
        </div>
      </div>
    </section>
  );
}
