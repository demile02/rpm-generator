import { useAlerts, useLoading } from '../state/appContext';
import { useDialogFocus } from '../lib/dialogFocus';

/* Overlay loading tengah + dialog alert terpusat
   (pengganti loading-overlay + alert-overlay). */
export function Overlays() {
  const { loadingJudul, loadingStatus } = useLoading();
  const { alert, tutupAlert } = useAlerts();
  const alertRef = useDialogFocus(!!alert, tutupAlert);
  /* Ambil persen dari status ("45% dari …") untuk bar determinasi. */
  const persen = (() => {
    const m = /^(\d{1,3})%/.exec(loadingStatus || '');
    if (!m) return -1;
    return Math.min(100, Math.max(0, Number(m[1])));
  })();
  return (
    <>
      {loadingJudul && (
        <div className="overlay overlay--loading" role="dialog" aria-modal="true" aria-live="polite">
          <div className="dialog dialog--loading">
            <div
              className={'progress__bar loading__bar' + (persen >= 0 ? ' progress__bar--pasti' : '')}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={persen >= 0 ? persen : undefined}
              aria-label={persen >= 0 ? 'Kemajuan ' + persen + ' persen' : 'Memuat'}
            >
              <span style={persen >= 0 ? { width: persen + '%', marginLeft: 0, animation: 'none' } : undefined} />
            </div>
            <h2>{loadingJudul}</h2>
            <p className="meta">{loadingStatus}</p>
          </div>
        </div>
      )}
      {alert && (
        <div
          className="overlay overlay--loading"
          onClick={(e) => {
            if (e.target === e.currentTarget) tutupAlert();
          }}
        >
          <div ref={alertRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="alert-judul" tabIndex={-1}>
            <h2 id="alert-judul">{alert.judul || 'Pemberitahuan'}</h2>
            <p className="lede">{alert.pesan}</p>
            <div className="form__actions">
              <button type="button" className="btn btn--aksi" onClick={tutupAlert} autoFocus>
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
