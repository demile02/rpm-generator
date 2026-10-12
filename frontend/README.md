# Frontend React (frontend/)

Migrasi UI vanilla `ui/` ke React 18 + Vite + TypeScript + Tailwind.
Backend Flask (`src/app.py`) menyediakan route utama `/app` untuk bundle React.

## Struktur

- `src/api.ts` — klien fetch ke `/api/*` (port setia `ui/api.js`)
- `src/types.ts` — kontrak tipe JSON backend
- `src/lib/moduleRender.ts` — port `ui/render.js` ke fungsi TS terstruktur
- `src/state/appContext.tsx` — loading tengah, alert, profil/default-buku
  (localStorage `rpm_profile`, `rpm_buku_default`, `rpm_pernah_buka`)
- `src/state/session.tsx` — sesi RPM aktif (modul, validasi, versi, job)
- `src/components/` — TopBar, Landing, LogDialog, ProfileDialog,
  ConfirmDialog, Overlays
- `src/screens/` — Beranda, Arsip, Formulir, Progres, Hasil, Editor
- `src/index.css` — salinan `ui/styles.css` dengan font Design.md
  (Outfit utama + Reenie Beanie aksen, lokal di `src/assets/fonts/`)
- `tailwind.config.js` — token warna legacy (primary, pagebg, …) +
  `font-display/body` Outfit, `font-script` Reenie Beanie

Desain: hanya font dari Design.md yang diterapkan. Warna, layout,
dan class CSS mengikuti `ui/` lama apa adanya.

## Menjalankan (dev)

```bash
cd frontend
npm install
# jalankan Flask di terminal lain: PYTHONPATH=src python3 src/app.py
npm run dev   # http://localhost:5173, /api diproxy ke Flask :5000
```

## Build + serve via Flask

```bash
cd frontend
npm run build            # output: frontend/dist/
```

Opsi A — serve statis manual (tanpa ubah backend):

```bash
cp -r frontend/dist/* /tmp/rpm-react/   # contoh
# serve /tmp/rpm-react dengan server statis apa pun + proxy /api ke Flask
```

Opsi B, root `/` di Flask:

```python
UI_REACT = PROJECT_ROOT / 'frontend' / 'dist'

@app.route('/', methods=['GET'])
def ui_react():
    resp = make_response(send_file(str(UI_REACT / 'index.html')))
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/assets/<path:asset>', methods=['GET'])
def ui_react_asset(asset):
    resp = make_response(send_from_directory(str(UI_REACT / 'assets'), asset))
    resp.headers['Cache-Control'] = 'no-cache'
    return resp
```

Lalu buka `http://localhost:5000/`. Route lama `/app` dan `/app2` mengarah ke root.

## Catatan verifikasi (2026-10-09)

- `npm run build` lolos (tsc + vite, 31 modul).
- Live lawan Flask: landing + statistik, Beranda, cascade
  sistem→institusi→kelas/mapel→fase, cek CP + panel CP, tolak
  generate tanpa buku — semua verified di browser.
- Generate penuh s.d. Hasil/Editor belum diuji end-to-end (butuh
  API key + buku di DB); alur kode mengikuti `ui/app.js` setia.
