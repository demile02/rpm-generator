import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useDialogFocus } from '../lib/dialogFocus';
import { api } from '../api';
import { bacaBukuDefault, bacaProfil, useAlerts, useLoading } from '../state/appContext';
import { useSession } from '../state/session';
import {
  pesanError,
  type BukuItem,
  type CpInfo,
  type CurriculumOptions,
  type GenerateFormParams,
  type RelevanceItem,
} from '../types';

/* Validasi alokasi: pesan persis ui/app.js validasiAlokasi. */
function validasiAlokasi(p: GenerateFormParams): string | null {
  function hitung(v: string | undefined): number | null | false {
    if (v === undefined || v === null || String(v).trim() === '') return null;
    const n = Number(String(v).trim());
    return Number.isInteger(n) && n >= 1 ? n : false;
  }
  const n = hitung(p.jumlah_pertemuan);
  const jp = hitung(p.jp_per_pertemuan);
  if (n === null || jp === null) {
    return 'Jumlah pertemuan dan JP per pertemuan wajib diisi ' +
      '(bilangan bulat >= 1).';
  }
  if (!n || !jp) {
    return 'Jumlah pertemuan dan JP per pertemuan wajib bilangan ' +
      'bulat >= 1.';
  }
  if (n > 16) {
    return 'Jumlah pertemuan harus diisi antara 1–16.';
  }
  if (jp > 10) {
    return 'JP per pertemuan harus diisi antara 1–10.';
  }
  return null;
}

/* Validasi jumlah soal: pesan persis ui/app.js validasiJumlah. */
function validasiJumlah(p: GenerateFormParams): string | null {
  const counts = p.assessment_counts || {};
  const labels: Record<string, string> = {
    diagnostic: 'asesmen awal',
    formative: 'asesmen formatif',
    summative: 'asesmen sumatif',
  };
  const keys = Object.keys(labels);
  let ada = false;
  for (const k of keys) {
    const v = (counts as Record<string, string | undefined>)[k];
    if (v === undefined || v === null || String(v).trim() === '') continue;
    const n = Number(String(v).trim());
    if (!Number.isInteger(n) || n < 0 || n > 30) {
      return 'Jumlah soal ' + labels[k] + ' harus bilangan bulat 0–30 (0 = tidak digenerate).';
    }
    if (n > 0) ada = true;
  }
  const semuaDiisi = keys.every((k) => {
    const vv = (counts as Record<string, string | undefined>)[k];
    return !(vv === undefined || vv === null || String(vv).trim() === '');
  });
  if (semuaDiisi && !ada) {
    return 'Minimal satu jenis asesmen berjumlah >= 1.';
  }
  return null;
}

function semesterProfilKeForm(semester: string): string {
  if (semester === 'Ganjil') return '1';
  if (semester === 'Genap') return '2';
  return '';
}

/* ELEMENT_NOT_FOUND = user belum pilih elemen: terjemahkan
   kode teknis backend ke instruksi yang bisa ditindaklanjuti. */
function ramahGalatCp(pesan: string): string {
  if (pesan.indexOf('ELEMENT_NOT_FOUND') !== -1) {
    return 'Mapel ini memiliki lebih dari satu elemen. ' +
      'Pilih Elemen pada formulir lalu cek CP lagi.';
  }
  return pesan;
}

const FORM_DRAFT_KEY = 'rpm-form-draft-v1';
type DraftRestoreStep = 'waiting' | 'system' | 'institution' | 'grade' | 'subject' | 'rest' | 'done';
type FormDraft = {
  sistem: string;
  institusi: string;
  kelas: string;
  mapel: string;
  elemenDipilih: string[];
  bukuId: string;
  topik: string;
  penyusun: string;
  satuan: string;
  semester: string;
  tahun: string;
  jumlah: string;
  jp: string;
  awal: string;
  formatif: string;
  sumatif: string;
  kesiapan: string;
};

function teksDraft(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function daftarDraft(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function bacaDraftForm(): Partial<FormDraft> | null {
  try {
    const raw = window.localStorage?.getItem(FORM_DRAFT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as Partial<FormDraft> : null;
  } catch {
    return null;
  }
}

function hapusDraftForm(): void {
  try {
    window.localStorage?.removeItem(FORM_DRAFT_KEY);
  } catch {
    // Storage unavailable must not block generation.
  }
}

export function Formulir({ onDone }: { onDone: () => void }) {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, sembunyiLoading } = useLoading();
  const { setJob } = useSession();

  const [options, setOptions] = useState<CurriculumOptions | null>(null);
  const [mapelList, setMapelList] = useState<string[]>([]);
  const [mapelMuat, setMapelMuat] = useState(false);
  const [mapelSiap, setMapelSiap] = useState(false);
  const [mapelCari, setMapelCari] = useState('');
  const [mapelBuka, setMapelBuka] = useState(false);
  const mapelRequestRef = useRef<AbortController | null>(null);
  const mapelBoxRef = useRef<HTMLDivElement | null>(null);
  const [elemenList, setElemenList] = useState<string[]>([]);
  const [elemenMuat, setElemenMuat] = useState(false);
  const [elemenReady, setElemenReady] = useState(false);
  const elemenRequestRef = useRef<AbortController | null>(null);
  /* Draft dibaca hanya oleh form ini. Restore berjalan setelah opsi kurikulum
     tersedia agar cascade dropdown tetap valid. */
  const [draftData] = useState<Partial<FormDraft> | null>(() => bacaDraftForm());
  const [draftRestoreStep, setDraftRestoreStep] = useState<DraftRestoreStep>(
    () => draftData ? 'waiting' : 'done',
  );
  const skipElementDefaultRef = useRef(Boolean(draftData));
  const draftDeletedRef = useRef(false);
  const [sistem, setSistem] = useState('');
  const [institusi, setInstitusi] = useState('');
  const [kelas, setKelas] = useState('');
  const [mapel, setMapel] = useState('');
  const [elemenDipilih, setElemenDipilih] = useState<string[]>([]);
  const [buku, setBuku] = useState<BukuItem[]>([]);
  const [bukuId, setBukuId] = useState('');
  const [bukuState, setBukuState] = useState<'muat' | 'siap' | 'gagal'>('muat');
  const [topik, setTopik] = useState('');
  const [penyusun, setPenyusun] = useState('');
  const [satuan, setSatuan] = useState('');
  const [semester, setSemester] = useState('');
  const [tahun, setTahun] = useState('');
  const [jumlah, setJumlah] = useState('2');
  const [jp, setJp] = useState('2');
  const [awal, setAwal] = useState('10');
  const [formatif, setFormatif] = useState('10');
  const [sumatif, setSumatif] = useState('5');
  const [kesiapan, setKesiapan] = useState('');
  const [galat, setGalat] = useState('');
  const [cp, setCp] = useState<CpInfo | null>(null);
  const [cpDaftar, setCpDaftar] = useState<CpInfo[]>([]);
  const [cpTerlihat, setCpTerlihat] = useState(false);
  const [cekBerjalan, setCekBerjalan] = useState(false);
  const [genBerjalan, setGenBerjalan] = useState(false);
  /* Modal peringatan relevansi topik vs elemen (peringatan, bukan larangan). */
  const [peringatan, setPeringatan] = useState<{
    relevansi: RelevanceItem[];
    saran: string;
  } | null>(null);
  const peringatanDialogRef = useDialogFocus(peringatan != null, () => setPeringatan(null));
  /* Langkah aktif mengikuti kartu yang terlihat: 1 = Konteks, 2 = Pendalaman.
     Hitung posisi scroll manual (IntersectionObserver tak fire di sebagian browser). */
  const [langkah, setLangkah] = useState(1);
  const refPendalaman = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let frame: number | null = null;
    const hitungSekarang = (): void => {
      frame = null;
      const b = refPendalaman.current;
      if (!b) return;
      const r = b.getBoundingClientRect();
      // Kartu Pendalaman masuk setengah layar: langkah 2 aktif.
      setLangkah((lama) => {
        const baru = r.top < window.innerHeight * 0.55 ? 2 : 1;
        return lama === baru ? lama : baru;
      });
    };
    const jadwalkanHitung = (): void => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame(hitungSekarang);
    };
    hitungSekarang();
    window.addEventListener('scroll', jadwalkanHitung, { passive: true });
    window.addEventListener('resize', jadwalkanHitung);
    return () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', jadwalkanHitung);
      window.removeEventListener('resize', jadwalkanHitung);
    };
  }, []);

  /* Auto-scroll ke panel CP setelah terlihat (commit React selesai).
     Pengaman: bila smooth tak menggerakkan halaman (sebagian headless),
     paksa scroll instan setelah 600ms. */
  useEffect(() => {
    if (!cpTerlihat) return;
    const gerak = (halus: boolean): void => {
      const panel = document.getElementById('panel-cp');
      if (!panel) return;
      try {
        if (halus) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        else panel.scrollIntoView();
      } catch {
        panel.scrollIntoView();
      }
    };
    const t1 = window.setTimeout(() => gerak(true), 150);
    const t2 = window.setTimeout(() => {
      const panel = document.getElementById('panel-cp');
      if (panel && panel.getBoundingClientRect().top > window.innerHeight) {
        gerak(false);
      }
    }, 800);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [cpTerlihat]);

  /* Error formulir: tampil di box + popup, seperti formError legacy. */
  const salah = (pesan: string): void => {
    setGalat(pesan);
    if (pesan) tampilAlert('Formulir belum lengkap', pesan);
  };

  useEffect(() => {
    const controller = new AbortController();
    api.getCurriculumOptions(true, controller.signal).then((res) => {
      setOptions(res);
    }).catch(() => {
      if (controller.signal.aborted) return;
      setGalat('Gagal memuat opsi kurikulum. Periksa server lalu muat ulang.');
    });
    return () => controller.abort();
  }, []);

  /* Pulihkan cascade satu tingkat per render. Nilai yang tidak lagi ada
     di database dilewati, bukan dipaksakan ke state dropdown. */
  useEffect(() => {
    if (!options || !draftData || draftRestoreStep !== 'waiting') return;
    const value = teksDraft(draftData.sistem);
    setSistem(value && options.systems[value] ? value : '');
    setDraftRestoreStep('system');
  }, [options, draftData, draftRestoreStep]);

  useEffect(() => {
    if (!options || !draftData || draftRestoreStep !== 'system') return;
    const institutionsForSystem = options.systems[sistem]?.institutions ?? {};
    const value = teksDraft(draftData.institusi);
    setInstitusi(value && institutionsForSystem[value] ? value : '');
    setDraftRestoreStep('institution');
  }, [options, draftData, draftRestoreStep, sistem]);

  useEffect(() => {
    if (!options || !draftData || draftRestoreStep !== 'institution') return;
    const gradesForInstitution = options.systems[sistem]?.institutions[institusi]?.grades ?? [];
    const value = teksDraft(draftData.kelas);
    setKelas(value && gradesForInstitution.includes(value) ? value : '');
    setDraftRestoreStep('grade');
  }, [options, draftData, draftRestoreStep, sistem, institusi]);

  useEffect(() => {
    if (!options || !draftData || draftRestoreStep !== 'grade') return;
    setDraftRestoreStep('subject');
  }, [options, draftData, draftRestoreStep, sistem, kelas]);

  /* Restore mapel menunggu daftar per-kelas (bukan aggregate sistem),
     cocokkan case-insensitive agar draft lama tetap valid; lalu pulihkan
     sisa field teks seperti cascade legacy. */
  useEffect(() => {
    if (!options || !draftData || draftRestoreStep !== 'subject') return;
    if (sistem && institusi && kelas) {
      if (mapelMuat || !mapelSiap) return;
      const value = teksDraft(draftData.mapel);
      const cocok = mapelList.find((m) => m.toLowerCase() === value.toLowerCase());
      setMapel(value && cocok ? cocok : '');
    }
    setTopik(teksDraft(draftData.topik));
    setPenyusun(teksDraft(draftData.penyusun));
    setSatuan(teksDraft(draftData.satuan));
    setSemester(teksDraft(draftData.semester));
    setTahun(teksDraft(draftData.tahun));
    setJumlah(teksDraft(draftData.jumlah) || '2');
    setJp(teksDraft(draftData.jp) || '2');
    setAwal(teksDraft(draftData.awal) || '10');
    setFormatif(teksDraft(draftData.formatif) || '10');
    setSumatif(teksDraft(draftData.sumatif) || '5');
    setKesiapan(teksDraft(draftData.kesiapan));
    setDraftRestoreStep('rest');
  }, [options, draftData, draftRestoreStep, sistem, institusi, kelas, mapelList, mapelMuat, mapelSiap]);

  useEffect(() => {
    const faseDraft = options?.systems[sistem]?.institutions[institusi]?.grade_phase?.[kelas] || '';
    if (!options || !draftData || draftRestoreStep !== 'rest' || bukuState === 'muat' ||
        (Boolean(mapel && faseDraft) && !elemenReady)) return;
    const storedElements = daftarDraft(draftData.elemenDipilih)
      .filter((element) => elemenList.includes(element));
    setElemenDipilih(elemenList.length > 1 ? storedElements : []);
    const storedBook = teksDraft(draftData.bukuId);
    setBukuId(storedBook && buku.some((item) => item.document_id === storedBook)
      ? storedBook
      : '');
    setSemester(['', '1', '2'].includes(teksDraft(draftData.semester))
      ? teksDraft(draftData.semester)
      : '');
    skipElementDefaultRef.current = true;
    setDraftRestoreStep('done');
  }, [
    options, draftData, draftRestoreStep, bukuState, buku, sistem, institusi,
    kelas, mapel, elemenReady, elemenList,
  ]);

  /* Draft hanya berisi input form, bukan CP atau status proses. */
  useEffect(() => {
    if (draftRestoreStep !== 'done' || draftDeletedRef.current) return;
    const timer = window.setTimeout(() => {
      if (draftDeletedRef.current) return;
      const draft: FormDraft = {
        sistem, institusi, kelas, mapel, elemenDipilih, bukuId, topik,
        penyusun, satuan, semester, tahun, jumlah, jp, awal, formatif,
        sumatif, kesiapan,
      };
      try {
        window.localStorage?.setItem(FORM_DRAFT_KEY, JSON.stringify(draft));
      } catch {
        // Storage penuh/tidak tersedia tidak boleh mengganggu form.
      }
    }, 450);
    return () => window.clearTimeout(timer);
  }, [
    draftRestoreStep, sistem, institusi, kelas, mapel, elemenDipilih,
    bukuId, topik, penyusun, satuan, semester, tahun, jumlah, jp, awal,
    formatif, sumatif, kesiapan,
  ]);

  /* Prefill profil hanya bila field masih kosong. */
  useEffect(() => {
    const p = bacaProfil();
    if (p.penyusun) setPenyusun((v) => v || p.penyusun);
    if (p.satuan_pendidikan) setSatuan((v) => v || p.satuan_pendidikan);
    const sem = semesterProfilKeForm(p.semester);
    if (sem) setSemester((v) => v || sem);
    if (p.tahun_ajaran) setTahun((v) => v || p.tahun_ajaran);
  }, []);

  /* Daftar buku + preselect default, seperti muatDaftarBuku legacy. */
  useEffect(() => {
    api.daftarBuku().then((res) => {
      const daftar = res?.buku ?? [];
      setBuku(daftar);
      const def = bacaBukuDefault();
      const masihAda = !def || daftar.some((b) => b.document_id === def);
      setBukuId(masihAda ? def : '');
      setBukuState('siap');
    }).catch(() => {
      setBukuState('gagal');
    });
  }, []);

  const institutions = ((options?.systems ?? {})[sistem]?.institutions) ?? {};
  const daftarInstitusi = Object.keys(institutions);
  const daftarKelas = institutions[institusi]?.grades ?? [];
  const gradePhase = institutions[institusi]?.grade_phase ?? {};
  const fase = (kelas && gradePhase[kelas]) || '';
  const faseTampil = kelas ? fase || ',' : '';
  /* Tampil UPPERCASE + A–Z; nilai state tetap ejaan kanonis DB supaya
     lookup elemen/CP exact-match tidak rusak. */
  const daftarMapelTampil = [...mapelList].sort((a, b) =>
    a.localeCompare(b, 'id', { sensitivity: 'base' }));
  const kataCari = mapelCari.trim().toLowerCase();
  const daftarMapelSaring = kataCari
    ? daftarMapelTampil.filter((m) => m.toLowerCase().includes(kataCari))
    : daftarMapelTampil;

  /* Daftar mapel mengikuti kelas: hanya mapel ber-CP aktif untuk fase
     kelas terpilih. Abort request lama agar respons basi tak menimpa. */
  useEffect(() => {
    mapelRequestRef.current?.abort();
    setMapelList([]);
    setMapelSiap(false);
    setMapelCari('');
    setMapelBuka(false);
    if (!sistem || !institusi || !kelas) {
      setMapelMuat(false);
      return;
    }
    const controller = new AbortController();
    mapelRequestRef.current = controller;
    setMapelMuat(true);
    api.getCurriculumSubjects(sistem, institusi, kelas, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setMapelList(res.subjects);
      })
      .catch(() => {
        if (!controller.signal.aborted) setGalat('Gagal memuat daftar mata pelajaran.');
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        setMapelMuat(false);
        setMapelSiap(true);
      });
    return () => controller.abort();
  }, [sistem, institusi, kelas]);

  /* Tutup daftar saat klik di luar kotak combobox. */
  useEffect(() => {
    if (!mapelBuka) return;
    const tutup = (e: MouseEvent): void => {
      if (mapelBoxRef.current && !mapelBoxRef.current.contains(e.target as Node)) {
        setMapelBuka(false);
      }
    };
    document.addEventListener('mousedown', tutup);
    return () => document.removeEventListener('mousedown', tutup);
  }, [mapelBuka]);

  /* Mapel tak ada di kelas baru ikut direset (seperti cascade legacy). */
  useEffect(() => {
    if (!mapel || mapelMuat || !mapelSiap || (!sistem || !institusi || !kelas)) return;
    if (!mapelList.includes(mapel)) {
      setMapel('');
      setElemenDipilih([]);
      setCpTerlihat(false);
    }
  }, [mapelList, mapelMuat, mapelSiap, mapel, sistem, institusi, kelas]);

  useEffect(() => {
    elemenRequestRef.current?.abort();
    setElemenList([]);
    setElemenReady(false);
    if (!mapel || !fase) {
      setElemenMuat(false);
      return;
    }
    const controller = new AbortController();
    elemenRequestRef.current = controller;
    setElemenMuat(true);
    api.getCurriculumElements(mapel, fase, sistem, institusi, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setElemenList(res.elements);
        setElemenReady(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setGalat('Gagal memuat elemen kurikulum.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setElemenMuat(false);
      });
    return () => controller.abort();
  }, [mapel, fase, sistem, institusi]);

  /* Cascade persis legacy: tiap pilih atas me-reset pilihan bawah. */
  const onSistem = (v: string): void => {
    setSistem(v);
    setInstitusi('');
    setKelas('');
    setMapel('');
    setElemenDipilih([]);
    setCpTerlihat(false);
  };

  const onInstitusi = (v: string): void => {
    setInstitusi(v);
    setKelas('');
    setMapel('');
    setElemenDipilih([]);
    setCpTerlihat(false);
  };

  const onKelas = (v: string): void => {
    setKelas(v);
    setMapel('');
    setElemenDipilih([]);
    setCpTerlihat(false);
  };

  const onMapel = (v: string): void => {
    setMapel(v);
    setMapelBuka(false);
    setElemenDipilih([]);
    setCpTerlihat(false);
  };

  /* Centang baru = default semua tercentang saat daftar elemen berubah. */
  useEffect(() => {
    /* Saat restore, selection tersimpan sudah dipasang oleh effect cascade.
       Jangan timpa dengan default semua elemen. */
    if (draftData && draftRestoreStep !== 'done') return;
    if (draftData && skipElementDefaultRef.current) {
      skipElementDefaultRef.current = false;
      return;
    }
    if (elemenList.length > 1) setElemenDipilih(elemenList);
    else setElemenDipilih([]);
  }, [elemenList.join('|'), draftData, draftRestoreStep]); // eslint-disable-line react-hooks/exhaustive-deps

  const alihElemen = (nama: string): void => {
    setElemenDipilih((dulu) => (
      dulu.indexOf(nama) === -1 ? [...dulu, nama] : dulu.filter((e) => e !== nama)
    ));
    setCpTerlihat(false);
  };

  /* Baca form live dari state, seperti bacaForm legacy. */
  const bacaForm = (): GenerateFormParams => {
    const dipilih = elemenList.length > 1 ? elemenDipilih : [];
    const primer = dipilih[0];
    return {
      education_system: sistem,
      institution_type: institusi,
      grade: kelas,
      phase: fase,
      subject: mapel,
      element: primer,
      elements: dipilih.length ? dipilih : undefined,
      topic: topik.trim(),
      satuan_pendidikan: satuan.trim() || undefined,
      semester: semester || undefined,
      tahun_ajaran: tahun.trim() || undefined,
      penyusun: penyusun.trim() || undefined,
      jumlah_pertemuan: jumlah.trim() || undefined,
      jp_per_pertemuan: jp.trim() || undefined,
      assessment_counts: {
        diagnostic: awal.trim() || undefined,
        formative: formatif.trim() || undefined,
        summative: sumatif.trim() || undefined,
      },
      buku_document_id: bukuId || undefined,
      student_readiness: kesiapan.trim() || undefined,
    };
  };

  const onCekCp = (e: FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    salah('');
    const p = bacaForm();
    if (!p.education_system || !p.institution_type || !p.grade ||
        !p.subject || !p.topic) {
      salah('Lengkapi sistem, jenjang, kelas, mapel, dan topik.');
      return;
    }
    if (!p.phase) {
      salah('Fase tidak ditemukan untuk kelas ini.');
      return;
    }
    if (elemenList.length > 1 && elemenDipilih.length === 0) {
      salah('Pilih minimal 1 elemen untuk mapel ini.');
      return;
    }
    if (!p.buku_document_id) {
      salah('Pilih buku ajar sumber materi dulu.');
      return;
    }
    const alokasiError = validasiAlokasi(p);
    if (alokasiError) {
      salah(alokasiError);
      return;
    }
    const jumlahError = validasiJumlah(p);
    if (jumlahError) {
      salah(jumlahError);
      return;
    }
    setCekBerjalan(true);
    tampilLoading('Memeriksa CP', 'Mengambil CP resmi dari backend…');
    api.generateContext(p).then((res) => {
      sembunyiLoading();
      setCekBerjalan(false);
      if (res.status !== 'success' || !res.context) {
        salah(ramahGalatCp(pesanError(res)));
        return;
      }
      setCp(res.context.cp || {});
      const ctx = res.context as { cps?: CpInfo[] };
      setCpDaftar(Array.isArray(ctx.cps) && ctx.cps.length
        ? ctx.cps
        : (res.context.cp ? [res.context.cp] : []));
      setCpTerlihat(true);
    }).catch((err: unknown) => {
      sembunyiLoading();
      setCekBerjalan(false);
      const data = (err as { data?: unknown } | null)?.data;
      const errors = (data as { errors?: unknown[] } | null)?.errors;
      salah(errors && errors.length
        ? ramahGalatCp(pesanError(data))
        : 'Backend tidak merespons. Periksa server lalu coba lagi.');
    });
  };

  /* Generate jalan; lewatiRelevansi = ulangi setelah user pilih
     "tetap lanjutkan" di modal peringatan (gate lunak, bukan blokir). */
  const jalanGenerate = (p: GenerateFormParams): void => {
    setGenBerjalan(true);
    tampilLoading('Menyusun RPM', 'Menghubungi backend…');
    api.generateModuleAsync(p).then((res) => {
      setGenBerjalan(false);
      draftDeletedRef.current = true;
      hapusDraftForm();
      setJob({ jobId: res.job_id, pollStart: Date.now(), retryParams: { ...p } });
      onDone();
    }).catch((err: unknown) => {
      setGenBerjalan(false);
      sembunyiLoading();
      const data = (err as { data?: unknown } | null)?.data;
      const errors = (data as { errors?: unknown[] } | null)?.errors;
      salah(errors && errors.length
        ? ramahGalatCp(pesanError(data))
        : 'Generation gagal tanpa pesan error.');
    });
  };

  const onGenerate = (lewatiRelevansi = false): void => {
    const p = bacaForm();
    const alokasiError = validasiAlokasi(p);
    const jumlahError = validasiJumlah(p);
    if (!p.education_system || !p.institution_type || !p.grade ||
        !p.subject || !p.topic || !p.phase || alokasiError || jumlahError) {
      salah(alokasiError || jumlahError ||
        'Lengkapi sistem, jenjang, kelas, mapel, dan topik sebelum generate.');
      return;
    }
    if (elemenList.length > 1 && elemenDipilih.length === 0) {
      salah('Pilih minimal 1 elemen untuk mapel ini.');
      return;
    }
    if (!p.buku_document_id) {
      salah('Pilih buku ajar sumber materi dulu.');
      return;
    }
    jalanGenerate(lewatiRelevansi
      ? { ...p, skip_relevance_check: true }
      : p);
  };

  const cpMeta = 'Fase ' + (cp?.phase || '') +
    (cp?.source_page ? ' · dokumen hal. ' + String(cp.source_page) : '');

  return (
    <section id="layar-formulir" className="screen" aria-labelledby="kicker-formulir">
      <h4 className="kicker kicker--judul" id="kicker-formulir">Langkah 1 dari 2, Konteks pembelajaran</h4>
      <p className="lede">Semua pilihan berasal dari database kurikulum.</p>
      <ol className="langkah-form" aria-label="Kemajuan pengisian">
        <li className={langkah === 1 ? 'aktif' : undefined} aria-current={langkah === 1 ? 'step' : undefined}><span className="nomor" aria-hidden="true">1</span><div><strong>Konteks Pembelajaran</strong><small>Sistem, jenjang, kelas, mapel, topik</small></div></li>
        <li className={langkah === 2 ? 'aktif' : undefined} aria-current={langkah === 2 ? 'step' : undefined}><span className="nomor" aria-hidden="true">2</span><div><strong>Pendalaman Pengajar</strong><small>Identitas, alokasi, kesiapan murid</small></div></li>
      </ol>
      <div id="form-error" className="error" role="alert" hidden={!galat}>{galat}</div>
      <form id="form-konteks" noValidate onSubmit={onCekCp}>
        <div className="form-kaca" aria-labelledby="judul-grup-konteks">
          <h3 id="judul-grup-konteks">Konteks Pembelajaran</h3>
          <p>Dasar kurikulum RPM: sistem, jenjang, dan materi yang diajarkan.</p>
          <div className="grid-form">
            <label className="field">Sistem pendidikan
              <select id="f-sistem" required value={sistem} onChange={(e) => onSistem(e.target.value)}>
                <option value="">Pilih</option>
                {Object.keys(options?.systems ?? {}).map((code) => {
                  const inst = Object.keys(options?.systems?.[code]?.institutions ?? {}).join(', ');
                  return <option key={code} value={code}>{code + (inst ? ' (' + inst + ')' : '')}</option>;
                })}
              </select>
            </label>
            <label className="field">Jenjang / institusi
              <select id="f-institusi" required disabled={!sistem} value={institusi} onChange={(e) => onInstitusi(e.target.value)}>
                <option value="">Pilih</option>
                {daftarInstitusi.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label className="field">Kelas
              <select id="f-kelas" required disabled={!institusi} value={kelas} onChange={(e) => onKelas(e.target.value)}>
                <option value="">Pilih</option>
                {daftarKelas.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <div className="field">Fase
              <output id="f-fase" className="fase-output" htmlFor="f-kelas">{faseTampil}</output>
            </div>
            <div className="field" ref={mapelBoxRef}>
              <label className="field__label" htmlFor="f-mapel">Mata pelajaran</label>
              <input
                id="f-mapel"
                type="text"
                required
                role="combobox"
                aria-expanded={mapelBuka}
                aria-controls="f-mapel-daftar"
                aria-autocomplete="list"
                autoComplete="off"
                disabled={!kelas || mapelMuat}
                placeholder={mapelMuat ? 'Memuat…' : 'Ketik untuk mencari'}
                value={mapelBuka ? mapelCari : mapel.toUpperCase()}
                onChange={(e) => {
                  setMapelCari(e.target.value);
                  setMapelBuka(true);
                }}
                onFocus={() => {
                  if (kelas && !mapelMuat) {
                    setMapelCari('');
                    setMapelBuka(true);
                  }
                }}
                onBlur={(e) => {
                  /* Klik opsi di dalam box tak boleh dianggap batal:
                     commit hanya saat fokus benar-benar keluar box. */
                  if (mapelBoxRef.current?.contains(e.relatedTarget as Node)) return;
                  /* Pilih kandidat pertama yang cocok saat fokus pergi,
                     supaya ketikan tak jadi nilai mapel yang invalid. */
                  const kata = mapelCari.trim().toLowerCase();
                  if (kata) {
                    const cocok = daftarMapelTampil.find((m) =>
                      m.toLowerCase().includes(kata));
                    if (cocok) onMapel(cocok);
                  }
                  setMapelBuka(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && mapelBuka && daftarMapelSaring.length) {
                    e.preventDefault();
                    onMapel(daftarMapelSaring[0]);
                  } else if (e.key === 'Escape') {
                    setMapelBuka(false);
                  }
                }}
              />
              {mapelBuka && (
                <ul id="f-mapel-daftar" className="mapel-daftar" role="listbox" aria-label="Daftar mata pelajaran">
                  {daftarMapelSaring.map((m) => (
                    <li key={m} role="option" aria-selected={mapel === m}>
                      <button type="button" onClick={() => onMapel(m)}>
                        {m.toUpperCase()}
                      </button>
                    </li>
                  ))}
                  {!daftarMapelSaring.length && (
                    <li className="mapel-daftar__kosong">Tidak ada mapel yang cocok.</li>
                  )}
                </ul>
              )}
            </div>
            {elemenMuat ? (
              <div className="field field--lebar" id="f-elemen-grup" role="status" aria-live="polite">
                <span className="field__label">Elemen</span>
                <p className="meta">Memuat elemen kurikulum…</p>
              </div>
            ) : elemenList.length <= 1 ? (
              <label className="field">Elemen <span className="field__cap field__cap--opsional">(opsional)</span>
                <select id="f-elemen" disabled value="">
                  <option value="">Otomatis, sistem memilih elemen yang paling sesuai</option>
                </select>
              </label>
            ) : (
              <div className="field field--lebar" id="f-elemen-grup" role="group" aria-label="Elemen">
                <span className="field__label">Elemen <span className="field__cap field__cap--opsional">(centang minimal 1)</span></span>
                <div className="elemen-grup__opsi">
                  {elemenList.map((el) => (
                    <label key={el} className="elemen-pilih">
                      <input
                        type="checkbox"
                        className="elemen-pilih__box"
                        checked={elemenDipilih.indexOf(el) !== -1}
                        onChange={() => alihElemen(el)}
                      />
                      <span>{el}</span>
                    </label>
                  ))}
                </div>
                {elemenDipilih.length > 3 && (
                  <p className="meta" role="note">Elemen yang dipilih mungkin terlalu luas untuk 1 pertemuan. Persempit bila perlu.</p>
                )}
              </div>
            )}
            <label className="field field--lebar">Topik / konteks pembelajaran
              <input id="f-topik" type="text" required maxLength={200} placeholder="mis. Taubat" value={topik} onChange={(e) => setTopik(e.target.value)} />
            </label>
            <label className="field field--lebar">Buku ajar sumber materi <span className="field__cap field__cap--wajib">(wajib)</span>
              <select id="f-buku" required value={bukuId} onChange={(e) => setBukuId(e.target.value)}>
                {bukuState === 'muat' && <option value="">Memuat…</option>}
                {bukuState === 'gagal' && <option value="">Gagal memuat daftar</option>}
                {bukuState === 'siap' && buku.length === 0 && <option value="">Belum ada buku, upload dulu</option>}
                {bukuState === 'siap' && buku.length > 0 && (
                  <>
                    <option value="">Pilih buku</option>
                    {buku.map((b) => (
                      <option key={b.document_id} value={b.document_id}>
                        {(b.judul || b.document_id) + ' (' + (b.fragmen || 0) + ' fragmen)'}
                      </option>
                    ))}
                  </>
                )}
              </select>
            </label>
            <label className="field">Jumlah pertemuan <span className="field__cap field__cap--wajib">(wajib)</span>
              <input id="f-jumlah" type="number" required min={1} max={16} value={jumlah} onChange={(e) => setJumlah(e.target.value)} />
            </label>
            <label className="field">JP per pertemuan <span className="field__cap field__cap--wajib">(wajib)</span>
              <input id="f-jp" type="number" required min={1} max={10} value={jp} onChange={(e) => setJp(e.target.value)} />
            </label>
          </div>
        </div>
        <div className="form-kaca" ref={refPendalaman} aria-labelledby="judul-grup-pendalaman">
          <h3 id="judul-grup-pendalaman">Pendalaman Pengajar</h3>
          <p>Identitas pengajar, jumlah soal, dan kondisi awal murid.</p>
          <div className="grid-form">
            <label className="field">Penyusun <span className="field__cap field__cap--opsional">(opsional)</span>
              <input id="f-penyusun" type="text" maxLength={100} placeholder="mis. Nama Guru" value={penyusun} onChange={(e) => setPenyusun(e.target.value)} />
            </label>
            <label className="field">Satuan pendidikan <span className="field__cap field__cap--opsional">(opsional)</span>
              <input id="f-satuan" type="text" maxLength={120} placeholder="mis. MTs Negeri 1" value={satuan} onChange={(e) => setSatuan(e.target.value)} />
            </label>
            <label className="field">Semester <span className="field__cap field__cap--opsional">(opsional)</span>
              <select id="f-semester" value={semester} onChange={(e) => setSemester(e.target.value)}>
                <option value="">Kosongkan</option>
                <option value="1">Ganjil</option>
                <option value="2">Genap</option>
              </select>
            </label>
            <label className="field">Tahun ajaran <span className="field__cap field__cap--opsional">(opsional)</span>
              <input id="f-tahun" type="text" maxLength={20} placeholder="mis. 2026/2027" value={tahun} onChange={(e) => setTahun(e.target.value)} />
            </label>
            <label className="field">Soal asesmen awal <span className="field__cap field__cap--opsional">(default 10)</span>
              <input id="f-awal" type="number" min={0} max={30} value={awal} onChange={(e) => setAwal(e.target.value)} />
            </label>
            <label className="field">Soal asesmen formatif <span className="field__cap field__cap--opsional">(default 10)</span>
              <input id="f-formatif" type="number" min={0} max={30} value={formatif} onChange={(e) => setFormatif(e.target.value)} />
            </label>
            <label className="field field--lebar">Soal asesmen sumatif <span className="field__cap field__cap--opsional">(default 5)</span>
              <input id="f-sumatif" type="number" min={0} max={30} value={sumatif} onChange={(e) => setSumatif(e.target.value)} />
            </label>
            <label className="field field--lebar">Kesiapan Murid <span className="field__cap field__cap--opsional">(opsional)</span>
              <textarea id="f-kesiapan" rows={4} maxLength={2000} placeholder="Isi kondisi awal berdasarkan observasi/asesmen awal, misalnya: pengetahuan prasyarat; kemampuan awal; miskonsepsi; kebutuhan belajar; kesulitan yang telah diamati. Kosongkan bila data belum tersedia." value={kesiapan} onChange={(e) => setKesiapan(e.target.value)} />
            </label>
          </div>
          <p className="meta">Isi 0 bila jenis asesmen tidak ikut digenerate (bisa digenerate susulan per jenis dari halaman hasil).</p>
        </div>
        <div className="form__actions">
          <button type="submit" id="btn-konteks" className="btn btn--aksi" disabled={cekBerjalan}>Cek CP</button>
        </div>
      </form>
      <div id="panel-cp" className="panel-cp" hidden={!cpTerlihat}>
        <h3>Capaian Pembelajaran (dari data resmi)</h3>
        <p className="lede">CP cocok. Langkah berikutnya: periksa lalu Generate RPM di bawah.</p>
        {cpDaftar.length > 1 ? (
          cpDaftar.map((c, i) => (
            <div key={(c.id || 'cp') + '-' + i} className="panel-cp__item">
              <p className="meta">[CP-{i + 1}] {c.element || ''}{c.source_page ? ' · dokumen hal. ' + String(c.source_page) : ''}</p>
              <blockquote id={'cp-teks-' + (i + 1)}>{c.text || 'CP tidak tersedia.'}</blockquote>
            </div>
          ))
        ) : (
          <>
            <blockquote id="cp-teks">{cp?.text || 'CP tidak tersedia.'}</blockquote>
            <p id="cp-meta" className="meta">{cpMeta}</p>
          </>
        )}
        <div className="form__actions">
          <button type="button" id="btn-generate" className="btn btn--aksi" disabled={genBerjalan} onClick={() => onGenerate()}>Generate RPM</button>
        </div>
      </div>
      {peringatan && (
        <div
          className="overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPeringatan(null);
          }}
        >
          <div ref={peringatanDialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="judul-relevansi" tabIndex={-1}>
            <h2 id="judul-relevansi">Periksa kembali pilihan elemen</h2>
            <p className="lede dialog__sub">Topik kurang relevan dengan elemen berikut:</p>
            <ul>
              {peringatan.relevansi
                .filter((r) => r.nilai !== 'RELEVAN')
                .map((r) => (
                  <li key={r.elemen}>
                    <strong>{r.elemen}</strong>
                    {r.alasan ? ' — ' + r.alasan : ''}
                  </li>
                ))}
            </ul>
            {peringatan.saran && (
              <p className="lede">{peringatan.saran}</p>
            )}
            <div className="form__actions">
              <button
                type="button"
                className="btn"
                onClick={() => setPeringatan(null)}
              >
                Ubah pilihan
              </button>
              <button
                type="button"
                className="btn btn--aksi"
                disabled={genBerjalan}
                onClick={() => {
                  setPeringatan(null);
                  onGenerate(true);
                }}
              >
                Tetap lanjutkan
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
