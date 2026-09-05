import { useEffect, useMemo, useState } from "react";
import { BarChart3, BriefcaseBusiness, Building2, Download, Gauge, PieChart, TrendingUp, Users } from "lucide-react";
import { apiClient } from "../api/client";
import { InlineSpinner } from "./ProcessingState";

type CompanyReport = {
  id: number;
  name: string;
  total_offers: number;
  active_offers: number;
};

type OfferReport = {
  id: number;
  title: string;
  company_name: string;
  total_applications: number;
  avg_similarity: number | null;
};

const toNumber = (value: number | string | null | undefined) => Number(value || 0);

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  accent = "red",
}: {
  icon: typeof Building2;
  label: string;
  value: string | number;
  detail: string;
  accent?: "red" | "amber" | "blue" | "green";
}) {
  const colors = {
    red: "bg-red-50 text-[#b91c1c]",
    amber: "bg-amber-50 text-amber-600",
    blue: "bg-blue-50 text-blue-600",
    green: "bg-emerald-50 text-emerald-600",
  };

  return (
    <article className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-gray-400">{label}</p>
          <p className="mt-2 text-3xl font-black tracking-tight text-gray-900">{value}</p>
        </div>
        <span className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl ${colors[accent]}`}>
          <Icon size={22} aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-xs leading-5 text-gray-500">{detail}</p>
    </article>
  );
}

function HorizontalBars({ rows, emptyMessage }: { rows: { label: string; value: number; note?: string }[]; emptyMessage: string }) {
  const maximum = Math.max(...rows.map(row => row.value), 1);

  if (!rows.length) {
    return <div className="flex min-h-48 items-center justify-center rounded-xl border border-dashed border-gray-200 p-5 text-center text-sm text-gray-400">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-5">
      {rows.map(row => (
        <div key={row.label}>
          <div className="mb-2 flex items-start justify-between gap-3 text-sm">
            <span className="min-w-0 truncate font-semibold text-gray-700" title={row.label}>{row.label}</span>
            <span className="flex-shrink-0 font-black text-gray-900">{row.value}{row.note}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-gray-100" role="img" aria-label={`${row.label}: ${row.value}${row.note || ""}`}>
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#b91c1c] to-red-400 transition-all duration-500"
              style={{ width: `${Math.max(row.value > 0 ? 5 : 0, (row.value / maximum) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ReportsPanel() {
  const [companyReports, setCompanyReports] = useState<CompanyReport[]>([]);
  const [offerReports, setOfferReports] = useState<OfferReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadReports() {
      try {
        setError("");
        const [companies, offers] = await Promise.all([
          apiClient.getCompanyReports(),
          apiClient.getOfferReports(),
        ]);
        setCompanyReports(companies);
        setOfferReports(offers);
      } catch (err) {
        console.error("Error loading reports", err);
        setError("No fue posible cargar los indicadores gerenciales.");
      } finally {
        setLoading(false);
      }
    }
    loadReports();
  }, []);

  const dashboard = useMemo(() => {
    const totalOffers = companyReports.reduce((sum, company) => sum + toNumber(company.total_offers), 0);
    const activeOffers = companyReports.reduce((sum, company) => sum + toNumber(company.active_offers), 0);
    const closedOffers = Math.max(totalOffers - activeOffers, 0);
    const totalApplications = offerReports.reduce((sum, offer) => sum + toNumber(offer.total_applications), 0);
    const weightedSimilarity = offerReports.reduce(
      (sum, offer) => sum + toNumber(offer.avg_similarity) * toNumber(offer.total_applications),
      0,
    );
    const avgSimilarity = totalApplications ? weightedSimilarity / totalApplications : 0;
    const activeRate = totalOffers ? (activeOffers / totalOffers) * 100 : 0;
    const topOffers = [...offerReports]
      .filter(offer => toNumber(offer.total_applications) > 0)
      .sort((a, b) => toNumber(b.total_applications) - toNumber(a.total_applications))
      .slice(0, 5);
    const topMatchOffers = [...offerReports]
      .filter(offer => offer.avg_similarity !== null)
      .sort((a, b) => toNumber(b.avg_similarity) - toNumber(a.avg_similarity))
      .slice(0, 5);
    const applicationsByCompany = Array.from(
      offerReports.reduce((grouped, offer) => {
        grouped.set(offer.company_name, (grouped.get(offer.company_name) || 0) + toNumber(offer.total_applications));
        return grouped;
      }, new Map<string, number>()),
    )
      .map(([label, value]) => ({ label, value }))
      .filter(row => row.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);

    return {
      totalOffers,
      activeOffers,
      closedOffers,
      totalApplications,
      avgSimilarity,
      activeRate,
      topOffers,
      topMatchOffers,
      applicationsByCompany,
    };
  }, [companyReports, offerReports]);

  const downloadPdf = async () => {
    try {
      setDownloading(true);
      setError("");
      const blob = await apiClient.downloadExecutiveReport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reporte-gerencial-pri-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error downloading report", err);
      setError(err instanceof Error ? err.message : "No fue posible descargar el reporte PDF.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-80 items-center justify-center rounded-2xl border border-gray-100 bg-white p-8 shadow-sm">
        <InlineSpinner label="Preparando indicadores gerenciales…" />
      </div>
    );
  }

  const pieGradient = dashboard.totalOffers
    ? `conic-gradient(#b91c1c 0 ${dashboard.activeRate}%, #f59e0b ${dashboard.activeRate}% 100%)`
    : "conic-gradient(#e5e7eb 0 100%)";

  return (
    <section className="mx-auto w-full max-w-7xl space-y-6 pb-8">
      <header className="overflow-hidden rounded-2xl bg-gradient-to-br from-[#7f1d1d] via-[#991b1b] to-[#b91c1c] p-5 text-white shadow-lg sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-red-100">
              <TrendingUp size={16} aria-hidden="true" />
              Inteligencia gerencial
            </div>
            <h1 className="text-2xl font-black tracking-tight sm:text-3xl">Reporte ejecutivo de reclutamiento</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-red-100 sm:text-base">
              Una lectura consolidada de la cartera de vacantes, el volumen de postulaciones y la afinidad del talento evaluado.
            </p>
          </div>
          <button
            type="button"
            onClick={downloadPdf}
            disabled={downloading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-bold text-[#991b1b] shadow-sm transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-70 sm:w-auto"
          >
            {downloading ? <InlineSpinner label="Generando PDF…" /> : <><Download size={18} aria-hidden="true" /> Descargar PDF</>}
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Building2} label="Empresas" value={companyReports.length} detail="Organizaciones incluidas en el análisis." accent="blue" />
        <MetricCard icon={BriefcaseBusiness} label="Vacantes activas" value={dashboard.activeOffers} detail={`${dashboard.closedOffers} ${dashboard.closedOffers === 1 ? "vacante cerrada" : "vacantes cerradas"} dentro de la cartera.`} accent="red" />
        <MetricCard icon={Users} label="Postulaciones" value={dashboard.totalApplications} detail="Candidatos vigentes asociados a las vacantes." accent="amber" />
        <MetricCard icon={Gauge} label="Afinidad promedio" value={`${dashboard.avgSimilarity.toFixed(1)}%`} detail="Promedio ponderado según el volumen por vacante." accent="green" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <article className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-6 flex items-center gap-3">
            <span className="rounded-xl bg-red-50 p-2.5 text-[#b91c1c]"><PieChart size={21} aria-hidden="true" /></span>
            <div>
              <h2 className="font-bold text-gray-900">Estado de las vacantes</h2>
              <p className="text-xs text-gray-500">Distribución de la cartera actual</p>
            </div>
          </div>
          <div className="flex flex-col items-center gap-7 sm:flex-row sm:justify-center">
            <div
              className="relative h-44 w-44 flex-shrink-0 rounded-full"
              style={{ background: pieGradient }}
              role="img"
              aria-label={`${dashboard.activeOffers} vacantes activas y ${dashboard.closedOffers} ${dashboard.closedOffers === 1 ? "cerrada" : "cerradas"}`}
            >
              <div className="absolute inset-7 flex flex-col items-center justify-center rounded-full bg-white shadow-inner">
                <span className="text-3xl font-black text-gray-900">{dashboard.totalOffers}</span>
                <span className="text-xs font-bold uppercase tracking-wide text-gray-400">Total</span>
              </div>
            </div>
            <div className="w-full max-w-xs space-y-4">
              <div className="flex items-center justify-between gap-4 rounded-xl bg-gray-50 p-3">
                <span className="flex items-center gap-2 text-sm font-semibold text-gray-600"><span className="h-3 w-3 rounded-full bg-[#b91c1c]" />Activas</span>
                <span className="font-black text-gray-900">{dashboard.activeOffers}</span>
              </div>
              <div className="flex items-center justify-between gap-4 rounded-xl bg-gray-50 p-3">
                <span className="flex items-center gap-2 text-sm font-semibold text-gray-600"><span className="h-3 w-3 rounded-full bg-amber-500" />Cerradas</span>
                <span className="font-black text-gray-900">{dashboard.closedOffers}</span>
              </div>
              <p className="text-center text-xs leading-5 text-gray-500 sm:text-left">
                El <b className="text-gray-800">{dashboard.activeRate.toFixed(0)}%</b> de la cartera se encuentra abierta para recibir candidatos.
              </p>
            </div>
          </div>
        </article>

        <article className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-6 flex items-center gap-3">
            <span className="rounded-xl bg-red-50 p-2.5 text-[#b91c1c]"><BarChart3 size={21} aria-hidden="true" /></span>
            <div>
              <h2 className="font-bold text-gray-900">Demanda por empresa</h2>
              <p className="text-xs text-gray-500">Empresas con mayor volumen de postulaciones</p>
            </div>
          </div>
          <HorizontalBars rows={dashboard.applicationsByCompany} emptyMessage="Todavía no hay postulaciones para comparar por empresa." />
        </article>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <article className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="font-bold text-gray-900">Vacantes con mayor convocatoria</h2>
          <p className="mb-6 mt-1 text-xs text-gray-500">Ranking por cantidad de postulaciones vigentes</p>
          <HorizontalBars
            rows={dashboard.topOffers.map(offer => ({ label: offer.title, value: toNumber(offer.total_applications) }))}
            emptyMessage="Todavía no hay postulaciones para construir el ranking."
          />
        </article>

        <article className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="font-bold text-gray-900">Mejor afinidad por vacante</h2>
          <p className="mb-6 mt-1 text-xs text-gray-500">Promedio de match de los candidatos evaluados</p>
          <HorizontalBars
            rows={dashboard.topMatchOffers.map(offer => ({ label: offer.title, value: toNumber(offer.avg_similarity), note: "%" }))}
            emptyMessage="Todavía no hay evaluaciones con afinidad calculada."
          />
        </article>
      </div>

      <article className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        <div className="border-b border-gray-100 p-5 sm:p-6">
          <h2 className="font-bold text-gray-900">Detalle ejecutivo por vacante</h2>
          <p className="mt-1 text-xs text-gray-500">Base consolidada utilizada para los indicadores y gráficos.</p>
        </div>
        <div className="responsive-table-shell">
          <table className="w-full min-w-[760px] divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-bold uppercase tracking-wider text-gray-500">Vacante</th>
                <th className="px-6 py-3 text-left text-xs font-bold uppercase tracking-wider text-gray-500">Empresa</th>
                <th className="px-6 py-3 text-center text-xs font-bold uppercase tracking-wider text-gray-500">Postulaciones</th>
                <th className="px-6 py-3 text-center text-xs font-bold uppercase tracking-wider text-gray-500">Afinidad</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {[...offerReports].sort((a, b) => toNumber(b.total_applications) - toNumber(a.total_applications)).map(offer => (
                <tr key={offer.id} className="transition-colors hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-bold text-gray-900">{offer.title}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{offer.company_name}</td>
                  <td className="px-6 py-4 text-center text-sm font-semibold text-gray-700">{offer.total_applications}</td>
                  <td className="px-6 py-4 text-center">
                    {offer.avg_similarity !== null ? (
                      <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold ${toNumber(offer.avg_similarity) >= 75 ? "bg-emerald-50 text-emerald-700" : toNumber(offer.avg_similarity) >= 60 ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-600"}`}>
                        {toNumber(offer.avg_similarity).toFixed(1)}%
                      </span>
                    ) : <span className="text-xs text-gray-400">Sin datos</span>}
                  </td>
                </tr>
              ))}
              {offerReports.length === 0 && (
                <tr><td colSpan={4} className="px-6 py-10 text-center text-sm text-gray-500">No hay vacantes registradas.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
