/* feedback-widget.js — klik elemen di halaman untuk kirim komentar revisi.
   Aktif otomatis saat URL mengandung ?feedback=1 (diinjeksikan oleh Flask).
   Dependency-free, mobile-friendly. */
(function () {
  if (window.__feedbackWidgetLoaded) return;
  window.__feedbackWidgetLoaded = true;

  var pickMode = false;
  var highlightEl = null;

  /* ---------- floating button ---------- */
  var fab = document.createElement('button');
  fab.id = 'fb-widget-fab';
  fab.innerHTML = '&#128172;';
  fab.title = 'Mode komentar';
  fab.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:999998;width:56px;height:56px;border-radius:50%;border:none;background:#FFB7B2;color:#292524;font-size:24px;cursor:pointer;box-shadow:0 4px 20px -2px rgba(0,0,0,0.2);';
  document.body.appendChild(fab);

  var hint = document.createElement('div');
  hint.id = 'fb-widget-hint';
  hint.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:999998;background:#292524;color:#FDFCF8;padding:10px 18px;border-radius:9999px;font-size:14px;display:none;font-family:sans-serif;box-shadow:0 4px 20px -2px rgba(0,0,0,0.2);';
  hint.textContent = 'Ketuk elemen yang ingin direvisi';
  document.body.appendChild(hint);

  function setPickMode(on) {
    pickMode = on;
    fab.style.background = on ? '#292524' : '#FFB7B2';
    fab.style.color = on ? '#FDFCF8' : '#292524';
    fab.innerHTML = on ? '&#10005;' : '&#128172;';
    hint.style.display = on ? 'block' : 'none';
    document.body.style.cursor = on ? 'crosshair' : '';
    clearHighlight();
  }
  fab.addEventListener('click', function (e) {
    e.stopPropagation();
    setPickMode(!pickMode);
  });

  /* ---------- highlight ---------- */
  function clearHighlight() {
    if (highlightEl) { highlightEl.remove(); highlightEl = null; }
  }
  function showHighlight(el) {
    if (el === fab || el === hint || fab.contains(el)) return;
    clearHighlight();
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    highlightEl = document.createElement('div');
    highlightEl.style.cssText = 'position:fixed;z-index:999997;pointer-events:none;border:2px dashed #FFB7B2;background:rgba(255,183,178,0.15);border-radius:8px;left:' + (r.left - 2) + 'px;top:' + (r.top - 2) + 'px;width:' + (r.width + 4) + 'px;height:' + (r.height + 4) + 'px;';
    document.body.appendChild(highlightEl);
  }

  document.addEventListener('mouseover', function (e) {
    if (!pickMode) return;
    showHighlight(e.target);
  }, true);

  /* ---------- selector builder ---------- */
  function getSelector(el) {
    if (!(el instanceof Element)) return '';
    if (el.id) return '#' + el.id;
    var parts = [];
    var cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body && parts.length < 4) {
      var sel = cur.tagName.toLowerCase();
      if (typeof cur.className === 'string' && cur.className.trim()) {
        var cls = cur.className.trim().split(/\s+/).slice(0, 2).join('.');
        if (cls) sel += '.' + cls;
      }
      var sibs = cur.parentNode ? Array.prototype.filter.call(cur.parentNode.children, function (c) { return c.tagName === cur.tagName; }) : [];
      if (sibs.length > 1) sel += ':nth-of-type(' + (sibs.indexOf(cur) + 1) + ')';
      parts.unshift(sel);
      cur = cur.parentNode;
    }
    return parts.join(' > ');
  }

  /* ---------- comment modal ---------- */
  var modal = null;
  function openModal(el) {
    closeModal();
    var r = el.getBoundingClientRect();
    modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;z-index:999999;left:16px;right:16px;bottom:90px;max-width:420px;margin:0 auto;background:#FDFCF8;border:1px solid #E7E5E0;border-radius:24px;padding:20px;box-shadow:0 8px 32px rgba(0,0,0,0.18);font-family:sans-serif;';
    var label = document.createElement('div');
    label.style.cssText = 'font-size:12px;color:#78716C;margin-bottom:8px;';
    var tagline = (el.tagName || '').toLowerCase();
    var snippet = (el.innerText || '').trim().slice(0, 60);
    label.textContent = 'Komentar untuk <' + tagline + '>' + (snippet ? ' "' + snippet + (snippet.length >= 60 ? '…' : '') + '"' : '');
    var ta = document.createElement('textarea');
    ta.placeholder = 'Tulis revisi yang diinginkan…';
    ta.rows = 3;
    ta.style.cssText = 'width:100%;box-sizing:border-box;border:1px solid #E7E5E0;border-radius:16px;padding:12px;font-size:15px;font-family:sans-serif;resize:vertical;';
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:10px;margin-top:12px;justify-content:flex-end;';
    var btnCancel = document.createElement('button');
    btnCancel.textContent = 'Batal';
    btnCancel.style.cssText = 'padding:10px 20px;border-radius:9999px;border:1px solid #E7E5E0;background:#fff;font-size:14px;cursor:pointer;';
    var btnSend = document.createElement('button');
    btnSend.textContent = 'Kirim';
    btnSend.style.cssText = 'padding:10px 24px;border-radius:9999px;border:none;background:#FFB7B2;color:#292524;font-weight:600;font-size:14px;cursor:pointer;';
    btnCancel.addEventListener('click', closeModal);
    btnSend.addEventListener('click', function () {
      var comment = ta.value.trim();
      if (!comment) { ta.focus(); return; }
      btnSend.disabled = true;
      btnSend.textContent = 'Mengirim…';
      sendFeedback({
        page_url: location.href.split('?')[0] + location.hash,
        selector: getSelector(el),
        tag: tagline,
        text_snippet: (el.innerText || '').trim().slice(0, 200),
        comment: comment,
        viewport: window.innerWidth + 'x' + window.innerHeight
      }, function (ok) {
        closeModal();
        toast(ok ? 'Komentar terkirim ✓' : 'Gagal mengirim, coba lagi');
      });
    });
    row.appendChild(btnCancel);
    row.appendChild(btnSend);
    modal.appendChild(label);
    modal.appendChild(ta);
    modal.appendChild(row);
    document.body.appendChild(modal);
    setTimeout(function () { ta.focus(); }, 100);
  }
  function closeModal() {
    if (modal) { modal.remove(); modal = null; }
  }

  /* ---------- click capture ---------- */
  document.addEventListener('click', function (e) {
    if (!pickMode) return;
    if (e.target === fab || fab.contains(e.target)) return;
    if (modal && modal.contains(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    openModal(e.target);
  }, true);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { setPickMode(false); closeModal(); }
  });

  /* ---------- send + toast ---------- */
  function sendFeedback(payload, cb) {
    payload.timestamp = new Date().toISOString();
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); })
      .then(function (j) { cb(j && j.status === 'ok'); })
      .catch(function () { cb(false); });
  }
  function toast(msg) {
    var t = document.createElement('div');
    t.style.cssText = 'position:fixed;bottom:90px;left:50%;transform:translateX(-50%);z-index:999999;background:#292524;color:#FDFCF8;padding:12px 22px;border-radius:9999px;font-size:14px;font-family:sans-serif;box-shadow:0 4px 20px -2px rgba(0,0,0,0.25);';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2500);
  }
})();
