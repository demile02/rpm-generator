import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { useAlerts, useLoading } from '../state/appContext';
import { useSession } from '../state/session';
import { pesanError, type RpmModule } from '../types';

/* Editor manual. Port masukEdit + kumpulkanChanges + simpanVersi:
   state form lokal per seksi, diff saat simpan, candidate bila ada draft. */

interface TpEdit {
  id: string;
  text: string;
}

interface KktpEdit {
  id: string;
  criteria: string[];
  cognitive_level?: string;
}

function linesOf(s: string): string[] {
  return String(s ?? '')
    .split('\n')
    .map((x) => x.trim())
    .filter((x) => x);
}

function asRec(v: unknown): Record<string, unknown> {
  return (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
}

function asArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function esc(v: unknown): string {
  return String(v == null ? '' : v);
}

interface EditorState {
  tp: TpEdit[];
  kktp: KktpEdit[];
  topic: string;
  readiness: string;
  matSummary: string;
  matPrasyarat: string;
  matMiskonsepsi: string;
  euCore: string;
  euRel: string;
  euApp: string;
  euVal: string;
  aktivitas: Record<string, unknown>[];
  reflStudent: string;
  reflTeacher: string;
  asmDiag: Record<string, unknown>[];
  asmForm: Record<string, unknown>[];
  asmSum: Record<string, unknown>[];
  rubrik: Record<string, string>;
  lkpd: Record<string, unknown>[];
  glosarium: { istilah: string; definisi: string }[];
  metaPenyusun: string;
  metaSatuan: string;
  metaSemester: string;
  metaYear: string;
  metaFacilities: string;
}

function initFromModule(m: RpmModule): EditorState {
  const los = asArr(m.learning_objectives);
  const scs = asArr(m.success_criteria);
  const mc = asRec(m.material_characteristics);
  const eu = asRec(m.essential_understanding);
  const reflOld: Record<string, string[]> = {};
  asArr(m.reflection).forEach((r) => {
    const rr = asRec(r);
    if (typeof rr.role === 'string') reflOld[rr.role] = asArr(rr.questions).map(esc);
  });
  const asm = asRec(m.assessments);
  const normItems = (b: unknown): Record<string, unknown>[] => {
    let arr: unknown[] = b as unknown[];
    if (b && !Array.isArray(b)) arr = asArr(asRec(b).items);
    return (arr || []).map((it) => ({ ...(asRec(it)) }));
  };
  const summ = asRec(asm.summative);
  const desc = asRec(asm.rubric_descriptors);
  const rubrik: Record<string, string> = {};
  Object.keys(desc).forEach((k) => {
    rubrik[k] = asArr(desc[k]).map(esc).join('\n');
  });
  const ident = asRec(m.module_identity);
  const semRaw = m.semester !== undefined && m.semester !== null ? m.semester : ident.semester;
  return {
    tp: los.map((t) => {
      const r = asRec(t);
      return { id: esc(r.id), text: esc(r.text) };
    }),
    kktp: scs.map((k) => {
      const r = asRec(k);
      return {
        id: esc(r.id),
        criteria: asArr(r.criteria).map(esc),
        cognitive_level: typeof r.cognitive_level === 'string' ? r.cognitive_level : undefined,
      };
    }),
    topic: esc(m.topic || ''),
    readiness: esc(m.student_readiness || ''),
    matSummary: esc(mc.summary || ''),
    matPrasyarat: asArr(mc.prerequisites).map(esc).join('\n'),
    matMiskonsepsi: asArr(mc.potential_misconceptions).map(esc).join('\n'),
    euCore: esc(eu.core_insight || ''),
    euRel: esc(eu.relationship || ''),
    euApp: esc(eu.application || ''),
    euVal: esc(eu.value || ''),
    aktivitas: asArr(m.learning_activities).map((a) => ({ ...(asRec(a)) })),
    reflStudent: (reflOld.student || []).join('\n'),
    reflTeacher: (reflOld.teacher || []).join('\n'),
    asmDiag: normItems(asm.diagnostic),
    asmForm: normItems(asm.formative),
    asmSum: normItems(summ.items),
    rubrik,
    lkpd: asArr(m.lkpd).map((l) => ({ ...(asRec(l)) })),
    glosarium: asArr(m.glosarium).map((g) => {
      const r = asRec(g);
      return { istilah: esc(r.istilah || ''), definisi: esc(r.definisi || '') };
    }),
    metaPenyusun: esc(m.penyusun || ''),
    metaSatuan: esc(m.satuan_pendidikan || ident.satuan_pendidikan || ''),
    metaSemester: semRaw === null || semRaw === undefined ? '' : String(semRaw),
    metaYear: esc(m.year || ident.year || ''),
    metaFacilities: asArr(m.facilities).map(esc).join('\n'),
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="field">
      {label}
      {hint ? <span className="field__cap field__cap--opsional"> {hint}</span> : null}
      {children}
    </label>
  );
}

interface AktivitasEditorSectionProps {
  aktivitas: Record<string, unknown>[];
  tpOpts: string[];
  onChange: (index: number, patch: Record<string, unknown>) => void;
  onDirty: () => void;
}

const AktivitasEditorSection = memo(function AktivitasEditorSection({
  aktivitas,
  tpOpts,
  onChange,
  onDirty,
}: AktivitasEditorSectionProps) {
  return (
    <section aria-label="Aktivitas">
      <h3>Aktivitas pembelajaran</h3>
      {aktivitas.map((a, i) => {
        const r = asRec(a);
        return (
          <div key={i}>
            <h4>{esc(r.id || 'ACT-' + i)}</h4>
            <Field label="Nama">
              <input type="text" value={esc(r.name || '')} onChange={(e) => { onChange(i, { name: e.target.value }); onDirty(); }} />
            </Field>
            <Field label="Deskripsi">
              <textarea rows={2} value={esc(r.description || '')} onChange={(e) => { onChange(i, { description: e.target.value }); onDirty(); }} />
            </Field>
            <Field label="Durasi (menit)">
              <input type="number" min="0" value={esc(r.duration ?? '')} onChange={(e) => { onChange(i, { duration: e.target.value }); onDirty(); }} />
            </Field>
            <Field label="Tahap">
              <select value={esc(r.stage || '')} onChange={(e) => { onChange(i, { stage: e.target.value }); onDirty(); }}>
                {['Pembuka', 'Inti', 'Penutup'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Pengalaman">
              <select value={esc(r.experience || '')} onChange={(e) => { onChange(i, { experience: e.target.value }); onDirty(); }}>
                {['memahami', 'mengaplikasi', 'merefleksi'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Pertemuan">
              <input type="number" min="0" value={esc(r.meeting ?? '')} onChange={(e) => { onChange(i, { meeting: e.target.value }); onDirty(); }} />
            </Field>
            <Field label="TP terkait">
              <select value={esc(r.tp_linked || '')} onChange={(e) => { onChange(i, { tp_linked: e.target.value }); onDirty(); }}>
                {tpOpts.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
          </div>
        );
      })}
    </section>
  );
});

interface AsesmenEditorBucket {
  label: string;
  key: 'asmDiag' | 'asmForm' | 'asmSum';
  items: Record<string, unknown>[];
}

interface AsesmenEditorSectionProps {
  buckets: AsesmenEditorBucket[];
  tpOpts: string[];
  onChange: (bucket: 'asmDiag' | 'asmForm' | 'asmSum', index: number, patch: Record<string, unknown>) => void;
  onDirty: () => void;
}

const AsesmenEditorSection = memo(function AsesmenEditorSection({
  buckets,
  tpOpts,
  onChange,
  onDirty,
}: AsesmenEditorSectionProps) {
  return (
    <section aria-label="Asesmen">
      <h3>Asesmen</h3>
      {buckets.map(({ label, key, items }) => (
        <div key={key}>
          <h4>{label}</h4>
          {items.map((it, i) => {
            const r = asRec(it);
            return (
              <div key={i}>
                <Field label={'Soal ' + (i + 1)}>
                  <textarea rows={2} value={esc(r.question || '')} onChange={(e) => { onChange(key, i, { question: e.target.value }); onDirty(); }} />
                </Field>
                <Field label="Tipe">
                  <input type="text" value={esc(r.type || '')} onChange={(e) => { onChange(key, i, { type: e.target.value }); onDirty(); }} />
                </Field>
                <Field label="TP">
                  <select value={esc(r.tp_linked || '')} onChange={(e) => { onChange(key, i, { tp_linked: e.target.value }); onDirty(); }}>
                    {tpOpts.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </Field>
              </div>
            );
          })}
        </div>
      ))}
    </section>
  );
});

export function Editor({ onDone }: { onDone: () => void }) {
  const { tampilAlert } = useAlerts();
  const { tampilLoading, sembunyiLoading } = useLoading();
  const session = useSession();
  const { module, generationId, version, draftChanges, setDirty } = session;
  const markDirty = useCallback(() => setDirty(true), [setDirty]);

  const [st, setSt] = useState<EditorState>(() => initFromModule(module ?? {}));
  const [glosTouched, setGlosTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  // Sinkron sekali saat modul berganti (mis. lihat versi / regen).
  // Via effect agar tidak setState saat render (StrictMode aman).
  const lastMod = useRef<RpmModule | null>(module);
  useEffect(() => {
    if (module !== lastMod.current) {
      lastMod.current = module;
      setSt(initFromModule(module ?? {}));
      setGlosTouched(false);
    }
  }, [module]);

  const m = module ?? {};
  const tpOpts = useMemo(
    () => asArr(m.learning_objectives).map((t) => esc(asRec(t).id)).filter((x) => x),
    [m.learning_objectives],
  );

  const set = <K extends keyof EditorState>(k: K, v: EditorState[K]) =>
    setSt((s) => (s ? { ...s, [k]: v } : s));

  const setAktivitas = useCallback((i: number, patch: Record<string, unknown>) => {
    setSt((s) => {
      if (!s) return s;
      const nx = s.aktivitas.map((a, j) => (j === i ? { ...a, ...patch } : a));
      return { ...s, aktivitas: nx };
    });
  }, []);

  const setAsm = useCallback((bucket: 'asmDiag' | 'asmForm' | 'asmSum', i: number, patch: Record<string, unknown>) => {
    setSt((s) => {
      if (!s) return s;
      const nx = s[bucket].map((a, j) => (j === i ? { ...a, ...patch } : a));
      return { ...s, [bucket]: nx };
    });
  }, []);

  const asesmenBuckets = useMemo(() => [
    { label: 'Awal', key: 'asmDiag' as const, items: st.asmDiag },
    { label: 'Proses', key: 'asmForm' as const, items: st.asmForm },
    { label: 'Akhir', key: 'asmSum' as const, items: st.asmSum },
  ], [st.asmDiag, st.asmForm, st.asmSum]);

  if (!module) return null;

  function same(a: unknown, b: unknown): boolean {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function kumpulkanChanges(): Record<string, unknown> {
    const changes: Record<string, unknown> = {};
    const los = asArr(m.learning_objectives);
    const tpNew = st.tp.map((t, i) => ({
      id: t.id || esc(asRec(los[i]).id),
      text: t.text,
    }));
    if (!same(tpNew.map((t) => t.text), los.map((t) => esc(asRec(t).text)))) {
      changes.tp = tpNew;
    }
    const scs = asArr(m.success_criteria);
    const kkNew = st.kktp.map((k, i) => {
      const old = asRec(scs[i]);
      return {
        id: k.id || esc(old.id),
        criteria: k.criteria,
        cognitive_level: k.cognitive_level ?? old.cognitive_level,
      };
    });
    if (!same(kkNew.map((k) => k.criteria), scs.map((k) => asArr(asRec(k).criteria).map(esc)))) {
      changes.kktp = kkNew;
    }
    if (st.topic.trim() !== esc(m.topic || '')) changes.topic = st.topic;
    if (st.readiness !== esc(m.student_readiness || '')) {
      changes.readiness = { student_readiness: st.readiness };
    }
    const mc = asRec(m.material_characteristics);
    const matNew = {
      summary: st.matSummary,
      prerequisites: linesOf(st.matPrasyarat),
      potential_misconceptions: linesOf(st.matMiskonsepsi),
    };
    if (
      !same(matNew, {
        summary: esc(mc.summary || ''),
        prerequisites: asArr(mc.prerequisites).map(esc),
        potential_misconceptions: asArr(mc.potential_misconceptions).map(esc),
      })
    ) {
      changes.material = matNew;
    }
    const eu = asRec(m.essential_understanding);
    const euNew = {
      core_insight: st.euCore,
      relationship: st.euRel,
      application: st.euApp,
      value: st.euVal,
    };
    if (
      !same(euNew, {
        core_insight: esc(eu.core_insight || ''),
        relationship: esc(eu.relationship || ''),
        application: esc(eu.application || ''),
        value: esc(eu.value || ''),
      })
    ) {
      changes.materi = euNew;
    }
    const actsOld = asArr(m.learning_activities).map((a) => ({ ...asRec(a) }));
    const actsNew = st.aktivitas.map((a) => {
      const r = asRec(a);
      return {
        ...r,
        duration: Number(r.duration),
        meeting: Number(r.meeting),
      };
    });
    if (!same(actsNew, actsOld)) changes.aktivitas = actsNew;
    const reflOld: Record<string, string[]> = {};
    asArr(m.reflection).forEach((r) => {
      const rr = asRec(r);
      if (typeof rr.role === 'string') reflOld[rr.role] = asArr(rr.questions).map(esc);
    });
    const reflNew = { student: linesOf(st.reflStudent), teacher: linesOf(st.reflTeacher) };
    if (!same(reflNew, { student: reflOld.student || [], teacher: reflOld.teacher || [] })) {
      changes.refleksi = reflNew;
    }
    const asm = asRec(m.assessments);
    const bucketShape = (items: Record<string, unknown>[]) =>
      items.map((it) => {
        const out: Record<string, unknown> = {
          question: it.question,
          type: it.type,
        };
        (['tp_linked', 'kktp_linked', 'points'] as const).forEach((k) => {
          if (it[k] !== undefined) out[k] = it[k];
        });
        Object.keys(it).forEach((k) => {
          if (!(k in out)) out[k] = it[k];
        });
        return out;
      });
    const summ = asRec(asm.summative);
    const normOld = (b: unknown): Record<string, unknown>[] => {
      let arr: unknown[] = b as unknown[];
      if (b && !Array.isArray(b)) arr = asArr(asRec(b).items);
      return (arr || []).map((it) => ({ ...(asRec(it)) }));
    };
    const asmNew = {
      diagnostic: bucketShape(st.asmDiag),
      formative: bucketShape(st.asmForm),
      summative: { items: bucketShape(st.asmSum), rubric: summ.rubric },
    };
    const asmOld = {
      diagnostic: bucketShape(normOld(asm.diagnostic)),
      formative: bucketShape(normOld(asm.formative)),
      summative: { items: bucketShape(normOld(summ.items)), rubric: summ.rubric },
    };
    if (!same(asmNew, asmOld)) changes.asesmen = asmNew;
    const descOld = asRec(asm.rubric_descriptors);
    const descNew: Record<string, string[]> = {};
    Object.keys(descOld).forEach((k) => {
      descNew[k] = st.rubrik[k] !== undefined ? linesOf(st.rubrik[k]) : asArr(descOld[k]).map(esc);
    });
    if (!same(descNew, Object.fromEntries(Object.keys(descOld).map((k) => [k, asArr(descOld[k]).map(esc)])))) {
      changes.rubrik = { descriptors: descNew };
    }
    const lkOld = asArr(m.lkpd).map((l) => ({ ...asRec(l) }));
    const lkNew = st.lkpd.map((l) => ({ ...asRec(l) }));
    if (!same(lkNew, lkOld)) {
      changes.lkpd = lkNew;
    }
    if (glosTouched || st.glosarium.length !== asArr(m.glosarium).length) {
      const glosOld = asArr(m.glosarium).map((g) => ({
        istilah: esc(asRec(g).istilah || ''),
        definisi: esc(asRec(g).definisi || ''),
      }));
      if (!same(st.glosarium, glosOld)) changes.glosarium = st.glosarium;
    }
    const ident = asRec(m.module_identity);
    const metaNew = {
      penyusun: st.metaPenyusun,
      satuan_pendidikan: st.metaSatuan,
      semester: st.metaSemester === '' ? null : st.metaSemester,
      year: st.metaYear,
      facilities: linesOf(st.metaFacilities),
    };
    const metaOldSem =
      m.semester !== undefined && m.semester !== null
        ? String(m.semester)
        : ident.semester !== undefined && ident.semester !== null
          ? String(ident.semester)
          : null;
    const metaOld = {
      penyusun: esc(m.penyusun || ident.penyusun || ''),
      satuan_pendidikan: esc(m.satuan_pendidikan || ident.satuan_pendidikan || ''),
      semester: metaOldSem === null ? null : String(metaOldSem),
      year: esc(m.year || ident.year || ''),
      facilities: asArr(m.facilities).map(esc),
    };
    if (
      !same(metaNew, {
        penyusun: metaOld.penyusun,
        satuan_pendidikan: metaOld.satuan_pendidikan,
        semester: metaOld.semester,
        year: metaOld.year,
        facilities: metaOld.facilities,
      })
    ) {
      const out = { ...metaNew };
      if (out.semester !== null) out.semester = Number(out.semester) as unknown as string;
      changes.meta = out;
    }
    return changes;
  }

  async function simpan() {
    if (!generationId || version == null) {
      const p = 'Riwayat versi belum tersedia untuk sesi ini. Muat ulang halaman.';
      markDirty();
      tampilAlert('Belum bisa menyimpan', p);
      return;
    }
    const changes = kumpulkanChanges();
    const adaDraft = Object.keys(draftChanges || {}).length > 0;
    if (!Object.keys(changes).length && !adaDraft) {
      tampilAlert('Tidak ada perubahan', 'Tidak ada perubahan.');
      return;
    }
    const los = asArr(m.learning_objectives);
    const kosong: string[] = [];
    ((changes.tp || []) as { id?: string; text?: string }[]).forEach((t) => {
      if (!t.text || !String(t.text).trim()) {
        let nomor = '?';
        los.forEach((o, i) => {
          if (esc(asRec(o).id) === t.id) nomor = String(i + 1);
        });
        kosong.push('TP-' + nomor);
      }
    });
    if (kosong.length) {
      tampilAlert('TP masih kosong', kosong.join(', ') + ' masih kosong. Isi dulu sebelum menyimpan.');
      return;
    }
    setSaving(true);
    tampilLoading('Menyimpan perubahan', 'Memvalidasi TP, KKTP, langkah pembelajaran, dan asesmen…');
    try {
      const gunakanCandidate = Object.keys(draftChanges || {}).length > 0;
      const res = gunakanCandidate
        ? await api.saveCandidate(generationId, version, m, changes)
        : await api.saveVersion(generationId, version, changes);
      session.setDraftChanges({});
      session.terapkanVersi(res.version);
      if (generationId) {
        try {
          const lv = await api.listVersions(generationId);
          session.setVersionsState(lv.versions || []);
          const latest = lv.latest_version ?? null;
          if (latest != null) session.setVersion(latest);
        } catch {
          /* abaikan */
        }
      }
      const pesanSimpan = 'Tersimpan sebagai v' + res.version.version_no + ' (' + res.version.status + ').';
      sembunyiLoading();
      setSaving(false);
      tampilAlert('Perubahan tersimpan', pesanSimpan + ' Perubahan RPM telah divalidasi dan berhasil disimpan.');
      onDone();
    } catch (err) {
      setSaving(false);
      sembunyiLoading();
      const e = err as { status?: number; data?: unknown };
      if (e.status === 409) {
        tampilAlert('Versi basi', 'Versi basi: ' + pesanError(e.data) + ' Muat ulang versi terbaru.');
      } else {
        tampilAlert('Gagal menyimpan', 'Gagal menyimpan: ' + pesanError(e.data));
      }
    }
  }

  const cp = asRec(asRec(m.curriculum_context).cp);
  const cpFallback = esc(asRec(asRec(m.master_outline).design).cp || '');

  return (
    <div id="editor-isi" className="dokumen">
      <section aria-label="Terkunci">
        <h3>CP &amp; Provenance (terkunci, data regulasi)</h3>
        <blockquote>{esc(cp.text || cpFallback)}</blockquote>
        <p className="meta">
          Sumber: {esc(cp.source_document_id || '')}
          {cp.source_page ? ', hal. ' + esc(cp.source_page) : ''}
        </p>
      </section>
      <section aria-label="TP">
        <h3>Tujuan Pembelajaran</h3>
        {st.tp.map((t, i) => (
          <Field key={i} label={'TP-' + (i + 1) + ' (level otomatis)'}>
            <textarea
              rows={2}
              value={t.text}
              onChange={(e) => {
                const nx = st.tp.map((x, j) => (j === i ? { ...x, text: e.target.value } : x));
                set('tp', nx);
                markDirty();
              }}
            />
          </Field>
        ))}
      </section>
      <section aria-label="KKTP">
        <h3>Kriteria Ketercapaian</h3>
        {st.kktp.map((k, i) => (
          <div key={i}>
            <h4>{k.id}</h4>
            {k.criteria.map((c, j) => (
              <Field key={j} label={'Kriteria ' + (j + 1)}>
                <textarea
                  rows={2}
                  value={c}
                  onChange={(e) => {
                    const nx = st.kktp.map((x, a) =>
                      a === i
                        ? { ...x, criteria: x.criteria.map((cc, b) => (b === j ? e.target.value : cc)) }
                        : x,
                    );
                    set('kktp', nx);
                    markDirty();
                  }}
                />
              </Field>
            ))}
          </div>
        ))}
      </section>
      <section aria-label="Topik">
        <h3>Topik / Konteks</h3>
        <Field label="Topik">
          <input
            type="text"
            value={st.topic}
            onChange={(e) => {
              set('topic', e.target.value);
              markDirty();
            }}
          />
        </Field>
      </section>
      <section aria-label="Kesiapan">
        <h3>Kesiapan murid</h3>
        <Field label="Observasi guru">
          <textarea
            rows={3}
            value={st.readiness}
            onChange={(e) => {
              set('readiness', e.target.value);
              markDirty();
            }}
          />
        </Field>
      </section>
      <section aria-label="Materi">
        <h3>Karakteristik materi</h3>
        <Field label="Ringkasan">
          <textarea
            rows={3}
            value={st.matSummary}
            onChange={(e) => {
              set('matSummary', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Prasyarat (satu per baris)">
          <textarea
            rows={3}
            value={st.matPrasyarat}
            onChange={(e) => {
              set('matPrasyarat', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Potensi miskonsepsi (satu per baris)">
          <textarea
            rows={3}
            value={st.matMiskonsepsi}
            onChange={(e) => {
              set('matMiskonsepsi', e.target.value);
              markDirty();
            }}
          />
        </Field>
      </section>
      <section aria-label="Pemahaman">
        <h3>Pemahaman bermakna</h3>
        {(
          [
            ['core_insight', 'euCore'],
            ['relationship', 'euRel'],
            ['application', 'euApp'],
            ['value', 'euVal'],
          ] as [string, 'euCore' | 'euRel' | 'euApp' | 'euVal'][]
        ).map(([label, key]) => (
          <Field key={label} label={label}>
            <textarea
              rows={2}
              value={st[key]}
              onChange={(e) => {
                set(key, e.target.value);
                markDirty();
              }}
            />
          </Field>
        ))}
      </section>
      <AktivitasEditorSection
        aktivitas={st.aktivitas}
        tpOpts={tpOpts}
        onChange={setAktivitas}
        onDirty={markDirty}
      />
      <section aria-label="Refleksi">
        <h3>Refleksi</h3>
        <Field label="Murid (satu per baris)">
          <textarea
            rows={3}
            value={st.reflStudent}
            onChange={(e) => {
              set('reflStudent', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Guru (satu per baris)">
          <textarea
            rows={3}
            value={st.reflTeacher}
            onChange={(e) => {
              set('reflTeacher', e.target.value);
              markDirty();
            }}
          />
        </Field>
      </section>
      <AsesmenEditorSection
        buckets={asesmenBuckets}
        tpOpts={tpOpts}
        onChange={setAsm}
        onDirty={markDirty}
      />
      <section aria-label="Rubrik">
        <h3>Deskriptor rubrik</h3>
        {Object.keys(st.rubrik).map((kid) => (
          <Field key={kid} label={kid + ' (satu per baris)'}>
            <textarea
              rows={3}
              value={st.rubrik[kid]}
              onChange={(e) => {
                setSt((s) => (s ? { ...s, rubrik: { ...s.rubrik, [kid]: e.target.value } } : s));
                markDirty();
              }}
            />
          </Field>
        ))}
      </section>
      <section aria-label="LKPD">
        <h3>LKPD</h3>
        {st.lkpd.map((l, i) => {
          const r = asRec(l);
          return (
            <div key={i}>
              <h4>{esc(r.id || 'LKPD-' + i)}</h4>
              <Field label="Judul">
                <input
                  type="text"
                  value={esc(r.title || '')}
                  onChange={(e) => {
                    setSt((s) =>
                      s ? { ...s, lkpd: s.lkpd.map((x, j) => (j === i ? { ...asRec(x), title: e.target.value } : x)) } : s,
                    );
                    markDirty();
                  }}
                />
              </Field>
              <Field label="Instruksi">
                <textarea
                  rows={2}
                  value={esc(r.instructions || '')}
                  onChange={(e) => {
                    setSt((s) =>
                      s
                        ? {
                            ...s,
                            lkpd: s.lkpd.map((x, j) =>
                              j === i ? { ...asRec(x), instructions: e.target.value } : x,
                            ),
                          }
                        : s,
                    );
                    markDirty();
                  }}
                />
              </Field>
              <Field label="Tugas">
                <textarea
                  rows={2}
                  value={esc(r.task || '')}
                  onChange={(e) => {
                    setSt((s) =>
                      s
                        ? {
                            ...s,
                            lkpd: s.lkpd.map((x, j) => (j === i ? { ...asRec(x), task: e.target.value } : x)),
                          }
                        : s,
                    );
                    markDirty();
                  }}
                />
              </Field>
            </div>
          );
        })}
      </section>
      <section aria-label="Glosarium">
        <h3>Glosarium</h3>
        <div id="glosarium-rows">
          {st.glosarium.map((g, i) => (
            <div key={i} data-glos-row={i}>
              <Field label="Istilah">
                <input
                  type="text"
                  value={g.istilah}
                  onChange={(e) => {
                    setSt((s) =>
                      s
                        ? {
                            ...s,
                            glosarium: s.glosarium.map((x, j) =>
                              j === i ? { ...x, istilah: e.target.value } : x,
                            ),
                          }
                        : s,
                    );
                    setGlosTouched(true);
                    markDirty();
                  }}
                />
              </Field>
              <Field label="Definisi">
                <textarea
                  rows={2}
                  value={g.definisi}
                  onChange={(e) => {
                    setSt((s) =>
                      s
                        ? {
                            ...s,
                            glosarium: s.glosarium.map((x, j) =>
                              j === i ? { ...x, definisi: e.target.value } : x,
                            ),
                          }
                        : s,
                    );
                    setGlosTouched(true);
                    markDirty();
                  }}
                />
              </Field>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setSt((s) =>
                    s ? { ...s, glosarium: s.glosarium.filter((_, j) => j !== i) } : s,
                  );
                  setGlosTouched(true);
                  markDirty();
                }}
              >
                Hapus
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setSt((s) => (s ? { ...s, glosarium: [...s.glosarium, { istilah: '', definisi: '' }] } : s));
            setGlosTouched(true);
            markDirty();
          }}
        >
          Tambah istilah
        </button>
      </section>
      <section aria-label="Metadata">
        <h3>Metadata</h3>
        <Field label="Penyusun">
          <input
            type="text"
            value={st.metaPenyusun}
            onChange={(e) => {
              set('metaPenyusun', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Satuan pendidikan">
          <input
            type="text"
            value={st.metaSatuan}
            onChange={(e) => {
              set('metaSatuan', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Semester">
          <select
            value={st.metaSemester}
            onChange={(e) => {
              set('metaSemester', e.target.value);
              markDirty();
            }}
          >
            <option value="">Kosongkan</option>
            <option value="1">1</option>
            <option value="2">2</option>
          </select>
        </Field>
        <Field label="Tahun ajaran">
          <input
            type="text"
            value={st.metaYear}
            onChange={(e) => {
              set('metaYear', e.target.value);
              markDirty();
            }}
          />
        </Field>
        <Field label="Fasilitas (satu per baris)">
          <textarea
            rows={2}
            value={st.metaFacilities}
            onChange={(e) => {
              set('metaFacilities', e.target.value);
              markDirty();
            }}
          />
        </Field>
      </section>
      <div className="form__actions">
        <button
          type="button"
          id="btn-simpan-versi"
          className={saving ? 'btn btn--aksi btn--busy' : 'btn btn--aksi'}
          disabled={saving}
          onClick={() => void simpan()}
        >
          Simpan
        </button>
      </div>
    </div>
  );
}
