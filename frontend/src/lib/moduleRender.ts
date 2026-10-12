/* Port ui/render.js ke TypeScript terstruktur (bukan HTML string).
   Merender module master_outline menjadi bagian A–E + glosarium.
   Aturan sama: bagian kosong tidak ditampilkan, tanpa total buatan. */
import type { RpmModule } from '../types';

function esc(v: unknown): string {
  return String(v == null ? '' : v);
}

export function friendlyGrade(grade: unknown): string {
  const g = String(grade == null ? '' : grade);
  const i = g.indexOf('_');
  if (i === -1) return g;
  const tail = g.slice(i + 1).replace(/_/g, ' ').trim();
  return tail || g;
}

export function friendlySemester(sem: unknown): string {
  const s = String(sem == null ? '' : sem).toLowerCase();
  if (s === '1' || s === 'ganjil') return 'Ganjil';
  if (s === '2' || s === 'genap') return 'Genap';
  return String(sem == null ? '' : sem);
}

const TYPE_LABELS: Record<string, string> = {
  multiple_choice: 'Pilihan Ganda',
  short_answer: 'Isian',
  essay: 'Uraian',
  true_false: 'Benar/Salah',
  matching: 'Menjodohkan',
  performance_task: 'Unjuk Kerja',
  performance_assessment: 'Unjuk Kerja',
  performance: 'Unjuk Kerja',
  oral_reading: 'Membaca Nyaring',
};

export function typeLabel(t: unknown): string {
  const s = String(t == null ? '' : t).trim();
  return TYPE_LABELS[s] || s;
}

export interface McOption {
  label: string;
  text: string;
}

function inlineMcOptions(question: string): { stem: string; options: McOption[] } {
  const matches = [...question.matchAll(/(?:^|\s)([A-D])\.\s*/g)];
  const start = matches.findIndex((m) => m[1] === 'A');
  if (start < 0) return { stem: question, options: [] };
  const selected: RegExpMatchArray[] = [];
  let expected = 'A';
  for (const match of matches.slice(start)) {
    if (match[1] !== expected) continue;
    selected.push(match);
    expected = String.fromCharCode(expected.charCodeAt(0) + 1);
    if (expected > 'D') break;
  }
  if (selected.length < 2) return { stem: question, options: [] };
  const options: McOption[] = selected.map((match, i) => {
    const from = (match.index ?? 0) + match[0].length;
    const to = i + 1 < selected.length
      ? (selected[i + 1].index ?? question.length)
      : question.length;
    return { label: match[1], text: question.slice(from, to).trim() };
  });
  return {
    stem: question.slice(0, selected[0].index ?? 0).trim(),
    options,
  };
}

export function mcOptions(item: unknown): McOption[] {
  const it = item as { options?: unknown; question?: unknown } | null;
  const explicit = Array.isArray(it?.options) ? it.options : [];
  const inline = inlineMcOptions(String(it?.question ?? '')).options;
  const out: McOption[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < explicit.length; i++) {
    const opt = explicit[i] as { label?: unknown; text?: unknown; option?: unknown } | string;
    const label = opt && typeof opt === 'object'
      ? String(opt.label || String.fromCharCode(65 + i)).toUpperCase()
      : String.fromCharCode(65 + i);
    const text = opt && typeof opt === 'object'
      ? String(opt.text !== undefined ? opt.text : opt.option ?? '')
      : String(opt);
    if (text.trim() && !seen.has(label)) {
      out.push({ label, text: text.trim() });
      seen.add(label);
    }
  }
  // Import lama dapat menyimpan opsi di question sekaligus options.
  // Opsi inline menang pada label sama; sumber eksplisit melengkapi label hilang.
  if (inline.length >= 2) {
    const merged: McOption[] = [];
    const mergedLabels = new Set<string>();
    for (const opt of [...inline, ...out]) {
      if (!mergedLabels.has(opt.label)) {
        merged.push(opt);
        mergedLabels.add(opt.label);
      }
    }
    return merged;
  }
  return out;
}

export function mcQuestion(item: unknown): string {
  const it = item as { question?: unknown } | null;
  const question = String(it?.question ?? '');
  return inlineMcOptions(question).stem;
}

/* Jawaban diagnostik: label saja, tanpa teks jawaban (sama persis
   docx_renderer._answer_label). */
export function answerLabel(item: unknown): string {
  if (!item || typeof item !== 'object') return '';
  const rec = item as Record<string, unknown>;
  let raw = '';
  for (const k of ['correct_answer', 'answer_key', 'answer']) {
    const v = rec[k];
    if (typeof v === 'string' && v.trim()) {
      raw = v.trim();
      break;
    }
    if (Array.isArray(v) && v.length) {
      raw = String(v[0]).trim();
      break;
    }
  }
  if (!raw) return '';
  const opts = mcOptions(item);
  const labels = opts.map((o) => o.label);
  if (raw.length === 1 && labels.indexOf(raw.toUpperCase()) !== -1) return raw.toUpperCase();
  const first = raw.split('.', 1)[0].trim().toUpperCase();
  if (first.length === 1 && labels.indexOf(first) !== -1) return first;
  for (const o of opts) {
    if (String(o.text).trim().toLowerCase() === raw.toLowerCase()) return o.label;
  }
  return raw;
}

export interface IdentityRow {
  label: string;
  value: string;
}

export interface TpRow {
  id: string;
  text: string;
  level: string;
}

export interface KktpItem {
  id: string;
  criteria: string[];
}

export interface MeetingActivity {
  name: string;
  description: string;
  duration: string;
  tp: string;
  experience: string;
}

export interface Meeting {
  index: string;
  jp: string;
  minutes: string;
  pembuka: MeetingActivity[];
  inti: MeetingActivity[];
  penutup: MeetingActivity[];
  principles: { label: string; text: string }[];
}

export interface AssessItem {
  raw: Record<string, unknown>;
  question: string;
  type: string;
  tp: string;
  kktp: string;
  answer: string;
  options: McOption[];
}

export interface KbcPair {
  theme: string | null;
  text: string | null;
}

export interface RenderedSections {
  identitas: IdentityRow[];
  kesiapanSummary: string;
  kesiapanAspects: string[];
  materiSummary: string;
  dims: { name: string; note: string }[];
  kbcPairs: KbcPair[];
  cp: string;
  sumberLine: string;
  tpRows: TpRow[];
  kktp: KktpItem[];
  practices: string[];
  meetings: Meeting[];
  fallbackExperiences: { nama: string; rows: { name: string; desc: string; dur: string; tp: string }[] }[];
  diagnostik: AssessItem[];
  formatif: AssessItem[];
  sumatif: AssessItem[];
  glosarium: { istilah: string; definisi: string }[];
  topic: string;
  toc: { id: string; banner: string }[];
}

function asRec(v: unknown): Record<string, unknown> {
  return (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
}

function asArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

export function renderModuleParts(module: RpmModule): RenderedSections {
  const outline = asRec(module.master_outline);
  const general = asRec(outline.general_information);
  const toc: { id: string; banner: string }[] = [];

  // ---- A. Identitas ----
  const ident = asRec(module.module_identity);
  const meetings = asArr(module.meetings) as Record<string, unknown>[];
  let alokasi = '';
  if (meetings.length) {
    const totalJp = meetings.reduce((s, m) => s + (Number(m.jp) || 0), 0);
    const seragam =
      meetings.length > 0 &&
      meetings.every((m) => Number(m.jp) === Number(meetings[0].jp));
    alokasi = seragam
      ? `${totalJp} JP (${meetings.length} Pertemuan x ${String(meetings[0].jp)} JP)`
      : `${totalJp} JP (${meetings.length} Pertemuan)`;
  }
  const kelasFase = [friendlyGrade(module.grade), esc(module.phase), friendlySemester(ident.semester)]
    .filter((v) => v)
    .join('/');
  const namaLabel =
    asRec(module.curriculum_context).education_system === 'KEMENAG'
      ? 'Nama Madrasah'
      : 'Nama Sekolah';
  const idRows: IdentityRow[] = (
    [
      [namaLabel, ident.satuan_pendidikan],
      ['Nama Penyusun', module.penyusun],
      ['Mata Pelajaran', module.subject],
      ['Kelas / Fase /Semester', kelasFase],
      ['Alokasi Waktu', alokasi],
      ['Tahun Pelajaran', ident.year],
    ] as [string, unknown][]
  )
    .filter((r) => r[1])
    .map((r) => ({ label: r[0], value: esc(r[1]) }));
  if (idRows.length) toc.push({ id: 'a-identitas', banner: 'A. IDENTITAS MODUL' });

  // ---- B. Identifikasi ----
  const identifikasi = asRec(outline.identification);
  const kesiapan = asRec(identifikasi.learner_readiness);
  const materi = asRec(identifikasi.material_characteristics);
  const kesiapanSummary = esc(kesiapan.summary || kesiapan.note || 'Belum ada data kesiapan.');
  const kesiapanAspects = asArr(kesiapan.aspects).map(esc);
  const materiSummary = esc(materi.summary || 'Belum ada ringkasan.');
  const dimsRaw = asArr(identifikasi.profile_dimensions);
  const dimNotes = asRec(identifikasi.profile_dimension_notes);
  const dims = dimsRaw.map((d) => ({
    name: esc(d),
    note: typeof dimNotes[esc(d)] === 'string' ? (dimNotes[esc(d)] as string) : '',
  }));
  // KBC berpasangan persis docx_renderer.pair_kbc_items
  const kbcB = asRec(general.kbc);
  const kbcThemes = asArr(kbcB.themes).map(String).filter((t) => t.trim());
  let kbcRaw: unknown[];
  if ('insertions' in kbcB) {
    kbcRaw = asArr(kbcB.insertions).filter(
      (ins) => ins && typeof ins === 'object' && (ins as Record<string, unknown>).active &&
        String((ins as Record<string, unknown>).text || '').trim(),
    );
  } else {
    kbcRaw = asArr(kbcB.insertion_material);
  }
  const kbcUnits: { text: string; tema: string | null }[] = [];
  kbcRaw.forEach((ins) => {
    if (ins && typeof ins === 'object') {
      const r = ins as Record<string, unknown>;
      const tema = typeof r.tema === 'string' && r.tema.trim() ? r.tema : null;
      kbcUnits.push({ text: String(r.text || '').trim(), tema });
    } else if (String(ins || '').trim()) {
      kbcUnits.push({ text: String(ins).trim(), tema: null });
    }
  });
  const units = kbcUnits.filter((u) => u.text);
  const kbcPairs: KbcPair[] = [];
  const used: Record<number, boolean> = {};
  const anyTema = units.some((u) => u.tema);
  kbcThemes.forEach((theme, pos) => {
    let idx: number | null = null;
    if (anyTema) {
      for (let i = 0; i < units.length; i++) {
        if (!used[i] && units[i].tema === theme) {
          idx = i;
          break;
        }
      }
    } else if (units.length === kbcThemes.length && !used[pos]) {
      idx = pos;
    }
    if (idx === null || idx === undefined) {
      kbcPairs.push({ theme, text: null });
    } else {
      used[idx] = true;
      kbcPairs.push({ theme, text: units[idx].text });
    }
  });
  units.forEach((u, i) => {
    if (!used[i]) kbcPairs.push({ theme: null, text: u.text });
  });
  const ctxB = asRec(module.curriculum_context);
  const showKbc = ctxB.education_system === 'KEMENAG' && kbcPairs.length > 0;
  toc.push({ id: 'b-identifikasi', banner: 'B. IDENTIFIKASI' });

  // ---- C. Desain ----
  const desain = asRec(outline.design);
  const tpRows: TpRow[] = asArr(desain.tp).map((t) => {
    const r = asRec(t);
    return { id: esc(r.id), text: esc(r.text), level: esc(r.cognitive_level) };
  });
  const kktp: KktpItem[] = asArr(desain.kktp).map((k) => {
    const r = asRec(k);
    return { id: esc(r.id), criteria: asArr(r.criteria).map(esc) };
  });
  const practices: string[] = asArr(desain.pedagogical_practices).map(esc);
  const prov = asRec(desain.cp_provenance);
  let sumberLine = '';
  if (prov.source_document_id) {
    sumberLine = 'Sumber: ' + esc(prov.source_document_id);
    if (prov.source_page !== undefined && prov.source_page !== null && String(prov.source_page).trim() !== '') {
      sumberLine += ', halaman ' + esc(prov.source_page);
    }
  }
  toc.push({ id: 'c-desain', banner: 'C. DESAIN PEMBELAJARAN' });

  // ---- D. Pengalaman ----
  const pengalaman = asRec(outline.learning_experience);
  const experiences = asRec(pengalaman.experiences);
  const outMeetings: Meeting[] = meetings.map((mtg) => {
    const stages = asRec(mtg.stages);
    const conv = (acts: unknown): MeetingActivity[] =>
      asArr(acts).map((a) => {
        const r = asRec(a);
        return {
          name: esc(r.name),
          description: esc(r.description),
          duration: esc(r.duration),
          tp: esc(r.tp_linked || r.tp_reference || ''),
          experience: esc(r.experience || ''),
        };
      });
    const pr = asRec(mtg.principles);
    const principles = (
      [
        ['Berkesadaran (Mindful Learning)', pr.berkesadaran],
        ['Bermakna (Meaningful Learning)', pr.bermakna],
        ['Menggembirakan (Joyful Learning)', pr.menggembirakan],
      ] as [string, unknown][]
    )
      .filter((p) => p[1])
      .map((p) => ({ label: p[0], text: esc(p[1]) }));
    return {
      index: esc(mtg.index),
      jp: esc(mtg.jp),
      minutes: esc(mtg.minutes),
      pembuka: conv(stages.Pembuka),
      inti: conv(stages.Inti),
      penutup: conv(stages.Penutup),
      principles,
    };
  });
  const fallbackExperiences: RenderedSections['fallbackExperiences'] = [];
  if (!meetings.length) {
    const urutan = ['memahami', 'mengaplikasi', 'merefleksi']
      .filter((k) => experiences[k])
      .concat(Object.keys(experiences).filter((k) => ['memahami', 'mengaplikasi', 'merefleksi'].indexOf(k) === -1));
    urutan.forEach((nama) => {
      const rows = asArr(experiences[nama]).map((a) => {
        const r = asRec(a);
        return {
          name: esc(r.name),
          desc: esc(r.description),
          dur: esc(r.duration),
          tp: esc(r.tp_linked || r.tp_reference || ''),
        };
      });
      fallbackExperiences.push({ nama, rows });
    });
  }
  toc.push({ id: 'd-pengalaman', banner: 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN' });

  // ---- E. Asesmen ----
  const asesmen = asRec(outline.assessment);
  const convAssess = (items: unknown, diagnostik: boolean): AssessItem[] => {
    let arr: unknown[] = items as unknown[];
    if (items && !Array.isArray(items)) arr = asArr((items as Record<string, unknown>).items);
    return (arr || []).map((it) => {
      const r = asRec(it);
      return {
        raw: r,
        question: diagnostik ? mcQuestion(it) : esc(r.question),
        type: typeLabel(r.type),
        tp: esc(r.tp_linked || ''),
        kktp: esc(r.kktp_linked || ''),
        answer: diagnostik ? answerLabel(it) : '',
        options: diagnostik ? mcOptions(it) : [],
      };
    });
  };
  const diagnostik = convAssess(asesmen.awal, true);
  const formatif = convAssess(asesmen.proses, false);
  const sumatif = convAssess(asesmen.akhir, false);
  toc.push({ id: 'e-asesmen', banner: 'E. ASESMEN' });

  // ---- G. Glosarium ----
  const glos = asArr(asRec(outline.attachments).glosarium);
  const glosarium = glos.map((g) => {
    const r = asRec(g);
    return { istilah: esc(r.istilah), definisi: esc(r.definisi) };
  });
  if (glosarium.length) toc.push({ id: 'glosarium', banner: 'G. Glosarium' });

  const topic = esc(module.topic || asRec(module.unit).name || desain.topic_context || '');

  return {
    identitas: idRows,
    kesiapanSummary,
    kesiapanAspects,
    materiSummary,
    dims,
    kbcPairs: showKbc ? kbcPairs : [],
    cp: esc(desain.cp || 'CP tidak tersedia.'),
    sumberLine,
    tpRows,
    kktp,
    practices,
    meetings: outMeetings,
    fallbackExperiences,
    diagnostik,
    formatif,
    sumatif,
    glosarium,
    topic,
    toc,
  };
}
