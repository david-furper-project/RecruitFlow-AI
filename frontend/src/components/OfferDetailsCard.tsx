import { useState, type ReactNode } from 'react';
import {
  Building2,
  ChevronDown,
  Clock3,
  Code2,
  DollarSign,
  MapPin,
} from 'lucide-react';

type CompanySummary = {
  name?: string | null;
};

export type OfferDetails = {
  id: number;
  title?: string | null;
  description?: string | null;
  requirements?: string | null;
  tech_stack?: string | null;
  salary_range?: string | null;
  experience_years?: number | null;
  seniority?: string | null;
  country?: string | null;
  modality?: string | null;
  message?: string | null;
  status?: string | null;
  company?: CompanySummary | null;
  company_name?: string | null;
};

type Props = {
  offer: OfferDetails;
  fallbackCompanyName?: string | null;
};

const present = (value?: string | null) => {
  const clean = value?.trim();
  return clean && clean.toLowerCase() !== 'no especificado' ? clean : 'No informado';
};

const statusDetails = (status?: string | null) => {
  if (status === 'closed_final') {
    return { label: 'Cierre definitivo', className: 'bg-slate-800 text-white' };
  }
  if (status === 'closed') {
    return { label: 'Cerrada · reabrible', className: 'bg-amber-100 text-amber-900' };
  }
  return { label: 'Vacante abierta', className: 'bg-emerald-100 text-emerald-800' };
};

export default function OfferDetailsCard({ offer, fallbackCompanyName }: Props) {
  const [expanded, setExpanded] = useState(true);
  const status = statusDetails(offer.status);
  const companyName = present(offer.company?.name || offer.company_name || fallbackCompanyName);
  const stack = (offer.tech_stack || '')
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
  const experience = offer.experience_years == null
    ? 'No informada'
    : `${offer.experience_years} ${offer.experience_years === 1 ? 'año' : 'años'} · ${present(offer.seniority)}`;
  const location = [offer.country, offer.modality]
    .map(value => value?.trim())
    .filter((value): value is string => Boolean(value) && value?.toLowerCase() !== 'no especificado')
    .join(' · ');
  const detailsId = `offer-details-${offer.id}`;

  return (
    <section aria-labelledby={`offer-title-${offer.id}`} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="bg-gradient-to-r from-[#8a1414] to-[#b91c1c] p-4 text-white sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-red-100">Información de la vacante</span>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${status.className}`}>{status.label}</span>
            </div>
            <h1 id={`offer-title-${offer.id}`} className="break-words text-2xl font-bold leading-tight sm:text-3xl">
              {present(offer.title)}
            </h1>
            <p className="mt-2 flex items-center gap-2 text-sm text-red-100">
              <Building2 size={16} aria-hidden="true" />
              <span className="break-words">{companyName}</span>
            </p>
          </div>
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={detailsId}
            onClick={() => setExpanded(value => !value)}
            className="inline-flex w-full flex-shrink-0 items-center justify-center gap-2 rounded-xl border border-white/30 bg-white/10 px-4 py-2.5 text-sm font-bold text-white hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white sm:w-auto"
          >
            {expanded ? 'Ocultar detalles' : 'Ver detalles'}
            <ChevronDown size={17} aria-hidden="true" className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 border-b border-slate-200 bg-slate-50 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryItem icon={<DollarSign size={18} />} label="Renta o rango ofrecido" value={present(offer.salary_range)} />
        <SummaryItem icon={<Clock3 size={18} />} label="Experiencia y seniority" value={experience} />
        <SummaryItem icon={<MapPin size={18} />} label="Ubicación y modalidad" value={location || 'No informado'} />
        <SummaryItem icon={<Code2 size={18} />} label="Stack principal" value={stack.slice(0, 3).join(', ') || 'No informado'} />
      </div>

      {expanded && (
        <div id={detailsId} className="grid gap-6 p-4 sm:p-6 lg:grid-cols-2">
          <DetailSection title="Descripción de la vacante" value={offer.description} />
          <DetailSection title="Requisitos del cargo" value={offer.requirements} />

          <div className="lg:col-span-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">Stack tecnológico</h2>
            {stack.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {stack.map(item => (
                  <span key={item.toLowerCase()} className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800">
                    {item}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm italic text-slate-400">No informado</p>
            )}
          </div>

          {offer.message && offer.message.trim().toLowerCase() !== 'no especificado' && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 lg:col-span-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-amber-800">Contexto adicional</h2>
              <p className="mt-2 whitespace-pre-line text-sm leading-6 text-amber-950">{offer.message}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex min-w-0 gap-3 border-slate-200 p-4 sm:border-r sm:last:border-r-0">
      <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-white text-[#b91c1c] shadow-sm" aria-hidden="true">{icon}</span>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
        <p className="mt-1 break-words text-sm font-semibold text-slate-800">{value}</p>
      </div>
    </div>
  );
}

function DetailSection({ title, value }: { title: string; value?: string | null }) {
  return (
    <div>
      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">{title}</h2>
      <p className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-700">{present(value)}</p>
    </div>
  );
}
