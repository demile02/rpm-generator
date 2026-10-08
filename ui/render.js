/* RPM Generator, pratinjau hasil.
   Merender module master_outline (data final backend) menjadi HTML
   mengikuti Templatku.docx: judul + topik terpusat, banner section
   A–E, identitas label-value, diagnostik label-only. Tanpa data
   buatan: bagian kosong tidak ditampilkan, tanpa baris total. */
(function () {
  'use strict';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function list(items, itemFn) {
    items = items || [];
    if (!items.length) return '';
    return '<ul>' + items.map(function (it) {
      return '<li>' + (itemFn ? itemFn(it) : esc(it)) + '</li>';
    }).join('') + '</ul>';
  }

  function table(headers, rows, cls, fracs) {
    if (!rows.length) return '';
    var html = '<div class="table-wrap"><table' +
      (cls ? ' class="' + cls + '"' : '') + '>';
    if (fracs && fracs.length === headers.length) {
      html += '<colgroup>' + fracs.map(function (f) {
        return '<col style="width:' + (f * 100).toFixed(1) + '%">';
      }).join('') + '</colgroup>';
    }
    html += '<thead><tr>' +
      headers.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>';
    rows.forEach(function (row) {
      html += '<tr>' + row.map(function (c) {
        return '<td>' + c + '</td>';
      }).join('') + '</tr>';
    });
    return html + '</tbody></table></div>';
  }

  // Proporsi kolom Templatku.docx (gridCol template).
  var TP_FRACS = [0.109, 0.782, 0.109];
  var ACTIVITY_FRACS = [0.187, 0.422, 0.109, 0.094, 0.188];
  var ASSESS_FRACS = [0.6561, 0.1251, 0.0937, 0.1251];
  var DIAG_FRACS = [0.6561, 0.1251, 0.2188];
  var GLOS_FRACS = [0.25, 0.75];

  function cells(row) {
    return row.map(esc);
  }

  function tombolUlang(target, label) {
    return '<button type="button" class="btn btn--retry" data-regen="' +
      target + '">Regenerate ' + label + '</button>';
  }

  function kepalaAksi(judul, target, label, count) {
    var stepper = '';
    if (count !== undefined && count !== null) {
      var awal = Math.max(1, Math.min(30, Number(count) || 1));
      stepper = '<span class="stepper" role="group" aria-label="Jumlah soal ' +
        esc(judul) + '">' +
        '<button type="button" class="btn btn--step" data-count="kurang" ' +
        'data-target="' + target + '" aria-label="Kurangi">−</button>' +
        '<span class="stepper__angka" aria-live="polite">' +
        awal + '</span>' +
        '<button type="button" class="btn btn--step" data-count="tambah" ' +
        'data-target="' + target + '" aria-label="Tambah">+</button></span>';
    }
    return '<div class="baris-aksi"><h4>' + esc(judul) + '</h4>' + stepper +
      tombolUlang(target, label === undefined ? judul : label) + '</div>';
  }

  function section(id, banner, inner) {
    if (!inner) return '';
    return '<section id="' + id + '">' +
      '<h3 class="banner">' + esc(banner) + '</h3>' + inner + '</section>';
  }

  // Kode ramah template: 'MA_10' -> '10' (presentation-friendly).
  function friendlyGrade(grade) {
    grade = String(grade == null ? '' : grade);
    var i = grade.indexOf('_');
    if (i === -1) return grade;
    var tail = grade.slice(i + 1).replace(/_/g, ' ').trim();
    return tail || grade;
  }

  function friendlySemester(sem) {
    sem = String(sem == null ? '' : sem).toLowerCase();
    if (sem === '1' || sem === 'ganjil') return 'Ganjil';
    if (sem === '2' || sem === 'genap') return 'Genap';
    return String(sem == null ? '' : sem);
  }

  var TYPE_LABELS = {
    multiple_choice: 'Pilihan Ganda',
    short_answer: 'Isian',
    essay: 'Uraian',
    true_false: 'Benar/Salah',
    matching: 'Menjodohkan',
    performance_task: 'Unjuk Kerja',
    performance_assessment: 'Unjuk Kerja',
    performance: 'Unjuk Kerja',
    oral_reading: 'Membaca Nyaring'
  };

  function typeLabel(t) {
    t = String(t == null ? '' : t).trim();
    return TYPE_LABELS[t] || t;
  }

  // Jawaban diagnostik: label saja, tanpa teks jawaban.
  // Sama persis dengan docx_renderer._answer_label.
  function answerLabel(item) {
    if (!item || typeof item !== 'object') return '';
    var raw = '';
    var keys = ['correct_answer', 'answer_key', 'answer'];
    for (var k = 0; k < keys.length; k++) {
      var v = item[keys[k]];
      if (typeof v === 'string' && v.trim()) { raw = v.trim(); break; }
      if (Array.isArray(v) && v.length) {
        raw = String(v[0]).trim();
        break;
      }
    }
    if (!raw) return '';
    var opts = mcOptions(item);
    var labels = opts.map(function (o) { return o.label; });
    if (raw.length === 1 && labels.indexOf(raw.toUpperCase()) !== -1) {
      return raw.toUpperCase();
    }
    var first = raw.split('.', 1)[0].trim().toUpperCase();
    if (first.length === 1 && labels.indexOf(first) !== -1) return first;
    for (var i = 0; i < opts.length; i++) {
      if (String(opts[i].text).trim().toLowerCase() === raw.toLowerCase()) {
        return opts[i].label;
      }
    }
    return esc(raw);
  }

  function mcOptions(item) {
    var options = item && item.options;
    if (!Array.isArray(options)) return [];
    var out = [];
    for (var i = 0; i < options.length; i++) {
      var opt = options[i];
      var label, text;
      if (opt && typeof opt === 'object') {
        label = String(opt.label || String.fromCharCode(65 + i));
        text = String(opt.text !== undefined ? opt.text : opt.option || '');
      } else {
        label = String.fromCharCode(65 + i);
        text = String(opt);
      }
      if (text) out.push({ label: label, text: text });
    }
    return out;
  }

  function mcOptionsHtml(item) {
    var opts = mcOptions(item);
    if (!opts.length) return '';
    return '<br>' + opts.map(function (o) {
      return esc(o.label + '. ' + o.text);
    }).join('<br>');
  }

  function renderModule(module, validation) {
    var outline = module.master_outline || {};
    var general = outline.general_information || {};
    var identity = general.identity || {};
    var parts = [];
    var toc = [];

    function add(id, banner, inner) {
      var html = section(id, banner, inner);
      if (html) {
        parts.push(html);
        toc.push('<li><a href="#' + id + '">' + esc(banner) +
          '</a></li>');
      }
    }

    // ---- A. Identitas: label-value template, tanpa tabel grid. ----
    var ident = module.module_identity || {};
    var meetings = module.meetings || [];
    var totalJp = meetings.reduce(function (s, mtg) {
      return s + (Number(mtg.jp) || 0);
    }, 0);
    var jpSeragam = meetings.length ?
      meetings.every(function (mtg) {
        return Number(mtg.jp) === Number(meetings[0].jp);
      }) : false;
    var alokasi = '';
    if (meetings.length) {
      alokasi = jpSeragam ?
        totalJp + ' JP (' + meetings.length + ' Pertemuan x ' +
          meetings[0].jp + ' JP)' :
        totalJp + ' JP (' + meetings.length + ' Pertemuan)';
    }
    var kelasFase = [friendlyGrade(module.grade), module.phase,
      friendlySemester(ident.semester)].filter(function (v) {
        return v;
      }).join('/');
    var namaLabel = ((module.curriculum_context || {}).education_system ===
      'KEMENAG') ? 'Nama Madrasah' : 'Nama Sekolah';
    var idRows = [
      [namaLabel, ident.satuan_pendidikan],
      ['Nama Penyusun', module.penyusun],
      ['Mata Pelajaran', module.subject],
      ['Kelas / Fase /Semester', kelasFase],
      ['Alokasi Waktu', alokasi],
      ['Tahun Pelajaran', ident.year]
    ].filter(function (r) { return r[1]; });
    add('a-identitas', 'A. IDENTITAS MODUL',
      '<dl class="identitas">' + idRows.map(function (r) {
        return '<div><dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) +
          '</dd></div>';
      }).join('') + '</dl>');

    // ---- B. Identifikasi: kesiapan verbatim + KBC berpasangan. ----
    var identifikasi = outline.identification || {};
    var kesiapan = identifikasi.learner_readiness || {};
    var materi = identifikasi.material_characteristics || {};
    var dims = identifikasi.profile_dimensions || [];
    var dimNotes = identifikasi.profile_dimension_notes || {};
    var dimsHtml = '';
    if (dims.length) {
      dimsHtml = '<h4>Dimensi Profil Lulusan</h4><ol>' +
        dims.map(function (d) {
          var note = dimNotes[d];
          return '<li><strong>' + esc(d) + '</strong>' +
            ((typeof note === 'string' && note) ?
              '<br>' + esc(note) : '') + '</li>';
        }).join('') + '</ol>';
    }
    var bHtml =
      '<h4>Kesiapan Murid</h4><p>' +
      esc(kesiapan.summary || kesiapan.note ||
        'Belum ada data kesiapan.') + '</p>' +
      list(kesiapan.aspects) +
      '<h4>Karakteristik materi</h4><p>' +
      esc(materi.summary || 'Belum ada ringkasan.') + '</p>' +
      dimsHtml;
    var ctxB = module.curriculum_context || {};
    var kbcB = general.kbc || {};
    // Pasangan bernomor persis docx_renderer.pair_kbc_items.
    var kbcThemes = (kbcB.themes || []).map(String).filter(function (t) {
      return t.trim();
    });
    var kbcRaw;
    if ('insertions' in kbcB) {
      kbcRaw = ((kbcB.insertions || []).filter(function (ins) {
        return ins && typeof ins === 'object' && ins.active &&
          String(ins.text || '').trim();
      }));
    } else {
      kbcRaw = kbcB.insertion_material || [];
    }
    var kbcUnits = [];
    (kbcRaw || []).forEach(function (ins) {
      if (ins && typeof ins === 'object') {
        var tema = (typeof ins.tema === 'string' && ins.tema.trim()) ?
          ins.tema : null;
        kbcUnits.push({ text: String(ins.text || '').trim(), tema: tema });
      } else if (String(ins || '').trim()) {
        kbcUnits.push({ text: String(ins).trim(), tema: null });
      }
    });
    kbcUnits = kbcUnits.filter(function (u) { return u.text; });
    var kbcPairs = [];
    var used = {};
    var anyTema = kbcUnits.some(function (u) { return u.tema; });
    kbcThemes.forEach(function (theme, pos) {
      var idx = null;
      if (anyTema) {
        for (var i = 0; i < kbcUnits.length; i++) {
          if (!used[i] && kbcUnits[i].tema === theme) { idx = i; break; }
        }
      } else if (kbcUnits.length === kbcThemes.length && !used[pos]) {
        idx = pos;
      }
      if (idx === null || idx === undefined) {
        kbcPairs.push({ theme: theme, text: null });
      } else {
        used[idx] = true;
        kbcPairs.push({ theme: theme, text: kbcUnits[idx].text });
      }
    });
    kbcUnits.forEach(function (u, i) {
      if (!used[i]) kbcPairs.push({ theme: null, text: u.text });
    });
    if (ctxB.education_system === 'KEMENAG' && kbcPairs.length) {
      bHtml += '<h4>Kurikulum Berbasis Cinta &amp; Materi Insersi</h4><ol>' +
        kbcPairs.map(function (it) {
          var label = it.theme ? it.theme : 'Materi insersi';
          return '<li><strong>' + esc(label) + '</strong>' +
            (it.text ? '<br>' + esc(it.text) : '') + '</li>';
        }).join('') + '</ol>';
    }
    add('b-identifikasi', 'B. IDENTIFIKASI', bHtml);

    // ---- C. Desain: CP + TP + KKTP + praktik (tanpa blok Topik). ----
    var desain = outline.design || {};
    var tpRows = (desain.tp || []).map(function (t) {
      return cells([t.id, t.text, t.cognitive_level]);
    });
    var kktpList = (desain.kktp || []).map(function (k, i) {
      var crit = (k.criteria || []).map(function (c) {
        return '<p>' + esc(c) + '</p>';
      }).join('');
      return '<p><strong>' + esc((i + 1) + '. ' + k.id) + '</strong></p>' +
        crit;
    }).join('');
    var practicesList = (desain.pedagogical_practices || []).map(
      function (p, i) {
        return '<p>' + esc((i + 1) + '. ' + p) + '</p>';
      }).join('');
    var prov = desain.cp_provenance || {};
    var sumberLine = '';
    if (prov.source_document_id) {
      sumberLine = 'Sumber: ' + prov.source_document_id;
      if (prov.source_page !== undefined && prov.source_page !== null &&
          String(prov.source_page).trim() !== '') {
        sumberLine += ', halaman ' + prov.source_page;
      }
    }
    add('c-desain', 'C. DESAIN PEMBELAJARAN',
      '<h4>Capaian Pembelajaran (CP)</h4><blockquote class="cp">' +
      esc(desain.cp || 'CP tidak tersedia.') + '</blockquote>' +
      (sumberLine ?
        '<p class="meta">' + esc(sumberLine) + '</p>' : '') +
      kepalaAksi('Tujuan Pembelajaran', 'tp', 'TP') +
      table(['Nomor', 'Tujuan Pembelajaran', 'Level'], tpRows,
        '', TP_FRACS) +
      (kktpList ? kepalaAksi('Kriteria Ketercapaian (KKTP)', 'kktp',
        'KKTP') + kktpList : '') +
      (practicesList ? kepalaAksi('Praktik Pedagogis', 'praktik_pedagogis',
        'Praktik Pedagogis') + practicesList : ''));

    // ---- D. Langkah per pertemuan + prinsip di akhir tiap pertemuan.
    // Ikut Templatku.docx: blok "Prinsip Pembelajaran Mendalam" menutup
    // tiap pertemuan (setelah Penutup), bukan blok tersendiri di bawah D.
    var pengalaman = outline.learning_experience || {};
    var experiences = pengalaman.experiences || {};
    function prinsipHtmlUntuk(pr) {
      pr = pr || {};
      var items = [
        ['Berkesadaran (Mindful Learning)', pr.berkesadaran],
        ['Bermakna (Meaningful Learning)', pr.bermakna],
        ['Menggembirakan (Joyful Learning)', pr.menggembirakan]
      ].filter(function (p) { return p[1]; });
      if (!items.length) return '';
      return '<p><strong>Prinsip Pembelajaran Mendalam</strong></p>' +
        '<ol>' + items.map(function (p) {
          return '<li><strong>' + esc(p[0]) + '</strong><br>' +
            esc(p[1]) + '</li>';
        }).join('') + '</ol>';
    }
    var expHtml = '';
    if (meetings.length) {
      expHtml = '<div class="baris-aksi baris-aksi--tunggal">' +
        '<span class="stepper" role="group" aria-label="Jumlah pertemuan">' +
        '<button type="button" class="btn btn--step" data-ptm="kurang" ' +
        'aria-label="Kurangi pertemuan">−</button>' +
        '<span class="stepper__angka" aria-live="polite">' +
        meetings.length + '</span>' +
        '<button type="button" class="btn btn--step" data-ptm="tambah" ' +
        'aria-label="Tambah pertemuan">+</button></span>' +
        tombolUlang('aktivitas', 'Aktivitas') + '</div>' +
        meetings.map(function (mtg) {
        var stages = mtg.stages || {};
        var body = ['Pembuka', 'Inti', 'Penutup'].map(function (tahap) {
          var acts = stages[tahap] || [];
          var rows = acts.map(function (a) {
            return cells([a.name, a.description, a.duration,
              a.tp_linked || a.tp_reference || '', a.experience || '']);
          });
          return '<h4>' + esc(tahap) + '</h4>' +
            table(['Aktivitas', 'Deskripsi', 'Durasi', 'TP',
              'Pengalaman'], rows, '', ACTIVITY_FRACS);
        }).join('');
        return '<h4>Pertemuan ' + esc(mtg.index) + ': ' + esc(mtg.jp) +
          ' JP (' + esc(mtg.minutes) + ' menit)</h4>' + body +
          prinsipHtmlUntuk(mtg.principles);
      }).join('');
    } else {
      var urutan = ['memahami', 'mengaplikasi', 'merefleksi'].filter(
        function (k) { return experiences[k]; }).concat(
        Object.keys(experiences).filter(function (k) {
          return ['memahami', 'mengaplikasi', 'merefleksi'].indexOf(k) === -1;
        }));
      expHtml = urutan.map(function (nama) {
        var acts = experiences[nama] || [];
        var rows = acts.map(function (a) {
          return cells([a.name, a.description, a.duration,
            a.tp_linked || a.tp_reference || '']);
        });
        return '<h4>Pengalaman ' + esc(nama) + '</h4>' +
          table(['Aktivitas', 'Deskripsi', 'Durasi', 'TP'], rows);
      }).join('');
    }
    add('d-pengalaman', 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN', expHtml);

    // ---- E. Asesmen Diagnostik/Formatif/Sumatif, label-only. ----
    var asesmen = outline.assessment || {};
    function itemsBucket(items) {
      items = items || [];
      if (items && !Array.isArray(items)) items = items.items || [];
      return items || [];
    }
    function asesmenTable(items, diagnostik) {
      var rows = itemsBucket(items).map(function (it) {
        if (diagnostik) {
          return [esc(it.question) + mcOptionsHtml(it),
            esc(typeLabel(it.type)), answerLabel(it)];
        }
        return [esc(it.question),
          esc(typeLabel(it.type)), esc(it.tp_linked || ''),
          esc(it.kktp_linked || '')];
      });
      if (diagnostik) {
        return table(['Instrumen', 'Tipe', 'Jawaban Benar'], rows,
          'val-mid');
      }
      return table(['Instrumen', 'Tipe', 'TP', 'KKTP'], rows);
    }
    add('e-asesmen', 'E. ASESMEN',
      kepalaAksi('Asesmen Diagnostik', 'diagnostik', 'Diagnostik',
        itemsBucket(asesmen.awal).length) +
      asesmenTable(asesmen.awal, true) +
      kepalaAksi('Asesmen Formatif', 'formatif', 'Formatif',
        itemsBucket(asesmen.proses).length) +
      asesmenTable(asesmen.proses, false) +
      kepalaAksi('Asesmen Sumatif', 'sumatif', 'Sumatif',
        itemsBucket(asesmen.akhir).length) +
      asesmenTable(asesmen.akhir, false) +
      ((itemsBucket(asesmen.awal).length +
        itemsBucket(asesmen.proses).length +
        itemsBucket(asesmen.akhir).length) ? '' :
        '<p class="meta">Asesmen belum digenerate. Gunakan tombol ' +
        'Regenerate Diagnostik / Formatif / Sumatif di atas untuk ' +
        'menambahkannya.</p>'));

    // Glosarium: lampiran opsional, bukan bagian A–E.
    var glos = ((outline.attachments || {}).glosarium) || [];
    if (glos.length) {
      parts.push(section('glosarium', 'G. Glosarium',
        table(['Istilah', 'Definisi'],
          glos.map(function (g) {
            return cells([g.istilah, g.definisi]);
          }), '', GLOS_FRACS)));
      toc.push('<li><a href="#glosarium">G. Glosarium</a></li>');
    }

    // Header template: 11pt bold uppercase + topik terpusat.
    var topic = module.topic || (module.unit || {}).name ||
      desain.topic_context || '';
    var header = '<p class="doc-title">PERENCANAAN PEMBELAJARAN ' +
      'MENDALAM</p>' +
      (String(topic).trim() ? '<p class="doc-topic">\u201c' +
        esc(String(topic).trim()) + '\u201d</p>' : '');
    return { header: header, toc: '<ul>' + toc.join('') + '</ul>',
             content: parts.join('') };
  }

  window.ModuleRender = { renderModule: renderModule, esc: esc };
})();
