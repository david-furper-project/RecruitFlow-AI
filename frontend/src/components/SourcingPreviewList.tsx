import { CheckCircle2, Mail, Phone, TriangleAlert } from 'lucide-react';
import { InlineSpinner } from './ProcessingState';

export type SourcingPreview = {
  full_name?: string | null;
  headline?: string | null;
  experience?: string | null;
  education?: string | null;
  skills?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  semantic_similarity?: number | null;
  match_explanation?: string | null;
};

export type SourcingPreviewItem = {
  filename: string;
  status: 'ready' | 'error' | 'confirmed' | 'confirmation_error';
  detail?: string;
  preview_token?: string;
  preview?: SourcingPreview;
};

type Props = {
  items: SourcingPreviewItem[];
  confirmingToken?: string | null;
  onConfirm: (item: SourcingPreviewItem) => void;
};

export default function SourcingPreviewList({ items, confirmingToken, onConfirm }: Props) {
  if (!items.length) return null;

  const ready = items.filter(item => item.status === 'ready').length;
  const confirmed = items.filter(item => item.status === 'confirmed').length;
  const errors = items.filter(item => item.status === 'error' || item.status === 'confirmation_error').length;

  return (
    <section className="space-y-3" aria-live="polite">
      <div className="flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-blue-100 px-3 py-1 text-blue-800">{ready} por confirmar</span>
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-800">{confirmed} confirmados</span>
        {errors > 0 && <span className="rounded-full bg-red-100 px-3 py-1 text-red-800">{errors} con error</span>}
      </div>

      {items.map((item, index) => {
        const key = `${item.filename}-${index}`;
        if (item.status === 'error' || !item.preview) {
          return (
            <article key={key} className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <p className="flex items-center gap-2 font-bold"><TriangleAlert size={17} aria-hidden="true" /> {item.filename}</p>
              <p className="mt-1 leading-6">{item.detail || 'No fue posible procesar este perfil.'}</p>
            </article>
          );
        }

        const isConfirmed = item.status === 'confirmed';
        const isConfirming = confirmingToken === item.preview_token;
        const confirmationFailed = item.status === 'confirmation_error';
        return (
          <article key={key} className={`rounded-xl border bg-white p-4 shadow-sm sm:p-5 ${isConfirmed ? 'border-emerald-300' : 'border-slate-200'}`}>
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div className="min-w-0">
                <p className={`text-xs font-bold uppercase tracking-wider ${isConfirmed ? 'text-emerald-700' : 'text-blue-700'}`}>
                  {isConfirmed ? 'Prospecto confirmado' : 'Vista previa · sin persistir'}
                </p>
                <h3 className="mt-1 break-words text-lg font-bold text-slate-900">{item.preview.full_name || 'Nombre no disponible'}</h3>
                <p className="break-words text-sm text-slate-600">{item.preview.headline || item.filename}</p>
              </div>
              <strong className="flex-shrink-0 text-2xl text-[#b91c1c]">{item.preview.semantic_similarity ?? 0}%</strong>
            </div>

            <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <PreviewField label="Experiencia" value={item.preview.experience} />
              <PreviewField label="Formación" value={item.preview.education} />
              <PreviewField label="Competencias" value={item.preview.skills} wide />
              <div className="rounded-lg border bg-slate-50 p-3">
                <p className="flex items-center gap-2 font-semibold text-slate-700"><Mail size={15} /> Correo sugerido</p>
                <p className="mt-1 break-all text-slate-600">{item.preview.contact_email || 'No detectado'}</p>
              </div>
              <div className="rounded-lg border bg-slate-50 p-3">
                <p className="flex items-center gap-2 font-semibold text-slate-700"><Phone size={15} /> Teléfono sugerido</p>
                <p className="mt-1 text-slate-600">{item.preview.contact_phone || 'No detectado'}</p>
              </div>
            </div>

            {item.preview.match_explanation && <p className="mt-4 text-sm leading-6 text-slate-600">{item.preview.match_explanation}</p>}
            {confirmationFailed && (
              <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <TriangleAlert className="mt-0.5 flex-shrink-0" size={17} aria-hidden="true" />
                {item.detail || 'No fue posible confirmar este prospecto. Puedes volver a intentarlo.'}
              </p>
            )}
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                disabled={isConfirmed || isConfirming || !item.preview_token}
                onClick={() => onConfirm(item)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-950 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                {isConfirming ? <InlineSpinner label="Confirmando…" /> : isConfirmed ? <><CheckCircle2 size={16} /> Confirmado</> : confirmationFailed ? 'Reintentar confirmación' : 'Confirmar prospecto'}
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
}

function PreviewField({ label, value, wide = false }: { label: string; value?: string | null; wide?: boolean }) {
  return (
    <div className={`rounded-lg border border-slate-200 p-3 ${wide ? 'sm:col-span-2' : ''}`}>
      <p className="font-semibold text-slate-700">{label}</p>
      <p className="mt-1 whitespace-pre-line leading-6 text-slate-600">{value || 'No disponible'}</p>
    </div>
  );
}
