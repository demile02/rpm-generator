import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (name) => fs.readFileSync(path.join(root, 'src', name), 'utf8');

const hasil = read('screens/Hasil.tsx');
const log = read('components/LogDialog.tsx');
const app = read('App.tsx');
const css = fs.readFileSync(path.join(root, 'src', 'index.css'), 'utf8');
const api = read('api.ts');
const focus = read('lib/dialogFocus.ts');
const editor = read('screens/Editor.tsx');
const polling = read('lib/uploadPolling.ts');
const formulir = read('screens/Formulir.tsx');

// Regresi data-loss: editor must spread complete records before changing fields.
assert.match(editor, /const actsOld = asArr\(m\.learning_activities\)\.map\(\(a\) => \(\{ \.\.\.asRec\(a\) \}\)\)/);
assert.match(editor, /const lkNew = st\.lkpd\.map\(\(l\) => \(\{ \.\.\.asRec\(l\) \}\)\)/);

// Regresi navigation/state: dirty guard, deep-link restoration, and version gate.
assert.match(app, /tinggalkan\(\)/);
assert.match(hasil, /versiMemuat/);
assert.match(hasil, /anchor\.startsWith\('#a-'\)/);

// Performance regression: route changes must not force an extra remount.
assert.doesNotMatch(app, /layarKey|setLayarKey/);
assert.doesNotMatch(app, /key=\{['"](?:beranda|arsip|formulir)-/);

// Performance regression: heavy editor collections stay memoized by section.
assert.match(editor, /const AktivitasEditorSection = memo\(/);
assert.match(editor, /const AsesmenEditorSection = memo\(/);
assert.match(editor, /const lastMod = useRef<[^>]+>\(module\)/);
assert.doesNotMatch(editor, /const \[lastMod, setLastMod\] = useState/);

// Regresi request race and modal keyboard accessibility.
assert.match(log, /detailRequestRef/);
assert.match(focus, /event\.key === 'Escape'/);
assert.match(focus, /FOCUSABLE/);

// Regresi upload hang: abort signal, bounded polling, and timeout remain wired.
assert.match(api, /signal\?: AbortSignal/);
assert.match(api, /UPLOAD_POLL_MAX_ATTEMPTS/);
assert.match(api, /UPLOAD_POLL_TIMEOUT/);
assert.match(polling, /UPLOAD_POLL_TIMEOUT_MS/);

// Regresi scroll bottleneck: handler schedules one animation frame.
assert.match(formulir, /requestAnimationFrame\(hitungSekarang\)/);

// Curriculum options load compactly; CP elements load on demand by subject/phase.
assert.match(formulir, /getCurriculumOptions\(true, controller\.signal\)/);
assert.match(formulir, /getCurriculumElements\(mapel, fase, sistem, institusi, controller\.signal\)/);
assert.match(api, /\/api\/curriculum\/elements\?/);
assert.match(formulir, /Boolean\(mapel && faseDraft\) && !elemenReady/);

// Mapel filter per kelas: fetch by grade, tampil uppercase, reset saat kelas ganti.
assert.match(formulir, /getCurriculumSubjects\(sistem, institusi, kelas, controller\.signal\)/);
assert.match(formulir, /daftarMapelTampil/);
assert.match(formulir, /\.toUpperCase\(\)/);
assert.match(formulir, /id="f-mapel-daftar"/);
assert.match(formulir, /setMapel\(''\)/);
assert.doesNotMatch(formulir, /daftarMapel = \(options/);

// Mobile swipe must transform only inner content stage, never the main shell.
assert.match(app, /getElementById\('swipe-stage'\)/);
assert.doesNotMatch(app, /const el = document\.getElementById\('konten'\)/);
assert.match(app, /<div id="swipe-stage" className="swipe-stage">/);
assert.doesNotMatch(app, /masukRef|translateX\(0\)/);
assert.match(css, /\.tabbar[\s\S]*position: fixed/);
assert.match(css, /\.tabbar[\s\S]*inset: auto 0 0/);

console.log('FRONTEND BUG REGRESSIONS PASS');
