import { CircleAlert, X } from "lucide-react";

export default function Alert({ message, onClose }: { message: string; onClose?: () => void }) {
  if (!message) return null;
  return (
    <div className="mb-5 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3 text-sm text-rose-800" role="alert">
      <CircleAlert className="mt-0.5 shrink-0" size={17} />
      <p className="flex-1 leading-6">{message}</p>
      {onClose && (
        <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded-lg hover:bg-rose-100" aria-label="بستن">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
