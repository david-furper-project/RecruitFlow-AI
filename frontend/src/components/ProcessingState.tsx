import { LoaderCircle } from 'lucide-react';

interface ProcessingOverlayProps {
  title: string;
  description?: string;
}

export function InlineSpinner({ label }: { label: string }) {
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center justify-center gap-2">
      <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />
      <span>{label}</span>
    </span>
  );
}

export function ProcessingOverlay({ title, description }: ProcessingOverlayProps) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-[2px] sm:p-4">
      <section
        role="status"
        aria-live="assertive"
        aria-busy="true"
        className="modal-shell w-full max-w-sm overflow-y-auto rounded-2xl bg-white p-5 text-center shadow-2xl sm:p-7"
      >
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-50 text-red-700">
          <LoaderCircle aria-hidden="true" className="h-8 w-8 animate-spin" />
        </div>
        <h2 className="mt-4 text-lg font-bold text-slate-900">{title}</h2>
        {description && <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>}
        <p className="mt-4 text-xs font-medium text-slate-400">No cierres esta página.</p>
      </section>
    </div>
  );
}
