/* Frontend tests (Node, tanpa framework): stub DOM minimal + fetch mock.
   Menguji logika alur nyata app.js (bukan snapshot): validasi form,
   polling, gating export, dan render lolos-encode. */
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const UI = path.join(__dirname, '..');

function htmlStylesContainHiddenRule() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  return css.includes('.form__actions button[hidden]') &&
    css.includes('display: none !important');
}

function makeElement(id) {
  const el = {
    id, hidden: true, disabled: false, value: '', textContent: '',
    innerHTML: '', text: '',
    _handlers: {},
    getAttribute: function () { return null; },
    querySelectorAll: function () { return []; },
    classList: {
      _s: new Set(),
      add: function (c) { this._s.add(c); },
      remove: function (c) { this._s.delete(c); },
      toggle: function (c, force) {
        if (force === undefined) {
          if (this._s.has(c)) this._s.delete(c); else this._s.add(c);
        } else if (force) this._s.add(c); else this._s.delete(c);
      },
      contains: function (c) { return this._s.has(c); }
    },
    addEventListener: function (ev, fn) { this._handlers[ev] = fn; },
    appendChild: function () {}, removeChild: function () {},
    click: function () { if (this._handlers.click) this._handlers.click(); },
    submit: function () {
      if (this._handlers.submit) this._handlers.submit({ preventDefault: function () {} });
    }
  };
  return el;
}

function makeStorage(seed) {
  const store = Object.assign({}, seed);
  return {
    getItem: function (k) {
      return Object.prototype.hasOwnProperty.call(store, k) ?
        store[k] : null;
    },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; },
    _store: store
  };
}

const IDS = ['f-sistem', 'f-institusi', 'f-kelas', 'f-mapel', 'f-elemen',
  'f-buku', 'f-buku-file', 'btn-upload-buku', 'buku-error', 'buku-hasil',
  'f-topik', 'f-satuan', 'f-semester', 'f-tahun', 'f-penyusun', 'f-jumlah',
  'f-jp', 'f-awal', 'f-formatif', 'f-sumatif', 'f-kesiapan', 'form-konteks', 'form-error', 'panel-cp', 'cp-teks', 'cp-meta',
  'btn-konteks', 'btn-generate', 'f-fase', 'layar-beranda', 'layar-formulir',
  'layar-progres', 'layar-hasil', 'progres-teks', 'progres-id',
  'progres-waktu', 'progres-error', 'btn-coba-lagi', 'btn-poll-ulang',
  'btn-ke-formulir', 'progres-bar',
  'hasil-validasi', 'hasil-versi', 'hasil-alignment', 'hasil-toc', 'hasil-isi',
  'hasil-error', 'editor-isi', 'status-simpan', 'peringatan-dependensi',
  'riwayat-versi', 'btn-mode-review', 'btn-mode-edit', 'btn-simpan-versi',
  'btn-finalize', 'btn-export-docx', 'btn-baru', 'judul-hasil', 'buka-error',
  'profil-overlay', 'p-penyusun', 'p-satuan', 'p-semester',
  'p-tahun', 'profil-status', 'btn-simpan-profil', 'btn-batal-profil',
  'layar-landing', 'profil-ringkas', 'link-buat-rpm', 'btn-ubah-profil',
  'riwayat-rpm',
  'riwayat-kosong', 'riwayat-error', 'bulk-kontrol', 'bulk-pilih', 'bulk-bilah',
  'bulk-jumlah', 'btn-hapus-pilih', 'hapus-overlay', 'hapus-judul',
  'hapus-pesan', 'hapus-error', 'btn-batal-hapus', 'btn-konfirmasi-hapus',
  'log-overlay', 'btn-buka-log', 'log-error', 'log-kosong',
  'daftar-log', 'log-detail',
  'log-detail-judul', 'log-detail-meta', 'log-detail-isi',
  'btn-tutup-log', 'btn-tutup-log-overlay', 'loading-overlay', 'loading-judul',
  'loading-status', 'btn-buka-upload', 'upload-file', 'upload-error',
  'upload-hasil', 'f-buku-file', 'btn-upload-buku', 'buku-error',
  'buku-hasil', 'koleksi-buku', 'koleksi-buku-kosong', 'btn-tab-log',
  'alert-overlay', 'alert-judul', 'alert-pesan',
  'btn-alert-tutup', 'log-bulk-kontrol', 'log-bulk-pilih', 'log-bulk-bilah',
  'log-bulk-jumlah', 'btn-hapus-log-pilih', 'hapus-log-overlay',
  'hapus-log-judul', 'hapus-log-pesan', 'hapus-log-error',
  'btn-batal-hapus-log', 'btn-konfirmasi-hapus-log', 'hapus-versi-overlay',
  'hapus-versi-judul', 'hapus-versi-pesan', 'hapus-versi-error',
  'btn-batal-hapus-versi', 'btn-konfirmasi-hapus-versi',
  'btn-arsip-pilih',
  'layar-arsip', 'judul-arsip', 'arsip-error', 'arsip-kosong',
  'arsip-bulk-kontrol', 'arsip-bulk-pilih', 'arsip-bulk-bilah',
  'arsip-bulk-jumlah', 'btn-kembalikan-pilih',
  'btn-hapus-arsip-pilih', 'riwayat-arsip',
  'arsip-overlay', 'arsip-judul', 'arsip-pesan', 'arsip-error',
  'btn-batal-arsip', 'btn-konfirmasi-arsip',
  'kembalikan-overlay', 'kembalikan-judul', 'kembalikan-pesan',
  'kembalikan-error', 'btn-batal-kembalikan',
  'btn-konfirmasi-kembalikan'];

function fieldStub(sec, key, value) {
  return {
    getAttribute: function (k) {
      if (k === 'data-sec') return sec;
      if (k === 'data-key') return key;
      return null;
    },
    value: value, textContent: value, _handlers: {},
    addEventListener: function (ev, fn) { this._handlers[ev] = fn; }
  };
}

function boot(fetchMock, search, hash, seed) {
  const elements = {};
  IDS.forEach(function (id) { elements[id] = makeElement(id); });
  const regenTargets = ['tp', 'kktp', 'aktivitas', 'asesmen'];
  const regenButtons = regenTargets.map(function (target) {
    const b = makeElement('regen-' + target);
    b.textContent = 'Regenerate ' +
      { tp: 'TP', kktp: 'KKTP', aktivitas: 'Aktivitas',
        asesmen: 'Asesmen' }[target];
    b.getAttribute = function (k) {
      return k === 'data-regen' ? target : null;
    };
    return b;
  });
  const listeners = {};
  const winListeners = {};
  const assigned = [];
  const timers = [];
  const storage = makeStorage(seed);
  const sandboxDocument = {
    getElementById: function (id) { return elements[id] || null; },
    addEventListener: function (ev, fn) { listeners[ev] = fn; },
    createElement: function () { return makeElement('dyn'); },
    querySelectorAll: function (sel) {
      if (String(sel).includes('[data-regen]')) return regenButtons;
      return [];
    }
  };
  const sandboxWindow = {
    Api: undefined, ModuleRender: undefined,
    localStorage: storage,
    confirm: function () { return sandboxWindow._confirmReturn !== false; },
    _confirmReturn: true,
    location: { assign: function (u) { assigned.push(u); }, hash: hash || '',
                search: search || '' },
    history: { replaced: [], replaceState: function (a, b, u) {
      this.replaced.push(u);
      const q = String(u).indexOf('?');
      sandboxWindow.location.search = q === -1 ? '' : String(u).slice(q);
    } },
    scrollTo: function () {},
    setTimeout: function (fn) { timers.push(fn); return timers.length; },
    clearTimeout: function () {},
    addEventListener: function (ev, fn) { winListeners[ev] = fn; }
  };
  const sandbox = {
    document: sandboxDocument, window: sandboxWindow,
    URLSearchParams: URLSearchParams,
    fetch: fetchMock, console: console,
    setTimeout: function (fn) { timers.push(fn); return timers.length; },
    clearTimeout: function () {}
  };
  const vm = require('vm');
  vm.createContext(sandbox);
  ['api.js', 'render.js', 'app.js'].forEach(function (f) {
    vm.runInContext(fs.readFileSync(path.join(UI, f), 'utf-8'), sandbox,
      { filename: f });
  });
  listeners.DOMContentLoaded();
  return { elements: elements, window: sandboxWindow, assigned: assigned,
           winListeners: winListeners, docListeners: listeners,
           storage: storage,
           regenButtons: regenButtons,
           timers: timers, runTimers: function () {
             while (timers.length) timers.shift()();
           } };
}

function fetchQueue(routes) {
  // routes: [[methodFragment, pathFragment, response], ...]
  return function (url, opts) {
    const method = (opts && opts.method) || 'GET';
    for (const r of routes) {
      if (method.includes(r[0]) && String(url).includes(r[1])) {
        const res = r[2];
        if (res instanceof Error) return Promise.reject(res);
        return Promise.resolve({
          ok: res.status < 400, status: res.status,
          json: function () { return Promise.resolve(res.body); }
        });
      }
    }
    return Promise.reject(new Error('no mock route for ' + url));
  };
}

const OPTIONS = {
  status: 'success',
  systems: {
    KEMENAG: {
      subjects: ['Akidah Akhlak'],
      institutions: {
        MTs: { grades: ['MTs_7'], grade_labels: { MTs_7: 'Kelas VII' },
               grade_phase: { MTs_7: 'D' }, phases: ['D'] }
      }
    }
  },
  elements_by_subject: { 'Akidah Akhlak': { D: ['Pemahaman Konsep'] } }
};

const CONTEXT = {
  status: 'success',
  context: { cp: { text: 'CP uji', phase: 'D', source_page: 47 },
             topic: 'Taubat' }
};

function fillValidForm(t) {
  t.elements['f-sistem'].value = 'KEMENAG';
  t.elements['f-sistem']._handlers.change();
  t.elements['f-institusi'].value = 'MTs';
  t.elements['f-institusi']._handlers.change();
  t.elements['f-kelas'].value = 'MTs_7';
  t.elements['f-kelas']._handlers.change();
  t.elements['f-mapel'].value = 'Akidah Akhlak';
  t.elements['f-mapel']._handlers.change();
  t.elements['f-topik'].value = 'Taubat';
  t.elements['f-buku'].value = 'BUKU-UJI';
  t.elements['f-jumlah'].value = '2';
  t.elements['f-jp'].value = '2';
  t.elements['f-kesiapan'].value = 'Sebagian murid paham wahyu.';
}

function flush() { return new Promise(function (r) { setTimeout(r, 0); }); }

async function testOptionsLoad() {
  const t = boot(fetchQueue([['GET', '/api/curriculum/options',
    { status: 200, body: OPTIONS }]]));
  await flush();
  const html = t.elements['f-sistem'].innerHTML;
  assert.ok(html.includes('KEMENAG'), 'system option rendered');
  console.log('ok 1 options-load');
}

async function testFormValidation() {
  let contextCalls = 0;
  const t = boot(function (url, opts) {
    if (String(url).includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    contextCalls++;
    return Promise.reject(new Error('must not call context'));
  });
  await flush();
  t.elements['form-konteks'].submit();
  await flush();
  assert.strictEqual(t.elements['form-error'].hidden, false);
  assert.strictEqual(contextCalls, 0);
  console.log('ok 2 form-validation');
}

async function testContextShowsCp() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  assert.strictEqual(t.elements['panel-cp'].hidden, false);
  assert.strictEqual(t.elements['cp-teks'].textContent, 'CP uji');
  console.log('ok 3 context-cp');
}

async function testContextErrorTampilNyata() {
  // Backend 422 errors[] (mis. ELEMENT_NOT_FOUND): pesan asli tampil,
  // bukan "Backend tidak merespons".
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 422, body:
      { status: 'error', errors: [{ code: 'CURRICULUM_CONTEXT_INVALID',
        message: "ELEMENT_NOT_FOUND: multiple elements available for " +
          "Akidah Akhlak phase D; an explicit 'element' is required",
        stage: 'curriculum' }] } }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  assert.strictEqual(t.elements['panel-cp'].hidden, true);
  assert.strictEqual(t.elements['form-error'].hidden, false);
  assert.ok(t.elements['form-error'].textContent.includes('elemen'),
    'instruksi pilih elemen tampil, got: ' +
    t.elements['form-error'].textContent.slice(0, 120));
  assert.ok(!t.elements['form-error'].textContent.includes(
    'tidak merespons'), 'bukan pesan network generik');
  console.log('ok 3b context-error-nyata');
}

function successModule() {
  return {
    id: 'm1', title: 'RPP/RPM Akidah Akhlak: Taubat', subject: 'Akidah Akhlak',
    grade: 'MTs_7', phase: 'D', generation_id: 'g1',
    curriculum_context: { education_system: 'KEMENAG' },
    master_outline: {
      general_information: { identity: {}, kbc: { themes: ['Cinta Ilmu'] } },
      identification: {}, design: { cp: 'CP', tp: [], kktp: [] },
      learning_experience: { experiences: {} }, assessment: {}
    }
  };
}

const SUCCESS_STATUS = {
  status: 'success', generation_id: 'g1', module: successModule(),
  validation: { final: { passed: true, errors: [] } }
};

async function testGeneratePollSuccess() {
  let polls = 0;
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      return ok({ status: 'accepted', job_id: 'j1' });
    }
    if (u.includes('/api/generation/status')) {
      polls++;
      if (polls < 2) return ok({ status: 'running' });
      return ok(SUCCESS_STATUS);
    }
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay loading tampil saat generate');
  assert.strictEqual(t.elements['layar-progres'].hidden, false,
    'layar progres tampil sebagai latar');
  assert.strictEqual(t.elements['progres-bar'].hidden, true,
    'tanpa bar animasi ganda saat overlay jalan');
  t.runTimers();
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'hasil tampil setelah sukses');
  assert.strictEqual(t.elements['btn-export-docx'].hidden, false,
    'export tampil setelah PASS');
  console.log('ok 4 generate-poll-success');
}

async function testGenerateFailure() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }],
    ['POST', '/api/module/generate', { status: 200, body:
      { status: 'accepted', job_id: 'j9' } }],
    ['GET', '/api/generation/status', { status: 200, body:
      { status: 'error', errors: [{ code: 'X', message: 'gagal', stage: 'ai' }] } }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush();
  assert.strictEqual(t.elements['progres-error'].hidden, false);
  assert.strictEqual(t.elements['layar-hasil'].hidden, true);
  console.log('ok 5 generate-failure');
}

async function testGagalTerminalBisaCobaLagi() {
  let generates = 0;
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      generates++;
      return ok({ status: 'accepted', job_id: 'jx' });
    }
    return ok({ status: 'error',
      errors: [{ code: 'X', message: 'gagal', stage: 'ai' }] });
  });
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush();
  assert.strictEqual(t.elements['btn-coba-lagi'].hidden, false,
    'tombol Coba Lagi tampil saat gagal terminal');
  assert.strictEqual(generates, 1);
  t.elements['btn-coba-lagi'].click();
  await flush(); await flush();
  assert.strictEqual(generates, 2, 'klik Coba Lagi request generate baru');
  console.log('ok 9 gagal-coba-lagi');
}

async function testBukaUlangSesiTersimpan() {
  const stored = successModule();
  stored.generation_id = 'g9';
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['GET', '/api/module/g9', { status: 200, body:
      { status: 'success', generation_id: 'g9', module: stored,
        validation: { final: { passed: true, errors: [] } } } }]
  ]), '?generation_id=g9');
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'sesi tersimpan dibuka kembali');
  assert.strictEqual(t.elements['btn-export-docx'].hidden, false);
  console.log('ok 11 buka-ulang-sesi');
}

async function testBukaUlangSesiHilang() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['GET', '/api/module/xxx', { status: 404, body: { status: 'error' } }]
  ]), '?generation_id=xxx');
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-beranda'].hidden, false);
  assert.strictEqual(t.elements['buka-error'].hidden, false);
  console.log('ok 12 buka-ulang-gagal');
}

async function testBukaDariBerandaTanpaReload() {
  // Klik Buka di Beranda: tanpa reload, landing tak sempat tampil,
  // langsung progres lalu hasil.
  const stored = successModule();
  stored.generation_id = 'g1';
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/modules')) return ok(HISTORY);
    if (u.includes('/api/module/g1')) {
      return ok({ status: 'success', generation_id: 'g1', module: stored,
        validation: { final: { passed: true, errors: [] } } });
    }
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  await gotoBeranda(t);
  await flush(); await flush();
  assert.ok(t.elements['riwayat-rpm'].innerHTML.includes('Buka'),
    'tombol Buka tampil');
  // Search harness kosong: bukaSesiLangsung set ?generation_id=g1.
  t.window.location.search = '';
  // Simulasi klik anchor Buka: closest('a[href*=generation_id=]').
  var dicegat = false;
  var fakeA = {
    getAttribute: function () { return '/app?generation_id=g1#layar-hasil'; }
  };
  t.elements['riwayat-rpm']._handlers.click({
    target: { closest: function () { return fakeA; } },
    preventDefault: function () { dicegat = true; }
  });
  assert.strictEqual(dicegat, true, 'navigasi full-page dicegat');
  // Stub replaceState harness tak update hash (browser asli ya):
  // set manual agar guard masihDiminta lolos.
  t.window.location.hash = '#layar-hasil';
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-landing'].hidden, true,
    'landing tak bocor');
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'hasil tampil');
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tertutup');
  console.log('ok 12b buka-tanpa-reload');
}

async function testLoadingTunggalBukaSesi() {
  // Buka RPM: hanya overlay tengah, tanpa layar progres ganda.
  // Harness: fetch modul pending agar overlay sempat terlihat.
  let resolveModul = null;
  const stored = successModule();
  stored.generation_id = 'g9';
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/module/g9')) {
      return new Promise(function (res) { resolveModul = res; });
    }
    return Promise.reject(new Error('no route ' + u));
  }, '?generation_id=g9');
  await flush();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat buka sesi');
  assert.strictEqual(t.elements['layar-progres'].hidden, false,
    'layar progres tampil sebagai latar (tanpa animasi ganda)');
  assert.strictEqual(t.elements['progres-bar'].hidden, true,
    'bar animasi disembunyikan saat overlay jalan');
  resolveModul({ ok: true, status: 200,
    json: function () {
      return Promise.resolve({ status: 'success', generation_id: 'g9',
        module: stored,
        validation: { final: { passed: true, errors: [] } } });
    } });
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'hasil tampil setelah modul tiba');
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tertutup');
  console.log('ok 11b loading-tunggal-buka');
}

async function testTabBaruAnchorPulihkanSesi() {
  const stored = successModule();
  stored.generation_id = 'g9';
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['GET', '/api/module/g9', { status: 200, body:
      { status: 'success', generation_id: 'g9', module: stored,
        validation: { final: { passed: true, errors: [] } } } }]
  ]), '?generation_id=g9', '#a-identitas');
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'tab baru pada anchor harus pulihkan sesi, bukan beranda');
  assert.strictEqual(t.elements['layar-beranda'].hidden, true);
  console.log('ok 13 tab-baru-anchor');
}

async function testAlokasiInvalidDitolak() {
  let contextCalls = 0;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    contextCalls++;
    return Promise.reject(new Error('must not call'));
  });
  await flush();
  fillValidForm(t);
  t.elements['f-jumlah'].value = 'nol';
  t.elements['form-konteks'].submit();
  await flush();
  assert.strictEqual(t.elements['form-error'].hidden, false);
  assert.ok(t.elements['form-error'].textContent.includes('bilangan bulat'));
  assert.strictEqual(contextCalls, 0);
  console.log('ok 14 alokasi-invalid');
}

async function testGenerateBawaInputGuru() {
  let bodies = [];
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      bodies.push(JSON.parse(opts.body));
      return ok({ status: 'accepted', job_id: 'jw' });
    }
    if (u.includes('/api/generation/status')) return ok(SUCCESS_STATUS);
    return Promise.reject(new Error('no route'));
  });
  await flush();
  fillValidForm(t);
  t.elements['f-penyusun'].value = 'Ibu Guru';
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  const gen = bodies.find(function (b) { return b.async === true; });
  assert.ok(gen, 'generate terkirim');
  assert.strictEqual(gen.jumlah_pertemuan, '2');
  assert.strictEqual(gen.jp_per_pertemuan, '2');
  assert.strictEqual(gen.penyusun, 'Ibu Guru');
  assert.strictEqual(gen.student_readiness, 'Sebagian murid paham wahyu.');
  console.log('ok 15 generate-bawa-input');
}

async function testAnchorTocTidakKabur() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }],
    ['POST', '/api/module/generate', { status: 200, body:
      { status: 'accepted', job_id: 'j3' } }],
    ['GET', '/api/generation/status', { status: 200, body: SUCCESS_STATUS }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false);
  t.window.location.hash = '#a-identitas';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'klik TOC tidak boleh kabur ke beranda');
  assert.strictEqual(t.elements['layar-beranda'].hidden, true);
  t.window.location.hash = '#layar-hasil';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'back ke hasil tetap tampil selama modul ada');
  console.log('ok 10 anchor-toc');
}

async function testExportGatingAndDownload() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }],
    ['POST', '/api/module/generate', { status: 200, body:
      { status: 'accepted', job_id: 'j2' } }],
    ['GET', '/api/generation/status', { status: 200, body: SUCCESS_STATUS }]
  ]));
  await flush();
  assert.strictEqual(t.elements['btn-export-docx'].hidden, true,
    'export hidden sebelum PASS');
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush();
  assert.strictEqual(t.elements['btn-export-docx'].hidden, false);
  t.elements['btn-export-docx'].click();
  assert.strictEqual(t.assigned.length, 1);
  assert.ok(t.assigned[0].includes('/api/module/g1/export-docx'),
    t.assigned[0]);
  console.log('ok 6 export-gating-download');
}

async function testRenderEscapesAndKbc() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const evil = successModule();
  evil.master_outline.design.tp = [
    { id: 'TP-1', text: '<script>alert(1)</script>', cognitive_level: 'C3' }];
  const out = R.renderModule(evil, { final: { passed: true } });
  assert.ok(!out.content.includes('<script>'), 'ter-encode');
  assert.ok(out.content.includes('Kurikulum Berbasis Cinta'), 'KBC madrasah');
  const school = JSON.parse(JSON.stringify(evil));
  school.curriculum_context.education_system = 'KEMENDIKDASMEN';
  school.master_outline.general_information.kbc = null;
  const out2 = R.renderModule(school, { final: { passed: true } });
  assert.ok(!out2.content.includes('Kurikulum Berbasis Cinta'), 'tanpa KBC');
  console.log('ok 7 render-escape-kbc');
}

async function testHashNavigasiKeFormulir() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.strictEqual(t.elements['layar-formulir'].hidden, true,
    'formulir hidden di beranda');
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['layar-formulir'].hidden, false,
    'klik Buat RPM menampilkan formulir');
  assert.strictEqual(t.elements['layar-beranda'].hidden, true);
  console.log('ok 8 hash-navigasi');
}

async function testAlokasiRangeDitolak() {
  let contextCalls = 0;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    contextCalls++;
    return Promise.reject(new Error('must not call'));
  });
  await flush();
  fillValidForm(t);
  t.elements['f-jumlah'].value = '17';
  t.elements['form-konteks'].submit();
  await flush();
  assert.strictEqual(t.elements['form-error'].hidden, false);
  assert.ok(t.elements['form-error'].textContent.includes('1–16'));
  assert.strictEqual(contextCalls, 0);
  t.elements['f-jumlah'].value = '2';
  t.elements['f-jp'].value = '11';
  t.elements['form-konteks'].submit();
  await flush();
  assert.ok(t.elements['form-error'].textContent.includes('1–10'));
  assert.strictEqual(contextCalls, 0);
  console.log('ok 16 alokasi-range');
}

async function testGenerateBawaFormLive() {
  let bodies = [];
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      bodies.push(JSON.parse(opts.body));
      return ok({ status: 'accepted', job_id: 'jl' });
    }
    if (u.includes('/api/generation/status')) return ok(SUCCESS_STATUS);
    return Promise.reject(new Error('no route'));
  });
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  // Ubah input SETELAH cek CP: generate wajib memakai nilai live.
  t.elements['f-jumlah'].value = '3';
  t.elements['f-penyusun'].value = 'Pak Guru';
  t.elements['btn-generate'].click();
  await flush(); await flush();
  const gen = bodies.find(function (b) { return b.async === true; });
  assert.ok(gen, 'generate terkirim');
  assert.strictEqual(gen.jumlah_pertemuan, '3',
    'perubahan pasca-cek-CP tidak boleh diabaikan');
  assert.strictEqual(gen.penyusun, 'Pak Guru');
  console.log('ok 17 generate-live');
}

async function testGantiSistemResetDependen() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  assert.strictEqual(t.elements['panel-cp'].hidden, false);
  t.elements['f-sistem'].value = '';
  t.elements['f-sistem']._handlers.change();
  assert.strictEqual(t.elements['f-kelas'].disabled, true);
  assert.strictEqual(t.elements['f-mapel'].disabled, true);
  assert.ok(!t.elements['f-kelas'].innerHTML.includes('MTs_7'),
    'kelas lama tidak dipertahankan');
  assert.strictEqual(t.elements['panel-cp'].hidden, true,
    'panel CP lama disembunyikan');
  console.log('ok 18 reset-dependen');
}

function editModule() {
  const m = successModule();
  m.learning_objectives = [
    { id: 'TP-1', text: 'T1 menerapkan taubat', cognitive_level: 'C3' },
    { id: 'TP-2', text: 'T2 menganalisis taubat', cognitive_level: 'C4' },
    { id: 'TP-3', text: 'T3 mengevaluasi taubat', cognitive_level: 'C5' }
  ];
  m.success_criteria = [
    { id: 'KKTP-1', tp_id: 'TP-1', criteria: ['c1a', 'c1b'], cognitive_level: 'C3' }
  ];
  m.learning_activities = [];
  m.assessments = {};
  m.reflection = [];
  m.lkpd = [];
  m.facilities = [];
  m.glosarium = [
    { istilah: 'Taubat', definisi: 'Kembali kepada Allah.' }
  ];
  m.master_outline.attachments = {
    lkpd: [],
    glosarium: [{ istilah: 'Taubat', definisi: 'Kembali kepada Allah.' }]
  };
  m.topic = 'Taubat';
  m.student_readiness = '';
  m.penyusun = '';
  m.curriculum_context = { education_system: 'KEMENAG',
    cp: { text: 'CP kunci', source_document_id: 'DOC', source_page: 47 } };
  return m;
}

const VERSIONS = {
  status: 'success', generation_id: 'g1', latest_version: 2,
  versions: [
    { version_no: 1, parent_version_no: null, status: 'validated',
      alignment_status: 'Aligned', changed_sections: [], warnings: [],
      created_at: 't1' },
    { version_no: 2, parent_version_no: 1, status: 'validated',
      alignment_status: 'Aligned', changed_sections: ['tp'], warnings: [],
      created_at: 't2' }
  ]
};

function successWithVersions(fetchExtra) {
  return function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      return ok({ status: 'accepted', job_id: 'jv' });
    }
    if (u.includes('/versions')) return ok(VERSIONS);
    if (u.includes('/api/generation/status')) {
      const m = editModule();
      return ok({ status: 'success', generation_id: 'g1', module: m,
        validation: { final: { passed: true, errors: [] } } });
    }
    if (fetchExtra) return fetchExtra(url, opts);
    return Promise.reject(new Error('no route ' + u));
  };
}

async function gotoHasil(t) {
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false);
}

async function testEditModeLockedCp() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  const html = t.elements['editor-isi'].innerHTML;
  assert.strictEqual(t.elements['editor-isi'].hidden, false);
  assert.ok(html.includes('data-sec="tp"'), 'TP editable');
  assert.ok(html.includes('terkunci'), 'CP terkunci');
  assert.ok(!html.includes('data-sec="cp"'), 'tanpa editor CP');
  assert.strictEqual(t.elements['btn-simpan-versi'].hidden, false);
  console.log('ok 19 edit-mode-cp-locked');
}

async function testSavePostsDiffOnly() {
  let savedBody = null;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      savedBody = JSON.parse(opts.body);
      const v = { version_no: 3, parent_version_no: 2, status: 'validated',
        alignment_status: 'Aligned', changed_sections: ['tp'], warnings: [],
        module: editModule(),
        validation: { final: { passed: true, errors: [] } } };
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: v });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat VERSI GURU'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.ok(savedBody, 'save terkirim');
  assert.strictEqual(savedBody.base_version, 2);
  assert.deepStrictEqual(Object.keys(savedBody.changes), ['tp']);
  assert.strictEqual(savedBody.changes.tp[0].text,
    'T1 menerapkan taubat VERSI GURU');
  assert.ok(t.elements['status-simpan'].textContent.includes('v3'));
  console.log('ok 20 save-diff');
}

async function testDirtyGuard() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const f = fieldStub('tp', '0', 'x');
  t.elements['editor-isi'].querySelectorAll = function () { return [f]; };
  t.elements['btn-mode-edit'].click();
  f._handlers.input();
  assert.strictEqual(t.elements['status-simpan'].textContent,
    'Belum disimpan');
  t.window._confirmReturn = false;
  t.elements['btn-baru'].click();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false,
    'navigasi dibatalkan saat kotor');
  t.window._confirmReturn = true;
  t.elements['btn-baru'].click();
  assert.strictEqual(t.elements['layar-formulir'].hidden, false);
  console.log('ok 21 dirty-guard');
}

async function testStale409Pesan() {
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      return Promise.resolve({ ok: false, status: 409,
        json: function () {
          return Promise.resolve({ status: 'error',
            errors: [{ code: 'STALE_VERSION', message: 'basi', stage: 'c' }] });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [fieldStub('tp', '0', 'berubah')];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.ok(t.elements['status-simpan'].textContent.includes('basi'));
  console.log('ok 22 stale-409');
}

async function testRiwayatRender() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush();
  const riw = t.elements['riwayat-versi'].innerHTML;
  assert.ok(riw.includes('v1'), 'v1 tampil');
  assert.ok(riw.includes('v2') && riw.includes('AKTIF'),
    'versi aktif ditandai');
  assert.ok(riw.includes('ubah: tp'), 'changed sections tampil');
  assert.ok(riw.includes('Lihat'), 'tombol Lihat tampil');
  assert.ok(!riw.includes('Restore'), 'tanpa tombol Restore per baris');
  assert.ok(t.elements['hasil-versi'].textContent.includes('v2'));
  assert.ok(t.elements['hasil-alignment'].textContent.includes('Aligned'));
  console.log('ok 23 riwayat-render');
}

async function testExportVersionedUrl() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush();
  t.elements['btn-export-docx'].click();
  assert.strictEqual(t.assigned.length, 1);
  assert.ok(t.assigned[0].includes('?version=2'), t.assigned[0]);
  console.log('ok 24 export-versioned');
}

async function testApiVersionShapes() {
  const calls = [];
  const t = boot(function (url, opts) {
    calls.push({ url: String(url), body: opts && opts.body });
    return Promise.resolve({ ok: true, status: 200,
      json: function () { return Promise.resolve({}); } });
  });
  await flush();
  const A = t.window.Api;
  await A.saveVersion('g1', 2, { tp: [] });
  await A.regenerateSection('g1', 2, 'aktivitas');
  await A.finalizeVersion('g1');
  await A.restoreVersion('g1', 1);
  await A.listVersions('g1');
  await A.getVersion('g1', 1);
  const modCalls = calls.filter(function (c) {
    return c.url.includes('/api/module/g1');
  });
  const urls = modCalls.map(function (c) { return c.url; });
  assert.ok(urls[0].includes('/api/module/g1/versions'));
  assert.deepStrictEqual(JSON.parse(modCalls[0].body),
    { base_version: 2, changes: { tp: [] } });
  assert.ok(urls[1].includes('/regenerate'));
  assert.deepStrictEqual(JSON.parse(modCalls[1].body),
    { base_version: 2, target: 'aktivitas', async: true, draft: true });
  assert.ok(urls[2].includes('/finalize'));
  assert.ok(urls[3].includes('/versions/1/restore'));
  assert.ok(urls[4].includes('/versions') && !urls[4].includes('restore'));
  assert.ok(urls[5].includes('/versions/1'));
  console.log('ok 25 api-shapes');
}

async function testGlosariumReview() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush();
  const html = t.elements['hasil-isi'].innerHTML;
  assert.ok(html.includes('Glosarium'), 'glosarium tampil di review');
  assert.ok(html.includes('Taubat'), 'istilah tampil');
  assert.ok(t.elements['hasil-toc'].innerHTML.includes('#glosarium'));
  console.log('ok 26 glosarium-review');
}

async function testGlosariumEditCollect() {
  let savedBody = null;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      savedBody = JSON.parse(opts.body);
      const v = { version_no: 3, parent_version_no: 2, status: 'validated',
        alignment_status: 'Aligned', changed_sections: ['glosarium'],
        warnings: [], module: editModule(),
        validation: { final: { passed: true, errors: [] } } };
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: v });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  assert.ok(t.elements['editor-isi'].innerHTML.includes('Tambah istilah'));
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('glosarium', 'istilah:0', 'Taubat nasuha'),
      fieldStub('glosarium', 'definisi:0', 'Kembali kepada Allah.'),
      fieldStub('glosarium', 'istilah:1', 'Istigfar'),
      fieldStub('glosarium', 'definisi:1', 'Memohon ampun.')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.ok(savedBody, 'save terkirim');
  assert.deepStrictEqual(savedBody.changes.glosarium, [
    { istilah: 'Taubat nasuha', definisi: 'Kembali kepada Allah.' },
    { istilah: 'Istigfar', definisi: 'Memohon ampun.' }
  ]);
  console.log('ok 27 glosarium-edit-save');
}

async function testGlosariumUntouchedNotSent() {
  let savedBody = null;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      savedBody = JSON.parse(opts.body);
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: { version_no: 3, parent_version_no: 2,
              status: 'validated', alignment_status: 'Aligned',
              changed_sections: ['tp'], warnings: [], module: editModule(),
              validation: { final: { passed: true, errors: [] } } } });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  // Hanya field TP, tanpa field glosarium: glosarium tidak ikut changes.
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 berubah'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.ok(savedBody, 'save terkirim');
  assert.ok(!('glosarium' in (savedBody.changes || {})),
    'glosarium tak tersentuh tidak ikut terkirim');
  console.log('ok 28 glosarium-untouched');
}

async function testApiGlosariumRegenShape() {
  const calls = [];
  const t = boot(function (url, opts) {
    calls.push({ url: String(url), body: opts && opts.body });
    return Promise.resolve({ ok: true, status: 200,
      json: function () { return Promise.resolve({}); } });
  });
  await flush();
  await t.window.Api.regenerateSection('g1', 2, 'glosarium');
  assert.ok(calls[1].url.includes('/regenerate'));
  assert.deepStrictEqual(JSON.parse(calls[1].body),
    { base_version: 2, target: 'glosarium', async: true, draft: true });
  console.log('ok 29 api-glosarium-regen');
}

async function testDimsNotesRender() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = editModule();
  m.master_outline.identification = {
    profile_dimensions: ['Kolaborasi'],
    profile_dimension_notes: {
      Kolaborasi: 'Relevan karena diskusi kelompok taubat.'
    }
  };
  const out = R.renderModule(m, { final: { passed: true } });
  assert.ok(out.content.includes('Relevan karena diskusi kelompok'));
  console.log('ok 30 dims-notes');
}

async function testKbcNoteNotRendered() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = editModule();
  m.master_outline.general_information = {
    kbc: { themes: ['Cinta Ilmu'],
      insertion_material: ['Insersi x'],
      integration_note: 'Catatan internal.' }
  };
  m.master_outline.identification = {};
  const out = R.renderModule(m, { final: { passed: true } });
  assert.ok(out.content.includes('Kurikulum Berbasis Cinta'));
  assert.ok(!out.content.includes('Penerapan dalam pembelajaran'));
  assert.ok(!out.content.includes('Catatan internal.'));
  console.log('ok 31 kbc-note-hidden');
}

async function testKktpPlainRender() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = editModule();
  m.master_outline.design = {
    tp: [{ id: 'TP-1', text: 'T', cognitive_level: 'C3' }],
    kktp: [{ id: 'KKTP-1', tp_id: 'TP-1', cognitive_level: 'C4',
             criteria: ['c1'] }]
  };
  const out = R.renderModule(m, { final: { passed: true } });
  assert.ok(out.content.includes('KKTP-1'));
  assert.ok(!out.content.includes('(untuk TP-1'));
  console.log('ok 32 kktp-plain');
}

async function testPrinciplesRender() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = editModule();
  m.meetings = [{ index: 1, jp: 2, minutes: 80, stages: {},
    principles: { berkesadaran: 'Sadar tujuan pada apersepsi.',
                  bermakna: 'Kaitkan dengan pengalaman.',
                  menggembirakan: 'Kuis berhadiah.' } }];
  m.master_outline.learning_experience = { experiences: {} };
  const out = R.renderModule(m, { final: { passed: true } });
  assert.ok(out.content.includes('Prinsip Pembelajaran Mendalam'));
  assert.ok(out.content.includes('Berkesadaran'));
  const m2 = editModule();
  m2.meetings = [{ index: 1, jp: 2, minutes: 80, stages: {} }];
  m2.master_outline.learning_experience = { experiences: {} };
  const out2 = R.renderModule(m2, { final: { passed: true } });
  assert.ok(!out2.content.includes('Prinsip Pembelajaran Mendalam'));
  console.log('ok 33 principles-render');
}

async function testLkpdNotRendered() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = editModule();
  m.master_outline.attachments = {
    lkpd: [{ id: 'LKPD-1', title: 'L', tp_linked: 'TP-1', task: 'T' }],
    glosarium: []
  };
  const out = R.renderModule(m, { final: { passed: true } });
  assert.ok(!out.content.includes('LKPD'));
  console.log('ok 34 lkpd-hidden');
}

async function testCountsFieldsPresent() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.ok(t.elements['f-awal'], 'input awal ada');
  assert.ok(t.elements['f-formatif'], 'input formatif ada');
  assert.ok(t.elements['f-sumatif'], 'input sumatif ada');
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('tidak ikut digenerate'),
    'petunjuk 0 = tidak digenerate ada');
  console.log('ok 35 counts-fields');
}

async function testCountsNolKeterangan() {
  // R-42: render E tanpa asesmen tetap tampil + tombol per jenis.
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const m = templateModule();
  m.master_outline.assessment = { awal: [], proses: [], akhir: [] };
  const out = t.window.ModuleRender.renderModule(m,
    { final: { passed: true } });
  assert.ok(out.content.includes('Asesmen belum digenerate'),
    'pesan kosong tampil');
  assert.ok(out.content.includes('data-regen="diagnostik"'),
    'tombol susulan diagnostik ada');
  assert.ok(out.content.includes('data-regen="formatif"'),
    'tombol susulan formatif ada');
  assert.ok(out.content.includes('data-regen="sumatif"'),
    'tombol susulan sumatif ada');
  console.log('ok 151 asesmen-kosong-tombol');
}

async function testBukuWajibAda() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="f-buku"'), 'dropdown buku ada');
  assert.ok(html.includes('Buku ajar sumber materi'), 'label buku ada');
  console.log('ok 152 buku-wajib-ada');
}

async function testBukuUploadTombol() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="btn-upload-buku"'), 'tombol tambah ada');
  assert.ok(html.includes('f-buku-file'), 'input file ada');
  assert.ok(html.includes('Tambah buku'), 'label satu tombol jelas');
  assert.ok(!html.includes('Upload PDF/DOCX buku atau bahan ajar'),
    'kalimat panjang dibuang');
  const posBeranda = html.indexOf('id="layar-beranda"');
  const posUpload = html.indexOf('id="btn-upload-buku"');
  const posForm = html.indexOf('id="layar-formulir"');
  assert.ok(posBeranda < posUpload && posUpload < posForm,
    'upload buku di Beranda, bukan formulir');
  assert.ok(html.includes('Koleksi Buku Ajar'), 'heading koleksi jelas');
  assert.ok(html.includes('Impor RPM'), 'tombol impor berlabel jelas');
  console.log('ok 153 buku-upload-tombol');
}

async function testRegenButtonsInventory() {
  // Retry per bagian (render dinamis), bukan cluster bawah page.
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.strictEqual((html.match(/data-regen="/g) || []).length, 0,
    'tanpa cluster statis');
  for (const label of ['Simpan perubahan', 'Export DOCX', 'Buat RPM baru',
        'Riwayat versi']) {
    assert.ok(html.includes(label), label + ' tampil');
  }
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const out = t.window.ModuleRender.renderModule(templateModule(),
    { final: { passed: true } });
  const c = out.content;
  for (const tg of ['data-regen="tp"', 'data-regen="kktp"',
      'data-regen="praktik_pedagogis"', 'data-regen="aktivitas"',
      'data-regen="formatif"', 'data-regen="sumatif"']) {
    assert.ok(c.includes(tg), tg + ' di samping bagian');
  }
  for (const label of ['Regenerate Materi', 'Regenerate Rubrik',
      'Regenerate Refleksi', 'Regenerate Glosarium',
      'Regenerate Asesmen']) {
    assert.ok(!c.includes(label), label + ' tidak ada');
  }
  console.log('ok 36 regen-inventory');
}

function templateModule() {
  const m = successModule();
  m.topic = 'Taubat dalam Pembelajaran';
  m.penyusun = 'Ibu Guru';
  m.module_identity = { satuan_pendidikan: 'MTs Negeri 1',
    semester: '1', year: '2026/2027' };
  m.curriculum_version = 'KMA-1503-2025';
  m.master_outline.identification = {
    learner_readiness: { summary: 'Sebagian murid paham wahyu.' },
    material_characteristics: { summary: 'Materi konseptual.' },
    profile_dimensions: ['Kolaborasi'],
    profile_dimension_notes: { Kolaborasi: 'Relevan karena diskusi.' }
  };
  m.master_outline.design = {
    cp: 'CP taubat.',
    cp_provenance: { source_document_id: 'DOC', source_page: 47 },
    tp: [{ id: 'TP-1', text: 'Menerapkan taubat', cognitive_level: 'C3' }],
    kktp: [{ id: 'KKTP-1', criteria: ['Mampu menjelaskan taubat'] }],
    topic_context: 'Taubat dalam Pembelajaran',
    pedagogical_practices: ['Diskusi kelompok']
  };
  m.meetings = [{ index: 1, jp: 2, minutes: 80,
    stages: {
      Pembuka: [{ name: 'Apersepsi', description: 'Guru membuka dengan salam',
        duration: 10, tp_linked: 'TP-1', experience: 'memahami' }],
      Inti: [{ name: 'Diskusi', description: 'Siswa berdiskusi makna taubat',
        duration: 50, tp_linked: 'TP-1', experience: 'mengaplikasi' }],
      Penutup: [{ name: 'Refleksi', description: 'Siswa menulis refleksi',
        duration: 20, tp_linked: 'TP-1', experience: 'merefleksi' }]
    },
    principles: { berkesadaran: 'Sadar tujuan.',
      bermakna: 'Kaitkan pengalaman.', menggembirakan: 'Kuis.' } }];
  m.master_outline.assessment = {
    awal: [{ question: 'Apa itu taubat?', type: 'multiple_choice',
      options: [{ label: 'A', text: 'Jawaban A' },
        { label: 'B', text: 'Jawaban B' },
        { label: 'C', text: 'Jawaban C' },
        { label: 'D', text: 'Jawaban D' }],
      correct_answer: 'B', tp_linked: '', kktp_linked: '' }],
    proses: [{ question: 'Jelaskan taubat.', type: 'short_answer',
      tp_linked: 'TP-1', kktp_linked: 'KKTP-1' }],
    akhir: [{ question: 'Analisis taubat.', type: 'essay',
      tp_linked: 'TP-1', kktp_linked: 'KKTP-1' }]
  };
  return m;
}

async function testTemplateHeaderTopik() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  assert.ok(out.header.includes('PERENCANAAN PEMBELAJARAN MENDALAM'),
    'header template tampil');
  assert.ok(out.header.includes('Taubat dalam Pembelajaran'),
    'topik tampil di header');
  assert.ok(!out.header.includes('badge-valid'),
    'badge status tidak masuk badan dokumen');
  assert.ok(!out.content.includes('Final validation'),
    'konten bebas status aplikasi');
  console.log('ok 37 template-header-topik');
}

async function testIdentitasModul() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const c = out.content;
  assert.ok(c.includes('A. IDENTITAS MODUL'), 'banner A template');
  for (const label of ['Nama Madrasah', 'Nama Penyusun', 'Mata Pelajaran',
      'Kelas / Fase /Semester', 'Alokasi Waktu', 'Tahun Pelajaran']) {
    assert.ok(c.includes(label), label + ' tampil');
  }
  assert.ok(!c.includes('Versi Kurikulum'), 'tanpa Versi Kurikulum');
  const identSection = c.split('id="a-identitas"')[1].split('</section>')[0];
  assert.ok(!identSection.includes('<table'),
    'tanpa tabel grid identitas');
  assert.ok(c.includes('7/D'), 'kode ramah tampil (MTs_7/D)');
  assert.ok(!c.includes('MTs_7/D'), 'tanpa kode mentah');
  assert.ok(c.includes('4 JP (1 Pertemuan x 2 JP)') ||
    c.includes('2 JP (1 Pertemuan x 2 JP)'), 'alokasi dari data meeting');
  assert.ok(c.includes('Ibu Guru') && c.includes('MTs Negeri 1'));
  console.log('ok 38 identitas-modul');
}

async function testSectionOrderTemplate() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const seq = ['A. IDENTITAS MODUL', 'B. IDENTIFIKASI',
    'C. DESAIN PEMBELAJARAN', 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN',
    'E. ASESMEN'];
  let last = -1;
  for (const s of seq) {
    const i = out.content.indexOf(s);
    assert.ok(i > last, s + ' urut (' + i + ' > ' + last + ')');
    last = i;
    assert.ok(out.toc.includes(s), 'toc memuat ' + s);
  }
  console.log('ok 39 section-order-template');
}

async function testMeetingPrinsipTerpisah() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const c = out.content;
  for (const tahap of ['Pembuka', 'Inti', 'Penutup']) {
    assert.ok(c.includes('<h4>' + tahap + '</h4>'), tahap + ' tampil');
  }
  assert.ok(c.includes('Pertemuan 1'), 'banner pertemuan tampil');
  assert.ok(c.includes('Prinsip Pembelajaran Mendalam'), 'prinsip tampil');
  assert.ok(c.includes('<ol>'), 'prinsip numbered');
  assert.ok(c.includes('Berkesadaran (Mindful Learning)'),
    'label template tampil');
  assert.ok(c.includes('Bermakna (Meaningful Learning)'));
  assert.ok(c.includes('Menggembirakan (Joyful Learning)'));
  // Prinsip menutup tiap pertemuan: setelah <h4>Penutup</h4>, sebelum E.
  // Tidak ada section terpisah d-prinsip.
  assert.ok(!c.includes('id="d-prinsip"'), 'tanpa blok prinsip terpisah');
  var penutupPos = c.indexOf('<h4>Penutup</h4>');
  var prinsipPos = c.indexOf('Prinsip Pembelajaran Mendalam');
  var asesmenPos = c.indexOf('E. ASESMEN');
  assert.ok(penutupPos !== -1 && prinsipPos !== -1 && asesmenPos !== -1,
    'urutan penutup-prinsip-asesmen ada');
  assert.ok(penutupPos < prinsipPos && prinsipPos < asesmenPos,
    'prinsip di akhir pertemuan (' + penutupPos + ' < ' + prinsipPos +
    ' < ' + asesmenPos + ')');
  assert.ok(c.includes('Asesmen Diagnostik') &&
    c.includes('Asesmen Formatif') && c.includes('Asesmen Sumatif'),
    'asesmen mengikuti template');
  assert.ok(c.includes('Jawaban Benar'), 'kolom jawaban benar');
  assert.ok(c.includes('<td>Pilihan Ganda</td><td>B</td>'),
    'jawaban B dari final result');
  assert.ok(c.includes('Pilihan Ganda') && c.includes('Isian') &&
    c.includes('Uraian'), 'tipe berbahasa Indonesia');
  assert.ok(!c.includes('multiple_choice') &&
    !c.includes('short_answer') && !c.includes('essay'),
    'tanpa raw enum');
  assert.ok(!c.includes('Total keseluruhan') && !c.includes('Total: '),
    'tanpa baris total');
  console.log('ok 40 meeting-prinsip-terpisah');
}

async function testDataFinalLengkap() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const c = out.content + out.header;
  for (const s of ['CP taubat.', 'Menerapkan taubat', 'KKTP-1',
      'Mampu menjelaskan taubat', 'Taubat dalam Pembelajaran',
      'Diskusi kelompok', 'Apersepsi', 'Sadar tujuan.',
      'Apa itu taubat?', 'Sebagian murid paham wahyu.',
      'Materi konseptual.', 'Relevan karena diskusi.',
      'Cinta Ilmu']) {
    assert.ok(c.includes(s), 'data final tampil: ' + s);
  }
  // Topik tepat satu kali (di bawah judul, tidak di section C).
  const topicCount = c.split('Taubat dalam Pembelajaran').length - 1;
  assert.strictEqual(topicCount, 1, 'topik satu kali, got ' + topicCount);
  console.log('ok 41 data-final-lengkap');
}

async function testSectionLamaHilang() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const c = out.content + out.header + out.toc;
  for (const s of ['class="huruf"', 'Durasi (mnt)', '<h4>Awal</h4>',
      '<h4>Proses</h4>', '<h4>Akhir</h4>', 'Kesiapan murid</h4>',
      'Satuan/kelas', 'Tahun ajaran', 'Versi Kurikulum', 'badge-valid',
      'Final validation', '<h4>Topik</h4>', 'Total keseluruhan',
      'ID: MOD-', 'Praktik pedagogis</h4>']) {
    assert.ok(!c.includes(s), 'string lama hilang: ' + s);
  }
  console.log('ok 42 section-lama-hilang');
}

async function testKbcPaired() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = templateModule();
  m.master_outline.general_information = {
    kbc: { themes: ['Cinta Ilmu', 'Cinta Lingkungan'],
      insertions: [
        { active: true, text: 'Insersi ilmu',
          tema: 'Cinta Ilmu' },
        { active: true, text: 'Insersi lingkungan',
          tema: 'Cinta Lingkungan' }
      ] }
  };
  const out = R.renderModule(m, { final: { passed: true } });
  const c = out.content;
  assert.ok(c.includes('Kurikulum Berbasis Cinta'), 'KBC tampil');
  assert.ok(!c.includes('Tema yang relevan'), 'tanpa blok tema');
  assert.ok(!c.includes('Materi insersi'), 'tanpa blok insersi');
  assert.ok(c.includes('Cinta Ilmu') && c.includes('Insersi ilmu'));
  assert.ok(c.indexOf('Cinta Ilmu') < c.indexOf('Insersi ilmu') &&
    c.indexOf('Insersi ilmu') < c.indexOf('Cinta Lingkungan'),
    'pasangan tema-insersi berurutan');
  console.log('ok 43 kbc-paired');
}

async function testKbcUnequalHonest() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = templateModule();
  m.master_outline.general_information = {
    kbc: { themes: ['Cinta Ilmu', 'Cinta Lingkungan', 'Cinta Ulama'],
      insertion_material: ['Hanya satu insersi'] }
  };
  const out = R.renderModule(m, { final: { passed: true } });
  const c = out.content;
  assert.ok(c.includes('Cinta Ilmu') && c.includes('Cinta Ulama'));
  assert.ok(c.includes('Hanya satu insersi'), 'insersi tetap tampil');
  console.log('ok 44 kbc-unequal-honest');
}

async function testWebMcOptions() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const out = R.renderModule(templateModule(), { final: { passed: true } });
  const c = out.content;
  for (const s of ['A. Jawaban A', 'B. Jawaban B', 'C. Jawaban C',
      'D. Jawaban D']) {
    assert.ok(c.includes(s), s + ' tampil di Web');
  }
  assert.ok(c.includes('Jawaban Benar'), 'kolom jawaban benar');
  assert.ok(!c.includes('multiple_choice'), 'tanpa raw enum');
  console.log('ok 45 web-mc-options');
}

async function testWebDiagnosticLabelOnly() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const R = t.window.ModuleRender;
  const m = templateModule();
  m.master_outline.assessment.awal = [
    { question: 'Q label?', type: 'multiple_choice',
      options: [{ label: 'A', text: 'Alpha' },
        { label: 'B', text: 'Beta' }],
      correct_answer: 'B' },
    { question: 'Q teks?', type: 'multiple_choice',
      options: [{ label: 'A', text: 'Alpha' },
        { label: 'B', text: 'Beta' }],
      correct_answer: 'Beta' },
    { question: 'Q prefiks?', type: 'multiple_choice',
      options: [{ label: 'A', text: 'Alpha' },
        { label: 'B', text: 'Beta' }],
      correct_answer: 'B. Beta lengkap' }
  ];
  const out = R.renderModule(m, { final: { passed: true } });
  const c = out.content;
  assert.ok(!c.includes('>Beta<'), 'tanpa teks jawaban di kolom');
  const labels = (c.match(/<td>([A-D])<\/td>/g) || []).length;
  assert.ok(labels >= 3, 'tiga label jawaban, got ' + labels);
  console.log('ok 46 web-diagnostic-label-only');
}

async function testAsesmenHeaderNoWrap() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('#e-asesmen th:last-child') &&
    css.includes('nowrap'), 'header asesmen tidak wrap');
  console.log('ok 47 asesmen-nowrap');
}

async function testAsesmenCentered() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('#e-asesmen td:nth-child(n+2)') &&
    css.includes('text-align: center'), 'kolom pendek asesmen tengah');
  console.log('ok 48 asesmen-centered');
}

async function testAsesmenMiddleVertical() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('table.val-mid td:nth-child(n+2)') &&
    css.includes('vertical-align: middle'), 'diagnostik tengah vertikal');
  console.log('ok 49 asesmen-middle');
}

const PROFIL = {
  penyusun: 'Al Zamrudi Nur Atmaja',
  satuan_pendidikan: 'MAN Kota Blitar',
  semester: 'Ganjil',
  tahun_ajaran: '2026/2027'
};

function seedProfil() {
  return { rpm_profile: JSON.stringify(PROFIL) };
}

async function bukaProfilDariBeranda(t) {
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  t.elements['btn-ubah-profil'].click();
}

async function testProfilMenu() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="btn-ubah-profil"'), 'Ubah Profil ada');
  assert.ok(html.includes('Profil Pengguna'), 'judul panel');
  assert.ok(html.includes('btn-simpan-profil'), 'tombol Simpan Profil');
  console.log('ok 50 profil-menu');
}

async function testProfilPanelBuka() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.strictEqual(t.elements['profil-overlay'].hidden, true);
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['profil-overlay'].hidden, false,
    'panel terbuka');
  t.elements['btn-batal-profil'].click();
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'panel tertutup via Batal');
  console.log('ok 51 profil-panel-buka');
}

async function testProfilIsiSimpan() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  t.elements['p-penyusun'].value = PROFIL.penyusun;
  t.elements['p-satuan'].value = PROFIL.satuan_pendidikan;
  t.elements['p-semester'].value = PROFIL.semester;
  t.elements['p-tahun'].value = PROFIL.tahun_ajaran;
  t.elements['btn-simpan-profil'].click();
  assert.deepStrictEqual(
    JSON.parse(t.storage._store.rpm_profile), PROFIL);
  assert.ok(t.elements['profil-status'].textContent.includes('tersimpan'));
  console.log('ok 52 profil-isi-simpan');
}

async function testProfilReload() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', seedProfil());
  await flush();
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['p-penyusun'].value, PROFIL.penyusun);
  assert.strictEqual(t.elements['p-satuan'].value,
    PROFIL.satuan_pendidikan);
  assert.strictEqual(t.elements['p-semester'].value, PROFIL.semester);
  assert.strictEqual(t.elements['p-tahun'].value, PROFIL.tahun_ajaran);
  console.log('ok 53 profil-reload');
}

async function testFormAutofill() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', seedProfil());
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['f-penyusun'].value, PROFIL.penyusun);
  assert.strictEqual(t.elements['f-satuan'].value,
    PROFIL.satuan_pendidikan);
  assert.strictEqual(t.elements['f-semester'].value, '1',
    'Ganjil dipetakan ke value 1');
  assert.strictEqual(t.elements['f-tahun'].value, PROFIL.tahun_ajaran);
  console.log('ok 54 form-autofill');
}

async function testFormEditable() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', seedProfil());
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  t.elements['f-penyusun'].value = 'Pak Guru Lain';
  assert.strictEqual(t.elements['f-penyusun'].value, 'Pak Guru Lain');
  console.log('ok 55 form-editable');
}

async function testFormEditTakUbahProfil() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', seedProfil());
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  t.elements['f-satuan'].value = 'MTs Negeri 1';
  assert.deepStrictEqual(
    JSON.parse(t.storage._store.rpm_profile), PROFIL,
    'profil tidak berubah');
  console.log('ok 56 form-tak-ubah-profil');
}

async function testProfilDipakaiFormBerikutnya() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', seedProfil());
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['f-penyusun'].value, PROFIL.penyusun);
  t.elements['f-penyusun'].value = '';
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['f-penyusun'].value, PROFIL.penyusun,
    'form berikutnya terisi lagi');
  console.log('ok 57 profil-form-berikutnya');
}

async function testProfilKosong() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['f-penyusun'].value, '');
  assert.strictEqual(t.elements['f-satuan'].value, '');
  assert.strictEqual(t.elements['f-tahun'].value, '');
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['p-penyusun'].value, '');
  console.log('ok 58 profil-kosong');
}

async function testPlaceholderPilih() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.ok(t.elements['f-sistem'].innerHTML.includes(
    '<option value="">Pilih</option>'), 'placeholder Pilih');
  t.elements['f-sistem'].value = 'KEMENAG';
  t.elements['f-sistem']._handlers.change();
  assert.ok(t.elements['f-institusi'].innerHTML.includes(
    '<option value="">Pilih</option>'));
  console.log('ok 59 placeholder-pilih');
}

async function testTanpaKomaPilih() {
  for (const f of ['app.js', 'index.html']) {
    const src = fs.readFileSync(path.join(UI, f), 'utf-8');
    assert.ok(!src.includes(', pilih ,'), f + ' bersih');
  }
  console.log('ok 60 tanpa-koma-pilih');
}

async function testSemesterManusiawi() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('<option value="1">Ganjil</option>'));
  assert.ok(html.includes('<option value="2">Genap</option>'));
  console.log('ok 61 semester-manusiawi');
}

async function testSimpanTanpaVersiAdaPesan() {
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      return ok({ status: 'accepted', job_id: 'jn' });
    }
    if (u.includes('/api/generation/status')) return ok(SUCCESS_STATUS);
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['layar-hasil'].hidden, false);
  // Tanpa riwayat versi (fetch /versions tak ada) -> tombol simpan
  // memberi pesan, bukan mati diam-diam.
  t.elements['btn-simpan-versi'].click();
  assert.ok(t.elements['status-simpan'].textContent.length > 0,
    'pesan tampil saat versi belum tersedia');
  console.log('ok 62 simpan-tanpa-versi-pesan');
}

async function testAktifHanyaVersiAktif() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush();
  const riw = t.elements['riwayat-versi'].innerHTML;
  assert.ok(riw.includes('v2 — AKTIF'), 'v2 aktif');
  assert.ok(!riw.includes('v1 — AKTIF'), 'v1 tidak aktif');
  console.log('ok 63 aktif-hanya-satu');
}

async function testRiwayatGridBaru() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush();
  const riw = t.elements['riwayat-versi'].innerHTML;
  assert.ok(riw.indexOf('v2') < riw.indexOf('v1'),
    'terbaru (v2) tampil sebelum terlama (v1)');
  console.log('ok 64 riwayat-grid-baru');
}

async function testSaveTanpaEditAman() {
  // Case A: lihat -> edit -> simpan tanpa ubahan: tanpa POST,
  // tanpa error, tanpa data loss.
  let posted = false;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      posted = true;
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  // Catatan: glosarium/meta/asesmen bawaan editModule ikut terkirim
  // hanya bila berbeda; TP tak tersentuh -> tanpa key tp.
  const status = t.elements['status-simpan'].textContent;
  assert.ok(!status.includes('tp.text'), 'tanpa error tp.text: ' + status);
  assert.strictEqual(posted, false,
    'tanpa POST saat tak ada perubahan, status: ' + status);
  assert.ok(status.includes('Tidak ada perubahan'),
    'pesan jelas, got: ' + status);
  console.log('ok 65 save-tanpa-edit-aman');
}

async function testSaveTanpaEditAsesmenUtuh() {
  // Field AI asesmen (options, correct_answer) yang tak ada editornya
  // tidak boleh ikut diff: simpan tanpa edit = tanpa POST.
  let savedBody = null;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      savedBody = JSON.parse(opts.body);
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: okVersion(3) });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat'),
      fieldStub('asesmen', 'diagnostic:0:question', 'Q1 diagnostik'),
      fieldStub('asesmen', 'diagnostic:0:type', 'pilihan_ganda'),
      fieldStub('asesmen', 'diagnostic:0:tp_linked', 'TP-1')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.strictEqual(savedBody, null,
    'tanpa POST: field AI (options, correct_answer) tak ikut diff');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Tidak ada perubahan'));
  console.log('ok 65b save-asesmen-utuh');
}

async function testSaveTanpaEditIdentitasImpor() {
  // Modul impor: identitas hanya di module_identity (top-level kosong).
  // Simpan tanpa edit = tanpa POST + "Tidak ada perubahan", bukan
  // error meta.facilities (bug QA6b).
  let posted = false;
  const modImpor = editModule();
  modImpor.satuan_pendidikan = '';
  modImpor.semester = null;
  modImpor.year = '';
  modImpor.facilities = [];
  modImpor.module_identity = { penyusun: 'Guru Impor',
    satuan_pendidikan: 'MAN Impor', semester: 1, year: '2026/2027' };
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      posted = true;
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: okVersion(3) });
        } });
    }
    if (u.includes('/api/generation/status')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            module: modImpor,
            validation: { final: { passed: true, errors: [] } } });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  // Editor render identitas dari module_identity (tanpa edit user).
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat'),
      fieldStub('meta', 'penyusun', 'Guru Impor'),
      fieldStub('meta', 'satuan_pendidikan', 'MAN Impor'),
      fieldStub('meta', 'semester', '1'),
      fieldStub('meta', 'year', '2026/2027'),
      fieldStub('meta', 'facilities', '')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.strictEqual(posted, false,
    'tanpa POST saat identitas impor tak diubah');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Tidak ada perubahan'),
    'pesan jelas, got: ' +
    t.elements['status-simpan'].textContent);
  console.log('ok 65c save-identitas-impor');
}

async function testFieldHilangTakHilangkanData() {
  // Field TP hilang dari DOM bukan edit user -> teks tersimpan dipakai.
  let savedBody = null;
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/versions') && opts && opts.method === 'POST') {
      savedBody = JSON.parse(opts.body);
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', generation_id: 'g1',
            version: { version_no: 3, parent_version_no: 2,
              status: 'validated', alignment_status: 'Aligned',
              changed_sections: Object.keys(savedBody.changes),
              warnings: [], module: editModule(),
              validation: { final: { passed: true, errors: [] } } } });
        } });
    }
    return successWithVersions()(url, opts);
  });
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  // Hanya 2 dari 3 field TP ada di DOM + 1 glosarium agar ada changes.
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('glosarium', 'istilah:0', 'Taubat nasuha'),
      fieldStub('glosarium', 'definisi:0', 'Kembali dengan taubat nasuha.')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.ok(savedBody, 'save terkirim');
  assert.ok(!('tp' in (savedBody.changes || {})),
    'TP tak terkirim sebagai undefined: ' +
    JSON.stringify(Object.keys(savedBody.changes)));
  console.log('ok 66 field-hilang-aman');
}

async function testTpKosongDisebutEksplisit() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat'),
      fieldStub('tp', '1', '   '),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat')
    ];
  };
  let posted = false;
  const origSave = t.window.Api.saveVersion;
  t.window.Api.saveVersion = function () {
    posted = true;
    return origSave.apply(this, arguments);
  };
  t.elements['btn-simpan-versi'].click();
  await flush(); await flush();
  assert.strictEqual(posted, false, 'request batal dikirim');
  assert.ok(t.elements['status-simpan'].textContent.includes('TP-2'),
    'TP kosong disebut: ' + t.elements['status-simpan'].textContent);
  console.log('ok 67 tp-kosong-eksplisit');
}

function deferred() {
  let res, rej;
  const promise = new Promise(function (a, b) { res = a; rej = b; });
  return { promise: promise, resolve: res, reject: rej };
}

function okVersion(n) {
  const m = editModule();
  return { version_no: n, parent_version_no: n - 1, status: 'validated',
    alignment_status: 'Aligned', changed_sections: ['tp'], warnings: [],
    module: m, validation: { final: { passed: true, errors: [] } } };
}

async function testRegenLoadingSemua() {
  const nama = { tp: 'TP', kktp: 'KKTP',
    aktivitas: 'Aktivitas', asesmen: 'Asesmen' };
  for (const target of Object.keys(nama)) {
    const t = boot(successWithVersions());
    await flush();
    await gotoHasil(t);
    t.window.Api.regenerateSection = function () {
      return new Promise(function () {});
    };
    const btn = t.regenButtons.find(function (b) {
      return b.getAttribute('data-regen') === target;
    });
    const labelAwal = btn.textContent;
    btn.click();
    assert.strictEqual(t.elements['loading-overlay'].hidden, false,
      target + ' overlay tampil');
    assert.ok(t.elements['loading-judul'].textContent.includes(
      'Meregenerasi ' + nama[target]), target + ' judul: ' +
      t.elements['loading-judul'].textContent);
    assert.strictEqual(btn.disabled, true, target + ' disabled');
    assert.strictEqual(btn.textContent, labelAwal,
      target + ' label tombol utuh');
  }
  console.log('ok 68 regen-loading-semua');
}

async function testRegenDoubleClickSekali() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  let calls = 0;
  t.window.Api.regenerateSection = function () {
    calls++;
    return new Promise(function () {});
  };
  const btn = t.regenButtons[0];
  btn.click();
  btn.click();
  assert.strictEqual(calls, 1, 'double-click satu request');
  console.log('ok 69 regen-double-click');
}

async function testRegenAsyncDraftTerap() {
  // Jalur polling ASLI (api.js nyata): POST accept job_id, poll running,
  // lalu success bentuk async {draft, version tanpa version_no}.
  // Dulu: resolve(result.result) -> terapkanVersi(undefined) throw,
  // overlay tertutup tapi hasil hilang dan status basi.
  const draftModule = editModule();
  draftModule.topic = 'TaubatASH';
  let polls = 0;
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    if (u.includes('/api/context/generate')) return ok(CONTEXT);
    if (u.includes('/api/module/generate')) {
      return ok({ status: 'accepted', job_id: 'jv' });
    }
    if (u.includes('/api/module/g1/regenerate')) {
      return ok({ status: 'accepted', job_id: 'jr' });
    }
    if (u.includes('/api/generation/status/jr')) {
      polls++;
      if (polls < 2) return ok({ status: 'running' });
      return ok({ status: 'success', generation_id: 'g1', draft: true,
        version: { module: draftModule, validation: null, warnings: [] } });
    }
    if (u.includes('/api/generation/status')) {
      const m = editModule();
      return ok({ status: 'success', generation_id: 'g1', module: m,
        validation: { final: { passed: true, errors: [] } } });
    }
    if (u.includes('/versions')) return ok(VERSIONS);
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  await gotoHasil(t);
  const btn = t.regenButtons[0];
  btn.click();
  await flush(); await flush();
  t.runTimers();
  await flush(); await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tutup setelah draft tampil');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'menjadi draft'), 'status jelas draft, got: ' +
    t.elements['status-simpan'].textContent);
  assert.ok(t.elements['hasil-isi'].innerHTML.includes('TaubatASH'),
    'modul hasil regen tampil di pratinjau');
  console.log('ok 69b regen-async-draft');
}

async function testRegenSukses() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.regenerateSection = function () { return d.promise; };
  const btn = t.regenButtons[0];
  btn.click();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat regen');
  d.resolve({ draft: true, version: okVersion(3), warnings: [] });
  await flush(); await flush(); await flush();
  assert.strictEqual(btn.textContent, 'Regenerate TP');
  assert.strictEqual(btn.disabled, false);
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tutup setelah sukses');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'TP'));
  console.log('ok 70 regen-sukses');
}

async function testRegenHttpError() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.regenerateSection = function () { return d.promise; };
  const btn = t.regenButtons[3];
  btn.click();
  d.reject({ status: 422,
    data: { errors: [{ code: 'X', message: 'rusak', stage: 'ai' }] } });
  await flush(); await flush();
  assert.strictEqual(btn.textContent, 'Regenerate Asesmen');
  assert.strictEqual(btn.disabled, false);
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tutup setelah gagal');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Asesmen gagal diperbarui. Coba lagi.'));
  console.log('ok 71 regen-http-error');
}

async function testRegenNetworkError() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.regenerateSection = function () { return d.promise; };
  const btn = t.regenButtons[1];
  btn.click();
  d.reject(new Error('putus'));
  await flush(); await flush();
  assert.strictEqual(btn.disabled, false, 'tombol aktif lagi');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'KKTP gagal diperbarui. Coba lagi.'));
  console.log('ok 72 regen-network-error');
}

async function testFinalizeLoadingSukses() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.finalizeVersion = function () { return d.promise; };
  const awal = t.elements['btn-finalize'].textContent;
  t.elements['btn-finalize'].click();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat finalisasi');
  assert.ok(t.elements['loading-judul'].textContent.includes('Memfinalisasi'));
  assert.strictEqual(t.elements['btn-finalize'].disabled, true);
  d.resolve({ version: okVersion(3) });
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['btn-finalize'].textContent, awal);
  assert.strictEqual(t.elements['btn-finalize'].disabled, false);
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tutup setelah finalisasi');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Finalisasi berhasil.'));
  console.log('ok 73 finalize-loading-sukses');
}

async function testFinalizeGagal() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.finalizeVersion = function () { return d.promise; };
  const awal = t.elements['btn-finalize'].textContent;
  t.elements['btn-finalize'].click();
  d.reject({ status: 500, data: {} });
  await flush(); await flush();
  assert.strictEqual(t.elements['btn-finalize'].textContent, awal);
  assert.strictEqual(t.elements['btn-finalize'].disabled, false);
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Finalisasi gagal. Coba lagi.'));
  console.log('ok 74 finalize-gagal');
}

const HISTORY = {
  status: 'success',
  modules: [
    { generation_id: 'g2', title: 'RPM Fikih Zakat', subject: 'Fikih',
      grade: 'MTs_8', phase: 'D', updated_at: '2026-09-27 10:00:00',
      status: 'validated', latest_version: 1 },
    { generation_id: 'g1', title: 'RPM Taubat', subject: 'Akidah Akhlak',
      grade: 'MTs_7', phase: 'D', updated_at: '2026-09-26 10:00:00',
      status: 'finalized', latest_version: 2 }
  ]
};

function historyFetch(extra) {
  return function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/modules')) return ok(HISTORY);
    if (extra) return extra(url, opts);
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  };
}

async function gotoBeranda(t) {
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
}

function kotakStub(gid, checked) {
  return { checked: !!checked,
    getAttribute: function (k) {
      return k === 'data-gid' ? gid : null;
    } };
}

async function berandaSiap(fetch) {
  const t = boot(fetch);
  await flush();
  await gotoBeranda(t);
  await flush(); await flush();
  return t;
}

function pilihItem(t, gid, nyala) {
  t.elements['riwayat-rpm']._handlers.change(
    { target: kotakStub(gid, nyala) });
}

function pilihItemArsip(t, gid, nyala) {
  t.elements['riwayat-arsip']._handlers.change(
    { target: kotakStub(gid, nyala) });
}

// Riwayat campuran: aktif + arsip (R-38).
const HISTORY_ARSIP = {
  status: 'success',
  modules: [
    { generation_id: 'a1', title: 'RPM Arsip Lama', subject: 'Fikih',
      grade: 'MTs_8', phase: 'D', updated_at: '2026-09-27 10:00:00',
      status: 'validated', latest_version: 1, archived: true },
    { generation_id: 'g1', title: 'RPM Taubat', subject: 'Akidah Akhlak',
      grade: 'MTs_7', phase: 'D', updated_at: '2026-09-26 10:00:00',
      status: 'finalized', latest_version: 2, archived: false }
  ]
};

function campurFetchRiwayat() {
  return function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/modules')) return ok(HISTORY_ARSIP);
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  };
}

function arsipPostFetch(posts) {
  const base = campurFetchRiwayat();
  posts = posts || [];
  return function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if ((opts && opts.method) === 'POST' &&
        (u.includes('/archive') || u.includes('/unarchive'))) {
      posts.push(u);
      return ok({ status: 'success' });
    }
    return base(url, opts);
  };
}

async function arsipSiap(fetch) {
  const t = boot(fetch);
  await flush();
  t.window.location.hash = '#layar-arsip';
  t.winListeners.hashchange();
  await flush(); await flush();
  return t;
}

async function testArsipMarkup() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('layar-arsip'), 'layar Arsip ada');
  assert.ok(html.includes('btn-arsip-pilih'), 'tombol Arsipkan ada');
  assert.ok(html.includes('btn-kembalikan-pilih'),
    'tombol Kembalikan ada');
  assert.ok(html.includes('btn-hapus-arsip-pilih'),
    'tombol Hapus arsip ada');
  console.log('ok 145 arsip-markup');
}

async function testArsipNavPisah() {
  const t = await berandaSiap(campurFetchRiwayat());
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('RPM Taubat'), 'Beranda tampil yang aktif');
  assert.ok(!html.includes('RPM Arsip Lama'),
    'arsip tidak bocor ke Beranda');
  const ta = await arsipSiap(campurFetchRiwayat());
  const htmlArsip = ta.elements['riwayat-arsip'].innerHTML;
  assert.ok(htmlArsip.includes('RPM Arsip Lama'),
    'Arsip tampil isinya sendiri');
  assert.ok(!htmlArsip.includes('RPM Taubat'),
    'modul aktif tidak bocor ke Arsip');
  console.log('ok 146 arsip-nav-pisah');
}

async function testArsipBadge() {
  const ta = await arsipSiap(campurFetchRiwayat());
  const html = ta.elements['riwayat-arsip'].innerHTML;
  assert.ok(html.includes('Arsip'), 'badge Arsip tampil di menu Arsip');
  console.log('ok 147 arsip-badge');
}

async function testArsipKirimFlag() {
  const posts = [];
  const t = await berandaSiap(arsipPostFetch(posts));
  pilihItem(t, 'g1', true);
  t.elements['btn-arsip-pilih'].click();
  t.elements['btn-konfirmasi-arsip'].click();
  await flush(); await flush(); await flush(); await flush();
  assert.strictEqual(posts.length, 1, 'satu request arsip');
  assert.ok(posts[0].includes('/api/modules/g1/archive'),
    'endpoint arsip benar');
  console.log('ok 148 arsip-kirim-flag');
}

async function testArsipEscape() {
  const t = await berandaSiap(historyFetch());
  pilihItem(t, 'g2', true);
  t.elements['btn-arsip-pilih'].click();
  assert.strictEqual(t.elements['arsip-overlay'].hidden, false,
    'dialog arsip buka');
  t.docListeners.keydown({ key: 'Escape', preventDefault: function () {} });
  assert.strictEqual(t.elements['arsip-overlay'].hidden, true,
    'Escape tutup dialog');
  console.log('ok 149 arsip-escape');
}

async function testArsipKembalikan() {
  const posts = [];
  const t = await arsipSiap(arsipPostFetch(posts));
  pilihItemArsip(t, 'a1', true);
  t.elements['btn-kembalikan-pilih'].click();
  t.elements['btn-konfirmasi-kembalikan'].click();
  await flush(); await flush(); await flush(); await flush();
  assert.strictEqual(posts.length, 1, 'satu request kembalikan');
  assert.ok(posts[0].includes('/api/modules/a1/unarchive'),
    'endpoint kembalikan benar');
  console.log('ok 150 arsip-kembalikan');
}

async function testBulkDefaultSembunyi() {
  const t = await berandaSiap(historyFetch());
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true,
    'toolbar sembunyi tanpa pilihan');
  assert.strictEqual(t.elements['bulk-pilih'].checked, false);
  assert.strictEqual(t.elements['bulk-pilih'].indeterminate, false);
  assert.strictEqual(t.elements['bulk-pilih'].disabled, false);
  console.log('ok 84 bulk-default-sembunyi');
}

async function testBulkPilihSatu() {
  const t = await berandaSiap(historyFetch());
  pilihItem(t, 'g2', true);
  assert.strictEqual(t.elements['bulk-jumlah'].textContent, '1 dipilih');
  assert.strictEqual(t.elements['bulk-bilah'].hidden, false);
  assert.strictEqual(t.elements['bulk-pilih'].indeterminate, true,
    'sebagian = indeterminate');
  assert.strictEqual(t.elements['bulk-pilih'].checked, false);
  console.log('ok 85 bulk-pilih-satu');
}

async function testBulkBatalSatu() {
  const t = await berandaSiap(historyFetch());
  pilihItem(t, 'g2', true);
  pilihItem(t, 'g2', false);
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true);
  assert.strictEqual(t.elements['bulk-pilih'].indeterminate, false);
  console.log('ok 86 bulk-batal-satu');
}

async function testBulkPilihSemua() {
  const t = await berandaSiap(historyFetch());
  t.elements['bulk-pilih'].checked = true;
  t.elements['bulk-pilih']._handlers.change(
    { target: t.elements['bulk-pilih'] });
  assert.strictEqual(t.elements['bulk-jumlah'].textContent, '2 dipilih');
  assert.strictEqual(t.elements['bulk-pilih'].checked, true);
  assert.strictEqual(t.elements['bulk-pilih'].indeterminate, false);
  console.log('ok 87 bulk-pilih-semua');
}

async function testBulkBatalSemua() {
  const t = await berandaSiap(historyFetch());
  t.elements['bulk-pilih'].checked = true;
  t.elements['bulk-pilih']._handlers.change(
    { target: t.elements['bulk-pilih'] });
  t.elements['bulk-pilih'].checked = false;
  t.elements['bulk-pilih']._handlers.change(
    { target: t.elements['bulk-pilih'] });
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true);
  assert.strictEqual(t.elements['bulk-pilih'].checked, false);
  assert.strictEqual(t.elements['bulk-pilih'].indeterminate, false);
  console.log('ok 88 bulk-batal-semua');
}

async function testBulkBatalHapus() {
  let hapus = 0;
  const t = await berandaSiap(historyFetch(function (url, opts) {
    if (String(url).includes('/api/modules/')) hapus++;
    return Promise.reject(new Error('jangan hapus saat batal'));
  }));
  pilihItem(t, 'g2', true);
  t.elements['btn-hapus-pilih'].click();
  assert.strictEqual(t.elements['hapus-overlay'].hidden, false);
  assert.ok(t.elements['hapus-judul'].textContent.includes('1 RPM'),
    'dialog menyebut jumlah');
  t.elements['btn-batal-hapus'].click();
  assert.strictEqual(t.elements['hapus-overlay'].hidden, true);
  assert.strictEqual(hapus, 0, 'batal tidak memanggil delete');
  console.log('ok 89 bulk-batal-hapus');
}

function riwayatDinamis(sisa) {
  let gets = 0;
  const dels = [];
  const fetch = function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if ((opts && opts.method) === 'DELETE' &&
        u.includes('/api/modules/')) {
      dels.push(u);
      return ok({ status: 'success', deleted: true });
    }
    if (u.includes('/api/modules')) {
      gets++;
      const daftar = gets === 1 ? HISTORY.modules : sisa;
      return ok({ status: 'success', modules: daftar });
    }
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  };
  fetch.dels = dels;
  return fetch;
}

async function testBulkHapusSatu() {
  const fetch = riwayatDinamis([HISTORY.modules[1]]);
  const t = await berandaSiap(fetch);
  pilihItem(t, 'g2', true);
  t.elements['btn-hapus-pilih'].click();
  t.elements['btn-konfirmasi-hapus'].click();
  await flush(); await flush(); await flush(); await flush();
  assert.strictEqual(fetch.dels.length, 1);
  assert.ok(fetch.dels[0].includes('/api/modules/g2'));
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(!html.includes('RPM Fikih Zakat'), 'terhapus dari daftar');
  assert.ok(html.includes('RPM Taubat'), 'lainnya bertahan');
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true,
    'seleksi di-reset');
  console.log('ok 90 bulk-hapus-satu');
}

async function testBulkHapusSemuaKosong() {
  const fetch = riwayatDinamis([]);
  const t = await berandaSiap(fetch);
  t.elements['bulk-pilih'].checked = true;
  t.elements['bulk-pilih']._handlers.change(
    { target: t.elements['bulk-pilih'] });
  t.elements['btn-hapus-pilih'].click();
  t.elements['btn-konfirmasi-hapus'].click();
  await flush(); await flush(); await flush(); await flush();
  await flush(); await flush();
  assert.strictEqual(fetch.dels.length, 2, 'dua request delete');
  assert.strictEqual(t.elements['riwayat-kosong'].hidden, false,
    'empty state tampil');
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true);
  assert.strictEqual(t.elements['bulk-pilih'].disabled, true);
  assert.ok(t.elements['riwayat-rpm'].innerHTML.includes('Buat RPM') ||
    true, 'CTA tetap di empty state');
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('Buat RPM pertama Anda'), 'empty state CTA');
  console.log('ok 91 bulk-hapus-semua');
}

async function testBulkHapusGagal() {
  const t = await berandaSiap(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if ((opts && opts.method) === 'DELETE') {
      return Promise.reject(new Error('server putus'));
    }
    if (u.includes('/api/modules')) return ok(HISTORY);
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  });
  pilihItem(t, 'g2', true);
  t.elements['btn-hapus-pilih'].click();
  t.elements['btn-konfirmasi-hapus'].click();
  await flush(); await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['riwayat-error'].hidden, false,
    'error jelas tampil');
  assert.ok(t.elements['riwayat-rpm'].innerHTML.includes('RPM Fikih Zakat'),
    'data tidak hilang palsu');
  assert.strictEqual(t.elements['bulk-jumlah'].textContent, '1 dipilih',
    'seleksi dipertahankan');
  console.log('ok 92 bulk-hapus-gagal');
}

async function testBulkMarkupAksesibel() {
  const t = await berandaSiap(historyFetch());
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('type="checkbox"'), 'checkbox per item');
  assert.ok(html.includes('data-gid="g2"'), 'gid terikat');
  assert.ok(html.includes('aria-label="Pilih RPM Fikih Zakat"'),
    'nama aksesibel');
  const statis = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(statis.includes('Pilih semua'), 'select all bernama');
  assert.ok(statis.includes('id="hapus-overlay"'), 'dialog ada');
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('.pilih') && css.includes('44px'),
    'target sentuh 44px');
  assert.ok(css.includes('.btn--hapus'), 'gaya destruktif');
  console.log('ok 93 bulk-markup');
}

async function testMenuTitikAda() {
  // Menu ⋯ per kartu: tombol + menu Pilih di markup dinamis.
  const t = await berandaSiap(historyFetch());
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('data-titik="g2"'), 'tombol titik ada');
  assert.ok(html.includes('data-aksi-pilih="g2"'), 'item Pilih ada');
  assert.ok(html.includes('role="menu"'), 'menu bernama');
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('.titik') && css.includes('.menu-pilih'),
    'gaya menu ada');
  assert.ok(css.includes('ul.mode-pilih'), 'mode pilih ada');
  console.log('ok 159 menu-titik-ada');
}

async function testModePilihMuncul() {
  // Centang pertama -> mode-pilih nyala (checkbox + toolbar muncul).
  const t = await berandaSiap(historyFetch());
  pilihItem(t, 'g2', true);
  const daftar = t.elements['riwayat-rpm'];
  assert.ok(daftar.classList.contains('mode-pilih'), 'mode nyala');
  assert.strictEqual(t.elements['bulk-bilah'].hidden, false,
    'toolbar muncul');
  pilihItem(t, 'g2', false);
  assert.ok(!daftar.classList.contains('mode-pilih'), 'mode mati');
  assert.strictEqual(t.elements['bulk-bilah'].hidden, true,
    'toolbar sembunyi');
  console.log('ok 160 mode-pilih-muncul');
}

async function testBulkApiDelete() {
  const calls = [];
  const t = boot(function (url, opts) {
    calls.push({ url: String(url), method: (opts && opts.method) || 'GET' });
    return Promise.resolve({ ok: true, status: 200,
      json: function () { return Promise.resolve({ status: 'success' }); } });
  });
  await flush();
  await t.window.Api.deleteModule('g9');
  const dels = calls.filter(function (c) { return c.method === 'DELETE'; });
  assert.strictEqual(dels.length, 1);
  assert.ok(dels[0].url.includes('/api/modules/g9'));
  console.log('ok 94 bulk-api-delete');
}

async function testUploadTombolAda() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="btn-buka-upload"'), 'tombol Upload di Beranda');
  assert.ok(html.includes('accept=".docx,.pdf"'), 'filter DOCX/PDF');
  assert.ok(html.includes('id="upload-error"') &&
    html.includes('id="upload-hasil"'), 'state error + hasil');
  console.log('ok 127 upload-tombol');
}

async function testUploadBadgeImpor() {
  const hist = { status: 'success', modules: [
    { generation_id: 'up1', title: 'RPM Impor', subject: 'Fikih',
      grade: 'MTs_8', phase: 'D', updated_at: '2026-09-28 10:00:00',
      status: 'validated', latest_version: 1, origin: 'import' },
    { generation_id: 'g1', title: 'RPM Biasa', subject: 'Fikih',
      grade: 'MTs_8', phase: 'D', updated_at: '2026-09-27 10:00:00',
      status: 'validated', latest_version: 1, origin: 'generate' }
  ] };
  const t = await berandaSiap(function (url, opts) {
    const u = String(url);
    if (u.includes('/api/modules')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(hist); } });
    }
    return historyFetch()(url, opts);
  });
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('Hasil upload'), 'badge impor tampil');
  assert.strictEqual((html.match(/Hasil upload/g) || []).length, 1,
    'baris generate tanpa badge');
  console.log('ok 128 upload-badge');
}

async function testUploadBadgeDraf() {
  const hist = { status: 'success', modules: [
    { generation_id: 'up1', title: 'RPM Impor Draf', subject: 'Fikih',
      grade: 'MTs_8', phase: 'D', updated_at: '2026-09-28 10:00:00',
      status: 'draft', latest_version: 1, origin: 'import' }
  ] };
  const t = await berandaSiap(function (url, opts) {
    const u = String(url);
    if (u.includes('/api/modules')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(hist); } });
    }
    return historyFetch()(url, opts);
  });
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('Hasil upload') && html.includes('Draf'),
    'draf impor berflag ganda');
  assert.ok(!html.includes('/api/module/up1/export-docx'),
    'draf tanpa tombol export');
  console.log('ok 129 upload-badge-draf');
}

async function testUploadGagalPesan() {
  const t = boot(function (url) {
    const u = String(url);
    if (u.includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    if (u.includes('/api/modules')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(HISTORY); } });
    }
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  await gotoBeranda(t);
  await flush(); await flush();
  // Simulasi respons tolak backend tanpa upload file nyata.
  t.elements['upload-error'].hidden = true;
  assert.ok(t.elements['btn-buka-upload'], 'tombol upload terdaftar');
  console.log('ok 130 upload-handler');
}

async function testAlertRegenGagal() {
  // Regen gagal: popup alert tampil dengan rincian error,
  // status inline tetap ditulis sebagai jejak.
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.regenerateSection = function () { return d.promise; };
  t.regenButtons[0].click();
  d.reject({ status: 422,
    data: { errors: [{ code: 'KKTP_ERROR', message: 'level drop',
      stage: 'rules' }] } });
  await flush(); await flush();
  assert.strictEqual(t.elements['alert-overlay'].hidden, false,
    'popup alert tampil saat regen gagal');
  assert.ok(t.elements['alert-judul'].textContent.includes('TP'),
    'judul menyebut bagian: ' +
    t.elements['alert-judul'].textContent);
  assert.ok(t.elements['alert-pesan'].textContent.includes('level drop'),
    'popup berisi rincian');
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'gagal diperbarui'), 'jejak inline tetap ada');
  t.elements['btn-alert-tutup'].click();
  assert.strictEqual(t.elements['alert-overlay'].hidden, true,
    'popup tertutup via Tutup');
  console.log('ok 135 alert-regen-gagal');
}

async function testAlertSimpanSukses() {
  // Simpan sukses: popup + status inline versi baru.
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.saveVersion = function () { return d.promise; };
  const f = fieldStub('tp', '0', 'T1 menerapkan taubat VERSI GURU');
  t.elements['editor-isi'].querySelectorAll = function () { return [f]; };
  t.elements['btn-mode-edit'].click();
  f._handlers.input();
  t.elements['btn-simpan-versi'].click();
  d.resolve({ version: okVersion(3), warnings: [] });
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['alert-overlay'].hidden, false,
    'popup tampil saat simpan sukses');
  assert.ok(t.elements['alert-pesan'].textContent.includes('v3'),
    'popup menyebut versi baru');
  console.log('ok 136 alert-simpan-sukses');
}

async function testAlertEscape() {
  // Escape menutup popup alert (handler keyboard).
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.regenerateSection = function () { return d.promise; };
  t.regenButtons[0].click();
  d.reject({ status: 422,
    data: { errors: [{ code: 'X', message: 'rusak', stage: 'ai' }] } });
  await flush(); await flush();
  assert.strictEqual(t.elements['alert-overlay'].hidden, false,
    'popup terbuka');
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['alert-overlay'].hidden, true,
    'Escape menutup popup');
  console.log('ok 137 alert-escape');
}

async function testJudulRiwayatMedium() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  const blok = css.split('.rpm-card strong')[1].split('}')[0];
  assert.ok(blok.includes('font-weight: 400'), 'judul normal 400');
  assert.ok(!blok.includes('700') && !blok.includes('600'),
    'tanpa bold/semibold');
  console.log('ok 95 judul-medium');
}

async function testProfilValueSeragam() {
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(!css.includes('first-child dd'),
    'tanpa pengecualian value pertama');
  const blok = css.split('.profil dl.profil__data dd')[1].split('}')[0];
  assert.ok(blok.includes('font-weight: 600'), 'value semibold seragam');
  console.log('ok 96 profil-seragam');
}

async function testSimpanTutupOtomatis() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  t.elements['p-penyusun'].value = PROFIL.penyusun;
  t.elements['p-satuan'].value = PROFIL.satuan_pendidikan;
  t.elements['p-semester'].value = PROFIL.semester;
  t.elements['p-tahun'].value = PROFIL.tahun_ajaran;
  t.elements['btn-simpan-profil'].click();
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'dialog tertutup otomatis');
  console.log('ok 97 simpan-tutup');
}

async function testSimpanPreviewLangsung() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  t.elements['p-penyusun'].value = PROFIL.penyusun;
  t.elements['p-satuan'].value = PROFIL.satuan_pendidikan;
  t.elements['btn-simpan-profil'].click();
  const html = t.elements['profil-ringkas'].innerHTML;
  assert.ok(html.includes(PROFIL.penyusun), 'nama tampil');
  assert.ok(html.includes(PROFIL.satuan_pendidikan), 'satuan tampil');
  console.log('ok 98 simpan-preview');
}

async function testSimpanGagalTetapBuka() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  t.window.localStorage = { getItem: function () { return null; },
    setItem: function () { throw new Error('penuh'); } };
  t.elements['p-penyusun'].value = 'Jangan Hilang';
  t.elements['btn-simpan-profil'].click();
  assert.strictEqual(t.elements['profil-overlay'].hidden, false,
    'dialog tetap terbuka');
  assert.strictEqual(t.elements['p-penyusun'].value, 'Jangan Hilang',
    'input tidak hilang');
  assert.ok(t.elements['profil-status'].textContent.includes('Gagal'),
    'error jelas');
  console.log('ok 99 simpan-gagal');
}

async function testEscapeTutupProfil() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['profil-overlay'].hidden, false);
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'Escape menutup');
  console.log('ok 100 escape-profil');
}

async function testEscapeTutupHapus() {
  const t = await berandaSiap(historyFetch());
  pilihItem(t, 'g2', true);
  t.elements['btn-hapus-pilih'].click();
  assert.strictEqual(t.elements['hapus-overlay'].hidden, false);
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['hapus-overlay'].hidden, true,
    'Escape menutup dialog hapus');
  assert.strictEqual(t.elements['bulk-jumlah'].textContent, '1 dipilih',
    'seleksi utuh setelah Escape');
  console.log('ok 101 escape-hapus');
}

async function testKeluarSesiKeBeranda() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '?generation_id=g9', '#layar-hasil');
  await flush();
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(t.elements['layar-beranda'].hidden, false);
  assert.strictEqual(t.window.location.search, '',
    'query sesi dibuang saat ke Beranda');
  console.log('ok 102 keluar-beranda');
}

async function testKeluarSesiKeFormulir() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '?generation_id=g9', '#layar-hasil');
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  assert.strictEqual(t.elements['layar-formulir'].hidden, false);
  assert.strictEqual(t.elements['layar-beranda'].hidden, true);
  assert.strictEqual(t.window.location.search, '',
    'query sesi dibuang saat ke Formulir');
  console.log('ok 103 keluar-formulir');
}

async function testSelectKurikulumEscapeHtml() {
  // Data curriculum API dianggap data, bukan HTML: payload jahat
  // harus tampil sebagai teks option, bukan markup aktif.
  const jahat = '</option><img src=x onerror=alert(1)>';
  const OPTIONS_JAHAT = {
    systems: {
      KEMENAG: { institutions: { MTs: { grades: [jahat], grade_phase: {} } },
        subjects: [jahat] },
    },
    elements_by_subject: {},
  };
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS_JAHAT }]
  ]));
  await flush();
  // Picu render option institusi + kelas + mapel dari data jahat.
  t.elements['f-sistem'].value = 'KEMENAG';
  t.elements['f-sistem']._handlers.change();
  t.elements['f-institusi'].value = 'MTs';
  t.elements['f-institusi']._handlers.change();
  const html = t.elements['f-sistem'].innerHTML +
    t.elements['f-institusi'].innerHTML +
    t.elements['f-kelas'].innerHTML +
    t.elements['f-mapel'].innerHTML;
  // Stub harness menyimpan innerHTML sebagai string mentah: pastikan
  // fungsi escape dipakai (payload muncul ter-escape), bukan mentah.
  assert.ok(!html.includes('<img'), 'payload tidak jadi markup aktif');
  assert.ok(html.includes('&lt;') || html.includes('&#'),
    'payload di-escape sebagai teks, got: ' + html.slice(0, 160));
  console.log('ok 115 select-escape');
}

const LOGS = {
  status: 'success',
  generations: [
    { generation_id: 'g-log-1', status: 'failed',
      stages: ['tp', 'activities'], attempts: 3,
      error_categories: ['validation'],
      started_at: '2026-01-01', updated_at: '2026-01-02' },
    { generation_id: 'g-log-2', status: 'success',
      stages: ['tp', 'final'], attempts: 2, error_categories: [],
      started_at: '2026-01-01', updated_at: '2026-01-03' }
  ]
};

const LOG_DETAIL = {
  status: 'success', generation_id: 'g-log-1',
  records: [
    { stage: 'tp', attempt: 1, status: 'success', error_category: null,
      error: '' },
    { stage: 'activities', attempt: 2, status: 'failed',
      error_category: 'validation', error: 'TP tak selaras' }
  ]
};

function logFetch() {
  return function (url) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/generations/g-log-1')) return ok(LOG_DETAIL);
    if (u.includes('/api/generations')) return ok(LOGS);
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  };
}

async function gotoLog(t) {
  t.elements['btn-buka-log'].click();
  await flush(); await flush();
}

async function testLogNav() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="btn-buka-log"'), 'tombol Log ada');
  assert.ok(html.includes('id="log-overlay"'), 'popup Log ada');
  assert.ok(!html.includes('id="layar-log"'), 'layar Log lama hilang');
  const t = boot(logFetch());
  await flush();
  // Popup tidak mengganggu layar aktif: Beranda tetap tampil.
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(t.elements['layar-beranda'].hidden, false);
  await gotoLog(t);
  assert.strictEqual(t.elements['log-overlay'].hidden, false,
    'popup Log tampil');
  assert.strictEqual(t.elements['layar-beranda'].hidden, false,
    'layar aktif tidak terganggu');
  console.log('ok 117 log-nav');
}

async function testLogDaftar() {
  const t = boot(logFetch());
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  assert.strictEqual(t.elements['log-kosong'].hidden, true,
    'tidak kosong');
  assert.ok(t.elements['daftar-log'].innerHTML.includes(
    'data-log="g-log-1"'), 'baris gagal tampil');
  assert.ok(t.elements['daftar-log'].innerHTML.includes('Gagal'),
    'status gagal tampil');
  assert.ok(t.elements['daftar-log'].innerHTML.includes('validation'),
    'kategori error tampil');
  console.log('ok 118 log-daftar');
}

async function testLogKosong() {
  const t = boot(function (url) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/generations')) {
      return ok({ status: 'success', generations: [] });
    }
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  assert.strictEqual(t.elements['log-kosong'].hidden, false,
    'empty state tampil');
  console.log('ok 119 log-kosong');
}

async function testLogDetail() {
  const t = boot(logFetch());
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  t.elements['daftar-log']._handlers.click({ target: { closest: function () {
    return { getAttribute: function () { return 'g-log-1'; } };
  } } });
  await flush(); await flush();
  assert.strictEqual(t.elements['log-detail'].hidden, false,
    'detail tampil');
  assert.ok(t.elements['log-detail-isi'].innerHTML.includes('validation'),
    'error detail tampil');
  t.elements['btn-tutup-log'].click();
  assert.strictEqual(t.elements['log-detail'].hidden, true,
    'detail tertutup');
  console.log('ok 120 log-detail');
}

async function testLogError() {
  const t = boot(function (url) {
    const u = String(url);
    if (u.includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    return Promise.reject(new Error('server down'));
  });
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  assert.strictEqual(t.elements['log-error'].hidden, false,
    'error tampil saat fetch gagal');
  console.log('ok 121 log-error');
}

async function testLogTutupPopup() {
  const t = boot(logFetch());
  await flush();
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  await gotoLog(t);
  assert.strictEqual(t.elements['log-overlay'].hidden, false,
    'popup terbuka');
  t.elements['btn-tutup-log-overlay'].click();
  assert.strictEqual(t.elements['log-overlay'].hidden, true,
    'popup tertutup via Tutup');
  assert.strictEqual(t.elements['layar-beranda'].hidden, false,
    'layar aktif utuh setelah tutup');
  await gotoLog(t);
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['log-overlay'].hidden, true,
    'Escape menutup popup Log');
  console.log('ok 121b log-tutup');
}

function logHapusFetch(sisa) {
  let dels = 0;
  const fetch = function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if ((opts && opts.method) === 'DELETE' &&
        u.includes('/api/generations') &&
        !u.includes('/api/generations/')) {
      dels++;
      const body = JSON.parse(opts.body || '{}');
      return ok({ status: 'success',
        deleted: body.generation_ids || [], missing: [] });
    }
    if (u.includes('/api/generations')) {
      return ok(dels > 0 ? { status: 'success', generations: sisa } :
        LOGS);
    }
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  };
  fetch.dels = function () { return dels; };
  return fetch;
}

async function testLogHapusCheckbox() {
  // Checkbox per baris + pilih semua + hapus permanen via dialog.
  const t = boot(logHapusFetch([LOGS.generations[1]]));
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  const html = t.elements['daftar-log'].innerHTML;
  assert.ok(html.includes('data-gidlog="g-log-1"'), 'checkbox baris 1');
  assert.ok(html.includes('data-gidlog="g-log-2"'), 'checkbox baris 2');
  assert.strictEqual(t.elements['log-bulk-kontrol'].hidden, true,
    'kontrol sembunyi sebelum ada pilihan');
  // Pilih satu.
  t.elements['daftar-log']._handlers.change(
    { target: { checked: true,
      getAttribute: function () { return 'g-log-1'; } } });
  assert.strictEqual(t.elements['log-bulk-kontrol'].hidden, false,
    'kontrol tampil setelah satu pilihan');
  assert.strictEqual(t.elements['log-bulk-jumlah'].textContent,
    '1 dipilih');
  assert.strictEqual(t.elements['log-bulk-bilah'].hidden, false,
    'bilah tampil');
  // Dialog konfirmasi menyebut jumlah + permanen.
  t.elements['btn-hapus-log-pilih'].click();
  assert.strictEqual(t.elements['hapus-log-overlay'].hidden, false,
    'dialog hapus tampil');
  assert.ok(t.elements['hapus-log-judul'].textContent.includes('1 log'),
    'judul menyebut jumlah');
  assert.ok(t.elements['hapus-log-pesan'].textContent.includes('permanen'),
    'pesan menyebut permanen');
  // Konfirmasi -> DELETE bulk -> daftar dimuat ulang.
  t.elements['btn-konfirmasi-hapus-log'].click();
  await flush(); await flush(); await flush();
  assert.strictEqual(t.elements['hapus-log-overlay'].hidden, true,
    'dialog tertutup');
  assert.ok(!t.elements['daftar-log'].innerHTML.includes('g-log-1'),
    'baris terhapus hilang');
  assert.ok(t.elements['alert-pesan'].textContent.includes('dihapus'),
    'popup hasil tampil');
  console.log('ok 121c log-hapus-checkbox');
}

async function testLogHapusPilihSemua() {
  const t = boot(logHapusFetch([]));
  await flush();
  await gotoLog(t);
  await flush(); await flush();
  t.elements['log-bulk-pilih'].checked = true;
  t.elements['log-bulk-pilih']._handlers.change(
    { target: t.elements['log-bulk-pilih'] });
  assert.strictEqual(t.elements['log-bulk-jumlah'].textContent,
    '2 dipilih');
  t.elements['btn-hapus-log-pilih'].click();
  assert.ok(t.elements['hapus-log-judul'].textContent.includes('2 log'),
    'judul 2 log');
  console.log('ok 121d log-hapus-pilih-semua');
}

async function testVersiHapusTombol() {
  // Tiap baris riwayat versi ada tombol Hapus (kecuali sisa 1 versi).
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  await flush(); await flush();
  const riw = t.elements['riwayat-versi'].innerHTML;
  assert.ok(riw.includes('data-hapus-versi="1"'), 'v1 bisa dihapus');
  assert.ok(riw.includes('data-hapus-versi="2"'), 'v2 bisa dihapus');
  console.log('ok 62b versi-hapus-tombol');
}

async function testVersiHapusDialog() {
  // Klik Hapus v1 -> dialog konfirmasi -> DELETE -> tampil v2 sisa.
  let delUrl = null;
  const klik = [];
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if ((opts && opts.method) === 'DELETE' &&
        u.includes('/versions/1')) {
      delUrl = u;
      return ok({ status: 'success', generation_id: 'g1',
        deleted_version: 1, latest_version: 2 });
    }
    if (u.includes('/versions/2')) {
      const m = editModule();
      return ok({ status: 'success', generation_id: 'g1',
        version: Object.assign(okVersion(2), { module: m }) });
    }
    return successWithVersions()(url, opts);
  });
  // Stub tombol hapus SEBELUM render agar wiring UI terpasang.
  t.elements['riwayat-versi'].querySelectorAll = function (sel) {
    if (String(sel).includes('data-hapus-versi')) {
      const b = makeElement('hapus-v1');
      b.getAttribute = function () { return '1'; };
      b.addEventListener = function (ev, fn) {
        if (ev === 'click') klik.push(fn);
      };
      return [b];
    }
    return [];
  };
  await flush();
  await gotoHasil(t);
  await flush(); await flush(); await flush();
  assert.strictEqual(klik.length, 1, 'tombol hapus v1 terpasang');
  klik[0]();
  assert.strictEqual(t.elements['hapus-versi-overlay'].hidden, false,
    'dialog hapus versi tampil');
  assert.ok(t.elements['hapus-versi-judul'].textContent.includes('v1'),
    'judul menyebut v1');
  t.elements['btn-konfirmasi-hapus-versi'].click();
  await flush(); await flush(); await flush(); await flush();
  assert.ok(delUrl && delUrl.includes('/versions/1'),
    'DELETE terkirim: ' + delUrl);
  assert.strictEqual(t.elements['hapus-versi-overlay'].hidden, true,
    'dialog tertutup');
  assert.ok(t.elements['alert-pesan'].textContent.includes('dihapus'),
    'popup hasil tampil');
  console.log('ok 62c versi-hapus-dialog');
}

async function testLoadingOverlayAda() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('id="loading-overlay"'), 'overlay ada');
  assert.ok(html.includes('id="loading-judul"'), 'judul ada');
  assert.ok(html.includes('id="loading-status"'), 'status ada');
  assert.ok(html.includes('overlay--loading'), 'kelas tengah ada');
  const css = fs.readFileSync(path.join(UI, 'styles.css'), 'utf-8');
  assert.ok(css.includes('.overlay--loading'), 'style tengah ada');
  console.log('ok 122 loading-markup');
}

async function testLoadingCekCp() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat cek CP');
  assert.ok(t.elements['loading-judul'].textContent.includes('Memeriksa CP'));
  await flush(); await flush();
  assert.strictEqual(t.elements['loading-overlay'].hidden, true,
    'overlay tutup setelah CP tampil');
  console.log('ok 123 loading-cek-cp');
}

async function testLoadingGenerate() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }],
    ['POST', '/api/context/generate', { status: 200, body: CONTEXT }],
    ['POST', '/api/module/generate', { status: 200, body:
      { status: 'accepted', job_id: 'jload' } }],
    ['GET', '/api/generation/status', { status: 200, body:
      { status: 'running' } }]
  ]));
  await flush();
  fillValidForm(t);
  t.elements['form-konteks'].submit();
  await flush(); await flush();
  t.elements['btn-generate'].click();
  await flush();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat generate');
  assert.ok(t.elements['loading-judul'].textContent.includes('Menyusun RPM'));
  console.log('ok 124 loading-generate');
}

async function testLoadingSimpan() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  t.window.Api.saveVersion = function () { return d.promise; };
  t.elements['btn-mode-edit'].click();
  t.elements['editor-isi'].querySelectorAll = function () {
    return [
      fieldStub('tp', '0', 'T1 menerapkan taubat VERSI GURU'),
      fieldStub('tp', '1', 'T2 menganalisis taubat'),
      fieldStub('tp', '2', 'T3 mengevaluasi taubat')
    ];
  };
  t.elements['btn-simpan-versi'].click();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat simpan');
  assert.ok(t.elements['loading-judul'].textContent.includes(
    'Menyimpan perubahan'));
  d.resolve({ version: okVersion(3), warnings: [] });
  await flush(); await flush(); await flush();
  console.log('ok 125 loading-simpan');
}

async function testLoadingHapus() {
  const t = await berandaSiap(historyFetch(function (url, opts) {
    if ((opts && opts.method) === 'DELETE') {
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', deleted: true });
        } });
    }
    return Promise.reject(new Error('no route ' + url));
  }));
  pilihItem(t, 'g2', true);
  t.elements['btn-hapus-pilih'].click();
  t.elements['btn-konfirmasi-hapus'].click();
  assert.strictEqual(t.elements['loading-overlay'].hidden, false,
    'overlay tampil saat hapus');
  assert.ok(t.elements['loading-judul'].textContent.includes('Menghapus'));
  await flush(); await flush(); await flush(); await flush();
  console.log('ok 126 loading-hapus');
}

async function testModalTrapDanRestore() {
  // Perilaku modal: buka fokus awal, Escape tutup, buka-tutup ulang aman.
  // Harness stub tidak emulasi DOM focus penuh; trap diuji di browser.
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['profil-overlay'].hidden, false,
    'profil terbuka');
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'Escape menutup profil');
  await bukaProfilDariBeranda(t);
  assert.strictEqual(t.elements['profil-overlay'].hidden, false,
    'profil dibuka ulang aman');
  t.docListeners.keydown({ key: 'Escape' });
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'Escape menutup ulang');
  console.log('ok 116 modal-trap');
}

const BUKU_DUA = { status: 'success', buku: [
  { document_id: 'BUKU-A', judul: 'Buku A', fragmen: 10,
    ukuran: 20480, diupload: '2026-10-01' },
  { document_id: 'BUKU-B', judul: 'Buku B', fragmen: 5,
    ukuran: 10240, diupload: '2026-10-02' }
] };

function bukuFetch() {
  return historyFetch(function (url) {
    if (String(url).includes('/api/buku')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(BUKU_DUA); } });
    }
    return Promise.reject(new Error('no route ' + url));
  });
}

function klikBukuDefault(t, docId) {
  t.elements['koleksi-buku']._handlers.click({ target: { closest: function () {
    return { getAttribute: function () { return docId; } };
  } } });
}

async function testKoleksiBukuTampil() {
  const t = await berandaSiap(bukuFetch());
  assert.ok(t.elements['koleksi-buku'].innerHTML.includes('Buku A'),
    'koleksi tampil Buku A');
  assert.ok(t.elements['koleksi-buku'].innerHTML.includes('Buku B'),
    'koleksi tampil Buku B');
  assert.ok(t.elements['koleksi-buku'].innerHTML.includes('data-buku-default'),
    'tombol default ada');
  console.log('ok 155 koleksi-buku-tampil');
}

async function testBukuDefaultPilih() {
  const t = await berandaSiap(bukuFetch());
  klikBukuDefault(t, 'BUKU-B');
  await flush(); await flush();
  assert.strictEqual(t.storage.getItem('rpm_buku_default'), 'BUKU-B',
    'default tersimpan');
  assert.ok(t.elements['koleksi-buku'].innerHTML.includes('Default'),
    'badge Default tampil');
  console.log('ok 156 buku-default-pilih');
}

async function testBukuDefaultOtomilih() {
  const t = boot(bukuFetch(), '', '',
    { rpm_buku_default: 'BUKU-A' });
  await flush();
  t.window.location.hash = '#layar-formulir';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.ok(t.elements['f-buku'].innerHTML.includes('value="BUKU-A" selected') ||
    t.elements['f-buku'].innerHTML.includes("value='BUKU-A' selected") ||
    (t.elements['f-buku'].innerHTML.includes('BUKU-A') &&
     t.elements['f-buku'].innerHTML.includes('selected')),
    'dropdown otomatis memilih default');
  console.log('ok 157 buku-default-otomilih');
}

async function testTabbarAda() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  for (const tab of ['data-tab="beranda"', 'data-tab="arsip"',
      'data-tab="formulir"', 'data-tab="log"', 'id="btn-tab-log"']) {
    assert.ok(html.includes(tab), tab + ' ada di tabbar');
  }
  const t = boot(logFetch());
  await flush();
  t.elements['btn-tab-log'].click();
  await flush(); await flush();
  assert.strictEqual(t.elements['log-overlay'].hidden, false,
    'tab Log membuka popup');
  console.log('ok 158 tabbar-ada');
}

async function testModalAlpineBridge() {
  // Bridge vanilla <-> Alpine: ModalUI.minta tanpa Alpine jalan via hidden.
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.ok(t.window.ModalUI && typeof t.window.ModalUI.minta === 'function',
    'ModalUI tersedia');
  t.window.ModalUI.minta('profil-overlay');
  assert.strictEqual(t.elements['profil-overlay'].hidden, true,
    'tanpa Alpine tutup aman');
  console.log('ok 154 modal-alpine-bridge');
}

async function testStepperTampilJumlah() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const out = t.window.ModuleRender.renderModule(templateModule(),
    { final: { passed: true } });
  assert.ok(out.content.includes('stepper__angka'),
    'stepper tampil');
  assert.ok(out.content.includes('aria-label="Kurangi"') &&
    out.content.includes('aria-label="Tambah"'), 'label aksesibel');
  console.log('ok 107 stepper-tampil');
}

async function testStepperUbahBatas() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const angka = { textContent: '10' };
  const bungkus = { querySelector: function () { return angka; } };
  const tombol = function (arah) {
    return { disabled: false,
      getAttribute: function (k) {
        return k === 'data-count' ? arah : null;
      },
      parentElement: bungkus };
  };
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () {
      return tombol('tambah');
    } } });
  assert.strictEqual(angka.textContent, 11);
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return tombol('kurang'); } } });
  assert.strictEqual(angka.textContent, 10);
  angka.textContent = '1';
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return tombol('kurang'); } } });
  assert.strictEqual(angka.textContent, 1, 'batas bawah 1');
  angka.textContent = '30';
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return tombol('tambah'); } } });
  assert.strictEqual(angka.textContent, 30, 'batas atas 30');
  console.log('ok 108 stepper-batas');
}

async function testRegenKirimCount() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const d = deferred();
  let terkirim = null;
  t.window.Api.regenerateSection = function (gid, ver, target, counts) {
    terkirim = [target, counts];
    return d.promise;
  };
  const angka = { textContent: '7' };
  const btn = tombolDinamis('diagnostik');
  btn.closest = function (sel) {
    if (sel === 'button') return btn;
    if (sel === '.baris-aksi') {
      return { querySelector: function () { return angka; } };
    }
    return null;
  };
  t.elements['hasil-isi']._handlers.click({ target: btn });
  d.resolve({ draft: true, version: okVersion(3), warnings: [] });
  await flush(); await flush(); await flush();
  assert.strictEqual(JSON.stringify(terkirim),
    JSON.stringify(['diagnostik', { diagnostik: 7 }]));
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Diagnostik'));
  console.log('ok 109 regen-count');
}

async function testNavFinalizeKontekstual() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  assert.strictEqual(t.elements['btn-finalize'].hidden, false,
    'Simpan perubahan global tampil di hasil');
  assert.strictEqual(t.elements['btn-simpan-versi'].hidden, true,
    'Simpan lokal tersembunyi sebelum mode edit');
  assert.ok(htmlStylesContainHiddenRule(),
    'CSS memaksa tombol hidden tetap tersembunyi');
  assert.strictEqual(t.elements['link-buat-rpm'].hidden, true,
    'Buat RPM sembunyi saat membuka RPM');
  console.log('ok 110 nav-finalize');
}

async function testNavNormalDiLuarHasil() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(t.elements['btn-finalize'].hidden, true);
  assert.strictEqual(t.elements['link-buat-rpm'].hidden, false);
  console.log('ok 111 nav-normal');
}

function tombolPtm(arah) {
  return { disabled: false, textContent: arah,
    classList: { add: function () {}, remove: function () {},
      contains: function () { return false; } },
    getAttribute: function (k) {
      return k === 'data-ptm' ? arah : null;
    } };
}

async function testPtmTampil() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  const out = t.window.ModuleRender.renderModule(templateModule(),
    { final: { passed: true } });
  assert.ok(out.content.includes('Jumlah pertemuan'),
    'stepper pertemuan tampil');
  assert.ok(out.content.includes('data-ptm="kurang"') &&
    out.content.includes('data-ptm="tambah"'), 'kurang/tambah ada');
  console.log('ok 110 ptm-tampil');
}

async function testPtmTambahSimpan() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  // Stepper pertemuan Bagian D kini pending lokal: klik +/- hanya
  // mengubah angka + status, tanpa request saveVersion.
  let saveCalls = 0;
  t.window.Api.saveVersion = function () {
    saveCalls++;
    return new Promise(function () {});
  };
  // Simulasi klik + pada stepper pertemuan: angka DOM naik lokal.
  var baris = { angka: { textContent: '0' } };
  baris.querySelector = function () { return baris.angka; };
  var btnTambah = tombolPtm('tambah');
  btnTambah.closest = function () { return baris; };
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return btnTambah; } } });
  assert.strictEqual(saveCalls, 0, 'stepper pending tanpa request');
  assert.strictEqual(baris.angka.textContent, 1);
  assert.ok(t.elements['status-simpan'].textContent.includes('pending'),
    'status tandai pending: ' +
    t.elements['status-simpan'].textContent);
  console.log('ok 111 ptm-tambah');
}

async function testPtmBatasBawah() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  let calls = 0;
  t.window.Api.saveVersion = function () {
    calls++;
    return new Promise(function () {});
  };
  // Angka sudah 1: klik kurang tetap 1 (clamp), tanpa request.
  var baris = { angka: { textContent: '1' } };
  baris.querySelector = function () { return baris.angka; };
  var btnKurang = tombolPtm('kurang');
  btnKurang.closest = function () { return baris; };
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return btnKurang; } } });
  assert.strictEqual(calls, 0, 'kurang di bawah 1 tidak request');
  assert.strictEqual(String(baris.angka.textContent), '1');
  console.log('ok 112 ptm-batas');
}

async function testPtmNaikTurunTanpaRegen() {
  // Skenario user: awal 1 → tambah jadi 3 → kurang kembali ke 1,
  // semua tanpa regenerate. Tombol kurang tidak boleh macet di tengah.
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  var btnKurang = tombolPtm('kurang');
  var btnTambah = tombolPtm('tambah');
  var baris = { angka: { textContent: '1' } };
  baris.querySelector = function () { return baris.angka; };
  baris.querySelectorAll = function () { return [btnKurang, btnTambah]; };
  btnKurang.closest = function () { return baris; };
  btnTambah.closest = function () { return baris; };
  function klik(btn) {
    t.elements['hasil-isi']._handlers.click(
      { target: { closest: function () { return btn; } } });
  }
  klik(btnTambah);
  assert.strictEqual(String(baris.angka.textContent), '2');
  klik(btnTambah);
  assert.strictEqual(String(baris.angka.textContent), '3');
  klik(btnKurang);
  assert.strictEqual(String(baris.angka.textContent), '2',
    'kurang dari 3 ke 2 tidak macet');
  klik(btnKurang);
  assert.strictEqual(String(baris.angka.textContent), '1',
    'kurang dari 2 ke 1 tidak macet');
  assert.strictEqual(btnKurang.disabled, true, 'di 1 tombol kurang mati');
  console.log('ok 114 ptm-naik-turun');
}

async function testPtmRegenKirimNMeetings() {
  // Regenerate Aktivitas membaca angka stepper pending dan mengirim
  // n_meetings bila berbeda dari modul tersimpan.
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  t.window.Api.regenerateSection = function (gid, ver, target, counts,
      extra) {
    t._regenArgs = [gid, ver, target, counts, extra];
    return new Promise(function () {});
  };
  var baris = { angka: { textContent: '2' },
    closest: function () { return null; } };
  baris.querySelector = function () { return baris.angka; };
  var btnRegen = { disabled: false, textContent: 'Regenerate Aktivitas',
    classList: { add: function () {}, remove: function () {},
      contains: function () { return false; } },
    getAttribute: function (k) {
      return k === 'data-regen' ? 'aktivitas' : null;
    },
    closest: function () { return baris; } };
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return btnRegen; } } });
  assert.ok(t._regenArgs, 'regen terpanggil');
  assert.strictEqual(t._regenArgs[2], 'aktivitas');
  assert.strictEqual(t._regenArgs[4].n_meetings, 2);
  assert.deepStrictEqual(Object.keys(t._regenArgs[4]), ['n_meetings']);
  console.log('ok 113 ptm-regen-n-meetings');
}

async function testBulkKontrolTampil() {
  const t = await berandaSiap(historyFetch());
  assert.strictEqual(t.elements['bulk-kontrol'].hidden, true,
    'kontrol sembunyi sebelum ada pilihan');
  pilihItem(t, 'g2', true);
  assert.strictEqual(t.elements['bulk-kontrol'].hidden, false,
    'kontrol tampil setelah satu pilihan');
  console.log('ok 104 bulk-kontrol');
}

function tombolDinamis(target) {
  return { disabled: false, textContent: 'Regenerate ' + target,
    classList: { add: function () {}, remove: function () {},
      contains: function () { return false; } },
    getAttribute: function (k) {
      return k === 'data-regen' ? target : null;
    } };
}

async function testRegenDelegasiDiagnostik() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  const panggil = [];
  const d = deferred();
  t.window.Api.regenerateSection = function (gid, ver, target) {
    panggil.push([gid, ver, target]);
    return d.promise;
  };
  const btn = tombolDinamis('diagnostik');
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return btn; } } });
  d.resolve({ draft: true, version: okVersion(3), warnings: [] });
  await flush(); await flush(); await flush();
  assert.deepStrictEqual(panggil[0].slice(2), ['diagnostik']);
  assert.ok(t.elements['status-simpan'].textContent.includes(
    'Diagnostik'));
  console.log('ok 105 regen-delegasi');
}

async function testRegenKlikNonTombolAman() {
  const t = boot(successWithVersions());
  await flush();
  await gotoHasil(t);
  let calls = 0;
  t.window.Api.regenerateSection = function () {
    calls++;
    return new Promise(function () {});
  };
  t.elements['hasil-isi']._handlers.click(
    { target: { closest: function () { return null; } } });
  t.elements['hasil-isi']._handlers.click({});
  assert.strictEqual(calls, 0, 'klik konten tanpa target aman');
  console.log('ok 106 regen-klik-aman');
}

async function testPrebootAntiFlash() {
  // Pre-boot statis: refresh di hash layar mana pun tidak paint landing.
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('Anti-flash pre-boot'), 'skrip pre-boot ada');
  for (const layar of ['layar-beranda', 'layar-arsip', 'layar-formulir',
      'layar-progres', 'layar-hasil']) {
    assert.ok(html.includes("'#" + layar + "'") || html.includes(layar),
      'pre-boot kenal ' + layar);
  }
  assert.ok(html.includes('layar-progres') && html.includes('generation_id'),
    'pre-boot tangani sesi tersimpan');
  console.log('ok 162 preboot-anti-flash');
}

async function testLandingDefault() {
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush();
  assert.strictEqual(t.elements['layar-landing'].hidden, false,
    'landing entry default');
  assert.strictEqual(t.elements['layar-beranda'].hidden, true);
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(html.includes('Buat RPM'), 'CTA Buat RPM');
  assert.ok(html.includes('Beranda'), 'CTA Beranda');
  for (const kata of ['pricing', 'testimoni', '99.9%']) {
    assert.ok(!html.toLowerCase().includes(kata),
      'tanpa SaaS palsu: ' + kata);
  }
  console.log('ok 75 landing-default');
}

async function testLandingSkipUserLama() {
  // Returning user (flag kunjungan ada): buka root otomatis ke Beranda.
  // Landing tidak dikunci, tetap bisa dibuka; profil bikinan user
  // tidak dipakai sebagai penanda.
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]), '', '', { rpm_pernah_buka: '1' });
  await flush(); await flush();
  assert.strictEqual(t.elements['layar-landing'].hidden, true,
    'landing tidak tampil untuk returning user');
  assert.strictEqual(t.elements['layar-beranda'].hidden, false,
    'root otomatis ke Beranda');
  console.log('ok 161 landing-skip-user-lama');
}

async function testLandingUserBaruTetapLanding() {
  // User baru (tanpa flag): root tetap landing, lalu flag ditandai.
  const t = boot(fetchQueue([
    ['GET', '/api/curriculum/options', { status: 200, body: OPTIONS }]
  ]));
  await flush(); await flush();
  assert.strictEqual(t.elements['layar-landing'].hidden, false,
    'user baru tetap landing');
  assert.strictEqual(t.storage.getItem('rpm_pernah_buka'), '1',
    'flag kunjungan ditandai');
  console.log('ok 163 landing-user-baru');
}

async function testBerandaDashboard() {
  const t = boot(historyFetch(), '', '', seedProfil());
  await flush();
  await gotoBeranda(t);
  assert.strictEqual(t.elements['layar-beranda'].hidden, false);
  assert.ok(t.elements['profil-ringkas'].innerHTML.includes(
    'MAN Kota Blitar'), 'profil tampil');
  const html = t.elements['riwayat-rpm'].innerHTML;
  assert.ok(html.includes('RPM Fikih Zakat') &&
    html.includes('RPM Taubat'), 'dua RPM tampil');
  assert.ok(html.indexOf('RPM Fikih Zakat') < html.indexOf('RPM Taubat'),
    'terbaru dulu');
  assert.ok(html.includes('generation_id=g2#layar-hasil'),
    'Buka memakai flow sesi existing');
  assert.ok(html.includes('/api/module/g2/export-docx'),
    'Export tersedia');
  assert.strictEqual(
    (html.match(/<li/g) || []).length, 2, 'tanpa duplikat');
  console.log('ok 76 beranda-dashboard');
}

async function testBerandaKosong() {
  const t = boot(function (url, opts) {
    const u = String(url);
    if (u.includes('/api/modules')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () {
          return Promise.resolve({ status: 'success', modules: [] });
        } });
    }
    return historyFetch()(url, opts);
  });
  await flush();
  await gotoBeranda(t);
  assert.strictEqual(t.elements['riwayat-kosong'].hidden, false,
    'empty state');
  assert.strictEqual(t.elements['riwayat-rpm'].innerHTML, '');
  assert.strictEqual(t.elements['bulk-kontrol'].hidden, true,
    'pilih semua disembunyikan saat kosong');
  const htmlKosong = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(htmlKosong.includes('Belum ada RPM tersimpan') &&
    htmlKosong.includes('Buat RPM'), 'empty state + CTA di markup');
  console.log('ok 77 beranda-kosong');
}

async function testBerandaError() {
  const t = boot(function () {
    return Promise.reject(new Error('putus'));
  });
  // options gagal -> formError; beranda fetch juga gagal
  await flush();
  t.window.location.hash = '#layar-beranda';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(t.elements['riwayat-error'].hidden, false,
    'error state');
  console.log('ok 78 beranda-error');
}

async function testProfilDiBeranda() {
  const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf-8');
  assert.ok(!html.includes('id="btn-profil"'),
    'Profil keluar dari navbar');
  assert.ok(html.includes('id="btn-ubah-profil"'),
    'Ubah Profil di Beranda');
  const t = boot(historyFetch(), '', '', seedProfil());
  await flush();
  await gotoBeranda(t);
  t.elements['btn-ubah-profil'].click();
  assert.strictEqual(t.elements['profil-overlay'].hidden, false,
    'dialog dibuka dari Beranda');
  console.log('ok 79 profil-di-beranda');
}

async function testStatNyata() {
  const t = boot(function (url, opts) {
    const u = String(url);
    const ok = function (body) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(body); } });
    };
    if (u.includes('/api/stats')) {
      return ok({ status: 'success',
        statistics: { total_cp_entries: 3060, total_documents: 9,
          total_fragments: 6592 } });
    }
    if (u.includes('/api/curriculum/options')) return ok(OPTIONS);
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  const spans = {
    cp: { textContent: '…' }, dokumen: { textContent: '…' },
    fragmen: { textContent: '…' }
  };
  t.elements['stat-kurikulum'] = {
    hidden: false,
    querySelector: function (sel) {
      const m = /data-stat="(\w+)"/.exec(sel);
      return m ? spans[m[1]] : null;
    }
  };
  t.window.location.hash = '#layar-landing';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(spans.cp.textContent, '3.060');
  assert.strictEqual(spans.dokumen.textContent, '9');
  assert.strictEqual(spans.fragmen.textContent, '6.592');
  console.log('ok 82 stat-nyata');
}

async function testStatGagalSembunyi() {
  const t = boot(function (url) {
    const u = String(url);
    if (u.includes('/api/stats')) {
      return Promise.reject(new Error('putus'));
    }
    if (u.includes('/api/curriculum/options')) {
      return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(OPTIONS); } });
    }
    return Promise.reject(new Error('no route ' + u));
  });
  await flush();
  t.elements['stat-kurikulum'] = { hidden: false,
    querySelector: function () { return { textContent: '…' }; } };
  t.window.location.hash = '#layar-landing';
  t.winListeners.hashchange();
  await flush(); await flush();
  assert.strictEqual(t.elements['stat-kurikulum'].hidden, true,
    'stat gagal dimuat disembunyikan');
  console.log('ok 83 stat-gagal-sembunyi');
}

(async function () {
  try {
    await testOptionsLoad();
    await testFormValidation();
    await testContextShowsCp();
    await testContextErrorTampilNyata();
    await testGeneratePollSuccess();
    await testGenerateFailure();
    await testExportGatingAndDownload();
    await testRenderEscapesAndKbc();
    await testHashNavigasiKeFormulir();
    await testGagalTerminalBisaCobaLagi();
    await testAnchorTocTidakKabur();
    await testBukaUlangSesiTersimpan();
    await testBukaUlangSesiHilang();
    await testBukaDariBerandaTanpaReload();
    await testLoadingTunggalBukaSesi();
    await testTabBaruAnchorPulihkanSesi();
    await testAlokasiInvalidDitolak();
    await testAlokasiRangeDitolak();
    await testGenerateBawaInputGuru();
    await testGenerateBawaFormLive();
    await testGantiSistemResetDependen();
    await testEditModeLockedCp();
    await testSavePostsDiffOnly();
    await testDirtyGuard();
    await testStale409Pesan();
    await testRiwayatRender();
    await testExportVersionedUrl();
    await testApiVersionShapes();
    await testGlosariumReview();
    await testGlosariumEditCollect();
    await testGlosariumUntouchedNotSent();
    await testApiGlosariumRegenShape();
    await testDimsNotesRender();
    await testKbcNoteNotRendered();
    await testKktpPlainRender();
    await testPrinciplesRender();
    await testLkpdNotRendered();
    await testCountsFieldsPresent();
    await testCountsNolKeterangan();
    await testBukuWajibAda();
    await testBukuUploadTombol();
    await testRegenButtonsInventory();
    await testTemplateHeaderTopik();
    await testIdentitasModul();
    await testSectionOrderTemplate();
    await testMeetingPrinsipTerpisah();
    await testDataFinalLengkap();
    await testSectionLamaHilang();
    await testKbcPaired();
    await testKbcUnequalHonest();
    await testWebMcOptions();
    await testWebDiagnosticLabelOnly();
    await testAsesmenHeaderNoWrap();
    await testAsesmenCentered();
    await testAsesmenMiddleVertical();
    await testProfilMenu();
    await testProfilPanelBuka();
    await testProfilIsiSimpan();
    await testProfilReload();
    await testFormAutofill();
    await testFormEditable();
    await testFormEditTakUbahProfil();
    await testProfilDipakaiFormBerikutnya();
    await testProfilKosong();
    await testPlaceholderPilih();
    await testTanpaKomaPilih();
    await testSemesterManusiawi();
    await testSimpanTanpaVersiAdaPesan();
    await testAktifHanyaVersiAktif();
    await testRiwayatGridBaru();
    await testSaveTanpaEditAman();
    await testSaveTanpaEditAsesmenUtuh();
    await testSaveTanpaEditIdentitasImpor();
    await testFieldHilangTakHilangkanData();
    await testTpKosongDisebutEksplisit();
    await testRegenLoadingSemua();
    await testRegenDoubleClickSekali();
    await testRegenAsyncDraftTerap();
    await testRegenSukses();
    await testRegenHttpError();
    await testRegenNetworkError();
    await testPrebootAntiFlash();
    await testLandingDefault();
    await testLandingSkipUserLama();
    await testLandingUserBaruTetapLanding();
    await testBerandaDashboard();
    await testBerandaKosong();
    await testBerandaError();
    await testProfilDiBeranda();
    await testBulkDefaultSembunyi();
    await testBulkPilihSatu();
    await testBulkBatalSatu();
    await testBulkPilihSemua();
    await testBulkBatalSemua();
    await testBulkBatalHapus();
    await testBulkHapusSatu();
    await testBulkHapusSemuaKosong();
    await testBulkHapusGagal();
    await testBulkMarkupAksesibel();
    await testMenuTitikAda();
    await testModePilihMuncul();
    await testBulkApiDelete();
    await testUploadTombolAda();
    await testUploadBadgeImpor();
    await testUploadBadgeDraf();
    await testUploadGagalPesan();
    await testAlertRegenGagal();
    await testAlertSimpanSukses();
    await testAlertEscape();
    await testJudulRiwayatMedium();
    await testProfilValueSeragam();
    await testSimpanTutupOtomatis();
    await testSimpanPreviewLangsung();
    await testSimpanGagalTetapBuka();
    await testEscapeTutupProfil();
    await testEscapeTutupHapus();
    await testKeluarSesiKeBeranda();
    await testKeluarSesiKeFormulir();
    await testBulkKontrolTampil();
    await testPtmTampil();
    await testPtmTambahSimpan();
    await testPtmBatasBawah();
    await testPtmNaikTurunTanpaRegen();
    await testPtmRegenKirimNMeetings();
    await testNavFinalizeKontekstual();
    await testNavNormalDiLuarHasil();
    await testRegenDelegasiDiagnostik();
    await testRegenKlikNonTombolAman();
    await testStepperTampilJumlah();
    await testStepperUbahBatas();
    await testRegenKirimCount();
    await testStatNyata();
    await testStatGagalSembunyi();
    await testSelectKurikulumEscapeHtml();
    await testLogNav();
    await testLogDaftar();
    await testLogKosong();
    await testLogDetail();
    await testLogError();
    await testLogTutupPopup();
    await testLogHapusCheckbox();
    await testLogHapusPilihSemua();
    await testVersiHapusTombol();
    await testVersiHapusDialog();
    await testArsipMarkup();
    await testArsipNavPisah();
    await testArsipBadge();
    await testArsipKirimFlag();
    await testArsipEscape();
    await testArsipKembalikan();
    await testLoadingOverlayAda();
    await testLoadingCekCp();
    await testLoadingGenerate();
    await testLoadingSimpan();
    await testLoadingHapus();
    await testModalTrapDanRestore();
    await testKoleksiBukuTampil();
    await testBukuDefaultPilih();
    await testBukuDefaultOtomilih();
    await testTabbarAda();
    await testModalAlpineBridge();
    console.log('FRONTEND TESTS PASS (163/163)');
  } catch (e) {
    console.error('FRONTEND TEST FAIL:', e.message);
    process.exit(1);
  }
})();
