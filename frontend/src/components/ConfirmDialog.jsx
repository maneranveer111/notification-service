import { useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import Button from './ui/Button';

export default function ConfirmDialog({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  loading = false,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
}) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white border border-[#E7E5E4] rounded-[12px] shadow-lg p-6 w-full max-w-sm mx-4 space-y-4"
      >
        <div className="flex items-start gap-3">
          {destructive && (
            <div className="w-8 h-8 rounded-full bg-[#FEF2F2] border border-[#FECACA] flex items-center justify-center text-[#B91C1C] shrink-0 mt-0.5">
              <AlertTriangle className="w-4 h-4" strokeWidth={1.5} />
            </div>
          )}
          <div>
            <h2 className="text-base font-semibold text-[#1C1917]">{title}</h2>
            <p className="text-xs text-[#78716C] mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2.5 pt-2">
          <Button
            ref={cancelRef}
            variant="secondary"
            size="sm"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? 'destructive-filled' : 'primary'}
            size="sm"
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
