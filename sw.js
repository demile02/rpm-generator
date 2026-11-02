var CACHE = "progres-v28";
var SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon.png"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if (list[i].url.indexOf("progres") !== -1) return list[i].focus();
      }
      return clients.openWindow("./");
    })
  );
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  // Data progres dan riwayat tidak pernah dari cache: selalu jaringan, supaya isinya tidak basi.
  if (url.pathname.indexOf("progress.json") !== -1 || url.pathname.indexOf("history.json") !== -1) {
    e.respondWith(fetch(e.request));
    return;
  }
  // Berkas video tidak pernah masuk cache papan.
  if (url.pathname.indexOf("/video/") !== -1 || url.pathname.endsWith(".mp4")) {
    e.respondWith(fetch(e.request));
    return;
  }
  // Dokumen HTML selalu jaringan dulu, supaya versi papan terbaru langsung
  // tampil tanpa menunggu siklus cache service worker.
  if (e.request.mode === "navigate" || url.pathname.endsWith("/") ||
      url.pathname.indexOf("index.html") !== -1) {
    e.respondWith(
      fetch(e.request).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        return res;
      }).catch(function () { return caches.match(e.request); })
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        return res;
      });
    })
  );
});
