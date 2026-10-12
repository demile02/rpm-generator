/* RPM Generator, alur aplikasi.
   Beranda -> Formulir (+cek CP) -> Progres (polling nyata) -> Hasil
   (pratinjau final) -> Export DOCX. Tanpa data palsu, tanpa progres palsu. */
(function () {
  'use strict';

  var state = {
    options: null,
    jobId: null, generationId: null, module: null, validation: null,
    pollTimer: null, pollStart: 0,
    // Batch 5: review/edit/versioning.
    mode: 'review', version: null, versions: [], hasVersions: false,
    dirty: false, editFields: [], draftChanges: {},
    // Batch 4A: bulk selection riwayat.
    pilihan: {}, riwayat: [],
    // Arsip (R-38): seleksi terpisah per layar.
    pilihanArsip: {}, riwayatArsip: [],
    arsipTarget: [], kembalikanTarget: [], pilihanArsipHapus: [],
    // Hapus log: seleksi baris audit (modul riwayat TIDAK ikut).
    pilihanLog: {}, riwayatLog: [],
    // Hapus versi: target versi yang dikonfirmasi.
    hapusVersiTarget: null
  };

  var els = {};
  function $(id) { return document.getElementById(id); }

  /* ---------- loading terpusat: satu overlay tengah + keterangan ---------- */
  var loadingBerjalan = null;

  function tampilLoading(judul, status) {
    var overlay = $('loading-overlay');
    if (!overlay) return;
    loadingBerjalan = judul || 'Memproses…';
    $('loading-judul').textContent = loadingBerjalan;
    $('loading-status').textContent = status || '';
    overlay.hidden = false;
  }

  function perbaruiLoading(status) {
    if (!$('loading-overlay') || $('loading-overlay').hidden) return;
    $('loading-status').textContent = status || '';
  }

  function sembunyiLoading() {
    loadingBerjalan = null;
    if ($('loading-overlay')) $('loading-overlay').hidden = true;
  }

  function show(id) {
    ['layar-landing', 'layar-beranda', 'layar-arsip', 'layar-formulir',
     'layar-progres', 'layar-hasil'].forEach(function (s) {
      $(s).hidden = (s !== id);
    });
    perbaruiNav();
    tandaiTabAktif(id);
    window.scrollTo(0, 0);
  }

  /* Tabbar mobile: tandai tujuan aktif sesuai layar. */
  function tandaiTabAktif(idLayar) {
    var peta = { 'layar-beranda': 'beranda', 'layar-arsip': 'arsip',
      'layar-formulir': 'formulir' };
    var aktif = peta[idLayar] || '';
    try {
      document.querySelectorAll('.tabbar [data-tab]').forEach(function (el) {
        var nyala = el.getAttribute('data-tab') === aktif;
        if (el.classList) el.classList.toggle('aktif', nyala);
        if (nyala) el.setAttribute('aria-current', 'page');
        else el.removeAttribute('aria-current');
      });
    } catch (e) { /* abaikan: tabbar dekoratif */ }
  }

  // Simpan perubahan global selalu tersedia pada hasil.
  // Simpan lokal hanya tersedia dalam editor manual.
  function perbaruiNav() {
    var diHasil = !$('layar-hasil').hidden && !!state.generationId;
    $('btn-finalize').hidden = !diHasil;
    $('btn-simpan-versi').hidden = !(diHasil && state.mode === 'edit');
    $('link-buat-rpm').hidden = diHasil;
  }

  function formError(msg) {
    var box = $('form-error');
    box.hidden = !msg;
    box.textContent = msg || '';
    // Error formulir juga muncul sebagai popup agar mudah dipahami.
    // Panggilan kosong (reset) tidak memicu popup.
    if (msg) tampilAlert('Formulir belum lengkap', msg);
  }

  function init() {
    ['f-sistem', 'f-institusi', 'f-kelas', 'f-mapel', 'f-elemen', 'f-topik',
     'f-buku', 'f-buku-file', 'btn-upload-buku', 'buku-error', 'buku-hasil',
     'f-satuan', 'f-semester', 'f-tahun', 'f-penyusun', 'f-jumlah', 'f-jp',
     'f-awal', 'f-formatif', 'f-sumatif', 'f-kesiapan',
     'form-konteks', 'form-error', 'panel-cp', 'cp-teks', 'cp-meta',
     'btn-konteks', 'btn-generate', 'f-fase', 'progres-teks', 'progres-id',
     'progres-waktu', 'progres-error', 'btn-coba-lagi', 'btn-poll-ulang',
     'btn-ke-formulir', 'progres-bar',
     'hasil-validasi', 'hasil-versi', 'hasil-alignment', 'hasil-toc',
     'hasil-isi', 'hasil-error', 'editor-isi', 'status-simpan',
     'peringatan-dependensi', 'riwayat-versi',
     'btn-mode-edit', 'btn-simpan-versi', 'btn-finalize',
     'btn-export-docx', 'btn-baru', 'profil-overlay',
     'p-penyusun', 'p-satuan', 'p-semester', 'p-tahun', 'profil-status',
     'btn-simpan-profil', 'btn-batal-profil', 'profil-ringkas',
     'btn-ubah-profil', 'riwayat-rpm', 'riwayat-kosong',
     'riwayat-error', 'buka-error', 'bulk-pilih', 'bulk-bilah',
     'bulk-jumlah', 'btn-hapus-pilih', 'btn-arsip-pilih',
     'arsip-error', 'arsip-kosong', 'arsip-bulk-kontrol',
     'arsip-bulk-pilih', 'arsip-bulk-bilah', 'arsip-bulk-jumlah',
     'btn-kembalikan-pilih', 'btn-hapus-arsip-pilih', 'riwayat-arsip',
     'arsip-overlay', 'arsip-judul', 'arsip-pesan',
     'btn-batal-arsip', 'btn-konfirmasi-arsip',
     'kembalikan-overlay', 'kembalikan-judul', 'kembalikan-pesan',
     'kembalikan-error', 'btn-batal-kembalikan',
     'btn-konfirmasi-kembalikan',
     'hapus-overlay', 'hapus-judul',
     'hapus-pesan', 'hapus-error', 'btn-batal-hapus',
     'btn-konfirmasi-hapus', 'log-overlay', 'btn-buka-log', 'btn-tab-log',
     'log-error',
     'log-kosong', 'daftar-log', 'log-detail', 'log-detail-judul',
     'btn-buka-upload', 'upload-file', 'upload-error', 'upload-hasil',
     'f-buku-file', 'btn-upload-buku', 'buku-error', 'buku-hasil',
     'koleksi-buku', 'koleksi-buku-kosong',
     'log-detail-meta', 'log-detail-isi', 'btn-tutup-log',
     'btn-tutup-log-overlay', 'log-bulk-kontrol', 'log-bulk-pilih',
     'log-bulk-bilah', 'log-bulk-jumlah', 'btn-hapus-log-pilih',
     'hapus-log-overlay', 'hapus-log-judul', 'hapus-log-pesan',
     'hapus-log-error', 'btn-batal-hapus-log', 'btn-konfirmasi-hapus-log',
     'hapus-versi-overlay', 'hapus-versi-judul', 'hapus-versi-pesan',
     'hapus-versi-error', 'btn-batal-hapus-versi',
     'btn-konfirmasi-hapus-versi',
     'alert-overlay', 'alert-judul',
     'alert-pesan', 'btn-alert-tutup', 'loading-overlay', 'loading-judul',
     'loading-status'].forEach(function (id) {
      els[id.replace(/-/g, '_')] = $(id);
    });
    $('form-konteks').addEventListener('submit', onCekCp);
    $('btn-generate').addEventListener('click', onGenerate);
    $('btn-upload-buku').addEventListener('click', function () {
      $('f-buku-file').click();
    });
    $('f-buku-file').addEventListener('change', onUploadBuku);
    $('btn-poll-ulang').addEventListener('click', function () {
      $('progres-error').hidden = true;
      tampilLoading('Melanjutkan polling', 'Menghubungi backend…');
      pollStatus();
    });
    $('btn-coba-lagi').addEventListener('click', function () {
      onGenerate();
    });
    $('btn-ke-formulir').addEventListener('click', function () {
      if (!bolehNinggalkanEdit()) return;
      stopPolling(); tampilkanFormulir();
    });
    $('btn-baru').addEventListener('click', function () {
      if (!bolehNinggalkanEdit()) return;
      try {
        window.history.replaceState(null, '', '/app#layar-formulir');
      } catch (e) { /* abaikan */ }
      tampilkanFormulir();
    });
    $('btn-ubah-profil').addEventListener('click', bukaProfil);
    $('btn-batal-profil').addEventListener('click', tutupProfil);
    $('btn-simpan-profil').addEventListener('click', simpanProfil);
    $('profil-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('profil-overlay')) tutupProfil();
    });
    $('riwayat-rpm').addEventListener('change', onPilihItem);
    // Menu ⋯ per kartu: buka menu / eksekusi Pilih.
    $('riwayat-rpm').addEventListener('click', function (e) {
      if (onMenuKartu(e, 'riwayat-rpm', 'pilihan',
          muatUlangCentang, perbaruiBulk, 'data-titik',
          'data-aksi-pilih')) return;
    });
    // Buka RPM dari Beranda tanpa reload: tanpa ini, navigasi full-page
    // ke /app?generation_id= mem-paint landing dulu sebelum JS boot.
    $('riwayat-rpm').addEventListener('click', function (e) {
      var a = e && e.target && e.target.closest ?
        e.target.closest('a[href*="generation_id="]') : null;
      if (!a) return;
      var href = a.getAttribute('href') || '';
      var m = href.match(/[?&]generation_id=([^&#]*)/);
      if (!m) return;
      e.preventDefault();
      bukaSesiLangsung(decodeURIComponent(m[1]));
    });
    $('btn-buka-upload').addEventListener('click', onBukaUpload);
    $('upload-file').addEventListener('change', onFileUpload);
    if ($('koleksi-buku')) {
      $('koleksi-buku').addEventListener('click', onPilihBukuDefault);
    }
    $('daftar-log').addEventListener('click', function (e) {
      if (onMenuKartu(e, 'daftar-log', 'pilihanLog',
          muatUlangCentangLog, perbaruiBulkLog, 'data-titiklog',
          'data-aksi-pilihlog')) return;
      var el = e && e.target && e.target.closest ?
        e.target.closest('[data-log]') : null;
      var gid = el && el.getAttribute &&
        el.getAttribute('data-log');
      if (gid) bukaDetailLog(gid);
    });
    $('daftar-log').addEventListener('change', onPilihLog);
    $('btn-tutup-log').addEventListener('click', tutupDetailLog);
    $('btn-buka-log').addEventListener('click', tampilkanLog);
    if ($('btn-tab-log')) {
      $('btn-tab-log').addEventListener('click', tampilkanLog);
    }
    $('btn-tutup-log-overlay').addEventListener('click', tutupLog);
    $('btn-alert-tutup').addEventListener('click', tutupAlert);
    $('alert-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('alert-overlay')) tutupAlert();
    });
    $('log-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('log-overlay')) tutupLog();
    });
    $('bulk-pilih').addEventListener('change', onPilihSemua);
    $('btn-hapus-pilih').addEventListener('click', bukaHapus);
    $('btn-batal-hapus').addEventListener('click', tutupHapus);
    $('btn-konfirmasi-hapus').addEventListener('click', hapusTerpilih);
    $('hapus-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('hapus-overlay')) tutupHapus();
    });
    $('log-bulk-pilih').addEventListener('change', onPilihSemuaLog);
    $('btn-hapus-log-pilih').addEventListener('click', bukaHapusLog);
    $('btn-batal-hapus-log').addEventListener('click', tutupHapusLog);
    $('btn-konfirmasi-hapus-log').addEventListener('click', hapusLogTerpilih);
    $('hapus-log-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('hapus-log-overlay')) tutupHapusLog();
    });
    $('btn-batal-hapus-versi').addEventListener('click', tutupHapusVersi);
    $('btn-konfirmasi-hapus-versi').addEventListener(
      'click', hapusVersiTerpilih);
    $('hapus-versi-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('hapus-versi-overlay')) tutupHapusVersi();
    });
    $('btn-arsip-pilih').addEventListener('click', bukaArsip);
    $('btn-batal-arsip').addEventListener('click', tutupArsip);
    $('btn-konfirmasi-arsip').addEventListener('click', arsipTerpilih);
    $('arsip-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('arsip-overlay')) tutupArsip();
    });
    $('arsip-bulk-pilih').addEventListener('change', onPilihSemuaArsip);
    $('riwayat-arsip').addEventListener('change', onPilihItemArsip);
    $('riwayat-arsip').addEventListener('click', function (e) {
      if (onMenuKartu(e, 'riwayat-arsip', 'pilihanArsip',
          muatUlangCentangArsip, perbaruiBulkArsip, 'data-titik',
          'data-aksi-pilih')) return;
    });
    $('riwayat-arsip').addEventListener('click', function (e) {
      var a = e && e.target && e.target.closest ?
        e.target.closest('a[href*="generation_id="]') : null;
      if (!a) return;
      var href = a.getAttribute('href') || '';
      var m = href.match(/[?&]generation_id=([^&#]*)/);
      if (!m) return;
      e.preventDefault();
      bukaSesiLangsung(decodeURIComponent(m[1]));
    });
    $('btn-kembalikan-pilih').addEventListener(
      'click', bukaKembalikan);
    $('btn-batal-kembalikan').addEventListener('click', tutupKembalikan);
    $('btn-konfirmasi-kembalikan').addEventListener(
      'click', kembalikanTerpilih);
    $('kembalikan-overlay').addEventListener('click', function (e) {
      if (!e || e.target === $('kembalikan-overlay')) tutupKembalikan();
    });
    $('btn-hapus-arsip-pilih').addEventListener(
      'click', bukaHapusArsip);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') tutupSemuaMenu();
      if (e.key === 'Escape' && !$('profil-overlay').hidden) tutupProfil();
      if (e.key === 'Escape' && !$('hapus-overlay').hidden) tutupHapus();
      if (e.key === 'Escape' && !$('hapus-log-overlay').hidden) tutupHapusLog();
      if (e.key === 'Escape' && !$('hapus-versi-overlay').hidden) tutupHapusVersi();
      if (e.key === 'Escape' && !$('arsip-overlay').hidden) tutupArsip();
      if (e.key === 'Escape' && !$('kembalikan-overlay').hidden) tutupKembalikan();
      if (e.key === 'Escape' && !$('log-overlay').hidden) tutupLog();
      if (e.key === 'Escape' && !$('alert-overlay').hidden) tutupAlert();
    });
    // Backdrop menu ⋯: klik di luar menu menutup menu terbuka.
    document.addEventListener('click', function (e) {
      var t = e && e.target;
      if (!t || !t.closest) return;
      if (t.closest('.menu-pilih') || t.closest('[data-titik]') ||
          t.closest('[data-titiklog]')) return;
      tutupSemuaMenu();
    });
    // Delegasi tombol retry per bagian (dirender dinamis di hasil),
    // stepper jumlah soal, dan stepper jumlah pertemuan (pending lokal:
    // +/- hanya mengubah angka, Regenerate Aktivitas yang mengeksekusi
    // via AI ikut angka itu).
    $('hasil-isi').addEventListener('click', function (e) {
      var el = e && e.target && e.target.closest ? e.target.closest(
        'button') : null;
      if (!el || el.disabled) return;
      var langkah = el.getAttribute && el.getAttribute('data-count');
      if (langkah) { aturJumlah(el, langkah); return; }
      var ptm = el.getAttribute && el.getAttribute('data-ptm');
      if (ptm) { aturPertemuanPending(el, ptm); return; }
      var target = el.getAttribute && el.getAttribute('data-regen');
      if (!target) return;
      if (target === 'aktivitas') {
        regenAktivitasDenganPertemuan(el); return;
      }
      regenBagian(target, el, hitungJumlah(el, target));
    });

    // Jumlah soal stepper (1..30) pada baris aksi asesmen.
    function aturJumlah(el, langkah) {
      var bungkus = el.parentElement;
      var angka = bungkus && bungkus.querySelector ?
        bungkus.querySelector('.stepper__angka') : null;
      if (!angka) return;
      var n = parseInt(angka.textContent, 10);
      if (isNaN(n)) n = 1;
      n += (langkah === 'tambah' ? 1 : -1);
      angka.textContent = Math.max(1, Math.min(30, n));
    }

    function hitungJumlah(el, target) {
      var baris = el.closest ? el.closest('.baris-aksi') : null;
      var angka = baris && baris.querySelector ?
        baris.querySelector('.stepper__angka') : null;
      if (!angka) return undefined;
      var n = parseInt(angka.textContent, 10);
      if (isNaN(n) || n < 1 || n > 30) return undefined;
      var out = {};
      out[target] = n;
      return out;
    }

    // Stepper pertemuan Bagian D: angka pending lokal (1..16).
    // +/- hanya mengubah angka di layar; Regenerate Aktivitas yang
    // mengeksekusi via AI ikut angka itu (pecah bila tambah,
    // gabung bila kurang). Tanpa klik regenerate, modul tak berubah.
    // Tombol selalu aktif di render; batas ditegakkan di sini ikut
    // angka pending (bukan jumlah tersimpan), agar 1→3 lalu 3→1
    // bisa tanpa regenerate dulu.
    function aturPertemuanPending(el, arah) {
      var baris = el.closest ? el.closest('.baris-aksi') : null;
      var angka = baris && baris.querySelector ?
        baris.querySelector('.stepper__angka') : null;
      if (!angka) return;
      var n = parseInt(angka.textContent, 10);
      if (isNaN(n)) {
        n = state.module && state.module.meetings ?
          state.module.meetings.length : 1;
      }
      n += (arah === 'tambah' ? 1 : -1);
      n = Math.max(1, Math.min(16, n));
      angka.textContent = n;
      // Sinkronkan status tombol ikut angka pending.
      var btns = baris && baris.querySelectorAll ?
        baris.querySelectorAll('[data-ptm]') : [];
      for (var i = 0; i < btns.length; i++) {
        var arahBtn = btns[i].getAttribute &&
          btns[i].getAttribute('data-ptm');
        if (arahBtn === 'kurang') btns[i].disabled = (n <= 1);
        if (arahBtn === 'tambah') btns[i].disabled = (n >= 16);
      }
      var cur = state.module && state.module.meetings ?
        state.module.meetings.length : undefined;
      $('status-simpan').textContent = (n === cur) ?
        'Jumlah pertemuan sama dengan versi tersimpan.' :
        ('Jumlah pertemuan: ' + n + ' (pending — klik Regenerate ' +
         'Aktivitas untuk memecah/menggabung via AI).');
    }

    function hitungPertemuanPending(el) {
      var baris = el.closest ? el.closest('.baris-aksi') : null;
      var angka = baris && baris.querySelector ?
        baris.querySelector('.stepper__angka') : null;
      if (!angka) return undefined;
      var n = parseInt(angka.textContent, 10);
      if (isNaN(n) || n < 1 || n > 16) return undefined;
      return n;
    }

    function regenAktivitasDenganPertemuan(el) {
      var n = hitungPertemuanPending(el);
      var cur = state.module && state.module.meetings ?
        state.module.meetings.length : undefined;
      var extra = (typeof n === 'number' && n !== cur) ?
        { n_meetings: n } : undefined;
      regenBagian('aktivitas', el, undefined, extra);
    }
    $('btn-mode-edit').addEventListener('click', masukEdit);
    $('btn-simpan-versi').addEventListener('click', simpanVersiDanKeluar);
    $('btn-finalize').addEventListener('click', simpanGlobal);
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-regen]'),
      function (btn) {
        btn.addEventListener('click', function () {
          regenBagian(btn.getAttribute('data-regen'), btn);
        });
      });
    window.addEventListener('beforeunload', function (e) {
      if (state.dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
    $('btn-export-docx').addEventListener('click', function () {
      if (state.generationId) {
        window.location.assign(currentExportUrl());
      }
    });
    $('f-sistem').addEventListener('change', onSistem);
    $('f-institusi').addEventListener('change', onInstitusi);
    $('f-kelas').addEventListener('change', onKelas);
    $('f-mapel').addEventListener('change', onMapel);
    window.Api.getCurriculumOptions().then(initForm).catch(function () {
      formError('Gagal memuat data kurikulum dari backend. Muat ulang halaman.');
    });
    route();
  }

  function route() {
    var hash = window.location.hash || '';
    if (hash === '#layar-formulir') {
      tampilkanFormulir();
    } else if (hash === '#layar-beranda') {
      tampilkanBeranda();
    } else if (hash === '#layar-arsip') {
      tampilkanArsip();
    } else if (hash === '#layar-hasil') {
      // Back browser / tab baru: kembali ke hasil bila modul ada,
      // bila belum (fresh load) coba buka sesi tersimpan.
      if (state.module) show('layar-hasil');
      else if (!bukaUlangDariUrl()) show('layar-landing');
    } else if (hash === '' || hash === '#' || hash === '#layar-landing') {
      // Param ?generation_id= (hasil tersimpan) lebih utama daripada
      // landing kosong: coba buka ulang sesi sukses dari storage.
      if (bukaUlangDariUrl()) return;
      // Root kosong + returning user: otomatis ke Beranda. Hash landing
      // eksplisit (#layar-landing) selalu dihormati, landing tidak dikunci.
      if ((hash === '' || hash === '#') && sudahPernahBuka()) {
        tampilkanBeranda(); return;
      }
      tandaiPernahBuka();
      show('layar-landing'); muatStatistik();
    } else if (!state.module) {
      // Fresh load / tab baru pada anchor bagian (#a-identitas) dengan
      // ?generation_id=: pulihkan sesi. Bila modul sudah tampil,
      // biarkan browser scroll.
      bukaUlangDariUrl();
    }
    // Hash lain (#a-identitas, ...) adalah anchor dalam halaman:
    // biarkan browser scroll, jangan pindah layar.
  }
  window.addEventListener('hashchange', route);

  // Buka RPM dari Beranda tanpa reload: set URL + pakai progres yang
  // sama dengan bukaUlangDariUrl, tanpa paint landing di tengah.
  function bukaSesiLangsung(gid) {
    if (!gid) return;
    try {
      window.history.replaceState(null, '',
        '/app?generation_id=' + encodeURIComponent(gid) + '#layar-hasil');
    } catch (e) { /* URL opsional, abaikan */ }
    bukaUlangDariUrl();
  }

  function bukaUlangDariUrl() {
    var gid;
    try {
      gid = new URLSearchParams(window.location.search || '').get('generation_id');
    } catch (e) { return false; }
    if (!gid) return false;
    var gidDiminta = gid;
    // Layar progres tampil tanpa animasi bar (spinner tunggal = overlay
    // tengah), agar belakang overlay bukan landing page.
    show('layar-progres');
    $('progres-teks').textContent = 'Membuka sesi tersimpan…';
    var bar = $('progres-bar');
    if (bar) bar.hidden = true;
    tampilLoading('Membuka sesi', 'Membuka sesi tersimpan…');
    $('progres-id').textContent = gid;
    $('progres-error').hidden = true;
    $('btn-coba-lagi').hidden = true;
    $('btn-poll-ulang').hidden = true;
    function masihDiminta() {
      var kini = null;
      try {
        kini = new URLSearchParams(window.location.search || '')
          .get('generation_id');
      } catch (e) { kini = null; }
      if (kini !== gidDiminta) return false;
      var hash = window.location.hash || '';
      if (hash === '' || hash === '#' || hash === '#layar-hasil') return true;
      // Anchor bagian (#a-...) pada tab baru: sesi tetap harus dipulihkan.
      return hash.indexOf('#a-') === 0;
    }
    window.Api.getModule(gid).then(function (res) {
      if (!masihDiminta()) return;
      if (res.status === 'success' && res.module) {
        tampilkanHasil(res.module, res.validation || null,
          res.generation_id || gid);
      } else {
        var box = $('buka-error');
        var pesanSesi = 'Sesi tidak ditemukan di penyimpanan server.';
        box.hidden = false;
        box.textContent = pesanSesi;
        tampilAlert('Sesi tidak ditemukan', pesanSesi);
        show('layar-beranda');
      }
    }).catch(function () {
      if (!masihDiminta()) return;
      var box = $('buka-error');
      var pesanBuka = 'Gagal membuka sesi tersimpan. Periksa server.';
      box.hidden = false;
      box.textContent = pesanBuka;
      tampilAlert('Gagal membuka sesi', pesanBuka);
      show('layar-beranda');
    });
    return true;
  }

  /* ---------- landing: statistik kurikulum nyata ---------- */
  function formatRibuan(n) {
    return Number(n || 0).toLocaleString('id-ID');
  }

  function muatStatistik() {
    var box = document.getElementById('stat-kurikulum');
    if (!box || !window.Api || !window.Api.getStats) return;
    window.Api.getStats().then(function (res) {
      var stats = (res && res.statistics) || {};
      function isi(kunci, nilai) {
        var el = box.querySelector('[data-stat="' + kunci + '"]');
        if (el) el.textContent = formatRibuan(nilai);
      }
      isi('cp', stats.total_cp_entries);
      isi('dokumen', stats.total_documents);
      isi('fragmen', stats.total_fragments);
    }).catch(function () {
      box.hidden = true;
    });
  }

  /* ---------- beranda (dashboard: profil + riwayat RPM) ---------- */
  var STATUS_RPM = { validated: 'Tervalidasi', finalized: 'Final',
    draft: 'Draf' };

  function tampilkanBeranda() {
    bersihkanQuerySesi();
    show('layar-beranda');
    renderProfilRingkas();
    muatRiwayatRpm();
    muatKoleksiBuku();
  }

  function renderProfilRingkas() {
    var profil = bacaProfil();
    var box = $('profil-ringkas');
    var baris = [
      ['Nama Penyusun', profil.penyusun],
      ['Satuan Pendidikan', profil.satuan_pendidikan],
      ['Semester', profil.semester],
      ['Tahun Pelajaran', profil.tahun_ajaran]
    ];
    var ada = baris.some(function (r) { return r[1]; });
    if (!ada) {
      box.innerHTML = '';
      var kosong = document.createElement('p');
      kosong.className = 'meta';
      kosong.textContent = 'Belum diatur.';
      box.appendChild(kosong);
      return;
    }
    box.innerHTML = baris.filter(function (r) {
      return r[1];
    }).map(function (r) {
      return '<div><dt>' + escHtml(r[0]) + '</dt><dd>' + escHtml(r[1]) +
        '</dd></div>';
    }).join('');
  }

  function muatRiwayatRpm() {
    var box = $('riwayat-error');
    var kosong = $('riwayat-kosong');
    var daftar = $('riwayat-rpm');
    box.hidden = true;
    kosong.hidden = true;
    daftar.innerHTML = '';
    state.riwayat = [];
    perbaruiBulk();
    window.Api.listModules().then(function (res) {
      var modules = (res && res.modules) || [];
      // Beranda hanya yang aktif; arsip pindah ke menu Arsip.
      var aktif = modules.filter(function (m) { return !m.archived; });
      state.riwayat = aktif;
      $('bulk-kontrol').hidden = true;
      if (!aktif.length) {
        kosong.hidden = false;
        perbaruiBulk();
        return;
      }
      daftar.innerHTML = aktif.map(barisRiwayat).join('');
      perbaruiBulk();
    }).catch(function () {
      $('bulk-kontrol').hidden = true;
      box.hidden = false;
      var pesanRiwayat = 'Gagal memuat riwayat RPM. ' +
        'Periksa server lalu muat ulang halaman.';
      box.textContent = pesanRiwayat;
      tampilAlert('Gagal memuat riwayat', pesanRiwayat);
    });
  }

  /* ---------- upload RPM (DOCX/PDF hasil generate aplikasi) ---------- */
  function onBukaUpload() {
    var box = $('upload-error');
    var hasil = $('upload-hasil');
    box.hidden = true;
    hasil.hidden = true;
    $('upload-file').click();
  }

  function onFileUpload(e) {
    var input = e && e.target;
    var file = input && input.files && input.files[0];
    input.value = '';
    if (!file) return;
    var box = $('upload-error');
    var hasil = $('upload-hasil');
    box.hidden = true;
    hasil.hidden = true;
    tampilLoading('Mengupload RPM', 'Mengirim ' + file.name + '…');
    window.Api.uploadModule(file).then(function (res) {
      sembunyiLoading();
      var masuk = (res && res.imported) || [];
      var tolak = (res && res.rejected) || [];
      var draf = masuk.filter(function (r) {
        return r.status === 'draft';
      }).length;
      var pesan = masuk.length + ' RPM masuk Beranda' +
        (draf ? ' (' + draf + ' draf, perlu perbaikan)' : '') +
        (tolak.length ? ', ' + tolak.length + ' ditolak' : '') + '.';
      // R-39: yang lama berjudul sama otomatis terarsip (tidak nabrak).
      var autoArsip = masuk.reduce(function (n, r) {
        return n + ((r.archived_lama || []).length);
      }, 0);
      if (autoArsip) {
        pesan += ' ' + autoArsip + ' RPM lama berjudul sama dipindah ' +
          'ke Arsip.';
      }
      if (tolak.length) {
        box.hidden = false;
        var pesanTolak = tolak.map(function (r) {
          return (r.title || '(tanpa judul)') + ': ' +
            pesanError({ errors: r.errors });
        }).join(' ');
        box.textContent = pesanTolak;
        if (!masuk.length) {
          tampilAlert('Upload ditolak', pesanTolak);
        }
      }
      if (masuk.length) {
        hasil.hidden = false;
        hasil.textContent = pesan;
        tampilAlert(tolak.length ? 'Upload sebagian masuk' :
          'Upload berhasil', pesan +
          (tolak.length ? ' Yang ditolak: ' + tolak.map(function (r) {
            return (r.title || '(tanpa judul)') + ': ' +
              pesanError({ errors: r.errors });
          }).join(' ') : ''));
        muatRiwayatRpm();
      } else if (!tolak.length) {
        box.hidden = false;
        var pesanNihil = 'Tidak ada RPM yang masuk. ' +
          pesanError(res);
        box.textContent = pesanNihil;
        tampilAlert('Upload gagal', pesanNihil);
      }
    }).catch(function (err) {
      sembunyiLoading();
      box.hidden = false;
      var pesanUp = 'Upload gagal: ' +
        pesanError(err && err.data) +
        ' (hanya DOCX/PDF hasil generate aplikasi, maks 10MB).';
      box.textContent = pesanUp;
      tampilAlert('Upload gagal', pesanUp);
    });
  }

  function barisRiwayat(m) {
    var gid = m.generation_id || '';
    var judul = m.title || '(tanpa judul)';
    var meta = [m.subject, [m.grade, m.phase].filter(function (v) {
      return v;
    }).join('/'), m.updated_at,
      STATUS_RPM[m.status] || m.status].filter(function (v) {
      return v;
    }).join(' · ');
    // Badge asal (R-34): 'Hasil upload' hanya untuk origin impor;
    // baris generate tanpa badge (tanpa dekorasi tambahan).
    // Draf impor (R-37) ikut flag 'Draf' agar beda dari validated.
    // Arsip (R-40): badge 'Arsip' ikut token badge existing.
    var badge = (m.origin === 'import') ?
      ' <span class="badge-valid inline-block text-xs font-medium rounded px-2 py-0.5 bg-pagebg text-text2 border border-bord">Hasil upload</span>' : '';
    if (m.archived) {
      badge += ' <span class="badge-valid inline-block text-xs font-medium rounded px-2 py-0.5 bg-pagebg text-text2 border border-bord">Arsip</span>';
    }
    if (m.status === 'draft') {
      badge += ' <span class="badge-valid is-gagal inline-block text-xs font-medium rounded px-2 py-0.5 bg-red-50 text-galat border border-galat">Draf</span>';
    }
    var buka = '/app?generation_id=' + encodeURIComponent(gid) +
      '#layar-hasil';
    var aksi = '<a class="btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1 inline-flex items-center" href="' + escHtml(buka) +
      '">Buka</a>';
    if (m.status && m.status !== 'draft') {
      aksi += ' <a class="btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1 inline-flex items-center" href="' +
        escHtml(window.Api.exportDocxUrl(gid)) + '">Export DOCX</a>';
    }
    var checked = state.pilihan[gid] ? ' checked' : '';
    var menuId = 'menu-' + gid;
    return '<li class="rpm-card bg-white border border-bord rounded-xl p-4 flex items-start gap-3">' +
      '<label class="pilih mt-1"><input type="checkbox" class="pilih__box w-5 h-5 accent-primary" data-gid="' +
      escHtml(gid) + '" aria-label="Pilih ' + escHtml(judul) + '"' +
      checked + '></label>' +
      '<div class="rpm-card__isi flex-1"><strong class="font-display text-text1">' + escHtml(judul) + badge +
      '</strong><p class="meta text-sm text-text2 mt-1">' + escHtml(meta) + '</p>' +
      '<button type="button" class="titik" data-titik="' + escHtml(gid) +
      '" aria-label="Opsi untuk ' + escHtml(judul) + '" aria-expanded="false" aria-controls="' +
      escHtml(menuId) + '">···</button>' +
      '<div class="menu-pilih" id="' + escHtml(menuId) + '" hidden role="menu">' +
      '<button type="button" data-aksi-pilih="' + escHtml(gid) + '" role="menuitem">Pilih</button>' +
      '</div></div>' +
      '<div class="form__actions flex gap-2">' + aksi + '</div></li>';
  }

  function gidTerlihat() {
    return (state.riwayat || []).map(function (m) {
      return m.generation_id;
    }).filter(function (g) { return g; });
  }

  function jumlahDipilih() {
    var n = 0;
    gidTerlihat().forEach(function (g) {
      if (state.pilihan[g]) n++;
    });
    return n;
  }

  // Sinkronkan Select All + toolbar dengan state pilihan.
  function perbaruiBulk() {
    var semua = gidTerlihat();
    var n = jumlahDipilih();
    var pilihSemua = $('bulk-pilih');
    var bilah = $('bulk-bilah');
    if (!semua.length) {
      pilihSemua.checked = false;
      pilihSemua.indeterminate = false;
      pilihSemua.disabled = true;
      bilah.hidden = true;
      return;
    }
    pilihSemua.disabled = false;
    pilihSemua.checked = n > 0 && n === semua.length;
    pilihSemua.indeterminate = n > 0 && n < semua.length;
    $('bulk-jumlah').textContent = n + ' dipilih';
    bilah.hidden = n === 0;
    $('bulk-kontrol').hidden = n === 0;
    terapkanModePilih('riwayat-rpm', n > 0);
  }

  function onPilihItem(e) {
    var box = e && e.target;
    if (!box || !box.getAttribute) return;
    var gid = box.getAttribute('data-gid');
    if (!gid) return;
    if (box.checked) state.pilihan[gid] = true;
    else delete state.pilihan[gid];
    perbaruiBulk();
  }

  function onPilihSemua(e) {
    var nyala = !!(e && e.target && e.target.checked);
    gidTerlihat().forEach(function (g) {
      if (nyala) state.pilihan[g] = true;
      else delete state.pilihan[g];
    });
    muatUlangCentang();
    perbaruiBulk();
  }

  /* ---------- menu ⋯ + mode pilih (Beranda/Arsip/Log) ---------- */
  // Satu menu terbuka dalam satu waktu; Escape/backdrop menutup.
  function tutupSemuaMenu(daftarId) {
    (daftarId || ['riwayat-rpm', 'riwayat-arsip', 'daftar-log']).forEach(
      function (id) {
        var daftar = $(id);
        if (!daftar || !daftar.querySelectorAll) return;
        Array.prototype.forEach.call(
          daftar.querySelectorAll('.menu-pilih'),
          function (m) { m.hidden = true; });
        Array.prototype.forEach.call(
          daftar.querySelectorAll('[data-titik],[data-titiklog]'),
          function (b) { b.setAttribute('aria-expanded', 'false'); });
      });
  }

  function bukaMenu(tombol, menu) {
    var sedangBuka = !menu.hidden;
    tutupSemuaMenu();
    menu.hidden = sedangBuka;
    tombol.setAttribute('aria-expanded', sedangBuka ? 'false' : 'true');
    if (!sedangBuka) {
      var item = menu.querySelector('button');
      if (item && item.focus) item.focus();
    }
  }

  // Mode pilih per daftar: checkbox + toolbar hanya muncul setelah
  // pengguna memilih lewat menu ⋯. Keluar otomatis saat kosong.
  function terapkanModePilih(idDaftar, adaPilihan) {
    var daftar = $(idDaftar);
    if (!daftar || !daftar.classList) return;
    daftar.classList.toggle('mode-pilih', !!adaPilihan);
  }

  function pilihKartu(idDaftar, gid, kunciState, muatUlang, perbarui) {
    if (kunciState === 'pilihanLog') state.pilihanLog[gid] = true;
    else if (kunciState === 'pilihanArsip') state.pilihanArsip[gid] = true;
    else state.pilihan[gid] = true;
    muatUlang();
    perbarui();
    terapkanModePilih(idDaftar, true);
    tutupSemuaMenu([idDaftar]);
  }

  function onMenuKartu(e, idDaftar, kunciState, muatUlang, perbarui,
      attrTitik, attrAksi) {
    var t = e && e.target;
    if (!t || !t.closest) return false;
    var tombol = t.closest('[data-titik],[data-titiklog]');
    if (tombol && tombol.tagName === 'BUTTON' && tombol.getAttribute &&
        tombol.getAttribute(attrTitik) !== null &&
        tombol.getAttribute(attrTitik) !== undefined) {
      var daftar = $(idDaftar);
      var menu = (daftar && daftar.querySelector) ? daftar.querySelector('#' +
        (tombol.getAttribute('aria-controls') || '')) : null;
      if (menu) bukaMenu(tombol, menu);
      if (e.preventDefault) e.preventDefault();
      return true;
    }
    var aksi = t.closest('[data-aksi-pilih],[data-aksi-pilihlog]');
    if (aksi && aksi.tagName === 'BUTTON' && aksi.getAttribute &&
        aksi.getAttribute(attrAksi) !== null &&
        aksi.getAttribute(attrAksi) !== undefined) {
      var gid = aksi.getAttribute(attrAksi);
      if (gid) pilihKartu(idDaftar, gid, kunciState, muatUlang, perbarui);
      if (e.preventDefault) e.preventDefault();
      return true;
    }
    return false;
  }

  // Terapkan state pilihan ke checkbox yang sedang tampil.
  function muatUlangCentang() {
    var daftar = $('riwayat-rpm');
    if (!daftar || !daftar.querySelectorAll) return;
    Array.prototype.forEach.call(
      daftar.querySelectorAll('.pilih__box'),
      function (box) {
        var gid = box.getAttribute && box.getAttribute('data-gid');
        if (gid) box.checked = !!state.pilihan[gid];
      });
  }

  /* ---------- focus trap modal (aksesibilitas keyboard) ---------- */
  // Dialog memakai aria-modal: fokus Tab terkunci di dalam dialog yang
  // terbuka, Esc menutup, dan fokus kembali ke tombol pemicu.
  var modalPemicu = null;
  var modalAktif = null;

  function kunciFokusModal(overlayId) {
    var overlay = $(overlayId);
    if (!overlay || overlay.hidden) return;
    var fokusabel = overlay.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    fokusabel = Array.prototype.filter.call(fokusabel, function (el) {
      return !el.disabled && el.offsetParent !== null;
    });
    if (!fokusabel.length) return;
    var pertama = fokusabel[0];
    var terakhir = fokusabel[fokusabel.length - 1];
    if (document.activeElement === terakhir) {
      pertama.focus();
    } else if (document.activeElement === pertama) {
      terakhir.focus();
    } else if (overlay.contains(document.activeElement)) {
      var idx = Array.prototype.indexOf.call(fokusabel, document.activeElement);
      var maju = !window.event || window.event.shiftKey !== true;
      var next = maju ? fokusabel[(idx + 1) % fokusabel.length] :
        fokusabel[(idx - 1 + fokusabel.length) % fokusabel.length];
      next.focus();
    } else {
      pertama.focus();
    }
  }

  /* Sinkron vanilla <-> Alpine store (body x-data="rpmModal()"). */
  function alpineStore() {
    try {
      if (!window.Alpine) return null;
      if (typeof window.Alpine.$data === 'function') {
        return window.Alpine.$data(document.body);
      }
      var root = document.querySelector('body');
      if (root && root._x_dataStack && root._x_dataStack[0]) {
        return root._x_dataStack[0];
      }
    } catch (e) { /* abaikan: fallback hidden tetap jalan */ }
    return null;
  }

  function bukaModal(overlayId, pemicu, fokusAwalId) {
    modalPemicu = pemicu || document.activeElement || null;
    modalAktif = overlayId;
    $(overlayId).hidden = false;
    var store = alpineStore();
    if (store && typeof store.open === 'function') store.open(overlayId);
    var awal = $(fokusAwalId);
    if (awal && awal.focus) awal.focus();
  }

  function tutupModal(overlayId) {
    $(overlayId).hidden = true;
    var store = alpineStore();
    if (store && typeof store.close === 'function') store.close(overlayId);
    if (modalAktif === overlayId) modalAktif = null;
    if (modalPemicu && modalPemicu.focus) {
      try { modalPemicu.focus(); } catch (e) { /* abaikan */ }
      modalPemicu = null;
    }
  }

  /* Bridge Alpine -> vanilla: Escape/backdrop dari store. */
  window.ModalUI = {
    minta: function (overlayId) {
      var peta = {
        'log-overlay': (typeof tutupLog !== 'undefined') && tutupLog,
        'hapus-overlay': (typeof tutupHapus !== 'undefined') && tutupHapus,
        'hapus-log-overlay': (typeof tutupHapusLog !== 'undefined') && tutupHapusLog,
        'hapus-versi-overlay': (typeof tutupHapusVersi !== 'undefined') && tutupHapusVersi,
        'arsip-overlay': (typeof tutupArsip !== 'undefined') && tutupArsip,
        'kembalikan-overlay': (typeof tutupKembalikan !== 'undefined') && tutupKembalikan,
        'profil-overlay': (typeof tutupProfil !== 'undefined') && tutupProfil,
        'alert-overlay': (typeof tutupAlert !== 'undefined') && tutupAlert
      };
      var fn = peta[overlayId];
      if (typeof fn === 'function') fn();
      else tutupModal(overlayId);
    }
  };

  /* ---------- popup alert terpusat ---------- */
  // Satu pintu info/sukses/gagal: judul + pesan di overlay dialog.
  // Bukan window.alert agar focus-trap + fokus-kembali + gaya dialog
  // tetap jalan. Status inline tetap ditulis agar jejak terbaca.
  function tampilAlert(judul, pesan) {
    // Bila dipanggil dari atas modal lain (hapus/profil/log/loading):
    // bukaModal menimpa modalAktif/pemicu, jadi simpan dulu agar
    // tutupAlert mengembalikan fokus ke dialog bawah.
    if (modalAktif && modalAktif !== 'alert-overlay' &&
        !$(modalAktif).hidden && !alertPrev) {
      alertPrev = { id: modalAktif, pemicu: modalPemicu };
    }
    $('alert-judul').textContent = judul || 'Pemberitahuan';
    $('alert-pesan').textContent = pesan || '';
    bukaModal('alert-overlay', document.activeElement,
      'btn-alert-tutup');
  }

  // Tumpukan alert di atas modal lain: ingat modal bawah agar
  // Escape/focus-trap kembali ke dialog bawah setelah alert tutup.
  var alertPrev = null;

  function tutupAlert() {
    tutupModal('alert-overlay');
    if (alertPrev) {
      modalAktif = alertPrev.id;
      modalPemicu = alertPrev.pemicu;
      alertPrev = null;
    }
  }

  document.addEventListener('keydown', function (ev) {
    if (!modalAktif || $(modalAktif).hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      if (modalAktif === 'hapus-overlay') tutupHapus();
      else if (modalAktif === 'hapus-log-overlay') tutupHapusLog();
      else if (modalAktif === 'hapus-versi-overlay') tutupHapusVersi();
      else if (modalAktif === 'arsip-overlay') tutupArsip();
      else if (modalAktif === 'kembalikan-overlay') tutupKembalikan();
      else if (modalAktif === 'profil-overlay') tutupProfil();
      else if (modalAktif === 'log-overlay') tutupLog();
      else if (modalAktif === 'alert-overlay') tutupAlert();
      return;
    }
    if (ev.key === 'Tab') {
      ev.preventDefault();
      kunciFokusModal(modalAktif);
    }
  });

  function bukaHapus() {
    var n = jumlahDipilih();
    if (!n) return;
    $('hapus-judul').textContent = 'Hapus ' + n + ' RPM?';
    $('hapus-pesan').textContent = 'RPM yang dipilih akan dihapus ' +
      'dari riwayat. Tindakan ini tidak dapat dibatalkan.';
    $('hapus-error').hidden = true;
    bukaModal('hapus-overlay', document.activeElement, 'btn-batal-hapus');
  }

  function tutupHapus() {
    tutupModal('hapus-overlay');
  }

  function hapusTerpilih() {
    // Hapus dari Beranda atau dari Arsip (pilihanArsipHapus): kedua
    // jalur hapus permanen yang sama (R-38).
    var dariArsip = (state.pilihanArsipHapus || []).length > 0;
    var daftar = dariArsip ? state.pilihanArsipHapus.slice() :
      gidTerlihat().filter(function (g) {
        return state.pilihan[g];
      });
    if (!daftar.length) { tutupHapus(); return; }
    var tombol = $('btn-konfirmasi-hapus');
    tombol.disabled = true;
    $('hapus-error').hidden = true;
    var gagal = [];
    tampilLoading('Menghapus RPM', 'Menghapus 1 dari ' + daftar.length + '…');
    function lanjut(i) {
      if (i >= daftar.length) {
        tombol.disabled = false;
        sembunyiLoading();
        tutupHapus();
        state.pilihanArsipHapus = [];
        daftar.forEach(function (g) {
          if (gagal.indexOf(g) === -1) {
            delete state.pilihan[g];
            delete state.pilihanArsip[g];
          }
        });
        muatRiwayatRpm();
        if (!$('layar-arsip').hidden) muatRiwayatArsip();
        if (gagal.length) {
          var box = $('riwayat-error');
          var pesanHapus = gagal.length + ' dari ' + daftar.length +
            ' RPM gagal dihapus. Pilihan yang gagal dipertahankan, ' +
            'silakan coba lagi.';
          box.hidden = false;
          box.textContent = pesanHapus;
          tampilAlert('Hapus sebagian gagal', pesanHapus);
        } else {
          tampilAlert('RPM dihapus',
            daftar.length + ' RPM dihapus dari riwayat.');
        }
        return;
      }
      perbaruiLoading('Menghapus ' + (i + 1) + ' dari ' + daftar.length + '…');
      window.Api.deleteModule(daftar[i]).then(function () {
        lanjut(i + 1);
      }).catch(function () {
        gagal.push(daftar[i]);
        lanjut(i + 1);
      });
    }
    lanjut(0);
  }

  /* ---------- Arsip RPM (R-38..R-40) ---------- */
  // Flag DB; baris + versi + log utuh; modul tetap bisa dibuka/edit.
  function gidArsipTerlihat() {
    return (state.riwayatArsip || []).map(function (m) {
      return m.generation_id;
    }).filter(function (g) { return g; });
  }

  function jumlahArsipDipilih() {
    var n = 0;
    gidArsipTerlihat().forEach(function (g) {
      if (state.pilihanArsip[g]) n++;
    });
    return n;
  }

  function perbaruiBulkArsip() {
    var semua = gidArsipTerlihat();
    var n = jumlahArsipDipilih();
    var pilihSemua = $('arsip-bulk-pilih');
    var kontrol = $('arsip-bulk-kontrol');
    var bilah = $('arsip-bulk-bilah');
    if (!semua.length) {
      pilihSemua.checked = false;
      pilihSemua.indeterminate = false;
      pilihSemua.disabled = true;
      kontrol.hidden = true;
      bilah.hidden = true;
      terapkanModePilih('riwayat-arsip', false);
      return;
    }
    kontrol.hidden = n === 0;
    pilihSemua.disabled = false;
    pilihSemua.checked = n > 0 && n === semua.length;
    pilihSemua.indeterminate = n > 0 && n < semua.length;
    $('arsip-bulk-jumlah').textContent = n + ' dipilih';
    bilah.hidden = n === 0;
    terapkanModePilih('riwayat-arsip', n > 0);
  }

  function muatUlangCentangArsip() {
    var daftar = $('riwayat-arsip');
    if (!daftar || !daftar.querySelectorAll) return;
    Array.prototype.forEach.call(
      daftar.querySelectorAll('.pilih__box'),
      function (box) {
        var gid = box.getAttribute && box.getAttribute('data-gid');
        if (gid) box.checked = !!state.pilihanArsip[gid];
      });
  }

  function onPilihItemArsip(e) {
    var box = e && e.target;
    if (!box || !box.getAttribute) return;
    var gid = box.getAttribute('data-gid');
    if (!gid) return;
    if (box.checked) state.pilihanArsip[gid] = true;
    else delete state.pilihanArsip[gid];
    perbaruiBulkArsip();
  }

  function onPilihSemuaArsip(e) {
    var nyala = !!(e && e.target && e.target.checked);
    gidArsipTerlihat().forEach(function (g) {
      if (nyala) state.pilihanArsip[g] = true;
      else delete state.pilihanArsip[g];
    });
    muatUlangCentangArsip();
    perbaruiBulkArsip();
  }

  function tampilkanArsip() {
    bersihkanQuerySesi();
    show('layar-arsip');
    muatRiwayatArsip();
  }

  function muatRiwayatArsip() {
    var box = $('arsip-error');
    var kosong = $('arsip-kosong');
    var daftar = $('riwayat-arsip');
    box.hidden = true;
    kosong.hidden = true;
    daftar.innerHTML = '';
    state.riwayatArsip = [];
    perbaruiBulkArsip();
    window.Api.listModules().then(function (res) {
      var modules = (res && res.modules) || [];
      var arsip = modules.filter(function (m) { return m.archived; });
      state.riwayatArsip = arsip;
      $('arsip-bulk-kontrol').hidden = true;
      if (!arsip.length) {
        kosong.hidden = false;
        perbaruiBulkArsip();
        return;
      }
      daftar.innerHTML = arsip.map(barisRiwayat).join('');
      muatUlangCentangArsip();
      perbaruiBulkArsip();
    }).catch(function () {
      $('arsip-bulk-kontrol').hidden = true;
      box.hidden = false;
      var pesan = 'Gagal memuat arsip. Periksa server lalu muat ulang.';
      box.textContent = pesan;
      tampilAlert('Gagal memuat arsip', pesan);
    });
  }

  function bukaArsip() {
    var daftar = gidTerlihat().filter(function (g) {
      return state.pilihan[g];
    });
    if (!daftar.length) return;
    state.arsipTarget = daftar;
    $('arsip-judul').textContent = 'Arsipkan ' + daftar.length + ' RPM?';
    $('arsip-pesan').textContent = daftar.length + ' RPM dipindah ke ' +
      'Arsip (data utuh, tetap bisa dibuka). Upload judul sama tidak ' +
      'akan nabrak lagi.';
    $('arsip-error').hidden = true;
    bukaModal('arsip-overlay', document.activeElement, 'btn-batal-arsip');
  }

  function tutupArsip() {
    state.arsipTarget = [];
    tutupModal('arsip-overlay');
  }

  function arsipTerpilih() {
    var daftar = state.arsipTarget || [];
    if (!daftar.length) { tutupArsip(); return; }
    var tombol = $('btn-konfirmasi-arsip');
    tombol.disabled = true;
    $('arsip-error').hidden = true;
    var gagal = [];
    tampilLoading('Mengarsipkan RPM',
      'Mengarsipkan 1 dari ' + daftar.length + '…');
    function lanjut(i) {
      if (i >= daftar.length) {
        tombol.disabled = false;
        sembunyiLoading();
        tutupArsip();
        daftar.forEach(function (g) {
          if (gagal.indexOf(g) === -1) delete state.pilihan[g];
        });
        muatRiwayatRpm();
        if (gagal.length) {
          tampilAlert('Arsip sebagian gagal', gagal.length + ' dari ' +
            daftar.length + ' RPM gagal diarsipkan. Silakan coba lagi.');
        } else {
          tampilAlert('RPM diarsipkan', daftar.length +
            ' RPM dipindah ke Arsip.');
        }
        return;
      }
      perbaruiLoading('Mengarsipkan ' + (i + 1) + ' dari ' +
        daftar.length + '…');
      window.Api.archiveModule(daftar[i]).then(function () {
        lanjut(i + 1);
      }).catch(function () {
        gagal.push(daftar[i]);
        lanjut(i + 1);
      });
    }
    lanjut(0);
  }

  function bukaKembalikan() {
    var daftar = gidArsipTerlihat().filter(function (g) {
      return state.pilihanArsip[g];
    });
    if (!daftar.length) return;
    state.kembalikanTarget = daftar;
    $('kembalikan-judul').textContent = 'Kembalikan ' + daftar.length +
      ' RPM?';
    $('kembalikan-pesan').textContent = daftar.length + ' RPM kembali ' +
      'aktif di Beranda.';
    $('kembalikan-error').hidden = true;
    bukaModal('kembalikan-overlay', document.activeElement,
      'btn-batal-kembalikan');
  }

  function tutupKembalikan() {
    state.kembalikanTarget = [];
    tutupModal('kembalikan-overlay');
  }

  function kembalikanTerpilih() {
    var daftar = state.kembalikanTarget || [];
    if (!daftar.length) { tutupKembalikan(); return; }
    var tombol = $('btn-konfirmasi-kembalikan');
    tombol.disabled = true;
    $('kembalikan-error').hidden = true;
    var gagal = [];
    tampilLoading('Mengembalikan RPM',
      'Mengembalikan 1 dari ' + daftar.length + '…');
    function lanjut(i) {
      if (i >= daftar.length) {
        tombol.disabled = false;
        sembunyiLoading();
        tutupKembalikan();
        daftar.forEach(function (g) {
          if (gagal.indexOf(g) === -1) delete state.pilihanArsip[g];
        });
        muatRiwayatArsip();
        muatRiwayatRpm();
        if (gagal.length) {
          tampilAlert('Kembalikan sebagian gagal', gagal.length +
            ' dari ' + daftar.length + ' RPM gagal dikembalikan.');
        } else {
          tampilAlert('RPM dikembalikan', daftar.length +
            ' RPM kembali aktif di Beranda.');
        }
        return;
      }
      perbaruiLoading('Mengembalikan ' + (i + 1) + ' dari ' +
        daftar.length + '…');
      window.Api.unarchiveModule(daftar[i]).then(function () {
        lanjut(i + 1);
      }).catch(function () {
        gagal.push(daftar[i]);
        lanjut(i + 1);
      });
    }
    lanjut(0);
  }

  function bukaHapusArsip() {
    var daftar = gidArsipTerlihat().filter(function (g) {
      return state.pilihanArsip[g];
    });
    if (!daftar.length) return;
    // Hapus dari Arsip = hapus permanen yang sama (R-38: arsip ikut
    // kehapus). Pakai dialog hapus existing, lalu muat ulang Arsip.
    state.pilihanArsipHapus = daftar;
    $('hapus-judul').textContent = 'Hapus ' + daftar.length +
      ' RPM arsip permanen?';
    $('hapus-pesan').textContent = daftar.length + ' RPM arsip akan ' +
      'dihapus permanen dari riwayat. Tindakan ini tidak dapat ' +
      'dibatalkan.';
    $('hapus-error').hidden = true;
    bukaModal('hapus-overlay', document.activeElement, 'btn-batal-hapus');
  }

  /* ---------- hapus permanen baris audit Log ---------- */
  // Hanya generation_logs; modul di Beranda TIDAK ikut terhapus.
  function gidLogTerlihat() {
    return (state.riwayatLog || []).map(function (g) {
      return g.generation_id;
    }).filter(function (g) { return g; });
  }

  function jumlahLogDipilih() {
    var n = 0;
    gidLogTerlihat().forEach(function (g) {
      if (state.pilihanLog[g]) n++;
    });
    return n;
  }

  function perbaruiBulkLog() {
    var semua = gidLogTerlihat();
    var n = jumlahLogDipilih();
    var pilihSemua = $('log-bulk-pilih');
    var kontrol = $('log-bulk-kontrol');
    var bilah = $('log-bulk-bilah');
    if (!semua.length) {
      pilihSemua.checked = false;
      pilihSemua.indeterminate = false;
      pilihSemua.disabled = true;
      kontrol.hidden = true;
      bilah.hidden = true;
      terapkanModePilih('daftar-log', false);
      return;
    }
    kontrol.hidden = n === 0;
    pilihSemua.disabled = false;
    pilihSemua.checked = n > 0 && n === semua.length;
    pilihSemua.indeterminate = n > 0 && n < semua.length;
    $('log-bulk-jumlah').textContent = n + ' dipilih';
    bilah.hidden = n === 0;
    terapkanModePilih('daftar-log', n > 0);
  }

  function muatUlangCentangLog() {
    var daftar = $('daftar-log');
    if (!daftar || !daftar.querySelectorAll) return;
    Array.prototype.forEach.call(
      daftar.querySelectorAll('.pilih__box'),
      function (box) {
        var gid = box.getAttribute && box.getAttribute('data-gidlog');
        if (gid) box.checked = !!state.pilihanLog[gid];
      });
  }

  function onPilihLog(e) {
    var box = e && e.target;
    if (!box || !box.getAttribute) return;
    var gid = box.getAttribute('data-gidlog');
    if (!gid) return;
    if (box.checked) state.pilihanLog[gid] = true;
    else delete state.pilihanLog[gid];
    perbaruiBulkLog();
  }

  function onPilihSemuaLog(e) {
    var nyala = !!(e && e.target && e.target.checked);
    gidLogTerlihat().forEach(function (g) {
      if (nyala) state.pilihanLog[g] = true;
      else delete state.pilihanLog[g];
    });
    muatUlangCentangLog();
    perbaruiBulkLog();
  }

  function bukaHapusLog() {
    var n = jumlahLogDipilih();
    if (!n) return;
    $('hapus-log-judul').textContent = 'Hapus ' + n + ' log permanen?';
    $('hapus-log-pesan').textContent = n + ' baris audit log akan ' +
      'dihapus permanen. RPM di Beranda TIDAK ikut terhapus.';
    $('hapus-log-error').hidden = true;
    bukaModal('hapus-log-overlay', document.activeElement,
      'btn-batal-hapus-log');
  }

  function tutupHapusLog() {
    tutupModal('hapus-log-overlay');
  }

  function hapusLogTerpilih() {
    var daftar = gidLogTerlihat().filter(function (g) {
      return state.pilihanLog[g];
    });
    if (!daftar.length) { tutupHapusLog(); return; }
    var tombol = $('btn-konfirmasi-hapus-log');
    tombol.disabled = true;
    $('hapus-log-error').hidden = true;
    tampilLoading('Menghapus log', 'Menghapus 1 dari ' + daftar.length + '…');
    window.Api.deleteGenerationLogs(daftar).then(function (res) {
      tombol.disabled = false;
      sembunyiLoading();
      tutupHapusLog();
      var sudah = ((res && res.deleted) || []).length;
      var hilang = ((res && res.missing) || []).length;
      daftar.forEach(function (g) {
        delete state.pilihanLog[g];
      });
      muatLog();
      var pesan = sudah + ' log dihapus permanen' +
        (hilang ? ', ' + hilang + ' sudah tidak ada' : '') + '.';
      tampilAlert(hilang && !sudah ? 'Sebagian log gagal dihapus' :
        'Log dihapus', pesan);
    }).catch(function (err) {
      tombol.disabled = false;
      sembunyiLoading();
      var rincian = pesanError((err && err.data) || {});
      var pesanGagal = 'Gagal menghapus log. ' + rincian;
      var box = $('hapus-log-error');
      box.hidden = false;
      box.textContent = pesanGagal;
      tampilAlert('Gagal menghapus log', pesanGagal);
    });
  }

  /* ---------- log generate (audit trail: riwayat + error per stage) ---------- */
  var STATUS_LOG = { success: 'Sukses', failed: 'Gagal',
    partial: 'Sebagian gagal', running: 'Berjalan' };

  function tampilkanLog() {
    muatLog();
    bukaModal('log-overlay', document.activeElement, 'btn-tutup-log-overlay');
  }

  function tutupLog() {
    tutupModal('log-overlay');
  }

  function muatLog() {
    var box = $('log-error');
    var kosong = $('log-kosong');
    var daftar = $('daftar-log');
    box.hidden = true;
    kosong.hidden = true;
    daftar.innerHTML = '<li class="meta" role="status">Memuat log…</li>';
    tutupDetailLog();
    window.Api.listGenerations().then(function (res) {
      var items = (res && res.generations) || [];
      state.riwayatLog = items;
      if (!items.length) {
        kosong.hidden = false;
        perbaruiBulkLog();
        return;
      }
      daftar.innerHTML = items.map(barisLog).join('');
      muatUlangCentangLog();
      perbaruiBulkLog();
    }).catch(function () {
      var pesanLog = 'Gagal memuat log generate. ' +
        'Periksa server lalu muat ulang halaman.';
      box.hidden = false;
      box.textContent = pesanLog;
      tampilAlert('Gagal memuat log', pesanLog);
    });
  }

  function barisLog(g) {
    var gid = g.generation_id || '';
    var pendek = gid.length > 8 ? gid.slice(0, 8) : gid;
    var meta = [(STATUS_LOG[g.status] || g.status),
      (g.attempts || 0) + ' tahap',
      (g.error_categories || []).join(', '),
      g.updated_at].filter(function (v) {
      return v;
    }).join(' · ');
    var checked = state.pilihanLog[gid] ? ' checked' : '';
    var menuId = 'menulog-' + gid;
    return '<li class="rpm-card">' +
      '<label class="pilih"><input type="checkbox" class="pilih__box" data-gidlog="' +
      escHtml(gid) + '" aria-label="Pilih log ' + escHtml(pendek) + '"' +
      checked + '></label>' +
      '<div class="rpm-card__isi"><strong>' + escHtml(pendek || '(tanpa id)') +
      '</strong><p class="meta">' + escHtml(meta) + '</p>' +
      '<button type="button" class="titik" data-titiklog="' + escHtml(gid) +
      '" aria-label="Opsi untuk log ' + escHtml(pendek) + '" aria-expanded="false" aria-controls="' +
      escHtml(menuId) + '">···</button>' +
      '<div class="menu-pilih" id="' + escHtml(menuId) + '" hidden role="menu">' +
      '<button type="button" data-aksi-pilihlog="' + escHtml(gid) + '" role="menuitem">Pilih</button>' +
      '</div></div>' +
      '<div class="form__actions"><button type="button" class="btn" data-log="' +
      escHtml(gid) + '">Detail</button></div></li>';
  }

  function bukaDetailLog(gid) {
    var panel = $('log-detail');
    panel.hidden = true;
    $('log-detail-isi').innerHTML =
      '<p class="meta" role="status">Memuat detail…</p>';
    window.Api.getGenerationLog(gid).then(function (res) {
      var records = (res && res.records) || [];
      $('log-detail-judul').textContent = 'Detail ' +
        (gid.length > 8 ? gid.slice(0, 8) : gid);
      $('log-detail-meta').textContent = records.length + ' tahap tercatat.';
      $('log-detail-isi').innerHTML = records.length ?
        '<ul class="toc"><li>' +
        records.map(function (r) {
          return escHtml([r.stage, 'percobaan ' + r.attempt, r.status,
            r.error_category || r.error || ''].filter(function (v) {
            return v;
          }).join(' · '));
        }).join('</li><li>') + '</li></ul>' :
        '<p class="meta">Tidak ada tahap tercatat untuk generate ini.</p>';
      panel.hidden = false;
    }).catch(function () {
      var box = $('log-error');
      var pesanDetail = 'Gagal memuat detail generate.';
      box.hidden = false;
      box.textContent = pesanDetail;
      tampilAlert('Gagal memuat detail log', pesanDetail);
    });
  }

  function tutupDetailLog() {
    var panel = $('log-detail');
    if (panel) panel.hidden = true;
  }

  /* ---------- profil pengguna (default metadata, localStorage) ---------- */
  var PROFIL_KEY = 'rpm_profile';

  /* ---------- flag kunjungan (localStorage, bukan cookie) ---------- */
  // Kunci kecil "pernah buka aplikasi" untuk bedakan user baru vs
  // returning user. Profil bikinan user tetap satu-satunya data profil.
  var KUNJUNGAN_KEY = 'rpm_pernah_buka';

  function sudahPernahBuka() {
    try {
      return !!(window.localStorage &&
        window.localStorage.getItem(KUNJUNGAN_KEY));
    } catch (e) { return false; }
  }

  function tandaiPernahBuka() {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(KUNJUNGAN_KEY, '1');
      }
    } catch (e) { /* penyimpanan tak tersedia: anggap user baru */ }
  }

  function bacaProfil() {
    var stored = null;
    try {
      stored = window.localStorage &&
        window.localStorage.getItem(PROFIL_KEY);
    } catch (e) { stored = null; }
    var profil = { penyusun: '', satuan_pendidikan: '', semester: '',
      tahun_ajaran: '' };
    if (!stored) return profil;
    try {
      var data = JSON.parse(stored);
      ['penyusun', 'satuan_pendidikan', 'semester',
        'tahun_ajaran'].forEach(function (k) {
        if (typeof data[k] === 'string') profil[k] = data[k];
      });
    } catch (e) { /* profil rusak: abaikan, pakai kosong */ }
    return profil;
  }

  function tulisProfil(profil) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(PROFIL_KEY, JSON.stringify(profil));
        return true;
      }
    } catch (e) { /* penyimpanan tak tersedia */ }
    return false;
  }

  function bukaProfil() {
    var profil = bacaProfil();
    $('p-penyusun').value = profil.penyusun;
    $('p-satuan').value = profil.satuan_pendidikan;
    $('p-semester').value = profil.semester;
    $('p-tahun').value = profil.tahun_ajaran;
    $('profil-status').textContent = '';
    bukaModal('profil-overlay', document.activeElement, 'p-penyusun');
  }

  function tutupProfil() {
    tutupModal('profil-overlay');
  }

  function simpanProfil() {
    var profil = {
      penyusun: $('p-penyusun').value.trim(),
      satuan_pendidikan: $('p-satuan').value.trim(),
      semester: $('p-semester').value,
      tahun_ajaran: $('p-tahun').value.trim()
    };
    if (tulisProfil(profil)) {
      $('profil-status').textContent = 'Profil tersimpan.';
      renderProfilRingkas();
      tutupProfil();
      tampilAlert('Profil tersimpan',
        'Data default penyusun tersimpan di browser ini.');
    } else {
      var pesanProfil = 'Gagal menyimpan profil di browser ini.';
      $('profil-status').textContent = pesanProfil;
      tampilAlert('Profil gagal tersimpan', pesanProfil);
    }
  }

  function semesterProfilKeForm(semester) {
    if (semester === 'Ganjil') return '1';
    if (semester === 'Genap') return '2';
    return '';
  }

  // Keluar dari sesi tersimpan: buang ?generation_id agar URL
  // benar-benar kembali ke Beranda/Formulir.
  function bersihkanQuerySesi() {
    try {
      var q = window.location.search || '';
      if (q.indexOf('generation_id') !== -1) {
        window.history.replaceState(null, '',
          '/app' + (window.location.hash || ''));
      }
    } catch (e) { /* abaikan */ }
  }

  // Tampilkan formulir + isi field kosong dari Profil. Nilai yang
  // sudah diisi user tidak ditimpa; edit form tidak mengubah Profil.
  function tampilkanFormulir() {
    bersihkanQuerySesi();
    show('layar-formulir');
    var profil = bacaProfil();
    var sem = semesterProfilKeForm(profil.semester);
    var pasangan = [
      ['f-penyusun', profil.penyusun],
      ['f-satuan', profil.satuan_pendidikan],
      ['f-semester', sem],
      ['f-tahun', profil.tahun_ajaran]
    ];
    pasangan.forEach(function (pas) {
      var el = $(pas[0]);
      if (el && !el.value && pas[1]) el.value = pas[1];
    });
    muatDaftarBuku();
  }

  /* ---------- formulir ---------- */
  function initForm(data) {
    state.options = data;
    var systems = data.systems || {};
    var sel = $('f-sistem');
    sel.innerHTML = '<option value="">Pilih</option>' +
      Object.keys(systems).map(function (code) {
        var inst = Object.keys(systems[code].institutions || {}).join(', ');
        return '<option value="' + escHtml(code) + '">' + escHtml(code) +
          (inst ? ' (' + escHtml(inst) + ')' : '') + '</option>';
      }).join('');
  }

  function institutions() {
    var sys = $('f-sistem').value;
    return ((state.options.systems || {})[sys] || {}).institutions || {};
  }

  function onSistem() {
    var inst = institutions();
    var sel = $('f-institusi');
    sel.innerHTML = '<option value="">Pilih</option>' +
      Object.keys(inst).map(function (k) {
        return '<option value="' + escHtml(k) + '">' + escHtml(k) + '</option>';
      }).join('');
    sel.disabled = false;
    $('f-kelas').innerHTML = ''; $('f-kelas').disabled = true;
    $('f-mapel').innerHTML = ''; $('f-mapel').disabled = true;
    resetBawah();
  }

  function onInstitusi() {
    var grades = institutions()[$('f-institusi').value] || {};
    grades = grades.grades || [];
    var sel = $('f-kelas');
    sel.innerHTML = '<option value="">Pilih</option>' +
      grades.map(function (g) { return '<option>' + escHtml(g) + '</option>'; }).join('');
    sel.disabled = false;
    var systems = state.options.systems[$('f-sistem').value] || {};
    var mapel = $('f-mapel');
    mapel.innerHTML = '<option value="">Pilih</option>' +
      (systems.subjects || []).map(function (s) {
        return '<option>' + escHtml(s) + '</option>';
      }).join('');
    mapel.disabled = false;
    resetBawah();
  }

  function onKelas() {
    var meta = (institutions()[$('f-institusi').value] || {}).grade_phase || {};
    $('f-fase').textContent = meta[$('f-kelas').value] || ',';
    resetBawah();
  }

  function onMapel() { resetBawah(); }

  function resetBawah() {
    $('panel-cp').hidden = true;
    var fase = $('f-fase').textContent;
    var elsBySubject = ((state.options.elements_by_subject || {})
      [ $('f-mapel').value ] || {})[fase] || [];
    var sel = $('f-elemen');
    sel.innerHTML = '<option value="">Otomatis, sistem memilih elemen ' +
      'yang paling sesuai</option>' +
      elsBySubject.map(function (e) {
        return '<option>' + escHtml(e) + '</option>';
      }).join('');
    sel.disabled = !elsBySubject.length;
  }

  function bacaForm() {
    var meta = (institutions()[$('f-institusi').value] || {}).grade_phase || {};
    return {
      education_system: $('f-sistem').value,
      institution_type: $('f-institusi').value,
      grade: $('f-kelas').value,
      phase: meta[$('f-kelas').value] || '',
      subject: $('f-mapel').value,
      element: $('f-elemen').value || undefined,
      topic: $('f-topik').value.trim(),
      satuan_pendidikan: $('f-satuan').value.trim() || undefined,
      semester: $('f-semester').value || undefined,
      tahun_ajaran: $('f-tahun').value.trim() || undefined,
      penyusun: $('f-penyusun').value.trim() || undefined,
      jumlah_pertemuan: $('f-jumlah').value.trim() || undefined,
      jp_per_pertemuan: $('f-jp').value.trim() || undefined,
      assessment_counts: {
        diagnostic: $('f-awal').value.trim() || undefined,
        formative: $('f-formatif').value.trim() || undefined,
        summative: $('f-sumatif').value.trim() || undefined,
      },
      buku_document_id: $('f-buku').value || undefined,
      student_readiness: $('f-kesiapan').value.trim() || undefined
    };
  }

  /* ---------- koleksi buku ajar (Beranda) + default generate ---------- */
  var BUKU_DEFAULT_KEY = 'rpm_buku_default';

  function bacaBukuDefault() {
    try {
      if (window.localStorage) {
        return window.localStorage.getItem(BUKU_DEFAULT_KEY) || '';
      }
    } catch (e) { /* abaikan */ }
    return '';
  }

  function tulisBukuDefault(id) {
    try {
      if (window.localStorage) {
        if (id) window.localStorage.setItem(BUKU_DEFAULT_KEY, id);
        else window.localStorage.removeItem(BUKU_DEFAULT_KEY);
        return true;
      }
    } catch (e) { /* abaikan */ }
    return false;
  }

  function barisBuku(b, bukuDefault) {
    var judul = b.judul || b.document_id || '(tanpa judul)';
    var meta = [(b.fragmen || 0) + ' fragmen',
      b.ukuran ? Math.round(b.ukuran / 1024) + ' KB' : '',
      b.diupload || ''].filter(function (v) { return v; }).join(' · ');
    var aktif = bukuDefault && bukuDefault === b.document_id;
    var badge = aktif ?
      ' <span class="badge-valid inline-block text-xs font-medium rounded px-2 py-0.5 bg-pagebg text-text2 border border-bord">Default</span>' : '';
    var aksi = '<button type="button" class="btn border border-bord rounded-[6px] h-8 px-4 text-sm text-text1" data-buku-default="' +
      escHtml(b.document_id) + '">' + (aktif ? 'Batalkan default' : 'Jadikan default') + '</button>';
    return '<li class="rpm-card bg-white border border-bord rounded-xl p-4 flex items-start gap-3">' +
      '<div class="rpm-card__isi flex-1"><strong class="font-display text-text1">' + escHtml(judul) + badge +
      '</strong><p class="meta text-sm text-text2 mt-1">' + escHtml(meta) + '</p></div>' +
      '<div class="form__actions flex gap-2">' + aksi + '</div></li>';
  }

  function muatKoleksiBuku() {
    var daftar = $('koleksi-buku');
    var kosong = $('koleksi-buku-kosong');
    if (!daftar) return;
    daftar.innerHTML = '';
    if (kosong) kosong.hidden = true;
    window.Api.daftarBuku().then(function (res) {
      var buku = (res && res.buku) || [];
      var bukuDefault = bacaBukuDefault();
      var masihAda = buku.some(function (b) {
        return b.document_id === bukuDefault;
      });
      if (bukuDefault && !masihAda) {
        tulisBukuDefault('');
        bukuDefault = '';
      }
      if (!buku.length) {
        if (kosong) kosong.hidden = false;
        return;
      }
      daftar.innerHTML = buku.map(function (b) {
        return barisBuku(b, bukuDefault);
      }).join('');
    }).catch(function () {
      if (kosong) {
        kosong.hidden = false;
        kosong.textContent = 'Gagal memuat koleksi buku. Periksa server.';
      }
    });
  }

  function onPilihBukuDefault(e) {
    var el = e && e.target && e.target.closest ?
      e.target.closest('[data-buku-default]') : null;
    if (!el) return;
    var id = el.getAttribute('data-buku-default');
    var lama = bacaBukuDefault();
    var baru = (lama === id) ? '' : id;
    tulisBukuDefault(baru);
    muatKoleksiBuku();
    tampilAlert(baru ? 'Buku default dipilih' : 'Buku default dibatalkan',
      baru ? 'Menu generate otomatis memilih buku ini.' :
        'Menu generate tidak lagi memilih otomatis.');
  }

  function muatDaftarBuku(pilihId) {
    var sel = $('f-buku');
    sel.innerHTML = '<option value="">Memuat…</option>';
    window.Api.daftarBuku().then(function (res) {
      var daftar = (res && res.buku) || [];
      if (!daftar.length) {
        sel.innerHTML = '<option value="">Belum ada buku, upload dulu</option>';
        return;
      }
      var def = pilihId || bacaBukuDefault();
      var masihAda = !def || daftar.some(function (b) {
        return b.document_id === def;
      });
      if (!masihAda) def = '';
      sel.innerHTML = '<option value="">Pilih buku</option>' +
        daftar.map(function (b) {
          var label = (b.judul || b.document_id) + ' (' + (b.fragmen || 0) +
            ' fragmen)';
          return '<option value="' + escHtml(b.document_id) + '"' +
            (def && def === b.document_id ? ' selected' : '') + '>' +
            escHtml(label) + '</option>';
        }).join('');
    }).catch(function () {
      sel.innerHTML = '<option value="">Gagal memuat daftar</option>';
    });
  }

  function onUploadBuku() {
    var box = $('buku-error');
    var hasil = $('buku-hasil');
    box.hidden = true;
    hasil.hidden = true;
    var input = $('f-buku-file');
    var file = input && input.files && input.files[0];
    if (!file) {
      box.hidden = false;
      box.textContent = 'Pilih file PDF/DOCX dulu.';
      return;
    }
    tampilLoading('Mengupload buku', 'Mengekstrak ' + file.name + '…');
    window.Api.uploadBuku(file).then(function (res) {
      sembunyiLoading();
      input.value = '';
      hasil.hidden = false;
      hasil.textContent = 'Buku "' + (res.judul || res.document_id) +
        '" masuk: ' + res.fragmen + ' fragmen dari ' + res.halaman +
        ' halaman.';
      tampilAlert('Buku diupload', hasil.textContent);
      muatDaftarBuku(res.document_id);
      muatKoleksiBuku();
    }).catch(function (err) {
      sembunyiLoading();
      box.hidden = false;
      var pesan = 'Upload buku gagal: ' + pesanError(err && err.data) +
        ' (PDF/DOCX, maks 10MB).';
      box.textContent = pesan;
      tampilAlert('Upload buku gagal', pesan);
    });
  }

  function validasiAlokasi(p) {
    function hitung(v) {
      if (v === undefined || v === null || String(v).trim() === '') return null;
      var n = Number(String(v).trim());
      return (Number.isInteger(n) && n >= 1) ? n : false;
    }
    var n = hitung(p.jumlah_pertemuan);
    var jp = hitung(p.jp_per_pertemuan);
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

  function validasiJumlah(p) {
    var counts = p.assessment_counts || {};
    var labels = { diagnostic: 'asesmen awal', formative: 'asesmen formatif',
                   summative: 'asesmen sumatif' };
    var keys = Object.keys(labels);
    var ada = false;
    for (var i = 0; i < keys.length; i++) {
      var v = counts[keys[i]];
      if (v === undefined || v === null || String(v).trim() === '') continue;
      var n = Number(String(v).trim());
      if (!Number.isInteger(n) || n < 0 || n > 30) {
        return 'Jumlah soal ' + labels[keys[i]] + ' harus bilangan bulat 0–30 (0 = tidak digenerate).';
      }
      if (n > 0) ada = true;
    }
    // R-42: boleh sebagian 0, tapi tidak boleh semua 0 (kolom kosong =
    // default, bukan 0, jadi form default tetap lolos).
    var semuaDiisi = keys.every(function (k) {
      var vv = counts[k];
      return !(vv === undefined || vv === null || String(vv).trim() === '');
    });
    if (semuaDiisi && !ada) {
      return 'Minimal satu jenis asesmen berjumlah >= 1.';
    }
    return null;
  }

  function onCekCp(e) {
    e.preventDefault();
    formError('');
    var p = bacaForm();
    if (!p.education_system || !p.institution_type || !p.grade ||
        !p.subject || !p.topic) {
      formError('Lengkapi sistem, jenjang, kelas, mapel, dan topik.');
      return;
    }
    if (!p.phase) {
      formError('Fase tidak ditemukan untuk kelas ini.');
      return;
    }
    var alokasiError = validasiAlokasi(p);
    if (alokasiError) {
      formError(alokasiError);
      return;
    }
    var jumlahError = validasiJumlah(p);
    if (jumlahError) {
      formError(jumlahError);
      return;
    }
    $('btn-konteks').disabled = true;
    tampilLoading('Memeriksa CP', 'Mengambil CP resmi dari backend…');
    window.Api.generateContext(p).then(function (res) {
      sembunyiLoading();
      $('btn-konteks').disabled = false;
      if (res.status !== 'success' || !res.context) {
        var galat = pesanError(res);
        // Teknis ELEMENT_NOT_FOUND = user belum pilih elemen: terjemahkan
        // ke instruksi yang bisa ditindaklanjuti.
        if (galat.indexOf('ELEMENT_NOT_FOUND') !== -1) {
          galat = 'Mapel ini memiliki lebih dari satu elemen. ' +
            'Pilih Elemen pada formulir lalu cek CP lagi.';
        }
        formError(galat);
        return;
      }
      var cp = res.context.cp || {};
      $('cp-teks').textContent = cp.text || 'CP tidak tersedia.';
      $('cp-meta').textContent = 'Fase ' + (cp.phase || '') +
        (cp.source_page ? ' · dokumen hal. ' + cp.source_page : '');
      $('panel-cp').hidden = false;
    }).catch(function (err) {
      sembunyiLoading();
      $('btn-konteks').disabled = false;
      var data = (err && err.data) || {};
      formError(data.errors && data.errors.length ? pesanError(data) :
        'Backend tidak merespons. Periksa server lalu coba lagi.');
    });
  }

  /* ---------- generation + polling nyata ---------- */
  function onGenerate() {
    // Baca form LIVE (bukan snapshot saat cek CP): perubahan input
    // setelah cek CP tidak boleh diam-diam diabaikan.
    var p = bacaForm();
    var alokasiError = validasiAlokasi(p);
    var jumlahError = validasiJumlah(p);
    if (!p.education_system || !p.institution_type || !p.grade ||
        !p.subject || !p.topic || !p.phase || alokasiError || jumlahError) {
      formError(alokasiError || jumlahError ||
        'Lengkapi sistem, jenjang, kelas, mapel, dan topik sebelum generate.');
      tampilkanFormulir();
      return;
    }
    if (!p.buku_document_id) {
      formError('Pilih 1 buku ajar sebagai sumber materi sebelum generate.');
      tampilkanFormulir();
      return;
    }
    // Layar progres tampil tanpa bar animasi (spinner tunggal = overlay
    // tengah), agar belakang overlay bukan landing page.
    show('layar-progres');
    var barGen = $('progres-bar');
    if (barGen) barGen.hidden = true;
    $('progres-error').hidden = true;
    $('btn-coba-lagi').hidden = true;
    $('btn-poll-ulang').hidden = true;
    $('progres-teks').textContent = 'Menghubungi backend…';
    tampilLoading('Menyusun RPM', 'Menghubungi backend…');
    window.Api.generateModuleAsync(p).then(function (res) {
      state.jobId = res.job_id;
      $('progres-id').textContent = res.job_id;
      state.pollStart = Date.now();
      pollStatus();
    }).catch(function (err) {
      tahapGagal(err.data);
    });
  }

  function stopPolling() {
    if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
  }

  function pollStatus() {
    stopPolling();
    window.Api.getGenerationStatus(state.jobId).then(function (res) {
      if (res.status === 'running') {
        var menit = Math.floor((Date.now() - state.pollStart) / 60000);
        $('progres-teks').textContent =
          'Backend sedang menyusun RPM (menit ke-' + (menit + 1) + ')…';
        $('progres-waktu').textContent = menit + ' mnt';
        perbaruiLoading('Backend sedang menyusun RPM (menit ke-' +
          (menit + 1) + ')…');
        state.pollTimer = setTimeout(pollStatus, 5000);
      } else if (res.status === 'success' && res.module) {
        selesai(res.module, res.validation || null, res.generation_id);
      } else {
        tahapGagal(res);
      }
    }).catch(function () {
      sembunyiLoading();
      show('layar-progres');
      var box = $('progres-error');
      var pesanPoll = 'Polling terputus. Koneksi bermasalah.';
      box.hidden = false;
      box.textContent = pesanPoll;
      tampilAlert('Koneksi terputus', pesanPoll +
        ' Tekan Poll ulang untuk melanjutkan.');
      $('btn-poll-ulang').hidden = false;
    });
  }

  function tahapGagal(res) {
    stopPolling();
    sembunyiLoading();
    show('layar-progres');
    var box = $('progres-error');
    var errors = (res && res.errors) || [];
    var pesanTahap = errors.length ?
      errors.map(function (e) {
        return (e.stage ? '[' + e.stage + '] ' : '') + (e.message || e.code);
      }).join(' · ') : 'Generation gagal tanpa pesan error.';
    box.hidden = false;
    box.textContent = pesanTahap;
    tampilAlert('Generate gagal', pesanTahap);
    $('btn-poll-ulang').hidden = true;
    $('btn-coba-lagi').hidden = false;
    $('progres-teks').textContent = 'Generation tidak berhasil.';
  }

  /* ---------- hasil ---------- */
  function currentExportUrl() {
    var url = window.Api.exportDocxUrl(state.generationId);
    if (state.hasVersions && state.version) {
      url += '?version=' + encodeURIComponent(state.version);
    }
    return url;
  }

  function tampilkanHasil(module, validation, generationId) {
    stopPolling();
    sembunyiLoading();
    state.module = module;
    state.validation = validation;
    state.generationId = generationId || module.generation_id;
    state.mode = 'review';
    state.dirty = false;
    state.glosTouched = false;
    var parts = window.ModuleRender.renderModule(module, validation);
    $('judul-hasil').textContent = 'Pratinjau RPM';
    var ok = !!((validation || {}).final && validation.final.passed);
    var badge = $('hasil-validasi');
    badge.textContent = 'Final validation: ' + (ok ? 'PASS' : 'BELUM LULUS');
    badge.classList.toggle('is-gagal', !ok);
    $('hasil-toc').innerHTML = parts.toc;
    $('hasil-isi').innerHTML = parts.header + parts.content;
    $('hasil-isi').hidden = false;
    $('editor-isi').hidden = true;
    $('editor-isi').innerHTML = '';
    var me = $('btn-mode-edit');
    if (me) me.disabled = false;
    $('btn-simpan-versi').hidden = true;
    $('hasil-error').hidden = true;
    $('btn-export-docx').hidden = !(ok && state.generationId);
    $('status-simpan').textContent = '';
    $('peringatan-dependensi').hidden = true;
    state.version = null;
    state.versions = [];
    state.hasVersions = false;
    show('layar-hasil');
    muatRiwayat();
  }

  function selesai(module, validation, generationId) {
    tampilkanHasil(module, validation, generationId);
    try {
      var url = '/app?generation_id=' +
        encodeURIComponent(state.generationId) + '#layar-hasil';
      window.history.replaceState(null, '', url);
      if (window.location.hash !== '#layar-hasil') {
        window.location.hash = '#layar-hasil';
      }
    } catch (e) { /* URL opsional, abaikan */ }
  }

  /* ---------- Batch 5: review / edit / versioning ---------- */
  function bolehNinggalkanEdit() {
    if (!state.dirty) return true;
    try {
      return window.confirm(
        'Perubahan belum disimpan. Tinggalkan halaman dan buang perubahan?');
    } catch (e) { return true; }
  }

  function tandaiDirty() {
    if (state.mode !== 'edit' || state.dirty) return;
    state.dirty = true;
    $('status-simpan').textContent = 'Belum disimpan';
  }

  function escHtml(s) {
    return window.ModuleRender.esc(s);
  }

  function fieldHtml(label, inner, hint) {
    return '<label class="field">' + escHtml(label) +
      (hint ? ' <span class="opsional">' + escHtml(hint) + '</span>' : '') +
      inner + '</label>';
  }

  function inputHtml(sec, key, value, kind, extra) {
    var v = escHtml(value == null ? '' : value);
    if (kind === 'textarea') {
      return '<textarea data-sec="' + sec + '" data-key="' + key + '" rows="3">' +
        v + '</textarea>';
    }
    if (kind === 'select') {
      return '<select data-sec="' + sec + '" data-key="' + key + '">' +
        (extra || '') + '</select>';
    }
    return '<input type="' + (kind || 'text') + '" data-sec="' + sec +
      '" data-key="' + key + '" value="' + v + '"' +
      (extra ? ' ' + extra : '') + '>';
  }

  function optionHtml(value, selected, label) {
    return '<option value="' + escHtml(value) + '"' +
      (String(value) === String(selected) ? ' selected' : '') + '>' +
      escHtml(label == null ? value : label) + '</option>';
  }

  function masukEdit() {
    if (!state.module) return;
    state.mode = 'edit';
    perbaruiNav();
    state.dirty = false;
    state.editFields = [];
    state.glosTouched = false;
    state.editGlosNext = (state.module.glosarium || []).length;
    var m = state.module;
    var parts = [];
    var cp = ((m.curriculum_context || {}).cp) || {};
    var cpFallback = (((m.master_outline || {}).design) || {}).cp || '';
    parts.push('<section aria-label="Terkunci"><h3>CP &amp; Provenance ' +
      '(terkunci, data regulasi)</h3><blockquote>' +
      escHtml(cp.text || cpFallback) +
      '</blockquote><p class="meta">Sumber: ' +
      escHtml(cp.source_document_id || '') +
      (cp.source_page ? ', hal. ' + escHtml(cp.source_page) : '') + '</p></section>');
    parts.push('<section aria-label="TP"><h3>Tujuan Pembelajaran</h3>' +
      (m.learning_objectives || []).map(function (t, i) {
        return fieldHtml('TP-' + (i + 1) + ' (level ' +
          (t.cognitive_level || '?') + ', otomatis)',
          '<textarea data-sec="tp" data-key="' + i + '" rows="2">' +
          escHtml(t.text || '') + '</textarea>');
      }).join('') + '</section>');
    parts.push('<section aria-label="KKTP"><h3>Kriteria Ketercapaian</h3>' +
      (m.success_criteria || []).map(function (k, i) {
        return '<h4>' + escHtml(k.id) + '</h4>' +
          (k.criteria || []).map(function (c, j) {
            return fieldHtml('Kriteria ' + (j + 1),
              '<textarea data-sec="kktp" data-key="' + i + '" rows="2">' +
              escHtml(c) + '</textarea>');
          }).join('');
      }).join('') + '</section>');
    var dimsEdit = m.profile_dimensions || [];
    var notesEdit = m.profile_dimension_notes || {};
    if (dimsEdit.length) {
      parts.push('<section aria-label="Dimensi"><h3>Dimensi Profil Lulusan ' +
        '(terkunci, alasan relevansi)</h3><ul>' +
        dimsEdit.map(function (d) {
          var note = notesEdit[d];
          return '<li><strong>' + escHtml(d) + '</strong>' +
            ((typeof note === 'string' && note) ?
              '<br>' + escHtml(note) : '') + '</li>';
        }).join('') + '</ul></section>');
    }
    parts.push('<section aria-label="Topik"><h3>Topik / Konteks</h3>' +
      fieldHtml('Topik', inputHtml('topic', '', m.topic || '')) + '</section>');
    parts.push('<section aria-label="Kesiapan"><h3>Kesiapan murid</h3>' +
      fieldHtml('Observasi guru',
        '<textarea data-sec="readiness" data-key="student_readiness" rows="3">' +
        escHtml(m.student_readiness || '') + '</textarea>') + '</section>');
    var mc = m.material_characteristics || {};
    parts.push('<section aria-label="Materi"><h3>Karakteristik materi</h3>' +
      fieldHtml('Ringkasan',
        '<textarea data-sec="material" data-key="summary" rows="3">' +
        escHtml(mc.summary || '') + '</textarea>') +
      fieldHtml('Prasyarat (satu per baris)',
        '<textarea data-sec="material" data-key="prerequisites" rows="3">' +
        escHtml((mc.prerequisites || []).join('\n')) + '</textarea>') +
      fieldHtml('Potensi miskonsepsi (satu per baris)',
        '<textarea data-sec="material" data-key="potential_misconceptions" rows="3">' +
        escHtml((mc.potential_misconceptions || []).join('\n')) +
        '</textarea>') + '</section>');
    var eu = m.essential_understanding || {};
    parts.push('<section aria-label="Pemahaman"><h3>Pemahaman bermakna</h3>' +
      ['core_insight', 'relationship', 'application', 'value'].map(function (k) {
        return fieldHtml(k,
          '<textarea data-sec="materi" data-key="' + k + '" rows="2">' +
          escHtml(eu[k] || '') + '</textarea>');
      }).join('') + '</section>');
    var tpOpts = (m.learning_objectives || []).map(function (t) { return t.id; });
    parts.push('<section aria-label="Aktivitas"><h3>Aktivitas pembelajaran</h3>' +
      (m.learning_activities || []).map(function (a, i) {
        return '<h4>' + escHtml(a.id || ('ACT-' + i)) + '</h4>' +
          fieldHtml('Nama', inputHtml('aktivitas', 'name:' + i, a.name || '')) +
          fieldHtml('Deskripsi',
            '<textarea data-sec="aktivitas" data-key="description:' + i +
            '" rows="2">' + escHtml(a.description || '') + '</textarea>') +
          fieldHtml('Durasi (menit)',
            inputHtml('aktivitas', 'duration:' + i, a.duration, 'number',
              'min="0"')) +
          fieldHtml('Tahap', '<select data-sec="aktivitas" data-key="stage:' +
            i + '">' + ['Pembuka', 'Inti', 'Penutup'].map(function (s) {
              return optionHtml(s, a.stage, s);
            }).join('') + '</select>') +
          fieldHtml('Pengalaman',
            '<select data-sec="aktivitas" data-key="experience:' + i + '">' +
            ['memahami', 'mengaplikasi', 'merefleksi'].map(function (s) {
              return optionHtml(s, a.experience, s);
            }).join('') + '</select>') +
          fieldHtml('Pertemuan',
            inputHtml('aktivitas', 'meeting:' + i, a.meeting, 'number',
              'min="0"')) +
          fieldHtml('TP terkait',
            '<select data-sec="aktivitas" data-key="tp_linked:' + i + '">' +
            tpOpts.map(function (t) {
              return optionHtml(t, a.tp_linked, t);
            }).join('') + '</select>');
      }).join('') + '</section>');
    var refl = {};
    (m.reflection || []).forEach(function (r) {
      refl[r.role] = r.questions || [];
    });
    parts.push('<section aria-label="Refleksi"><h3>Refleksi</h3>' +
      fieldHtml('Murid (satu per baris)',
        '<textarea data-sec="refleksi" data-key="student" rows="3">' +
        escHtml((refl.student || []).join('\n')) + '</textarea>') +
      fieldHtml('Guru (satu per baris)',
        '<textarea data-sec="refleksi" data-key="teacher" rows="3">' +
        escHtml((refl.teacher || []).join('\n')) + '</textarea>') +
      '</section>');
    var asm = m.assessments || {};
    function itemsEditor(bucket, label) {
      var items = asm[bucket] || [];
      if (items && !Array.isArray(items)) items = items.items || [];
      return '<h4>' + escHtml(label) + '</h4>' + (items || []).map(function (it, i) {
        return fieldHtml('Soal ' + (i + 1),
          '<textarea data-sec="asesmen" data-key="' + bucket + ':' + i +
          ':question" rows="2">' + escHtml(it.question || '') + '</textarea>') +
          fieldHtml('Tipe', inputHtml('asesmen', bucket + ':' + i + ':type',
            it.type || '')) +
          fieldHtml('TP', '<select data-sec="asesmen" data-key="' + bucket +
            ':' + i + ':tp_linked">' + tpOpts.map(function (t) {
              return optionHtml(t, it.tp_linked, t);
            }).join('') + '</select>');
      }).join('');
    }
    parts.push('<section aria-label="Asesmen"><h3>Asesmen</h3>' +
      itemsEditor('diagnostic', 'Awal') + itemsEditor('formative', 'Proses') +
      itemsEditor('summative', 'Akhir') + '</section>');
    var desc = asm.rubric_descriptors || {};
    parts.push('<section aria-label="Rubrik"><h3>Deskriptor rubrik</h3>' +
      Object.keys(desc).map(function (kid) {
        return fieldHtml(kid + ' (satu per baris)',
          '<textarea data-sec="rubrik" data-key="' + kid + '" rows="3">' +
          escHtml((desc[kid] || []).join('\n')) + '</textarea>');
      }).join('') + '</section>');
    parts.push('<section aria-label="LKPD"><h3>LKPD</h3>' +
      (m.lkpd || []).map(function (l, i) {
        return '<h4>' + escHtml(l.id || ('LKPD-' + i)) + '</h4>' +
          fieldHtml('Judul', inputHtml('lkpd', 'title:' + i, l.title || '')) +
          fieldHtml('Instruksi',
            '<textarea data-sec="lkpd" data-key="instructions:' + i +
            '" rows="2">' + escHtml(l.instructions || '') + '</textarea>') +
          fieldHtml('Tugas',
            '<textarea data-sec="lkpd" data-key="task:' + i + '" rows="2">' +
            escHtml(l.task || '') + '</textarea>');
      }).join('') + '</section>');
    parts.push('<section aria-label="Glosarium"><h3>Glosarium</h3>' +
      '<div id="glosarium-rows">' +
      (m.glosarium || []).map(function (g, i) {
        return glosariumRowHtml(i, g.istilah || '', g.definisi || '');
      }).join('') + '</div>' +
      '<button type="button" id="btn-tambah-istilah" class="btn">Tambah istilah</button>' +
      '</section>');
    var ident = m.module_identity || {};
    parts.push('<section aria-label="Metadata"><h3>Metadata</h3>' +
      fieldHtml('Penyusun', inputHtml('meta', 'penyusun', m.penyusun || '')) +
      fieldHtml('Satuan pendidikan',
        inputHtml('meta', 'satuan_pendidikan',
          m.satuan_pendidikan || ident.satuan_pendidikan || '')) +
      fieldHtml('Semester',
        '<select data-sec="meta" data-key="semester">' +
        optionHtml('', ident.semester, 'Kosongkan') +
        optionHtml('1', ident.semester, '1') +
        optionHtml('2', ident.semester, '2') + '</select>') +
      fieldHtml('Tahun ajaran',
        inputHtml('meta', 'year', m.year || ident.year || '')) +
      fieldHtml('Fasilitas (satu per baris)',
        '<textarea data-sec="meta" data-key="facilities" rows="2">' +
        escHtml((m.facilities || []).join('\n')) + '</textarea>') +
      '</section>');
    $('editor-isi').innerHTML = parts.join('');
    wireGlosariumButtons();
    Array.prototype.forEach.call(
      $('editor-isi').querySelectorAll
        ? $('editor-isi').querySelectorAll('textarea, input, select')
        : [],
      function (el) {
        el.addEventListener('input', tandaiDirty);
        el.addEventListener('change', tandaiDirty);
      });
    $('hasil-isi').hidden = true;
    $('editor-isi').hidden = false;
    $('btn-mode-edit').disabled = true;
    $('btn-simpan-versi').hidden = false;
    $('status-simpan').textContent = 'Belum ada perubahan.';
  }

  function nilaiEdit() {
    var root = $('editor-isi');
    var nodes = root.querySelectorAll
      ? root.querySelectorAll('[data-sec]') : [];
    var bySec = {};
    Array.prototype.forEach.call(nodes, function (el) {
      var sec = el.getAttribute('data-sec');
      var key = el.getAttribute('data-key') || '';
      var val = ('value' in el) ? el.value : el.textContent;
      (bySec[sec] = bySec[sec] || []).push({ key: key, value: val, el: el });
    });
    return bySec;
  }

  function linesOf(s) {
    return String(s == null ? '' : s).split('\n').map(function (x) {
      return x.trim();
    }).filter(function (x) { return x; });
  }

  function glosariumRowHtml(i, istilah, definisi) {
    return '<div data-glos-row="' + i + '">' +
      fieldHtml('Istilah',
        '<input type="text" data-sec="glosarium" data-key="istilah:' + i +
        '" value="' + escHtml(istilah) + '">') +
      fieldHtml('Definisi',
        '<textarea data-sec="glosarium" data-key="definisi:' + i +
        '" rows="2">' + escHtml(definisi) + '</textarea>') +
      '<button type="button" data-hapus-glosarium="' + i +
      '" class="btn">Hapus</button></div>';
  }

  function wireGlosariumButtons() {
    var root = $('editor-isi');
    if (!root || !root.querySelectorAll) return;
    function wireDelete(scope) {
      Array.prototype.forEach.call(
        scope.querySelectorAll('[data-hapus-glosarium]'), function (btn) {
          if (btn._glosWired) return;
          btn._glosWired = true;
          btn.addEventListener('click', function () {
            var row = btn.parentNode;
            if (row && row.parentNode && row.parentNode.removeChild) {
              row.parentNode.removeChild(row);
              state.glosTouched = true;
              tandaiDirty();
            }
          });
        });
    }
    wireDelete(root);
    Array.prototype.forEach.call(
      root.querySelectorAll('#btn-tambah-istilah'), function (addBtn) {
        if (addBtn._glosWired) return;
        addBtn._glosWired = true;
        addBtn.addEventListener('click', function () {
          var box = null;
          if (root.querySelectorAll) {
            Array.prototype.forEach.call(
              root.querySelectorAll('#glosarium-rows'), function (el) {
                box = el;
              });
          }
          if (!box) return;
          var idx = state.editGlosNext || 0;
          state.editGlosNext = idx + 1;
          var html = glosariumRowHtml('n' + idx, '', '');
          if (box.insertAdjacentHTML) {
            box.insertAdjacentHTML('beforeend', html);
          } else {
            box.innerHTML = (box.innerHTML || '') + html;
          }
          wireDelete(root);
          state.glosTouched = true;
          tandaiDirty();
        });
      });
  }

  function kumpulkanChanges() {
    var m = state.module;
    var bySec = nilaiEdit();
    var changes = {};
    function same(a, b) {
      return JSON.stringify(a) === JSON.stringify(b);
    }
    (bySec.tp || []).forEach(function () {});
    var tpVals = {};
    (bySec.tp || []).forEach(function (f) {
      tpVals[f.key] = f.value;
    });
    var tpItems = (m.learning_objectives || []).map(function (t, i) {
      var v = tpVals[String(i)];
      // Batch 9: field yang hilang dari DOM bukan edit user — pakai
      // teks tersimpan agar tidak ada data loss (undefined akan
      // terbuang oleh JSON.stringify dan ditolak server).
      if (v === undefined) v = t.text;
      return { id: t.id, text: v };
    });
    if (!same(tpItems.map(function (t) { return t.text; }),
        (m.learning_objectives || []).map(function (t) { return t.text; }))) {
      changes.tp = tpItems;
    }
    var kkGroups = {};
    (bySec.kktp || []).forEach(function (f) {
      (kkGroups[f.key] = kkGroups[f.key] || []).push(f.value);
    });
    var kkItems = (m.success_criteria || []).map(function (k, i) {
      return { id: k.id, criteria: kkGroups[String(i)] || k.criteria,
               cognitive_level: k.cognitive_level };
    });
    if (!same(kkItems.map(function (k) { return k.criteria; }),
        (m.success_criteria || []).map(function (k) { return k.criteria; }))) {
      changes.kktp = kkItems;
    }
    var topicVal = (bySec.topic || [])[0];
    if (topicVal && topicVal.value.trim() !== (m.topic || '')) {
      changes.topic = topicVal.value;
    }
    var readVal = (bySec.readiness || [])[0];
    if (readVal && readVal.value !== (m.student_readiness || '')) {
      changes.readiness = { student_readiness: readVal.value };
    }
    var matMap = {};
    (bySec.material || []).forEach(function (f) { matMap[f.key] = f.value; });
    var mc = m.material_characteristics || {};
    var matNew = {
      summary: matMap.summary !== undefined ? matMap.summary : (mc.summary || ''),
      prerequisites: matMap.prerequisites !== undefined
        ? linesOf(matMap.prerequisites) : (mc.prerequisites || []),
      potential_misconceptions: matMap.potential_misconceptions !== undefined
        ? linesOf(matMap.potential_misconceptions)
        : (mc.potential_misconceptions || [])
    };
    if (!same(matNew, { summary: mc.summary || '',
        prerequisites: mc.prerequisites || [],
        potential_misconceptions: mc.potential_misconceptions || [] })) {
      changes.material = matNew;
    }
    var euMap = {};
    (bySec.materi || []).forEach(function (f) { euMap[f.key] = f.value; });
    var eu = m.essential_understanding || {};
    var euNew = {};
    ['core_insight', 'relationship', 'application', 'value'].forEach(function (k) {
      euNew[k] = euMap[k] !== undefined ? euMap[k] : (eu[k] || '');
    });
    if (!same(euNew, { core_insight: eu.core_insight || '',
        relationship: eu.relationship || '', application: eu.application || '',
        value: eu.value || '' })) {
      changes.materi = euNew;
    }
    var actMap = {};
    (bySec.aktivitas || []).forEach(function (f) { actMap[f.key] = f.value; });
    var actsNew = (m.learning_activities || []).map(function (a, i) {
      function g(k, fb) {
        var v = actMap[k + ':' + i];
        return v !== undefined ? v : fb;
      }
      return { id: a.id, name: g('name', a.name),
        description: g('description', a.description),
        duration: Number(g('duration', a.duration)),
        tp_linked: g('tp_linked', a.tp_linked),
        experience: g('experience', a.experience),
        stage: g('stage', a.stage), meeting: Number(g('meeting', a.meeting)),
        type: a.type || '', resources: a.resources || [] };
    });
    if (!same(actsNew, (m.learning_activities || []).map(function (a) {
        return { id: a.id, name: a.name, description: a.description,
          duration: a.duration, tp_linked: a.tp_linked,
          experience: a.experience, stage: a.stage, meeting: a.meeting,
          type: a.type || '', resources: a.resources || [] };
      }))) {
      changes.aktivitas = actsNew;
    }
    var refMap = {};
    (bySec.refleksi || []).forEach(function (f) { refMap[f.key] = f.value; });
    var reflOld = {};
    (m.reflection || []).forEach(function (r) { reflOld[r.role] = r.questions || []; });
    var reflNew = {
      student: refMap.student !== undefined ? linesOf(refMap.student)
        : (reflOld.student || []),
      teacher: refMap.teacher !== undefined ? linesOf(refMap.teacher)
        : (reflOld.teacher || [])
    };
    if (!same(reflNew, { student: reflOld.student || [],
        teacher: reflOld.teacher || [] })) {
      changes.refleksi = reflNew;
    }
    var asm = m.assessments || {};
    var asmMap = {};
    (bySec.asesmen || []).forEach(function (f) { asmMap[f.key] = f.value; });
    function bucketItems(bucket, over) {
      var items = asm[bucket] || [];
      if (items && !Array.isArray(items)) items = items.items || [];
      return (items || []).map(function (it, i) {
        function g(k, fb) {
          var v = (over || {})[bucket + ':' + i + ':' + k];
          return v !== undefined ? v : fb;
        }
        var out = { question: g('question', it.question),
          type: g('type', it.type) };
        ['tp_linked', 'kktp_linked', 'points'].forEach(function (k) {
          if (it[k] !== undefined) out[k] = it[k];
        });
        var tplink = (over || {})[bucket + ':' + i + ':tp_linked'];
        if (tplink !== undefined) out.tp_linked = tplink || null;
        // Field AI lain (options, correct_answer, dsb) dipertahankan
        // agar diff tanpa edit tidak menghapus data.
        Object.keys(it || {}).forEach(function (k) {
          if (!(k in out)) out[k] = it[k];
        });
        return out;
      });
    }
    function summItems(over) {
      var s = asm.summative || {};
      var items = s.items || [];
      return (items || []).map(function (it, i) {
        function g(k, fb) {
          var v = (over || {})['summative:' + i + ':' + k];
          return v !== undefined ? v : fb;
        }
        var out = { question: g('question', it.question),
          type: g('type', it.type) };
        ['tp_linked', 'kktp_linked', 'points'].forEach(function (k) {
          if (it[k] !== undefined) out[k] = it[k];
        });
        var tplink = (over || {})['summative:' + i + ':tp_linked'];
        if (tplink !== undefined) out.tp_linked = tplink || null;
        Object.keys(it || {}).forEach(function (k) {
          if (!(k in out)) out[k] = it[k];
        });
        return out;
      });
    }
    var summ = asm.summative || {};
    var asmNew = { diagnostic: bucketItems('diagnostic', asmMap),
      formative: bucketItems('formative', asmMap),
      summative: { items: summItems(asmMap), rubric: summ.rubric } };
    var asmOld = { diagnostic: bucketItems('diagnostic', {}),
      formative: bucketItems('formative', {}),
      summative: { items: summItems({}), rubric: summ.rubric } };
    if (!same(asmNew, asmOld)) {
      changes.asesmen = asmNew;
    }
    var rubMap = {};
    (bySec.rubrik || []).forEach(function (f) { rubMap[f.key] = f.value; });
    var descOld = (m.assessments || {}).rubric_descriptors || {};
    var descNew = {};
    Object.keys(descOld).forEach(function (k) {
      descNew[k] = rubMap[k] !== undefined ? linesOf(rubMap[k])
        : (descOld[k] || []);
    });
    if (!same(descNew, descOld)) {
      changes.rubrik = { descriptors: descNew };
    }
    var lkMap = {};
    (bySec.lkpd || []).forEach(function (f) { lkMap[f.key] = f.value; });
    var lkNew = (m.lkpd || []).map(function (l, i) {
      function g(k, fb) {
        var v = lkMap[k + ':' + i];
        return v !== undefined ? v : fb;
      }
      return { id: l.id, title: g('title', l.title),
        instructions: g('instructions', l.instructions),
        task: g('task', l.task), tp_linked: l.tp_linked };
    });
    if (!same(lkNew, m.lkpd || [])) {
      changes.lkpd = lkNew;
    }
    var glosMap = {};
    (bySec.glosarium || []).forEach(function (f) { glosMap[f.key] = f.value; });
    // Hanya diff bila field glosarium memang dirender atau disentuh
    // (tambah/hapus); tanpa itu, jangan hapus data diam-diam.
    if ((bySec.glosarium || []).length || state.glosTouched) {
      var glosIdx = {};
      Object.keys(glosMap).forEach(function (k) {
        var parts = k.split(':');
        if (parts.length === 2) {
          (glosIdx[parts[1]] = glosIdx[parts[1]] || {})[parts[0]] = glosMap[k];
        }
      });
      var glosNew = Object.keys(glosIdx).sort().map(function (idx) {
        return { istilah: glosIdx[idx].istilah || '',
          definisi: glosIdx[idx].definisi || '' };
      });
      var glosOld = (m.glosarium || []).map(function (g) {
        return { istilah: g.istilah || '', definisi: g.definisi || '' };
      });
      if (!same(glosNew, glosOld)) {
        changes.glosarium = glosNew;
      }
    }
    var metaMap = {};
    (bySec.meta || []).forEach(function (f) { metaMap[f.key] = f.value; });
    var ident = m.module_identity || {};
    var metaNew = {
      penyusun: metaMap.penyusun !== undefined ? metaMap.penyusun
        : (m.penyusun || ''),
      satuan_pendidikan: metaMap.satuan_pendidikan !== undefined
        ? metaMap.satuan_pendidikan : (m.satuan_pendidikan || ''),
      semester: metaMap.semester !== undefined
        ? (metaMap.semester || null) : (m.semester || null),
      year: metaMap.year !== undefined ? metaMap.year : (m.year || ''),
      facilities: metaMap.facilities !== undefined
        ? linesOf(metaMap.facilities) : (m.facilities || [])
    };
    var metaOld = {
      penyusun: m.penyusun || ident.penyusun || '',
      satuan_pendidikan: m.satuan_pendidikan || ident.satuan_pendidikan || '',
      semester: (m.semester !== undefined && m.semester !== null) ?
        m.semester : (ident.semester !== undefined ? ident.semester : null),
      year: m.year || ident.year || '',
      facilities: m.facilities || []
    };
    // Samakan semester tipe string/number sebelum banding.
    metaNew.semester = metaNew.semester === '' ? null : metaNew.semester;
    if (metaNew.semester !== null && metaNew.semester !== undefined) {
      metaNew.semester = String(metaNew.semester);
    }
    if (!same(metaNew, { penyusun: metaOld.penyusun,
        satuan_pendidikan: metaOld.satuan_pendidikan,
        semester: metaOld.semester === null ? null : String(metaOld.semester),
        year: metaOld.year, facilities: metaOld.facilities })) {
      if (metaNew.semester !== null) {
        metaNew.semester = Number(metaNew.semester);
      }
      changes.meta = metaNew;
    }
    return changes;
  }

  function simpanGlobal() {
    simpanVersi();
  }

  function bukaSimpanOverlay() {
    tampilLoading('Menyimpan perubahan',
      'Memvalidasi TP, KKTP, langkah pembelajaran, dan asesmen…');
    if ($('btn-finalize')) $('btn-finalize').disabled = true;
    if ($('btn-simpan-versi')) $('btn-simpan-versi').disabled = true;
    // Backend menjadi authority; status awal tampil sebelum request berjalan.
    // UI harness dan browser sama-sama tidak memerlukan timer untuk lock state.
  }

  function tutupSimpanOverlay() {
    sembunyiLoading();
    if ($('btn-finalize')) $('btn-finalize').disabled = false;
    if ($('btn-simpan-versi')) $('btn-simpan-versi').disabled = false;
  }

  function tampilkanHasilSimpan(gagal, pesan) {
    if (gagal) {
      sembunyiLoading();
      $('status-simpan').textContent = pesan;
      return;
    }
    tampilLoading('Perubahan berhasil disimpan', pesan);
    setTimeout(sembunyiLoading, 1500);
    if ($('btn-finalize')) $('btn-finalize').disabled = false;
    if ($('btn-simpan-versi')) $('btn-simpan-versi').disabled = false;
  }

  function simpanVersiDanKeluar() {
    simpanVersi(function () {
      state.mode = 'review';
      state.dirty = false;
      $('editor-isi').hidden = true;
      $('hasil-isi').hidden = false;
      perbaruiNav();
    });
  }

  function simpanVersi(onSuccess) {
    if (!state.generationId || state.version == null) {
      var pesanVersi = 'Riwayat versi belum tersedia untuk sesi ini. ' +
        'Muat ulang halaman.';
      $('status-simpan').textContent = pesanVersi;
      tampilAlert('Belum bisa menyimpan', pesanVersi);
      return;
    }
    var changes = kumpulkanChanges();
    var adaDraft = Object.keys(state.draftChanges || {}).length > 0;
    if (!Object.keys(changes).length && !adaDraft) {
      var pesanKosong = 'Tidak ada perubahan.';
      $('status-simpan').textContent = pesanKosong;
      tampilAlert('Tidak ada perubahan', pesanKosong);
      return;
    }
    // Batch 9: TP kosong disebut eksplisit (TP-berapa), bukan error
    // server generik — tanpa mengisi dummy apa pun.
    var los = state.module ? (state.module.learning_objectives || []) : [];
    var kosong = [];
    (changes.tp || []).forEach(function (t) {
      if (!t.text || !String(t.text).trim()) {
        var nomor = '?';
        los.forEach(function (o, i) {
          if (o.id === t.id) nomor = String(i + 1);
        });
        kosong.push('TP-' + nomor);
      }
    });
    if (kosong.length) {
      var pesanTp = kosong.join(', ') +
        ' masih kosong. Isi dulu sebelum menyimpan.';
      $('status-simpan').textContent = pesanTp;
      tampilAlert('TP masih kosong', pesanTp);
      return;
    }
    $('status-simpan').textContent = 'Sedang memvalidasi perubahan…';
    bukaSimpanOverlay();
    var gunakanCandidate = Object.keys(state.draftChanges || {}).length > 0 &&
      !!window.Api.saveCandidate;
    var simpanApi = gunakanCandidate ? window.Api.saveCandidate :
      window.Api.saveVersion;
    var simpanArg = gunakanCandidate ?
      [state.generationId, state.version, state.module, changes] :
      [state.generationId, state.version, changes];
    simpanApi.apply(window.Api, simpanArg).then(
      function (res) {
        state.dirty = false;
        state.draftChanges = {};
        terapkanVersi(res.version, res.warnings || []);
        var pesanSimpan = 'Tersimpan sebagai v' +
          res.version.version_no + ' (' + res.version.status + ').';
        $('status-simpan').textContent = pesanSimpan;
        tampilAlert('Perubahan tersimpan', pesanSimpan +
          ' Perubahan RPM telah divalidasi dan berhasil disimpan.');
        tampilkanHasilSimpan(false,
          'Perubahan RPM telah divalidasi dan berhasil disimpan.');
        if (typeof onSuccess === 'function') onSuccess();
      }).catch(function (err) {
        tutupSimpanOverlay();
        var data = err.data || {};
        if (err.status === 409) {
          var pesanBasi = 'Versi basi: ' + pesanError(data) +
            ' Muat ulang versi terbaru.';
          $('status-simpan').textContent = pesanBasi;
          tampilAlert('Versi basi', pesanBasi);
        } else {
          var alasan = pesanError(data);
          var pesanGgl = 'Gagal menyimpan: ' + alasan;
          $('status-simpan').textContent = pesanGgl;
          tampilkanHasilSimpan(true, alasan);
          tampilAlert('Gagal menyimpan', pesanGgl);
        }
      });
  }

  function pesanError(data) {
    var errors = (data && data.errors) || [];
    return errors.length ? errors.map(function (e) {
      return (e.stage ? '[' + e.stage + '] ' : '') + (e.message || e.code);
    }).join(' · ') : 'kesalahan tak dikenal';
  }

  /* ---------- Batch 10: state tombol proses ---------- */
  var NAMA_BAGIAN = { tp: 'TP', kktp: 'KKTP', materi: 'Materi',
    praktik_pedagogis: 'Praktik Pedagogis', aktivitas: 'Aktivitas',
    asesmen: 'Asesmen', diagnostik: 'Diagnostik', formatif: 'Formatif',
    sumatif: 'Sumatif' };
  var tombolTerkunci = [];

  function tombolProses() {
    var daftar = [];
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-regen]'),
      function (b) { daftar.push(b); });
    if ($('btn-finalize')) daftar.push($('btn-finalize'));
    return daftar;
  }

  function kunciTombol() {
    tombolTerkunci = [];
    tombolProses().forEach(function (b) {
      tombolTerkunci.push({ btn: b });
      b.disabled = true;
    });
  }

  function bukaTombol() {
    tombolTerkunci.forEach(function (t) {
      t.btn.disabled = false;
    });
    tombolTerkunci = [];
  }

  function regenBagian(target, btn, counts, extra) {
    if (!state.generationId || state.version == null) {
      $('status-simpan').textContent =
        'Riwayat versi belum tersedia untuk sesi ini. Muat ulang halaman.';
      return;
    }
    // Cegah double-click / request tumpang tindih.
    if (tombolTerkunci.length) return;
    if (state.dirty &&
        !window.confirm('Ada perubahan belum disimpan. Regenerasi memakai versi ' +
          'tersimpan terakhir; perubahan tak tersimpan akan hilang. Lanjut?')) {
      return;
    }
    var nama = NAMA_BAGIAN[target] || target;
    var berapa = counts && counts[target] ? ' ' + counts[target] + ' soal' : '';
    if (extra && extra.n_meetings) {
      berapa += ' (' + extra.n_meetings + ' pertemuan)';
    }
    kunciTombol();
    tampilLoading('Meregenerasi ' + nama,
      'Meregenerasi ' + target + berapa + ' via AI…');
    $('status-simpan').textContent = 'Meregenerasi ' + target + berapa + '…';
    window.Api.regenerateSection(
      state.generationId, state.version, target, counts,
      extra).then(function (res) {
        bukaTombol();
        sembunyiLoading();
        if (res.draft) {
          state.draftChanges[target] = true;
        }
        terapkanVersi(res.version, res.warnings || res.version.warnings || []);
        state.dirty = true;
        var pesanDraft = nama +
          ' menjadi draft. Klik Simpan perubahan untuk menyimpan.';
        $('status-simpan').textContent = pesanDraft;
        tampilAlert(nama + ' diregenerasi', pesanDraft);
      }, function (err) {
        bukaTombol();
        sembunyiLoading();
        var rincian = pesanError((err && err.data) || {});
        var pesanGagal = nama + ' gagal diperbarui. Coba lagi.' +
          ((rincian && rincian !== 'kesalahan tak dikenal') ?
            ' Rincian: ' + rincian : '');
        $('status-simpan').textContent = pesanGagal;
        tampilAlert(nama + ' gagal diregenerasi', pesanGagal);
      });
  }

  function finalizeVersi() {
    if (!state.generationId) {
      $('status-simpan').textContent =
        'Belum ada sesi aktif untuk difinalisasi.';
      return;
    }
    if (tombolTerkunci.length) return;
    kunciTombol();
    tampilLoading('Memfinalisasi', 'Memfinalisasi versi RPM…');
    window.Api.finalizeVersion(state.generationId).then(function (res) {
      bukaTombol();
      sembunyiLoading();
      terapkanVersi(res.version, []);
      $('status-simpan').textContent = 'Finalisasi berhasil.';
      tampilAlert('Finalisasi berhasil',
        'RPM difinalisasi. Dokumen siap diekspor.');
    }, function (err) {
      bukaTombol();
      sembunyiLoading();
      var rincian = pesanError((err && err.data) || {});
      var pesanFinal = 'Finalisasi gagal. Coba lagi.' +
        ((rincian && rincian !== 'kesalahan tak dikenal') ?
          ' Rincian: ' + rincian : '');
      $('status-simpan').textContent = pesanFinal;
      tampilAlert('Finalisasi gagal', pesanFinal);
    });
  }

  function terapkanVersi(version, warnings) {
    if (!version || !version.module) return;
    state.module = version.module;
    state.validation = version.validation || state.validation;
    state.version = version.version_no;
    state.dirty = false;
    perbaruiNav();
    var parts = window.ModuleRender.renderModule(
      state.module, state.validation);
    $('hasil-toc').innerHTML = parts.toc;
    $('hasil-isi').innerHTML = parts.header + parts.content;
    var ok = !!((state.validation || {}).final && state.validation.final.passed);
    $('hasil-validasi').textContent = 'Final validation: ' +
      (ok ? 'PASS' : 'BELUM LULUS');
    $('hasil-validasi').classList.toggle('is-gagal', !ok);
    $('btn-export-docx').hidden = !(ok && state.generationId);
    var box = $('peringatan-dependensi');
    if ((warnings || []).length) {
      box.hidden = false;
      box.innerHTML = '<h3>Perhatian</h3><ul>' + warnings.map(function (w) {
        return '<li>' + escHtml(w) + '</li>';
      }).join('') + '</ul>';
    } else {
      box.hidden = true;
    }
    muatRiwayat();
    if (state.mode === 'edit') masukEdit();
  }

  function muatRiwayat() {
    var gid = state.generationId;
    if (!gid || !window.Api.listVersions) return;
    window.Api.listVersions(gid).then(function (res) {
      state.versions = res.versions || [];
      state.hasVersions = state.versions.length > 0;
      var target = null;
      if (state.pinVersion != null) {
        target = state.pinVersion;
        state.pinVersion = null;
      } else if (state.hasVersions) {
        target = res.latest_version;
      }
      // Draft regen belum tersimpan: versi draft yang sedang tampil
      // lebih baru dari riwayat server — jangan mundur ke versi lama.
      if (target != null && (state.version == null || target >= state.version)) {
        state.version = target;
      }
      renderVersiInfo();
    }).catch(function () { /* riwayat opsional, abaikan */ });
  }

  function renderVersiInfo() {
    var hv = $('hasil-versi');
    if (!hv) return;
    var cur = null;
    (state.versions || []).forEach(function (v) {
      if (v.version_no === state.version) cur = v;
    });
    hv.textContent = (state.hasVersions && cur) ?
      ('Versi v' + cur.version_no + ' dari ' + state.versions.length +
        ' (' + (cur.status || '') +
        (cur.alignment_status ? ' / ' + cur.alignment_status : '') + ')') : '';
    var ha = $('hasil-alignment');
    if (ha) {
      ha.textContent = (cur && cur.alignment_status) ?
        ('Keselarasan: ' + cur.alignment_status +
          ((cur.warnings || []).length ? ' — ' + cur.warnings.join(' ') : '')) : '';
    }
    var ul = $('riwayat-versi');
    if (!ul) return;
    var urut = (state.versions || []).slice().sort(function (a, b) {
      return b.version_no - a.version_no;
    });
    ul.innerHTML = urut.map(function (v) {
      var aktif = (v.version_no === state.version) ? ' — AKTIF' : '';
      var hapusBtn = (state.versions.length > 1) ?
        ' <button type="button" class="btn btn--hapus" data-hapus-versi="' +
        v.version_no + '">Hapus</button>' : '';
      return '<li><strong>v' + v.version_no + escHtml(aktif) + '</strong><br>' +
        escHtml(v.status || '') +
        (v.alignment_status ? ' / ' + escHtml(v.alignment_status) : '') +
        ((v.changed_sections && v.changed_sections.length) ?
          '<br>ubah: ' + escHtml(v.changed_sections.join(', ')) : '') +
        '<br><button type="button" data-lihat="' + v.version_no +
        '">Lihat</button>' + hapusBtn + '</li>';
    }).join('');
    Array.prototype.forEach.call(
      ul.querySelectorAll ? ul.querySelectorAll('[data-lihat]') : [],
      function (btn) {
        btn.addEventListener('click', function () {
          lihatVersi(Number(btn.getAttribute('data-lihat')));
        });
      });
    Array.prototype.forEach.call(
      ul.querySelectorAll ? ul.querySelectorAll('[data-hapus-versi]') : [],
      function (btn) {
        btn.addEventListener('click', function () {
          bukaHapusVersi(Number(btn.getAttribute('data-hapus-versi')));
        });
      });
  }

  function bukaHapusVersi(v) {
    if (v == null || isNaN(v)) return;
    if ((state.versions || []).length <= 1) {
      tampilAlert('Tidak bisa dihapus',
        'Versi terakhir tidak boleh dihapus; modul harus punya ' +
        'minimal 1 versi.');
      return;
    }
    state.hapusVersiTarget = v;
    $('hapus-versi-judul').textContent = 'Hapus v' + v + ' permanen?';
    $('hapus-versi-pesan').textContent = 'Riwayat v' + v + ' akan ' +
      'dihapus permanen dari modul ini. Versi lain tetap utuh.';
    $('hapus-versi-error').hidden = true;
    bukaModal('hapus-versi-overlay', document.activeElement,
      'btn-batal-hapus-versi');
  }

  function tutupHapusVersi() {
    state.hapusVersiTarget = null;
    tutupModal('hapus-versi-overlay');
  }

  function hapusVersiTerpilih() {
    var v = state.hapusVersiTarget;
    if (v == null) { tutupHapusVersi(); return; }
    var tombol = $('btn-konfirmasi-hapus-versi');
    tombol.disabled = true;
    $('hapus-versi-error').hidden = true;
    tampilLoading('Menghapus versi', 'Menghapus v' + v + '…');
    window.Api.deleteVersion(state.generationId, v).then(function (res) {
      tombol.disabled = false;
      sembunyiLoading();
      tutupHapusVersi();
      var latestNo = res && res.latest_version;
      // Bila versi yang tampil ikut terhapus, pindah ke terbaru sisa.
      return window.Api.getVersion(state.generationId, latestNo).then(
        function (r) {
          state.pinVersion = r.version.version_no;
          tampilkanHasil(r.version.module,
            r.version.validation || state.validation, state.generationId);
          tampilAlert('Versi dihapus',
            'v' + v + ' dihapus permanen. Menampilkan v' +
            r.version.version_no + '.');
        });
    }).catch(function (err) {
      tombol.disabled = false;
      sembunyiLoading();
      var rincian = pesanError((err && err.data) || {});
      var pesanGagal = 'Gagal menghapus versi. ' + rincian;
      var box = $('hapus-versi-error');
      box.hidden = false;
      box.textContent = pesanGagal;
      tampilAlert('Gagal menghapus versi', pesanGagal);
    });
  }

  function lihatVersi(v) {
    if (!bolehNinggalkanEdit()) return;
    window.Api.getVersion(state.generationId, v).then(function (res) {
      state.pinVersion = res.version.version_no;
      tampilkanHasil(res.version.module,
        res.version.validation || state.validation, state.generationId);
    }).catch(function (err) {
      var pesanBukaV = 'Gagal membuka versi: ' +
        pesanError(err.data);
      $('hasil-error').hidden = false;
      $('hasil-error').textContent = pesanBukaV;
      tampilAlert('Gagal membuka versi', pesanBukaV);
    });
  }

  function restoreVersi(v) {
    window.Api.restoreVersion(state.generationId, v).then(function (res) {
      terapkanVersi(res.version, res.version.warnings || []);
      var pesanRestore = 'Restore v' + v + ' tersimpan sebagai v' +
        res.version.version_no + ' (history utuh).';
      $('status-simpan').textContent = pesanRestore;
      tampilAlert('Versi dipulihkan', pesanRestore);
    }).catch(function (err) {
      var pesanRestoreGgl = 'Restore gagal: ' + pesanError(err.data);
      $('status-simpan').textContent = pesanRestoreGgl;
      tampilAlert('Restore gagal', pesanRestoreGgl);
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
