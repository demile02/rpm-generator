import { useDialogFocus } from '../lib/dialogFocus';


interface ConfirmDialogProps {
  open: boolean;
  judul: string;
  pesan: string;
  error: string;
  confirmLabel: string;
  cancelLabel: string;
  confirmClass?: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  judul,
  pesan,
  error,
  confirmLabel,
  cancelLabel,
  confirmClass,
  busy,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const dialogRef = useDialogFocus(open, onClose, busy);
  if (!open) return null;

  const aksi = confirmClass ?? (busy ? 'btn btn--hapus btn--busy' : 'btn btn--hapus');
  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (!busy && e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="konfirmasi-judul" tabIndex={-1}>
        <h2 id="konfirmasi-judul">{judul}</h2>
        <p className="lede">{pesan}</p>
        {error && (
          <p className="error" role="alert">{error}</p>
        )}
        <div className="form__actions">
          <button
            type="button"
            className={aksi}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? 'Memproses…' : confirmLabel}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose} autoFocus>
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
