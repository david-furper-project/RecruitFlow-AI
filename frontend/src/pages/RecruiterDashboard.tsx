/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useEffect, useState } from 'react';
import { Copy, ExternalLink, Eye, History, Mail, Menu, Phone, Plus, RefreshCw, Send, Upload, X } from 'lucide-react';
import { apiClient } from '../api/client';
import OfferDetailsCard from '../components/OfferDetailsCard';
import ReportsPanel from '../components/ReportsPanel';
import { InlineSpinner, ProcessingOverlay } from '../components/ProcessingState';
import SourcingPreviewList, { type SourcingPreviewItem } from '../components/SourcingPreviewList';
import { useAuthStore } from '../stores/authStore';
import {
  CV_ACCEPT,
  MAX_CV_SIZE_LABEL,
  SOURCING_CV_ACCEPT,
  SOURCING_CV_VALIDATION,
  selectCvBatch,
  selectSingleCv,
  validateCvFile,
} from '../utils/cvUpload';

const recruiterTabs = ['Inicio', 'Vacantes', 'Empresas', 'Banco de talento', 'Sourcing de talento', 'Reportes'] as const;
type RecruiterTab = typeof recruiterTabs[number];

export default function RecruiterDashboard() {
  const [offers, setOffers] = useState<any[]>([]);
  const [selectedOffer, setSelectedOffer] = useState<any>(null);
  const [loadingOffers, setLoadingOffers] = useState(true);

  // Tab State
  const [currentTab, setCurrentTab] = useState<RecruiterTab>('Vacantes');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [offerTab, setOfferTab] = useState<'Activas'|'Inactivas'>('Activas');

  // Create Offer State
  const [isCreatingOffer, setIsCreatingOffer] = useState(false);
  const [newOffer, setNewOffer] = useState({ company_id: '', title: '', description: '', requirements: '', tech_stack: '', salary_range: '', experience_years: 0, seniority: 'Junior', country: '', modality: 'presencial', message: '', stages_count: 4 });
  const [rawTextForAI, setRawTextForAI] = useState('');
  const [isGeneratingOffer, setIsGeneratingOffer] = useState(false);

  // Companies State
  const [companies, setCompanies] = useState<any[]>([]);
  const [newCompany, setNewCompany] = useState({ name: '', industry: '', description: '' });
  const [selectedCompanyForOffers, setSelectedCompanyForOffers] = useState<any>(null);

  // Matches state
  const [matches, setMatches] = useState<any[]>([]);
  const [loadingMatches, setLoadingMatches] = useState(false);

  // Upload CVs State
  const [isUploading, setIsUploading] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<'idle'|'uploading'|'success'|'error'>('idle');
  const [uploadOrigin, setUploadOrigin] = useState<'authorized_application'|'sourcing'>('authorized_application');
  const [uploadAuthorizationConfirmed, setUploadAuthorizationConfirmed] = useState(false);
  const [uploadSource, setUploadSource] = useState('linkedin');
  const [uploadSourcingPreviews, setUploadSourcingPreviews] = useState<SourcingPreviewItem[]>([]);
  const [confirmingSourcingToken, setConfirmingSourcingToken] = useState<string | null>(null);
  const [uploadResults, setUploadResults] = useState<any[]>([]);
  const [uploadError, setUploadError] = useState('');
  const [vacancyPeopleTab, setVacancyPeopleTab] = useState<'applications'|'sourcing'>('applications');

  // Candidate View Modal State
  const [selectedCandidate, setSelectedCandidate] = useState<any>(null);
  const [discardTarget, setDiscardTarget] = useState<any>(null);
  const [discardFeedback, setDiscardFeedback] = useState('');
  const [discardError, setDiscardError] = useState('');
  const [discardSubmitting, setDiscardSubmitting] = useState(false);

  // Filter State
  const [candidateFilter, setCandidateFilter] = useState<'Todos'|'Top 20%'>('Todos');
  const [candidateView, setCandidateView] = useState<'all'|'stage'|'discarded'>('all');
  const [activeStageId, setActiveStageId] = useState<number | null>(null);

  const [pipelineStages, setPipelineStages] = useState<any[]>([]);
  const [pipelineCounts, setPipelineCounts] = useState<any>({});

  useEffect(() => {
    loadOffers();
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const data = await apiClient.getCompanies();
      setCompanies(data);
    } catch(err) {
      console.error(err);
    }
  };

  const loadOffers = async () => {
    try {
      const data = await apiClient.getOffers();
      setOffers(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingOffers(false);
    }
  };

  // New feature states
  const [isClosingOffer, setIsClosingOffer] = useState(false);
  const [finalistId, setFinalistId] = useState<number | null>(null);
  const [isExtractingTech, setIsExtractingTech] = useState(false);
  const [offerLifecycleBusy, setOfferLifecycleBusy] = useState<number | null>(null);

  const loadMatches = useCallback(async (offerId: number) => {
    setLoadingMatches(true);
    try {
      // By default get candidates based on the active view
      let stageId = undefined;
      let outcome = undefined;

      if (candidateView === 'stage') {
        stageId = activeStageId !== null ? activeStageId : undefined;
      } else if (candidateView === 'discarded') {
        outcome = 'descartado';
      }

      // If we only want top 20%, we can filter in the frontend or backend.
      // The backend getCandidates doesn't accept Top20% filter directly yet unless we pass top_percent, but the UI is simpler if we fetch all for the tab and filter frontend.

      const data = await apiClient.getCandidates(offerId, stageId, outcome);
      setMatches(data.candidates || []);
      setPipelineStages(data.stages || []);
      setPipelineCounts(data.counts || {});
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingMatches(false);
    }
  }, [activeStageId, candidateView]);

  useEffect(() => {
    if (selectedOffer) {
      loadMatches(selectedOffer.id);
    }
  }, [selectedOffer, loadMatches]);

  // Auto-refresh cada 5s mientras haya candidatos sin score calculado.
  // Detecta TANTO similarity_score null/undefined COMO pending_evaluation=true
  // para cubrir el caso de reinicio de servicios donde el score queda en 0
  // sin evaluation real en BD.
  useEffect(() => {
    if (!selectedOffer) return;
    const hasPending = matches.some(
      m => m.pending_evaluation === true
        || m.similarity_score === null
        || m.similarity_score === undefined
    );
    if (!hasPending) return;
    const interval = setInterval(() => {
      loadMatches(selectedOffer.id);
    }, 5000);
    return () => clearInterval(interval);
  }, [matches, selectedOffer, loadMatches]);

  const handleReEvaluateAll = async () => {
    if (!selectedOffer) return;
    try {
      await apiClient.reEvaluateCandidates(selectedOffer.id);
      // Esperar un momento y refrescar
      setTimeout(() => loadMatches(selectedOffer.id), 1500);
    } catch (err) {
      console.error('Error re-evaluating:', err);
    }
  };

  const handleExtractTechStack = async () => {
    const textToAnalyze = `${newOffer.description} ${newOffer.requirements}`.trim();
    if (!textToAnalyze) {
      alert("Por favor, llena la Descripción y los Requerimientos primero.");
      return;
    }
    setIsExtractingTech(true);
    try {
      const res = await apiClient.extractTechStack(textToAnalyze);
      setNewOffer(prev => ({ ...prev, tech_stack: res.tech_stack }));
    } catch (error) {
      console.error(error);
      alert("Hubo un error al extraer el stack con IA.");
    } finally {
      setIsExtractingTech(false);
    }
  };

  const handleGenerateOfferWithAI = async () => {
    if (!rawTextForAI.trim()) {
      alert("Por favor, pega el texto crudo de la vacante primero.");
      return;
    }
    setIsGeneratingOffer(true);
    try {
      const res = await fetch('http://localhost:8000/api/offers/generate-from-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` },
        body: JSON.stringify({ text: rawTextForAI })
      });
      if (!res.ok) throw new Error("Error generating offer with AI");
      const data = await res.json();
      setNewOffer(prev => ({
        ...prev,
        title: data.title || '',
        description: data.description || '',
        requirements: data.requirements || '',
        tech_stack: data.tech_stack || '',
        salary_range: data.salary_range || '',
        experience_years: data.experience_years || 0,
        seniority: data.seniority || 'Junior',
        country: data.country || '',
        modality: data.modality || 'presencial',
        message: data.message || '',
        stages_count: data.stages_count || 4
      }));
    } catch (error) {
      console.error(error);
      alert("Hubo un error al extraer los datos con IA.");
    } finally {
      setIsGeneratingOffer(false);
    }
  };

  const handleCloseOffer = async () => {
    if (!selectedOffer) return;
    setOfferLifecycleBusy(selectedOffer.id);
    try {
      await apiClient.closeOffer(selectedOffer.id, finalistId);
      setIsClosingOffer(false);
      setSelectedOffer(null);
      await loadOffers();
    } catch (err: any) {
      console.error(err);
      alert(err.message || 'Error al cerrar vacante');
    } finally {
      setOfferLifecycleBusy(null);
    }
  };

  const handleReopenOffer = async (offer: any) => {
    setOfferLifecycleBusy(offer.id);
    try {
      await apiClient.reopenOffer(offer.id);
      const refreshed = await apiClient.getOffers();
      setOffers(refreshed);
      if (selectedOffer?.id === offer.id) setSelectedOffer(refreshed.find((item: any) => item.id === offer.id) || null);
    } catch (err: any) {
      alert(err.message || 'No fue posible reabrir la vacante');
    } finally {
      setOfferLifecycleBusy(null);
    }
  };

  const handleFinalCloseOffer = async (offer: any) => {
    const confirmed = window.confirm('Este cierre es definitivo y la vacante ya no podrá reabrirse. ¿Deseas continuar?');
    if (!confirmed) return;
    setOfferLifecycleBusy(offer.id);
    try {
      await apiClient.closeOfferDefinitively(offer.id);
      const refreshed = await apiClient.getOffers();
      setOffers(refreshed);
      if (selectedOffer?.id === offer.id) setSelectedOffer(refreshed.find((item: any) => item.id === offer.id) || null);
    } catch (err: any) {
      alert(err.message || 'No fue posible cerrar definitivamente la vacante');
    } finally {
      setOfferLifecycleBusy(null);
    }
  };

  const handleCreateOffer = async () => {
    const targetCompanyId = selectedCompanyForOffers ? selectedCompanyForOffers.id : newOffer.company_id;
    if (!newOffer.title || !targetCompanyId) {
      alert("Por favor selecciona una empresa y escribe un título");
      return;
    }
    try {
      await apiClient.createOffer({
        ...newOffer,
        company_id: parseInt(targetCompanyId)
      });
      setIsCreatingOffer(false);
      setNewOffer({ company_id: '', title: '', description: '', requirements: '', tech_stack: '', salary_range: '', experience_years: 0, seniority: 'Junior', country: '', modality: 'presencial', message: '', stages_count: 4 });
      setRawTextForAI('');
      loadOffers();
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateCompany = async () => {
    if (!newCompany.name) {
      alert("Por favor ingresa un nombre para la empresa.");
      return;
    }
    try {
      await apiClient.createCompany(newCompany);
      setNewCompany({ name: '', industry: '', description: '' });
      loadCompanies();
    } catch(err) {
      console.error(err);
    }
  };

  const handleMassiveUpload = async () => {
    if (!selectedOffer || uploadFiles.length === 0) return;
    setUploadStatus('uploading');
    setUploadResults([]);
    setUploadError('');
    try {
      if (uploadOrigin === 'sourcing') {
        const response = await apiClient.previewSourcingProspects(uploadFiles, uploadSource, selectedOffer.id);
        const results: SourcingPreviewItem[] = response.results || [];
        setUploadSourcingPreviews(results);
        const failures = results.filter(item => item.status === 'error');
        setUploadStatus(failures.length === results.length ? 'error' : 'idle');
        setUploadError(failures.length ? `${failures.length} perfil(es) no pudieron analizarse; los demás siguen disponibles para confirmar.` : '');
        return;
      }
      if (!uploadAuthorizationConfirmed) throw new Error('Debes confirmar la autorización de los candidatos.');
      const response = await apiClient.massUploadCVs(uploadFiles, selectedOffer.id, uploadOrigin, true);
      const results = response.results || [];
      setUploadResults(results);
      const failures = results.filter((item: any) => item.status === 'error');
      setUploadStatus(failures.length ? 'error' : 'success');
      if (failures.length) {
        setUploadError(`${failures.length} CV no pudo procesarse. Revisa el detalle de cada archivo.`);
      } else {
        setUploadFiles([]);
      }
      setTimeout(() => {
        if (!failures.length) setUploadStatus('idle');
        loadMatches(selectedOffer.id);
      }, 1500);
    } catch (err) {
      console.error(err);
      setUploadError(err instanceof Error ? err.message : 'No fue posible procesar los CV.');
      setUploadStatus('error');
    }
  };

  const confirmManualSourcing = async (item: SourcingPreviewItem) => {
    if (!item.preview_token || !selectedOffer) return;
    setConfirmingSourcingToken(item.preview_token);
    try {
      await apiClient.confirmSourcingProspect(item.preview_token);
      setUploadSourcingPreviews(current => current.map(result => result.preview_token === item.preview_token ? { ...result, status: 'confirmed', detail: undefined } : result));
    } catch (err: any) {
      console.error(err);
      setUploadSourcingPreviews(current => current.map(result => result.preview_token === item.preview_token ? { ...result, status: 'confirmation_error', detail: err.message || 'No fue posible confirmar el prospecto.' } : result));
    } finally {
      setConfirmingSourcingToken(null);
    }
  };

  const applyDecision = async (candidateId: number, status: string, feedback?: string) => {
    if (!selectedOffer) return;
    let action = 'avanzar';
    if (status === 'rejected') action = 'descartar';
    if (status === 'reservar') action = 'reservar';
    const match = matches.find(m => m.candidate_id === candidateId);
    if (!match) throw new Error('No se encontró la postulación del candidato.');

    const result = await apiClient.makeDecision(match.application_id, action, feedback);
    await loadMatches(selectedOffer.id);
    const refreshed = await apiClient.getOffers();
    setOffers(refreshed);
    setSelectedOffer(refreshed.find((offer: any) => offer.id === selectedOffer.id) || selectedOffer);
    return result;
  };

  const handleUpdateStatus = async (candidateId: number, status: string) => {
    const candidate = matches.find(m => m.candidate_id === candidateId);
    if (status === 'rejected') {
      setDiscardTarget(candidate);
      setDiscardFeedback('');
      setDiscardError('');
      return;
    }
    if (status === 'advanced' && (candidate?.status === 'rejected' || candidate?.outcome === 'descartado')) {
      const confirmAdvance = window.confirm('Este candidato ya fue descartado. ¿Quieres reincorporarlo al proceso?');
      if (!confirmAdvance) return;
    }

    try {
      await applyDecision(candidateId, status);
    } catch (err: any) {
      console.error(err);
      alert(`Error: ${err.message}`);
    }
  };

  const confirmDiscard = async () => {
    const feedback = discardFeedback.trim();
    if (!discardTarget || feedback.length < 10) {
      setDiscardError('Escribe un feedback claro de al menos 10 caracteres.');
      return;
    }
    setDiscardSubmitting(true);
    setDiscardError('');
    try {
      await applyDecision(discardTarget.candidate_id, 'rejected', feedback);
      setDiscardTarget(null);
      setDiscardFeedback('');
    } catch (err: any) {
      setDiscardError(err.message || 'No fue posible registrar el descarte.');
    } finally {
      setDiscardSubmitting(false);
    }
  };

  const filteredMatches = candidateFilter === 'Top 20%'
    ? matches.slice(0, Math.max(1, Math.ceil(matches.length * 0.2)))
    : matches;

  const activeOffers = offers.filter(o => o.status === 'open' || !o.status);
  const inactiveOffers = offers.filter(o => o.status === 'closed' || o.status === 'closed_final');
  let displayedOffers = offerTab === 'Activas' ? activeOffers : inactiveOffers;
  if (selectedCompanyForOffers) {
    displayedOffers = displayedOffers.filter(o => o.company_id === selectedCompanyForOffers.id);
  }

  const selectRecruiterTab = (tab: RecruiterTab) => {
    setCurrentTab(tab);
    setSelectedOffer(null);
    setIsCreatingOffer(false);
    setSelectedCompanyForOffers(null);
    setIsMobileMenuOpen(false);
  };

  return (
    <div className="flex min-h-screen min-h-[100dvh] min-w-0 flex-col bg-gray-50 font-sans">
      {uploadStatus === 'uploading' && <ProcessingOverlay
        title={uploadOrigin === 'sourcing' ? `Analizando ${uploadFiles.length} perfil${uploadFiles.length === 1 ? '' : 'es'}` : `Procesando ${uploadFiles.length} CV${uploadFiles.length === 1 ? '' : 's'}`}
        description={uploadOrigin === 'sourcing' ? 'Extraemos cada perfil y calculamos individualmente su afinidad con esta vacante.' : 'Extraemos cada CV, creamos las postulaciones autorizadas y calculamos su afinidad.'}
      />}
      {discardTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-3 sm:p-4">
        <div role="dialog" aria-modal="true" aria-labelledby="discard-title" className="modal-shell w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
          <div className="flex items-start justify-between gap-4 border-b p-4 sm:p-6">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-red-700">Decisión con feedback obligatorio</p>
              <h2 id="discard-title" className="mt-1 text-xl font-bold text-slate-900">Descartar a {discardTarget.full_name}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">El feedback quedará en el historial de la postulación y se enviará al correo del candidato.</p>
            </div>
            <button type="button" aria-label="Cerrar" disabled={discardSubmitting} onClick={() => setDiscardTarget(null)} className="rounded-full p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-50"><X size={20} /></button>
          </div>
          <div className="space-y-3 p-4 sm:p-6">
            {discardError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{discardError}</div>}
            <label className="block text-sm font-semibold text-slate-700">Feedback para el candidato
              <textarea
                autoFocus
                rows={6}
                maxLength={2000}
                value={discardFeedback}
                onChange={event => { setDiscardFeedback(event.target.value); setDiscardError(''); }}
                placeholder="Ej.: Agradecemos tu participación. Para esta vacante necesitamos mayor experiencia práctica en automatización de pruebas..."
                className="mt-2 w-full rounded-xl border border-slate-300 p-3 text-sm leading-6 outline-none focus:border-red-700 focus:ring-2 focus:ring-red-100"
              />
            </label>
            <div className="flex items-center justify-between text-xs text-slate-500"><span>Mínimo 10 caracteres. Evita información sensible o discriminatoria.</span><span>{discardFeedback.length}/2000</span></div>
          </div>
          <div className="flex flex-col-reverse gap-3 border-t bg-slate-50 p-4 sm:flex-row sm:justify-end sm:p-5">
            <button type="button" disabled={discardSubmitting} onClick={() => setDiscardTarget(null)} className="rounded-xl border border-slate-300 bg-white px-5 py-3 font-semibold text-slate-700 disabled:opacity-50">Cancelar</button>
            <button type="button" disabled={discardSubmitting || discardFeedback.trim().length < 10} onClick={confirmDiscard} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-700 px-5 py-3 font-bold text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-40">
              {discardSubmitting ? <InlineSpinner label="Registrando y notificando…" /> : <><Mail size={17} /> Descartar y enviar feedback</>}
            </button>
          </div>
        </div>
      </div>}
      {/* Top Bar Falsa estilo MacOS */}
      <div className="z-20 flex min-w-0 items-center bg-[#b91c1c] px-4 py-3 text-white shadow-md sm:px-6">
        <div className="mr-3 flex flex-shrink-0 gap-2 sm:mr-auto">
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
        </div>
        <div className="min-w-0 flex-1 truncate text-right text-xs font-medium opacity-90 sm:absolute sm:left-1/2 sm:mx-auto sm:max-w-[60vw] sm:-translate-x-1/2 sm:text-center sm:text-sm">
          {selectedOffer ? `pri.empresa.com / vacantes / ${selectedOffer.title.toLowerCase().replace(/\s+/g, '-')}` : 'pri.empresa.com / reclutador / vacantes'}
        </div>
      </div>

      <nav aria-label="Secciones del portal" className="relative z-20 border-b border-gray-200 bg-white shadow-sm md:hidden">
        <button
          type="button"
          aria-expanded={isMobileMenuOpen}
          aria-controls="recruiter-mobile-menu"
          onClick={() => setIsMobileMenuOpen(open => !open)}
          className="flex w-full items-center gap-3 px-4 py-3 text-left text-gray-800 transition-colors hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#b91c1c]"
        >
          <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[#b91c1c] text-white">
            {isMobileMenuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-semibold uppercase tracking-wide text-gray-400">Menú</span>
            <span className="block truncate text-sm font-bold text-[#b91c1c]">{currentTab}</span>
          </span>
          <span className="text-xs font-semibold text-gray-500">{isMobileMenuOpen ? 'Cerrar' : 'Abrir'}</span>
        </button>

        {isMobileMenuOpen && (
          <div id="recruiter-mobile-menu" className="border-t border-gray-100 bg-gray-50 p-2">
            {recruiterTabs.map(tab => (
              <button
                type="button"
                key={tab}
                onClick={() => selectRecruiterTab(tab)}
                aria-current={currentTab === tab ? 'page' : undefined}
                className={`flex w-full items-center justify-between rounded-lg px-4 py-3 text-left text-sm font-semibold transition-colors ${currentTab === tab ? 'bg-[#b91c1c] text-white shadow-sm' : 'text-gray-700 hover:bg-white hover:text-[#b91c1c]'}`}
              >
                <span>{tab}</span>
                {currentTab === tab && <span className="text-xs font-bold uppercase tracking-wide text-white/80">Actual</span>}
              </button>
            ))}
          </div>
        )}
      </nav>

      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-gray-100 border-r border-gray-200 flex flex-col pt-4 z-10 hidden md:flex">
          {recruiterTabs.map(tab => (
            <button
              type="button"
              key={tab}
              onClick={() => selectRecruiterTab(tab)}
              className={`px-6 py-4 cursor-pointer text-left text-sm font-medium transition-colors ${currentTab === tab ? 'bg-[#b91c1c] text-white shadow-inner' : 'text-gray-600 hover:bg-gray-200'}`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <main className="min-w-0 flex-1 overflow-y-auto bg-white p-4 shadow-inner sm:p-6 md:border-l md:border-gray-200 lg:p-8">
          {currentTab === 'Banco de talento' && <TalentBank />}
          {currentTab === 'Sourcing de talento' && <SourcingPanel offers={offers.filter(o => o.status === 'open')} />}
          {currentTab === 'Inicio' && (
            <div className="max-w-6xl mx-auto animate-fade-in">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
                <div>
                  <h1 className="text-3xl font-bold text-gray-800 mb-1">¡Hola, Reclutador! 👋</h1>
                  <p className="text-gray-500 text-sm md:text-base">Aquí tienes un resumen de tu actividad en la plataforma.</p>
                </div>
                <div className="text-right">
                  <span className="text-sm font-medium text-gray-400 bg-gray-50 border border-gray-100 px-4 py-2 rounded-full">
                    {new Date().toLocaleDateString('es-ES', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="p-4 bg-red-50 text-red-700 rounded-xl">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500 mb-1">Vacantes Activas</p>
                    <p className="text-3xl font-bold text-gray-800">{offers.filter(o => o.status === 'open' || !o.status).length}</p>
                  </div>
                </div>

                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="p-4 bg-blue-50 text-blue-700 rounded-xl">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500 mb-1">Empresas</p>
                    <p className="text-3xl font-bold text-gray-800">{companies.length}</p>
                  </div>
                </div>

                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4 hover:shadow-md transition-shadow">
                  <div className="p-4 bg-emerald-50 text-emerald-700 rounded-xl">
                    <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500 mb-1">Banco de Talento</p>
                    <button onClick={() => setCurrentTab('Banco de talento')} className="text-emerald-700 font-bold hover:underline text-left">Ir al buscador →</button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-8">
                  <h3 className="font-bold text-xl text-gray-800 mb-6 flex items-center gap-2">
                    <span className="text-[#b91c1c] bg-red-50 p-2 rounded-lg">⚡</span> Accesos Rápidos
                  </h3>
                  <div className="flex flex-col gap-3">
                    <button onClick={() => setCurrentTab('Vacantes')} className="w-full text-left px-5 py-4 bg-gray-50 hover:bg-gray-100 hover:shadow-sm rounded-xl text-gray-700 font-semibold transition-all flex justify-between items-center border border-gray-100 group">
                      Gestionar Vacantes Activas
                      <span className="text-gray-400 group-hover:text-gray-600 transition-colors transform group-hover:translate-x-1">→</span>
                    </button>
                    <button onClick={() => setCurrentTab('Empresas')} className="w-full text-left px-5 py-4 bg-gray-50 hover:bg-gray-100 hover:shadow-sm rounded-xl text-gray-700 font-semibold transition-all flex justify-between items-center border border-gray-100 group">
                      Crear nueva Empresa
                      <span className="text-gray-400 group-hover:text-gray-600 transition-colors transform group-hover:translate-x-1">→</span>
                    </button>
                    <button onClick={() => setCurrentTab('Sourcing de talento')} className="w-full text-left px-5 py-4 bg-gray-50 hover:bg-gray-100 hover:shadow-sm rounded-xl text-gray-700 font-semibold transition-all flex justify-between items-center border border-gray-100 group">
                      Cargar perfiles por Sourcing
                      <span className="text-gray-400 group-hover:text-gray-600 transition-colors transform group-hover:translate-x-1">→</span>
                    </button>
                  </div>
                </div>

                <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-red-900 bg-gradient-to-br from-[#8a1414] to-[#b91c1c] p-5 text-white shadow-md sm:p-8">
                  <div className="absolute top-0 right-0 -mr-16 -mt-16 opacity-10 pointer-events-none">
                     <svg width="250" height="250" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                  </div>
                  <div className="relative z-10">
                    <span className="bg-red-950 bg-opacity-40 text-red-100 text-xs font-bold px-3 py-1 rounded-full mb-4 inline-block border border-red-500">PRI AI Engine v1.0</span>
                    <h3 className="font-bold text-3xl mb-4 leading-tight">Potencia tu reclutamiento con IA</h3>
                    <p className="text-red-100 text-base mb-8 leading-relaxed">
                      La Plataforma de Reclutamiento Inteligente automatiza la lectura de currículums, extrae habilidades técnicas y rankea automáticamente a los candidatos según su porcentaje de "match" usando IA generativa avanzada.
                    </p>
                  </div>
                  <button
                    onClick={() => { setCurrentTab('Vacantes'); setIsCreatingOffer(true); }}
                    className="relative z-10 bg-white text-[#b91c1c] font-bold py-3.5 px-6 rounded-xl shadow-lg hover:bg-gray-50 hover:scale-[1.02] transition-all self-start flex items-center gap-2"
                  >
                    ✨ Crear Vacante Mágica
                  </button>
                </div>
              </div>
            </div>
          )}

          {currentTab === "Reportes" && <ReportsPanel />}

          {currentTab === 'Vacantes' && (
            <div className="max-w-6xl mx-auto">
              {!selectedCompanyForOffers ? (
                <div className="rounded-sm border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
                  <h2 className="text-xl font-bold text-[#b91c1c] mb-6">Selecciona una Empresa para ver sus Vacantes</h2>
                  {companies.length === 0 ? (
                    <p className="text-gray-500 text-sm">No hay empresas registradas. Ve a la pestaña "Empresas" para crear una.</p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {companies.map(c => (
                        <div key={c.id} onClick={() => setSelectedCompanyForOffers(c)} className="cursor-pointer hover:shadow-md p-4 border border-gray-200 rounded-sm shadow-sm bg-white transition-shadow">
                          <h4 className="font-bold text-[#b91c1c] text-lg">{c.name}</h4>
                          <p className="text-sm text-gray-500 mt-1">{c.industry || 'Industria no especificada'}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : !selectedOffer ? (
                <div>
                  <div className="mb-4">
                    <button onClick={() => setSelectedCompanyForOffers(null)} className="text-gray-500 hover:text-gray-800 text-sm font-medium flex items-center gap-2">← Volver a Empresas</button>
                  </div>
                  <div className="mt-4 flex flex-col items-stretch justify-between gap-4 border-b border-gray-200 pb-4 sm:mb-6 sm:flex-row sm:items-end">
                    <div>
                      <h1 className="text-2xl font-bold text-[#b91c1c] mb-2">Vacantes de {selectedCompanyForOffers.name}</h1>
                      <div className="flex bg-gray-100 w-max rounded-sm overflow-hidden border border-gray-200">
                        <button onClick={() => setOfferTab('Activas')} className={`px-8 py-2 font-medium text-sm transition-colors ${offerTab === 'Activas' ? 'bg-[#b91c1c] text-white' : 'text-gray-600 hover:bg-gray-200'}`}>Activas</button>
                        <button onClick={() => setOfferTab('Inactivas')} className={`px-8 py-2 font-medium text-sm border-l border-gray-200 transition-colors ${offerTab === 'Inactivas' ? 'bg-[#b91c1c] text-white' : 'text-gray-600 hover:bg-gray-200'}`}>Inactivas</button>
                      </div>
                    </div>
                    <button
                      onClick={() => setIsCreatingOffer(!isCreatingOffer)}
                      className="w-full rounded-sm bg-[#f59e0b] px-6 py-2.5 text-sm font-bold text-black shadow-sm transition-colors hover:bg-amber-400 sm:w-auto"
                    >
                      {isCreatingOffer ? 'Cancelar' : '+ Nueva vacante'}
                    </button>
                  </div>

                  {isCreatingOffer && (
                    <div className="mb-6 flex flex-col gap-4 rounded-sm border border-gray-200 bg-gray-50 p-4 sm:p-6">
                      <h3 className="font-bold text-[#b91c1c] mb-2">Crear nueva oferta laboral en {selectedCompanyForOffers.name}</h3>

                      <div className="p-4 bg-white border border-gray-200 rounded-sm flex flex-col gap-2">
                        <label className="text-sm font-bold text-gray-700">Autocompletar con IA (Pega el texto de la vacante aquí)</label>
                        <textarea
                          placeholder="Pega el texto crudo aquí (ej. de LinkedIn) y la IA extraerá todos los campos..."
                          className="p-2 border rounded text-sm w-full h-24"
                          value={rawTextForAI}
                          onChange={e => setRawTextForAI(e.target.value)}
                        />
                        <button
                          onClick={handleGenerateOfferWithAI}
                          disabled={isGeneratingOffer}
                          className="self-end px-4 py-2 bg-purple-600 text-white font-bold rounded text-sm hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2"
                        >
                          {isGeneratingOffer ? 'Procesando...' : '✨ Procesar con IA'}
                        </button>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input type="text" placeholder="Título (ej. Frontend Developer) *" className="p-2 border rounded text-sm md:col-span-2" value={newOffer.title} onChange={e => setNewOffer({ ...newOffer, title: e.target.value })} />
                        <div className="flex flex-col gap-2 sm:flex-row md:col-span-2">
                          <input type="text" placeholder="Stack Tecnológico *" className="p-2 border rounded text-sm flex-1" value={newOffer.tech_stack} onChange={e => setNewOffer({ ...newOffer, tech_stack: e.target.value })} />
                          <button onClick={handleExtractTechStack} disabled={isExtractingTech} className="whitespace-nowrap rounded bg-[#f59e0b] px-4 py-2 text-sm font-bold text-black shadow-sm hover:bg-amber-400 disabled:opacity-50">
                            {isExtractingTech ? 'Procesando...' : '✨ Extraer Stack'}
                          </button>
                        </div>
                        <textarea placeholder="Descripción *" className="p-2 border rounded text-sm md:col-span-2 h-20" value={newOffer.description} onChange={e => setNewOffer({ ...newOffer, description: e.target.value })} />
                        <textarea placeholder="Requerimientos *" className="p-2 border rounded text-sm md:col-span-2 h-20" value={newOffer.requirements} onChange={e => setNewOffer({ ...newOffer, requirements: e.target.value })} />
                        <textarea placeholder="Mensaje / Contexto extra" className="p-2 border rounded text-sm md:col-span-2" value={newOffer.message} onChange={e => setNewOffer({ ...newOffer, message: e.target.value })} />

                        <input type="text" placeholder="Rango / Pretensión Salarial *" className="p-2 border rounded text-sm" value={newOffer.salary_range} onChange={e => setNewOffer({ ...newOffer, salary_range: e.target.value })} />
                        <div className="flex gap-2">
                          <input type="number" min="0" placeholder="Exp. (años) *" className="w-1/2 p-2 border rounded text-sm" value={newOffer.experience_years} onChange={e => setNewOffer({ ...newOffer, experience_years: parseInt(e.target.value) || 0 })} />
                          <select className="w-1/2 p-2 border rounded text-sm bg-white" value={newOffer.seniority} onChange={e => setNewOffer({ ...newOffer, seniority: e.target.value })}>
                            <option value="Junior">Junior</option><option value="Semi-Senior">Semi-Senior</option><option value="Senior">Senior</option><option value="Lead">Lead</option>
                          </select>
                        </div>

                        <div className="flex gap-2">
                          <input type="text" placeholder="País (ej. LATAM, Chile) *" className="w-1/2 p-2 border rounded text-sm" value={newOffer.country} onChange={e => setNewOffer({ ...newOffer, country: e.target.value })} />
                          <select className="w-1/2 p-2 border rounded text-sm bg-white" value={newOffer.modality} onChange={e => setNewOffer({ ...newOffer, modality: e.target.value })}>
                            <option value="presencial">Presencial</option>
                            <option value="remoto">Remoto</option>
                            <option value="híbrido">Híbrido</option>
                          </select>
                        </div>

                        <div className="flex items-center gap-2">
                           <label className="text-sm font-semibold text-gray-700 w-1/2">Cant. de procesos:</label>
                           <input type="number" min="1" max="10" placeholder="Ej. 4" className="w-1/2 p-2 border rounded text-sm" value={newOffer.stages_count} onChange={e => setNewOffer({ ...newOffer, stages_count: parseInt(e.target.value) || 1 })} />
                        </div>
                      </div>
                      <button onClick={handleCreateOffer} className="w-full py-2 mt-2 bg-[#b91c1c] text-white rounded font-bold hover:bg-red-800 transition-colors">Guardar Vacante</button>
                    </div>
                  )}

              {loadingOffers ? (
                 <p className="text-center py-10 text-gray-400">Cargando vacantes...</p>
              ) : (
                <div className="responsive-table-shell rounded-sm border border-gray-200">
                  <table className="responsive-table min-w-[860px] border-collapse text-left">
                    <thead>
                      <tr className="bg-[#b91c1c] text-white text-sm">
                        <th className="p-4 font-semibold border-r border-[#a01616]">Cargo</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616]">Estado</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616]">Candidatos</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616]">Score promedio</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616]">Días abiertos</th>
                        <th className="p-4 font-semibold text-center">Acción</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayedOffers.length === 0 ? (
                        <tr className="bg-white">
                          <td colSpan={6} className="p-8 text-center text-gray-500 font-medium">
                            No hay vacantes registradas en esta pestaña.
                          </td>
                        </tr>
                      ) : (
                        displayedOffers.map((offer, idx) => (
                          <tr key={offer.id} className={`border-b border-gray-200 text-sm ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                            <td className="p-4 font-bold text-[#b91c1c]">{offer.title}</td>
                            <td className="p-4 text-center">
                              <span className={`${offer.status === 'closed_final' ? 'bg-slate-800' : offer.status === 'closed' ? 'bg-amber-600' : 'bg-green-700'} text-white text-xs px-3 py-1 font-bold rounded-full`}>
                                {offer.status === 'closed_final' ? 'Cierre definitivo' : offer.status === 'closed' ? 'Cerrada · reabrible' : 'Abierta'}
                              </span>
                            </td>
                            <td className="p-4 text-center font-bold text-gray-800">0</td>
                            <td className="p-4 text-center font-bold text-[#b91c1c]">-</td>
                            <td className="p-4 text-center text-gray-600 font-medium">1 día</td>
                            <td className="p-4 text-center space-x-2 whitespace-nowrap">
                              <button
                                onClick={() => setSelectedOffer(offer)}
                                className="bg-[#b91c1c] text-white text-xs px-3 py-2 font-bold hover:bg-red-800 transition-colors rounded-sm shadow-sm"
                              >
                                {offer.status === 'open' || !offer.status ? 'Ver candidatos' : 'Ver proceso'}
                              </button>
                              {offer.status === 'closed' && <button disabled={offerLifecycleBusy === offer.id} onClick={() => handleReopenOffer(offer)} className="border border-emerald-700 text-emerald-700 text-xs px-3 py-2 font-bold hover:bg-emerald-50 disabled:opacity-50">Reabrir</button>}
                              {offer.status === 'closed' && <button disabled={offerLifecycleBusy === offer.id} onClick={() => handleFinalCloseOffer(offer)} className="text-slate-600 text-xs px-2 py-2 font-bold hover:text-red-800 disabled:opacity-50">Cerrar definitivamente</button>}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div>
              {/* PANTALLA 2: Candidatos */}
              <div className="flex flex-col gap-4 mb-6 mt-4">
                <button type="button" className="flex w-max max-w-full items-center gap-2 text-left text-sm font-medium text-gray-500 hover:text-gray-800" onClick={() => { setSelectedOffer(null); setIsUploading(false); setVacancyPeopleTab('applications'); }}>
                  <span aria-hidden="true">←</span> Volver a vacantes
                </button>

                <OfferDetailsCard
                  key={selectedOffer.id}
                  offer={selectedOffer}
                  fallbackCompanyName={selectedCompanyForOffers?.name}
                />

                <h2 className="text-2xl font-bold text-[#b91c1c]">{vacancyPeopleTab === 'applications' ? `Postulantes (${filteredMatches.length})` : 'Sourcing'}</h2>

                <div className="responsive-table-shell border-b border-gray-200">
                  <div className="flex min-w-max gap-2">
                  <button onClick={() => setVacancyPeopleTab('applications')} className={`px-5 py-2 font-bold border-b-2 ${vacancyPeopleTab === 'applications' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500'}`}>Postulantes</button>
                  <button onClick={() => { setVacancyPeopleTab('sourcing'); setIsUploading(false); }} className={`px-5 py-2 font-bold border-b-2 ${vacancyPeopleTab === 'sourcing' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500'}`}>Sourcing</button>
                  </div>
                </div>

                {vacancyPeopleTab === 'sourcing' && <SourcingPanel offers={[selectedOffer]} fixedOfferId={selectedOffer.id} />}

                <div className={`${vacancyPeopleTab === 'applications' ? 'flex' : 'hidden'} flex-col gap-4 w-full border-b border-gray-200 pb-4`}>
                  {/* Pipeline Stages Tabs */}
                  <div className="flex w-full overflow-x-auto border-b border-gray-200" style={{ scrollbarWidth: 'none' }}>
                    <button
                      onClick={() => { setCandidateView('all'); setActiveStageId(null); }}
                      className={`px-5 py-3 font-semibold text-sm whitespace-nowrap border-b-2 transition-colors flex items-center gap-2 ${candidateView === 'all' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50'}`}
                    >
                      <span>Todos</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${candidateView === 'all' ? 'bg-[#b91c1c] text-white' : 'bg-gray-200 text-gray-600'}`}>
                        {pipelineCounts.all_active || 0}
                      </span>
                    </button>
                    {pipelineStages.map(stage => {
                      const isSelected = candidateView === 'stage' && activeStageId === stage.id;
                      return (
                        <button
                          key={stage.id}
                          onClick={() => { setCandidateView('stage'); setActiveStageId(stage.id); }}
                          className={`px-5 py-3 font-semibold text-sm whitespace-nowrap border-b-2 transition-colors flex items-center gap-2 ${isSelected ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50'}`}
                        >
                          <span>{stage.name}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${isSelected ? 'bg-[#b91c1c] text-white' : (stage.count && stage.count > 0 ? 'bg-red-50 text-red-700' : 'bg-gray-200 text-gray-600')}`}>
                            {stage.count || 0}
                          </span>
                        </button>
                      );
                    })}
                    <button
                      onClick={() => { setCandidateView('discarded'); setActiveStageId(null); }}
                      className={`px-5 py-3 font-semibold text-sm whitespace-nowrap border-b-2 transition-colors flex items-center gap-2 ${candidateView === 'discarded' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-50'}`}
                    >
                      <span>Descartados</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${candidateView === 'discarded' ? 'bg-[#b91c1c] text-white' : 'bg-gray-200 text-gray-600'}`}>
                        {pipelineCounts.discarded || 0}
                      </span>
                    </button>
                  </div>

                  {/* Filters & Actions row */}
                  <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex bg-gray-100 rounded-sm overflow-hidden border border-gray-200 shadow-sm hidden md:flex">
                      {(['Todos', 'Top 20%'] as const).map(filter => (
                        <button
                          key={filter}
                          onClick={() => setCandidateFilter(filter)}
                          className={`px-6 py-2 font-medium text-xs border-l border-gray-200 transition-colors ${candidateFilter === filter ? 'bg-gray-800 text-white' : 'text-gray-600 hover:bg-gray-200'}`}
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-2 sm:justify-end">
                      <button
                        onClick={() => setIsUploading(!isUploading)}
                        className="flex-1 rounded-sm bg-[#b91c1c] px-4 py-2 text-sm font-bold text-white shadow-sm transition-colors hover:bg-red-900 sm:flex-none"
                      >
                        {isUploading ? 'Cancelar' : '+ Cargar CVs'}
                      </button>
                      <button
                        onClick={() => loadMatches(selectedOffer.id)}
                        title="Actualizar lista"
                        className="px-3 py-2 bg-white border border-gray-300 text-gray-600 font-bold text-sm hover:bg-gray-100 transition-colors rounded-sm shadow-sm"
                      >
                        ↻
                      </button>
                      {/* Botón re-evaluar: recupera scores perdidos tras reinicio */}
                      {matches.some(m => m.pending_evaluation || m.similarity_score === null || m.similarity_score === undefined) && (
                        <button
                          onClick={handleReEvaluateAll}
                          title="Re-calcular scores de match con IA"
                          className="px-3 py-2 bg-amber-500 text-white font-bold text-xs hover:bg-amber-600 transition-colors rounded-sm shadow-sm flex items-center gap-1 animate-pulse"
                        >
                          ⚡ Re-evaluar todo
                        </button>
                      )}
                      {(selectedOffer.status === 'open' || !selectedOffer.status) && (
                        <button
                          onClick={() => setIsClosingOffer(true)}
                          className="bg-red-900 text-white font-bold text-xs px-6 py-2.5 rounded-sm shadow-sm hover:bg-red-700 transition-colors"
                        >
                          Cerrar proceso
                        </button>
                      )}
                      {selectedOffer.status === 'closed' && <>
                        <button disabled={offerLifecycleBusy === selectedOffer.id} onClick={() => handleReopenOffer(selectedOffer)} className="border border-emerald-700 bg-white text-emerald-700 font-bold text-xs px-5 py-2.5 rounded-sm hover:bg-emerald-50 disabled:opacity-50">Reabrir vacante</button>
                        <button disabled={offerLifecycleBusy === selectedOffer.id} onClick={() => handleFinalCloseOffer(selectedOffer)} className="bg-slate-800 text-white font-bold text-xs px-5 py-2.5 rounded-sm hover:bg-slate-950 disabled:opacity-50">Cerrar definitivamente</button>
                      </>}
                      {selectedOffer.status === 'closed_final' && <span className="rounded-full bg-slate-100 px-4 py-2 text-xs font-bold text-slate-700">Cierre definitivo</span>}
                    </div>

                  </div>
                </div>
              </div>

              {isUploading && vacancyPeopleTab === 'applications' && (
                <div className="mb-6 rounded-sm border border-gray-200 bg-gray-50 p-4 shadow-inner sm:p-6">
                  <h3 className="font-bold text-[#b91c1c] mb-4">Carga de CVs (individual o masiva)</h3>
                  <div className="grid md:grid-cols-2 gap-3 mb-4 text-sm">
                    <label className={`border p-3 cursor-pointer ${uploadOrigin === 'authorized_application' ? 'border-[#b91c1c] bg-red-50' : 'bg-white'}`}>
                      <input className="mr-2" type="radio" checked={uploadOrigin === 'authorized_application'} onChange={() => { setUploadOrigin('authorized_application'); setUploadSourcingPreviews([]); }} />
                      Postulación autorizada por el candidato
                    </label>
                    <label className={`border p-3 cursor-pointer ${uploadOrigin === 'sourcing' ? 'border-[#b91c1c] bg-red-50' : 'bg-white'}`}>
                      <input className="mr-2" type="radio" checked={uploadOrigin === 'sourcing'} onChange={() => { setUploadOrigin('sourcing'); setUploadFiles([]); setUploadSourcingPreviews([]); }} />
                      Perfil encontrado por sourcing
                    </label>
                  </div>
                  {uploadOrigin === 'sourcing' && <div className="mb-4">
                    <label className="text-sm font-bold text-gray-700">Origen del perfil</label>
                    <select className="mt-2 block w-full border bg-white p-2 sm:ml-3 sm:mt-0 sm:inline-block sm:w-auto" value={uploadSource} onChange={e => setUploadSource(e.target.value)}>
                      <option value="linkedin">LinkedIn</option><option value="computrabajo">Computrabajo</option><option value="laborum">Laborum</option><option value="referido">Referido</option><option value="otro">Otro</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-2">Puedes analizar hasta 20 perfiles juntos. Cada uno tendrá su propia vista previa y no se creará ninguna postulación.</p>
                  </div>}
                  {uploadOrigin === 'authorized_application' && <label className="flex gap-2 mb-4 text-sm bg-white border p-3">
                    <input type="checkbox" checked={uploadAuthorizationConfirmed} onChange={e => setUploadAuthorizationConfirmed(e.target.checked)} />
                    Confirmo que cada candidato autorizó expresamente esta postulación y el tratamiento de su CV.
                  </label>}
                  <label className="w-full h-32 border-2 border-dashed border-red-300 rounded-sm flex flex-col items-center justify-center cursor-pointer hover:bg-white transition-colors bg-white mb-4">
                    <span className="text-sm text-[#b91c1c] font-medium px-4 text-center">
                      {uploadFiles.length > 0
                        ? `${uploadFiles.length} archivo(s) seleccionado(s).`
                        : uploadOrigin === 'sourcing'
                          ? `Selecciona hasta 20 perfiles en PDF o Word (.doc o .docx), máximo ${MAX_CV_SIZE_LABEL} cada uno`
                          : `Selecciona hasta 20 CV en PDF o Word (.doc o .docx), máximo ${MAX_CV_SIZE_LABEL} cada uno`}
                    </span>
                    <input
                      type="file"
                      accept={uploadOrigin === 'sourcing' ? SOURCING_CV_ACCEPT : CV_ACCEPT}
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        const selection = selectCvBatch(e.target.files, 20, uploadOrigin === 'sourcing' ? SOURCING_CV_VALIDATION : undefined);
                        setUploadFiles(selection.files); setUploadSourcingPreviews([]);
                        if (selection.error) { alert(selection.error); e.target.value = ''; }
                      }}
                    />
                  </label>
                  {uploadFiles.length > 0 && (
                    <button
                      onClick={handleMassiveUpload}
                      disabled={uploadStatus === 'uploading' || (uploadOrigin === 'authorized_application' && !uploadAuthorizationConfirmed)}
                      className="w-full py-3 bg-[#b91c1c] text-white font-bold rounded-sm hover:bg-red-800 disabled:opacity-50 transition-colors"
                    >
                      {uploadStatus === 'uploading' ? 'Procesando con IA, por favor espera...' : uploadStatus === 'success' ? 'Carga completada' : uploadOrigin === 'sourcing' ? `Analizar y previsualizar ${uploadFiles.length} perfil(es)` : 'Crear postulaciones autorizadas'}
                    </button>
                  )}
                  {uploadSourcingPreviews.length > 0 && <div className="mt-4"><SourcingPreviewList items={uploadSourcingPreviews} confirmingToken={confirmingSourcingToken} onConfirm={confirmManualSourcing} /></div>}
                  {uploadResults.length > 0 && <div className="mt-4 space-y-2" aria-live="polite">
                    {uploadResults.map((item: any) => <div key={`${item.filename}-${item.status}`} className={`rounded border p-3 text-sm ${item.status === 'error' ? 'border-red-200 bg-red-50 text-red-800' : item.status === 'already_linked' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
                      <strong>{item.filename}</strong>
                      <span className="ml-2">{item.status === 'created' ? 'Candidato y postulación creados.' : item.status === 'updated' ? 'Perfil existente actualizado; el CV anterior quedó en el historial.' : item.status === 'reused' ? 'Perfil existente reutilizado; se agregó esta vacante sin duplicar el CV.' : item.status === 'already_linked' ? 'Este candidato ya estaba en la vacante; no se duplicó.' : item.detail || 'No fue posible procesarlo.'}</span>
                    </div>)}
                  </div>}
                  {uploadStatus === 'error' && <p role="alert" className="text-red-600 mt-3 text-sm text-center font-bold">{uploadError || 'Ocurrió un error al procesar algunos archivos.'}</p>}
                </div>
              )}

              {vacancyPeopleTab === 'applications' && (loadingMatches ? (
                 <p className="text-center py-10 text-gray-500"><InlineSpinner label="Cargando candidatos…" /></p>
              ) : (
                <div className="responsive-table-shell rounded-sm border border-gray-200 shadow-sm">
                  <table className="responsive-table min-w-[900px] border-collapse text-left">
                    <thead>
                      <tr className="bg-[#b91c1c] text-white text-sm">
                        <th className="p-4 font-semibold border-r border-[#a01616]">Candidato</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616]">Origen</th>
                        <th className="p-4 font-semibold text-center border-r border-[#a01616] w-1/4">% Match al cargo</th>
                        <th className="p-4 font-semibold text-center w-[300px]">Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMatches.length === 0 ? (
                        <tr className="bg-white">
                          <td colSpan={4} className="p-8 text-center text-gray-500 font-medium">
                            Aún no hay candidatos para esta vacante o en este filtro.
                          </td>
                        </tr>
                      ) : (
                        filteredMatches.map((match, idx) => {
                          const isUnavailable = match.evaluation_status === 'unavailable';
                          const isPending = !isUnavailable && (match.pending_evaluation === true
                            || match.similarity_score === null
                            || match.similarity_score === undefined);
                          const matchScore = isPending ? null : Number(((match.similarity_score ?? 0) * 100).toFixed(2));
                          const displayedScore = matchScore ?? 0;
                          const isHigh = match.suggested_category === 'apto' || (matchScore !== null && matchScore >= 75);
                          const isReview = match.suggested_category === 'en_revision' || (matchScore !== null && matchScore >= 60 && !isHigh);
                          const scoreColor = isHigh ? 'text-emerald-700' : isReview ? 'text-amber-700' : 'text-red-700';
                          const barColor = isHigh ? 'bg-emerald-600' : isReview ? 'bg-amber-500' : 'bg-red-600';
                          const categoryLabel = isHigh ? 'Alta afinidad' : isReview ? 'En revisión' : 'Afinidad limitada';
                          const initials = match.full_name ? match.full_name.substring(0, 2).toUpperCase() : 'CA';
                          return (
                            <tr key={match.candidate_id || idx} className={`border-b border-gray-200 text-sm ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                              <td className="p-4 font-bold text-gray-800 flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-[#b91c1c] text-white flex items-center justify-center text-xs shadow-inner">
                                  {initials}
                                </div>
                                {match.full_name || `Candidato #${match.candidate_id}`}
                              </td>
                              <td className="p-4 text-center text-gray-600 font-medium">{match.source || 'Sin origen'}</td>
                              <td className="p-4 text-center">
                                {isUnavailable ? (
                                  <div className="mx-auto w-44 lg:w-52 text-red-700 text-center flex flex-col justify-center h-full">
                                    <span className="text-xs font-bold leading-tight block">Scoring no disponible</span>
                                    <span className="text-[10px] text-red-600/80 mt-0.5 block leading-tight">No fue posible realizar la evaluación de afinidad en este momento.</span>
                                  </div>
                                ) : isPending ? (
                                  <div className="flex items-center justify-center gap-2 text-amber-600 font-medium text-xs">
                                    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                                    </svg>
                                    Calculando IA...
                                  </div>
                                ) : (
                                  <div className="mx-auto w-44 lg:w-52">
                                    <div className="flex items-center justify-center gap-3">
                                      <div className="h-3 w-full bg-gray-200 rounded-sm overflow-hidden border border-gray-300">
                                        <div className={`h-full transition-all duration-500 ${barColor}`} style={{ width: `${displayedScore}%` }}></div>
                                      </div>
                                      <span className={`font-bold min-w-14 text-right ${scoreColor}`}>{displayedScore.toLocaleString('es-CL', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%</span>
                                    </div>
                                    <span className={`mt-1 block text-[11px] font-semibold ${scoreColor}`}>{categoryLabel}</span>
                                  </div>
                                )}
                              </td>

                              <td className="p-4 text-center">
                                <div className="flex flex-wrap items-center justify-center gap-2">
                                  <button onClick={() => setSelectedCandidate(match)} className="bg-[#b91c1c] text-white text-xs px-4 py-2 font-bold hover:bg-red-800 transition-colors rounded-sm shadow-sm">Ver</button>
                                  {match.outcome === 'descartado' ? (
                                    <>
                                      <div className="flex items-center gap-1 text-xs px-3 py-1 font-bold text-gray-500 bg-gray-100 rounded-full cursor-not-allowed">
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                        Descartado
                                      </div>
                                      <button onClick={() => handleUpdateStatus(match.candidate_id, 'advanced')} className="bg-[#f59e0b] text-black text-xs px-4 py-2 font-bold hover:bg-amber-400 transition-colors rounded-sm shadow-sm">Recuperar</button>
                                    </>
                                  ) : match.outcome === 'contratado' ? (
                                    <div className="flex items-center gap-1 text-xs px-3 py-1 font-bold text-green-700 bg-green-100 rounded-full">
                                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                      Contratado
                                    </div>
                                  ) : match.outcome === 'reservado' ? (
                                    <div className="flex items-center gap-1 text-xs px-3 py-1 font-bold text-blue-700 bg-blue-100 rounded-full">
                                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                      Reservado
                                    </div>
                                  ) : (
                                    <>
                                      <button onClick={() => handleUpdateStatus(match.candidate_id, 'rejected')} className="bg-white text-[#b91c1c] border border-[#b91c1c] text-xs px-4 py-2 font-bold hover:bg-red-50 transition-colors rounded-sm shadow-sm">Descartar</button>
                                      <button onClick={() => handleUpdateStatus(match.candidate_id, 'reservar')} className="bg-[#1e40af] text-white text-xs px-4 py-2 font-bold hover:bg-blue-800 transition-colors rounded-sm shadow-sm">Reservar</button>
                                      <button onClick={() => handleUpdateStatus(match.candidate_id, 'advanced')} className="bg-[#f59e0b] text-black text-xs px-4 py-2 font-bold hover:bg-amber-400 transition-colors rounded-sm shadow-sm">Avanzar</button>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

          {currentTab === 'Empresas' && (
            <div className="rounded-sm border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
              <h2 className="text-xl font-bold text-[#b91c1c] mb-6">Empresas Clientes</h2>

              <div className="mb-8 flex flex-col gap-4 rounded-sm border border-gray-200 bg-gray-50 p-4 sm:p-6">
                <h3 className="font-bold text-[#b91c1c] mb-2">Registrar nueva empresa</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <input type="text" placeholder="Nombre de la empresa *" className="p-2 border rounded text-sm" value={newCompany.name} onChange={e => setNewCompany({ ...newCompany, name: e.target.value })} />
                  <input type="text" placeholder="Industria (ej. Finanzas)" className="p-2 border rounded text-sm" value={newCompany.industry} onChange={e => setNewCompany({ ...newCompany, industry: e.target.value })} />
                  <textarea placeholder="Descripción breve" className="p-2 border rounded text-sm md:col-span-2" value={newCompany.description} onChange={e => setNewCompany({ ...newCompany, description: e.target.value })} />
                </div>
                <div className="flex justify-end mt-2">
                  <button onClick={handleCreateCompany} className="px-6 py-2 bg-[#b91c1c] text-white font-bold text-sm hover:bg-red-800 transition-colors rounded-sm shadow-sm">
                    Guardar Empresa
                  </button>
                </div>
              </div>

              <div>
                <h3 className="font-bold text-gray-700 mb-4">Directorio de Empresas</h3>
                {companies.length === 0 ? (
                  <p className="text-gray-500 text-sm">No hay empresas registradas.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {companies.map(c => (
                      <div key={c.id} className="p-4 border border-gray-200 rounded-sm shadow-sm bg-white">
                        <h4 className="font-bold text-[#b91c1c] text-lg">{c.name}</h4>
                        <p className="text-sm text-gray-500 mt-1">{c.industry || 'Industria no especificada'}</p>
                        <p className="text-sm text-gray-700 mt-2 line-clamp-2">{c.description || 'Sin descripción'}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Candidate Modal */}
      {selectedCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-2 sm:p-4">
          <div className="modal-shell flex w-full max-w-2xl flex-col rounded-sm bg-white shadow-lg">
            <div className="flex items-start justify-between gap-3 border-b border-gray-200 p-4 sm:items-center sm:p-6">
              <h2 className="break-words text-lg font-bold text-[#b91c1c] sm:text-xl">Perfil de {selectedCandidate.full_name}</h2>
              <button onClick={() => setSelectedCandidate(null)} className="text-gray-400 hover:text-gray-600 font-bold">✕</button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 text-sm text-gray-700 sm:p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Porcentaje de Match</p>
                  {selectedCandidate.evaluation_status === 'unavailable' ? (
                    <div className="text-red-700 mt-1">
                      <p className="text-sm font-bold leading-tight">Scoring no disponible</p>
                      <p className="text-[11px] opacity-80 mt-0.5 max-w-xs leading-tight">No fue posible realizar la evaluación de afinidad en este momento.</p>
                    </div>
                  ) : (
                    <p className="text-xl font-bold text-green-700">{selectedCandidate.similarity_score !== undefined && selectedCandidate.similarity_score !== null ? Math.round(selectedCandidate.similarity_score * 100) : 0}%</p>
                  )}
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Años de Experiencia</p>
                  <p className="text-gray-900 font-medium">{selectedCandidate.years_of_experience || 'No especificada'}</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Formación y certificaciones</p>
                  <p className="text-gray-900 font-medium text-sm mt-1">{selectedCandidate.courses_and_diplomas || 'Estudios no especificados'}</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Pretensiones de Sueldo</p>
                  <p className="text-gray-900 font-medium">{selectedCandidate.salary_expectation || 'No especificadas'}</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Disponibilidad</p>
                  <p className="text-gray-900 font-medium">Inmediata</p> {/* Backend doesn't have availability yet */}
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Email de Contacto</p>
                  <p className="text-gray-900 font-medium break-all">{selectedCandidate.email || 'No especificado'}</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Teléfono</p>
                  <p className="text-gray-900 font-medium">{selectedCandidate.phone || 'No especificado'}</p>
                </div>
              </div>

              <div className="mb-6 bg-gray-50 p-4 rounded-sm border border-gray-100">
                <p className="font-bold text-[#b91c1c] mb-2 text-sm uppercase tracking-wider">Stack Tecnológico</p>
                <p className="text-gray-800 font-medium leading-relaxed">{selectedCandidate.tech_stack || 'No especificado'}</p>
              </div>

              <div className="mb-6">
                <p className="font-bold text-gray-500 mb-2 text-sm uppercase tracking-wider">Resumen Profesional</p>
                <p className="whitespace-pre-wrap text-gray-700 leading-relaxed bg-gray-50 p-4 rounded-sm border border-gray-100">{selectedCandidate.career_summary || 'Información extraída no disponible'}</p>
              </div>

              {selectedCandidate.resume_url && selectedCandidate.resume_url !== 'pending' && selectedCandidate.resume_url !== 'linkedin_import' && (
                <div className="flex justify-center mt-2 mb-4 border-t border-gray-200 pt-6">
                  <a
                    href={`http://localhost:8000/static/cvs/${selectedCandidate.resume_url.split('/').pop()}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-[#2563eb] text-white font-bold px-8 py-3 rounded-sm shadow-sm hover:bg-blue-700 transition-colors flex items-center gap-2"
                  >
                    📄 Descargar CV Original
                  </a>
                </div>
              )}


              {selectedCandidate.extracted_text && (
                <div>
                  <p className="font-bold text-gray-500 mb-2">Texto Original Extraído del CV</p>
                  <div className="bg-gray-50 p-4 rounded-sm text-xs font-mono text-gray-600 max-h-48 overflow-y-auto border border-gray-200">
                    {selectedCandidate.extracted_text}
                  </div>
                </div>
              )}
            </div>
            <div className="flex flex-col-reverse justify-end gap-3 border-t border-gray-200 bg-gray-50 p-4 sm:flex-row sm:p-6">
              <button onClick={() => setSelectedCandidate(null)} className="w-full rounded-sm border border-gray-300 bg-white px-6 py-2 font-bold text-gray-700 hover:bg-gray-100 sm:w-auto">Cerrar</button>
              {selectedCandidate.outcome === 'contratado' ? (
                <span className="px-6 py-2 bg-green-100 text-green-700 font-bold rounded-sm flex items-center gap-2">✓ Finalista / Contratado</span>
              ) : selectedCandidate.outcome === 'reservado' ? (
                <span className="px-6 py-2 bg-blue-100 text-blue-700 font-bold rounded-sm flex items-center gap-2">● Reservado</span>
              ) : (
                <button onClick={() => { handleUpdateStatus(selectedCandidate.candidate_id, 'advanced'); setSelectedCandidate(null); }} className="w-full rounded-sm bg-[#f59e0b] px-6 py-2 font-bold text-black shadow-sm hover:bg-amber-400 sm:w-auto">Avanzar Candidato</button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Close Offer Modal */}
      {isClosingOffer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-2 sm:p-4">
          <div className="modal-shell flex w-full max-w-md flex-col overflow-y-auto rounded-sm bg-white shadow-lg">
            <div className="border-b border-gray-200 p-4 sm:p-6">
              <h2 className="text-xl font-bold text-[#b91c1c]">Cerrar proceso</h2>
              <p className="text-sm text-gray-500 mt-2">La vacante pasará a inactivas y podrás reabrirla más adelante. El cierre definitivo se realiza por separado.</p>
            </div>
            <div className="flex-1 p-4 text-sm text-gray-700 sm:p-6">
              <label className="font-bold text-gray-700 block mb-2">Finalista (opcional)</label>
              <select
                className="w-full p-3 border border-gray-300 rounded-sm bg-gray-50"
                value={finalistId || ''}
                onChange={(e) => setFinalistId(e.target.value ? parseInt(e.target.value) : null)}
              >
                <option value="">Sin finalista seleccionado</option>
                {matches.map(m => (
                  <option key={m.candidate_id} value={m.candidate_id}>{m.full_name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col-reverse justify-end gap-3 border-t border-gray-200 bg-gray-50 p-4 sm:flex-row sm:p-6">
              <button onClick={() => { setIsClosingOffer(false); setFinalistId(null); }} className="w-full rounded-sm border border-gray-300 bg-white px-6 py-2 font-bold text-gray-700 hover:bg-gray-100 sm:w-auto">Cancelar</button>
              <button disabled={offerLifecycleBusy === selectedOffer?.id} onClick={handleCloseOffer} className="w-full rounded-sm bg-red-900 px-6 py-2 font-bold text-white shadow-sm hover:bg-red-700 disabled:opacity-50 sm:w-auto">Cerrar proceso</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SourcingPanel({ offers, fixedOfferId }: { offers: any[]; fixedOfferId?: number }) {
  const [offerId, setOfferId] = useState<number | undefined>(fixedOfferId);
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState('');
  const [source, setSource] = useState('linkedin');
  const [sourceUrl, setSourceUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [previewResults, setPreviewResults] = useState<SourcingPreviewItem[]>([]);
  const [confirmingPreviewToken, setConfirmingPreviewToken] = useState<string | null>(null);
  const [prospects, setProspects] = useState<any[]>([]);
  const [counters, setCounters] = useState<Record<string, number>>({});
  const [invitationLinks, setInvitationLinks] = useState<Record<number, string>>({});
  const [externalProspect, setExternalProspect] = useState<any>(null);
  const [externalFile, setExternalFile] = useState<File | null>(null);
  const [externalFileError, setExternalFileError] = useState('');
  const [externalConverting, setExternalConverting] = useState(false);
  const [externalForm, setExternalForm] = useState({ full_name: '', email: '', phone: '', channel: 'correo', authorization_at: new Date().toISOString().slice(0, 16), notes: '', confirmed: false, consent: false });
  const [externalSubmitError, setExternalSubmitError] = useState('');
  const [contactProspect, setContactProspect] = useState<any>(null);
  const [contactForm, setContactForm] = useState({ channel: 'correo', value: '', notes: '' });
  const [contactSending, setContactSending] = useState(false);
  const [contactError, setContactError] = useState('');
  const [inviteProspect, setInviteProspect] = useState<any>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteResult, setInviteResult] = useState<any>(null);
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [status, setStatus] = useState<'idle'|'loading'>('idle');
  const [message, setMessage] = useState('');

  const loadProspects = useCallback(async (targetOfferId = offerId) => {
    if (!targetOfferId) { setProspects([]); return; }
    try { const data = await apiClient.getSourcingProspects(targetOfferId); setProspects(data.prospects || []); setCounters(data.counters || {}); }
    catch (err: any) { setMessage(err.message); }
  }, [offerId]);
  useEffect(() => { if (fixedOfferId) setOfferId(fixedOfferId); }, [fixedOfferId]);
  useEffect(() => { loadProspects(offerId); }, [offerId, loadProspects]);

  const analyze = async () => {
    if (!files.length || !offerId) return;
    if (files.length > 1 && sourceUrl.trim()) {
      setFileError('En una carga múltiple, cada URL debe venir dentro del documento correspondiente. Deja el campo URL vacío.');
      return;
    }
    const invalidFile = files.map(file => ({ file, error: validateCvFile(file, SOURCING_CV_VALIDATION) })).find(result => result.error);
    if (invalidFile) {
      setFiles([]);
      setFileError(`${invalidFile.file.name}: ${invalidFile.error}`);
      return;
    }
    setStatus('loading'); setMessage(''); setPreviewResults([]); setFileError('');
    try {
      const response = await apiClient.previewSourcingProspects(files, source, offerId, sourceUrl || undefined, notes || undefined);
      const results: SourcingPreviewItem[] = response.results || [];
      setPreviewResults(results);
      setMessage(`${response.ready || 0} perfil(es) listos para confirmar${response.errors ? ` y ${response.errors} con error` : ''}.`);
    }
    catch (err: any) { setMessage(err.message); }
    finally { setStatus('idle'); }
  };
  const confirm = async (item: SourcingPreviewItem) => {
    if (!item.preview_token) return;
    setConfirmingPreviewToken(item.preview_token); setMessage('');
    try {
      await apiClient.confirmSourcingProspect(item.preview_token);
      setPreviewResults(current => current.map(result => result.preview_token === item.preview_token ? { ...result, status: 'confirmed', detail: undefined } : result));
      setMessage('Prospecto confirmado. No se creó una postulación.');
      await loadProspects();
    }
    catch (err: any) {
      setPreviewResults(current => current.map(result => result.preview_token === item.preview_token ? { ...result, status: 'confirmation_error', detail: err.message || 'No fue posible confirmar el prospecto.' } : result));
    }
    finally { setConfirmingPreviewToken(null); }
  };
  const openContact = (prospect: any) => {
    const suggestedEmail = prospect.suggested_email || prospect.candidate?.contact_email || '';
    const suggestedPhone = prospect.suggested_phone || prospect.candidate?.phone || '';
    const channel = suggestedEmail ? 'correo' : suggestedPhone ? 'telefono' : 'correo';
    setContactProspect(prospect);
    setContactError('');
    setContactForm({ channel, value: channel === 'correo' ? suggestedEmail : suggestedPhone, notes: '' });
  };
  const setContactChannel = (channel: 'correo'|'telefono') => {
    if (!contactProspect) return;
    setContactForm(current => ({
      ...current,
      channel,
      value: channel === 'correo'
        ? (contactProspect.suggested_email || contactProspect.candidate?.contact_email || '')
        : (contactProspect.suggested_phone || contactProspect.candidate?.phone || ''),
    }));
    setContactError('');
  };
  const registerContact = async () => {
    if (!contactProspect || !contactForm.value.trim()) return;
    setContactSending(true);
    setContactError('');
    try {
      const result = await apiClient.recordSourcingContact(contactProspect.id, contactForm.channel, contactForm.value, contactForm.notes || undefined, contactMessageText);
      if (result.delivery?.status === 'local_preview') {
        setMessage('El correo quedó en la vista local de desarrollo y no se envió a una bandeja real.');
      } else if (result.delivery?.status === 'accepted') {
        setMessage(`Correo aceptado por ${result.delivery.provider} para ${result.delivery.recipient}.`);
      } else {
        setMessage(`Contacto por ${contactForm.channel} registrado para ${contactProspect.candidate?.full_name}.`);
      }
      setContactProspect(null);
      await loadProspects();
    } catch (err: any) {
      setContactError(err.message);
    } finally {
      setContactSending(false);
    }
  };
  const respond = async (prospect: any, response: string) => {
    try { await apiClient.recordSourcingResponse(prospect.id, response); await loadProspects(); }
    catch (err: any) { setMessage(err.message); }
  };
  const openInvite = (prospect: any) => {
    setInviteProspect(prospect);
    setInviteEmail(prospect.suggested_email || prospect.candidate?.contact_email || '');
    setInviteResult(null);
    setInviteError('');
  };
  const invite = async () => {
    if (!inviteProspect) return;
    setInviteSending(true);
    setInviteError('');
    try {
      const result = await apiClient.inviteSourcingProspect(inviteProspect.id, inviteEmail || undefined);
      setInvitationLinks(current => ({ ...current, [inviteProspect.id]: result.invitation_url }));
      setInviteResult(result);
      setMessage(result.delivery_warning || (result.email_delivered ? `Invitación enviada a ${result.recipient_email}.` : 'Enlace privado generado para compartir.'));
      await loadProspects();
    } catch (err: any) {
      setInviteError(err.message);
    } finally {
      setInviteSending(false);
    }
  };
  const openExternalAcceptance = (prospect: any) => {
    setExternalProspect(prospect); setExternalFile(null);
    setExternalFileError('');
    setExternalSubmitError('');
    setExternalForm({ full_name: prospect.candidate?.full_name || '', email: prospect.suggested_email || prospect.candidate?.contact_email || '', phone: prospect.suggested_phone || prospect.candidate?.phone || '', channel: 'correo', authorization_at: new Date().toISOString().slice(0, 16), notes: '', confirmed: false, consent: false });
  };
  const convertExternal = async () => {
    if (!externalProspect || !externalFile) return;
    setExternalSubmitError('');
    const validationError = validateCvFile(externalFile);
    if (validationError) {
      setExternalFile(null);
      setExternalFileError(validationError);
      return;
    }
    const data = new FormData();
    data.append('full_name', externalForm.full_name); data.append('email', externalForm.email); data.append('phone', externalForm.phone); data.append('authorization_confirmed', String(externalForm.confirmed)); data.append('consent', String(externalForm.consent)); data.append('authorization_channel', externalForm.channel); data.append('authorization_at', new Date(externalForm.authorization_at).toISOString()); data.append('authorization_notes', externalForm.notes); data.append('file', externalFile);
    setExternalConverting(true);
    try {
      const result = await apiClient.convertSourcingProspect(externalProspect.id, data);
      setMessage(`Postulación #${result.application_id} creada con autorización registrada.`);
      setExternalProspect(null);
      await loadProspects();
    }
    catch (err: any) { setExternalSubmitError(err.message); }
    finally { setExternalConverting(false); }
  };

  const statusLabels: Record<string, string> = { identificado: 'Identificados', contactado: 'Contactados', interesado: 'Interesados', invitado: 'Invitados', no_interesado: 'No interesados', sin_respuesta: 'Sin respuesta', convertido: 'Convertidos' };
  const currentOffer = offers.find(offer => offer.id === offerId);
  const contactMessageText = contactProspect
    ? `Hola ${contactProspect.candidate?.full_name || ''},\n\nEstuvimos revisando tu perfil profesional y encontramos una oportunidad como ${currentOffer?.title || 'parte de nuestro equipo'} que podría tener una muy buena afinidad con tu experiencia.\n\n¿Te interesa que te enviemos los detalles para participar en el proceso?\n\nSaludos,\nEquipo de Selección`
    : '';
  const contactHref = contactForm.channel === 'correo'
    ? `mailto:${encodeURIComponent(contactForm.value)}?subject=${encodeURIComponent(`Oportunidad profesional: ${currentOffer?.title || 'proceso de selección'}`)}&body=${encodeURIComponent(contactMessageText)}`
    : `tel:${contactForm.value.replace(/\s/g, '')}`;
  return <div className="mx-auto w-full min-w-0 max-w-6xl space-y-6">
    {status !== 'idle' && <ProcessingOverlay
      title={`Analizando ${files.length} perfil(es)`}
      description="Gemini extrae la experiencia de cada documento y calculamos individualmente su afinidad con la vacante."
    />}
    {externalConverting && <ProcessingOverlay title="Procesando el CV" description="Actualizamos el perfil y creamos la postulación autorizada." />}
    {!fixedOfferId && <div><h1 className="text-2xl font-bold text-[#b91c1c] sm:text-3xl">Sourcing de talento</h1><p className="mt-2 text-sm leading-6 text-gray-500 sm:text-base">Descubre perfiles externos, valida su afinidad y gestiona un contacto responsable antes de invitarlos.</p></div>}
    <div className="grid gap-3 rounded-sm border bg-gray-50 p-4 sm:p-5 md:grid-cols-2">
      {!fixedOfferId && <select className="p-3 border bg-white" value={offerId || ''} onChange={e => setOfferId(e.target.value ? Number(e.target.value) : undefined)}><option value="">Selecciona una vacante</option>{offers.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}</select>}
      <select className="p-3 border bg-white" value={source} onChange={e => setSource(e.target.value)}><option value="linkedin">LinkedIn</option><option value="computrabajo">Computrabajo</option><option value="laborum">Laborum</option><option value="referido">Referido</option><option value="otro">Otro</option></select>
      <input className="p-3 border bg-white" value={sourceUrl} onChange={e => { setSourceUrl(e.target.value); setFileError(''); }} placeholder="URL de origen (solo para una carga individual)" />
      <input className="p-3 border bg-white" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notas iniciales (opcional)" />
      <label className="cursor-pointer break-all border-2 border-dashed bg-white p-4 text-sm text-gray-600 md:col-span-2">
        <span>{files.length ? `${files.length} perfil(es) seleccionado(s)` : 'Seleccionar hasta 20 perfiles externos'}</span>
        <span className="mt-1 block text-xs text-gray-500">PDF o Word (.doc o .docx), máximo {MAX_CV_SIZE_LABEL} cada uno. Validaremos individualmente que contengan información profesional propia de un CV.</span>
        <input className="hidden" type="file" multiple accept={SOURCING_CV_ACCEPT} onChange={event => {
          const selection = selectCvBatch(event.target.files, 20, SOURCING_CV_VALIDATION);
          setFiles(selection.files);
          setFileError(selection.error);
          setPreviewResults([]);
          if (selection.error) event.target.value = '';
        }} />
      </label>
      {fileError && <p role="alert" className="text-sm font-medium text-red-700 md:col-span-2">{fileError}</p>}
      <button disabled={!files.length || !offerId || status !== 'idle'} onClick={analyze} className="md:col-span-2 py-3 bg-[#b91c1c] text-white font-bold disabled:opacity-50">{status === 'loading' ? <InlineSpinner label="Extrayendo con Gemini…" /> : `Analizar ${files.length || ''} perfil(es) y mostrar vistas previas`}</button>
    </div>
    {message && <div className="p-3 border bg-white text-sm break-all">{message}</div>}
    <SourcingPreviewList items={previewResults} confirmingToken={confirmingPreviewToken} onConfirm={confirm} />
    {offerId && <>
      <div className="grid grid-cols-2 md:grid-cols-7 gap-2">{Object.entries(statusLabels).map(([key, label]) => <div key={key} className="bg-white border p-3 text-center"><strong className="block text-xl text-[#b91c1c]">{counters[key] || 0}</strong><span className="text-xs text-gray-500">{label}</span></div>)}</div>
      <div className="responsive-table-shell border bg-white"><table className="responsive-table min-w-[820px] text-sm"><thead><tr className="bg-gray-800 text-left text-white"><th className="p-3">Perfil</th><th className="p-3">Origen</th><th className="p-3">Afinidad</th><th className="p-3">Estado</th><th className="p-3">Acciones</th></tr></thead><tbody>
        {prospects.length === 0 ? <tr><td colSpan={5} className="p-8 text-center text-gray-500">Aún no hay prospectos para esta vacante.</td></tr> : prospects.map(prospect => <tr key={prospect.id} className="border-t"><td className="p-3"><b>{prospect.candidate?.full_name}</b><div className="text-xs text-gray-500">{prospect.candidate?.professional_headline}</div>{prospect.suggested_email && <div className="mt-1 flex items-center gap-1 text-xs text-emerald-700"><Mail size={12} /> {prospect.suggested_email}</div>}{prospect.suggested_phone && <div className="mt-1 flex items-center gap-1 text-xs text-slate-500"><Phone size={12} /> {prospect.suggested_phone}</div>}</td><td className="p-3 capitalize">{prospect.source}{prospect.source_url && <a className="block text-xs text-blue-700 underline" href={prospect.source_url} target="_blank" rel="noreferrer">Abrir perfil original</a>}</td><td className="p-3 font-bold">{prospect.semantic_similarity}%<div className="text-xs text-gray-500 font-normal max-w-xs">{prospect.match_explanation}</div></td><td className="p-3"><span className="px-2 py-1 bg-gray-100 rounded-full">{statusLabels[prospect.status] || prospect.status}</span>{prospect.contacted_at && <div className="text-xs text-gray-500 mt-1">Último contacto: {new Date(prospect.contacted_at).toLocaleDateString()}</div>}</td><td className="p-3 space-x-2">
          {['identificado','contactado','sin_respuesta'].includes(prospect.status) && <button onClick={() => openContact(prospect)} className="text-blue-700 underline">Contactar</button>}
          {prospect.status === 'contactado' && <><button onClick={() => respond(prospect, 'interesado')} className="text-green-700 underline">Interesado</button><button onClick={() => respond(prospect, 'no_interesado')} className="text-red-700 underline">No interesado</button><button onClick={() => respond(prospect, 'sin_respuesta')} className="text-gray-600 underline">Sin respuesta</button></>}
          {prospect.status === 'interesado' && <><button onClick={() => openInvite(prospect)} className="text-[#b91c1c] font-bold underline">Invitar</button><button onClick={() => openExternalAcceptance(prospect)} className="text-blue-700 underline">Registrar aceptación externa</button></>}
          {prospect.status === 'invitado' && <button onClick={() => openInvite(prospect)} className="text-[#b91c1c] underline">Reenviar / renovar enlace</button>}
          {invitationLinks[prospect.id] && <button onClick={() => navigator.clipboard.writeText(invitationLinks[prospect.id])} className="text-blue-700 underline">Copiar enlace</button>}
          {prospect.status === 'convertido' && <span className="text-green-700 font-bold">Postulación #{prospect.application_id || 'Creada'}</span>}
        </td></tr>)}
      </tbody></table></div>
    </>}
    {contactProspect && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-2 sm:p-4">
      <div className="modal-shell w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b p-4 sm:p-6">
          <div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wider text-red-700">Primer contacto</p><h3 className="mt-1 break-words text-xl font-bold text-slate-900 sm:text-2xl">Contactar a {contactProspect.candidate?.full_name}</h3><p className="mt-1 text-sm text-slate-500">Elige un canal. Recomendamos correo cuando está disponible.</p></div>
          <button aria-label="Cerrar" onClick={() => setContactProspect(null)} className="rounded-full p-2 text-slate-500 hover:bg-slate-100"><X size={20} /></button>
        </div>
        <div className="space-y-5 p-4 sm:p-6">
          {contactError && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{contactError}</div>}
          <div className="grid gap-3 sm:grid-cols-2">
            <button onClick={() => setContactChannel('correo')} className={`rounded-xl border-2 p-4 text-left transition ${contactForm.channel === 'correo' ? 'border-red-700 bg-red-50' : 'border-slate-200 hover:border-slate-300'}`}>
              <span className="flex items-center gap-2 font-bold text-slate-900"><Mail size={18} /> Correo <small className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] text-emerald-700">RECOMENDADO</small></span>
              <span className="mt-1 block truncate text-sm text-slate-600">{contactProspect.suggested_email || 'Ingresa un correo'}</span>
            </button>
            <button onClick={() => setContactChannel('telefono')} className={`rounded-xl border-2 p-4 text-left transition ${contactForm.channel === 'telefono' ? 'border-red-700 bg-red-50' : 'border-slate-200 hover:border-slate-300'}`}>
              <span className="flex items-center gap-2 font-bold text-slate-900"><Phone size={18} /> Teléfono</span>
              <span className="mt-1 block truncate text-sm text-slate-600">{contactProspect.suggested_phone || 'Ingresa un teléfono'}</span>
            </button>
          </div>
          <label className="block text-sm font-semibold text-slate-700">{contactForm.channel === 'correo' ? 'Correo de contacto' : 'Teléfono de contacto'}
            <input type={contactForm.channel === 'correo' ? 'email' : 'tel'} value={contactForm.value} onChange={event => setContactForm(current => ({ ...current, value: event.target.value }))} className="mt-1 w-full rounded-xl border border-slate-300 p-3 outline-none focus:border-red-700 focus:ring-2 focus:ring-red-100" placeholder={contactForm.channel === 'correo' ? 'nombre@correo.com' : '+56 9 1234 5678'} />
          </label>
          {contactForm.channel === 'correo' && <div>
            <div className="mb-2 flex items-center justify-between"><label className="text-sm font-semibold text-slate-700">Mensaje que se enviará al candidato</label></div>
            <textarea readOnly value={contactMessageText} rows={8} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700" />
            <p className="mt-2 text-xs text-slate-500">El enlace privado de postulación se generará automáticamente cuando registres que la persona está interesada.</p>
          </div>}
          <label className="block text-sm font-semibold text-slate-700">Nota interna (opcional)
            <textarea value={contactForm.notes} onChange={event => setContactForm(current => ({ ...current, notes: event.target.value }))} rows={2} className="mt-1 w-full rounded-xl border border-slate-300 p-3" placeholder="Ej.: correo enviado desde Gmail" />
          </label>
        </div>
        <div className="flex flex-col-reverse gap-3 border-t bg-slate-50 p-5 sm:flex-row sm:justify-end">
          <button onClick={() => setContactProspect(null)} className="rounded-xl border border-slate-300 bg-white px-5 py-3 font-semibold text-slate-700">Cancelar</button>
          {contactForm.channel === 'telefono' && <a href={contactForm.value ? contactHref : undefined} className={`inline-flex items-center justify-center gap-2 rounded-xl border border-blue-700 bg-white px-5 py-3 font-semibold text-blue-700 ${!contactForm.value ? 'pointer-events-none opacity-40' : ''}`}><ExternalLink size={17} /> Llamar</a>}
          <button disabled={!contactForm.value.trim() || contactSending} onClick={registerContact} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-700 px-5 py-3 font-bold text-white hover:bg-red-800 disabled:opacity-40"><Send size={17} /> {contactSending ? 'Enviando…' : contactForm.channel === 'correo' ? 'Enviar correo' : 'Registrar como contactado'}</button>
        </div>
      </div>
    </div>}
    {inviteProspect && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-2 sm:p-4">
      <div className="modal-shell w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b p-4 sm:p-6">
          <div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wider text-red-700">Invitación a postular</p><h3 className="mt-1 break-words text-xl font-bold text-slate-900 sm:text-2xl">{inviteProspect.candidate?.full_name}</h3><p className="mt-1 text-sm text-slate-500">Se creará un enlace privado. Esto aún no crea una postulación.</p></div>
          <button aria-label="Cerrar" onClick={() => setInviteProspect(null)} className="rounded-full p-2 text-slate-500 hover:bg-slate-100"><X size={20} /></button>
        </div>
        {!inviteResult ? <>
          {inviteError && <div className="mx-6 mt-6 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">{inviteError}</div>}
          <div className="space-y-5 p-4 sm:p-6">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="flex items-center gap-2 text-sm font-bold text-emerald-800"><Mail size={17} /> Correo recomendado</p>
              <p className="mt-1 text-xs text-emerald-700">Usamos el correo extraído del perfil como sugerencia. Puedes corregirlo antes de enviar.</p>
            </div>
            <label className="block text-sm font-semibold text-slate-700">Destinatario
              <input type="email" value={inviteEmail} onChange={event => setInviteEmail(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-300 p-3 outline-none focus:border-red-700 focus:ring-2 focus:ring-red-100" placeholder="nombre@correo.com" />
            </label>
            <div className="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
              El correo contará que vimos su perfil, explicará por qué la oportunidad puede ser adecuada e incluirá un botón directo para revisar la oferta y postular.
            </div>
          </div>
          <div className="flex flex-col-reverse gap-3 border-t bg-slate-50 p-4 sm:flex-row sm:justify-end sm:p-5"><button onClick={() => setInviteProspect(null)} className="rounded-xl border border-slate-300 bg-white px-5 py-3 font-semibold text-slate-700">Cancelar</button><button disabled={inviteSending} onClick={invite} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-700 px-5 py-3 font-bold text-white hover:bg-red-800 disabled:opacity-50"><Send size={17} /> {inviteSending ? 'Preparando…' : inviteEmail ? 'Enviar invitación' : 'Generar enlace'}</button></div>
        </> : <div className="space-y-5 p-4 sm:p-6">
          <div className={`rounded-xl border p-4 ${inviteResult.email_delivered ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}><p className="font-bold">{inviteResult.email_delivered ? `Invitación enviada a ${inviteResult.recipient_email}` : 'Enlace generado para compartir'}</p>{inviteResult.delivery_warning && <p className="mt-1 text-sm">{inviteResult.delivery_warning}</p>}</div>
          <div><div className="mb-2 flex items-center justify-between"><label className="text-sm font-semibold text-slate-700">Mensaje de invitación</label><button onClick={() => navigator.clipboard.writeText(inviteResult.suggested_message)} className="flex items-center gap-1 text-xs font-semibold text-blue-700"><Copy size={14} /> Copiar mensaje</button></div><textarea readOnly rows={10} value={inviteResult.suggested_message} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700" /></div>
          <div className="flex flex-wrap justify-end gap-3"><button onClick={() => navigator.clipboard.writeText(inviteResult.invitation_url)} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 font-semibold text-slate-700"><Copy size={16} /> Copiar enlace</button><a href={inviteResult.invitation_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 font-semibold text-white"><ExternalLink size={16} /> Abrir postulación</a><button onClick={() => setInviteProspect(null)} className="rounded-xl bg-red-700 px-5 py-2 font-bold text-white">Listo</button></div>
        </div>}
      </div>
    </div>}
    {externalProspect && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"><div className="modal-shell w-full max-w-xl space-y-3 overflow-y-auto bg-white p-4 sm:p-6"><h3 className="text-xl font-bold text-[#b91c1c]">Registrar aceptación externa</h3><p className="text-sm text-gray-600">Esto creará la postulación sólo si adjuntas un CV actualizado y confirmas la autorización.</p>
      {externalSubmitError && <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">{externalSubmitError}</div>}
      <input className="w-full border p-3" value={externalForm.full_name} onChange={e => setExternalForm(v => ({...v, full_name: e.target.value}))} placeholder="Nombre completo" /><input required type="email" className="w-full border p-3" value={externalForm.email} onChange={e => setExternalForm(v => ({...v, email: e.target.value}))} placeholder="Correo del candidato" /><input className="w-full border p-3" value={externalForm.phone} onChange={e => setExternalForm(v => ({...v, phone: e.target.value}))} placeholder="Teléfono" /><div className="grid gap-3 sm:grid-cols-2"><select className="border p-3" value={externalForm.channel} onChange={e => setExternalForm(v => ({...v, channel: e.target.value}))}><option value="correo">Correo</option><option value="linkedin">LinkedIn</option><option value="telefono">Teléfono</option><option value="otro">Otro</option></select><input type="datetime-local" className="border p-3" value={externalForm.authorization_at} onChange={e => setExternalForm(v => ({...v, authorization_at: e.target.value}))} /></div><textarea className="w-full border p-3" value={externalForm.notes} onChange={e => setExternalForm(v => ({...v, notes: e.target.value}))} placeholder="Nota o referencia de respaldo (obligatoria)" /><label className="block border p-3 text-sm">CV actualizado<span className="mt-1 block text-xs text-gray-500">Un archivo PDF o Word (.doc o .docx), máximo {MAX_CV_SIZE_LABEL}. El servidor verificará que sea un CV válido.</span><input className="mt-2 block max-w-full text-xs sm:text-sm" type="file" accept={CV_ACCEPT} onChange={event => { const selection = selectSingleCv(event.target.files); setExternalFile(selection.file); setExternalFileError(selection.error); if (selection.error) event.target.value = ''; }} /></label>{externalFileError && <p role="alert" className="text-sm font-medium text-red-700">{externalFileError}</p>}<label className="flex gap-2 text-sm"><input type="checkbox" checked={externalForm.confirmed} onChange={e => setExternalForm(v => ({...v, confirmed: e.target.checked}))} />Confirmo que recibí aceptación verificable por el canal indicado.</label><label className="flex gap-2 text-sm"><input type="checkbox" checked={externalForm.consent} onChange={e => setExternalForm(v => ({...v, consent: e.target.checked}))} />Confirmo el consentimiento para tratar estos datos en esta postulación.</label><div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button disabled={externalConverting} onClick={() => setExternalProspect(null)} className="border px-4 py-2">Cancelar</button><button disabled={externalConverting || !externalFile || !externalForm.email || !externalForm.notes.trim() || !externalForm.confirmed || !externalForm.consent} onClick={convertExternal} className="bg-[#b91c1c] px-4 py-2 font-bold text-white disabled:opacity-50">{externalConverting ? <InlineSpinner label="Procesando…" /> : 'Crear postulación'}</button></div>
    </div></div>}
  </div>;
}

function TalentBank() {
  const logout = useAuthStore(state => state.logout);
  const [candidates, setCandidates] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [bankError, setBankError] = React.useState('');
  const [bankNeedsLogin, setBankNeedsLogin] = React.useState(false);
  const [filter, setFilter] = React.useState<'todos'|'activo'|'contratado'|'descartado'|'reservado'>('todos');
  const [search, setSearch] = React.useState('');
  const [selectedTalent, setSelectedTalent] = React.useState<any>(null);
  const [profileLoading, setProfileLoading] = React.useState(false);
  const [profileError, setProfileError] = React.useState('');
  const [assignTalent, setAssignTalent] = React.useState<any>(null);
  const [assignOfferId, setAssignOfferId] = React.useState<number|null>(null);
  const [assignSending, setAssignSending] = React.useState(false);
  const [assignMessage, setAssignMessage] = React.useState('');
  const [openOffers, setOpenOffers] = React.useState<any[]>([]);
  const [resumeUpdating, setResumeUpdating] = React.useState(false);
  const [resumeUpdateMessage, setResumeUpdateMessage] = React.useState('');

  const loadTalentBank = React.useCallback(async () => {
    setLoading(true);
    setBankError('');
    setBankNeedsLogin(false);
    try {
      const data = await apiClient.getTalentBank();
      setCandidates(data.candidates || []);
    } catch (error) {
      const apiError = error as Error & { status?: number };
      setBankError(apiError.message || 'No fue posible cargar el Banco de Talento.');
      setBankNeedsLogin(apiError.status === 401);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadTalentBank();
    // Load open offers for assigning
    apiClient.getOffers().then(data => {
      setOpenOffers((data.offers || data || []).filter((o: any) => o.status === 'open' || !o.status));
    }).catch(() => {});
  }, [loadTalentBank]);

  const statusConfig: Record<string, { label: string; bg: string; text: string }> = {
    contratado: { label: '✓ Contratado', bg: 'bg-green-100', text: 'text-green-700' },
    reservado:  { label: '● Reservado',  bg: 'bg-blue-100',  text: 'text-blue-700'  },
    activo:     { label: '◉ Activo',     bg: 'bg-gray-100',  text: 'text-gray-600'  },
    descartado: { label: '✕ Descartado', bg: 'bg-red-100',   text: 'text-red-700'   },
  };

  const filtered = candidates.filter(c => {
    const matchFilter = filter === 'todos' || c.global_status === filter;
    const q = search.toLowerCase();
    const matchSearch = !q
      || c.full_name?.toLowerCase().includes(q)
      || c.origins?.some((origin: string) => origin.toLowerCase().includes(q));
    return matchFilter && matchSearch;
  });

  const openTalentProfile = async (candidateId: number) => {
    setProfileLoading(true);
    setProfileError('');
    try {
      setSelectedTalent(await apiClient.getTalentProfile(candidateId));
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : 'No fue posible abrir el perfil.');
    } finally {
      setProfileLoading(false);
    }
  };

  const assignToVacancy = async () => {
    if (!assignTalent || !assignOfferId) return;
    setAssignSending(true);
    setAssignMessage('');
    try {
      const res = await fetch(`http://localhost:8000/api/recruiter/talent-bank/${assignTalent.candidate_id}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` },
        body: JSON.stringify({ job_offer_id: assignOfferId })
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error asignando candidato'); }
      await res.json();
      setAssignMessage(`✅ ${assignTalent.full_name} fue agregado exitosamente a la vacante.`);
      // Refresh candidates list
      const refreshed = await apiClient.getTalentBank();
      setCandidates(refreshed.candidates || []);
      setTimeout(() => { setAssignTalent(null); setAssignMessage(''); setAssignOfferId(null); }, 2000);
    } catch (err: any) {
      setAssignMessage(`❌ ${err.message}`);
    } finally {
      setAssignSending(false);
    }
  };

  const updateResume = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const selection = selectSingleCv(input.files);
    input.value = '';
    if (selection.error || !selection.file || !selectedTalent) {
      if (selection.error) setResumeUpdateMessage(`❌ ${selection.error}`);
      return;
    }
    setResumeUpdating(true);
    setResumeUpdateMessage('');
    try {
      const result = await apiClient.updateTalentResume(selectedTalent.candidate_id, selection.file);
      const refreshedProfile = await apiClient.getTalentProfile(selectedTalent.candidate_id);
      setSelectedTalent(refreshedProfile);
      setResumeUpdateMessage(`✅ ${result.message}`);
    } catch (error) {
      setResumeUpdateMessage(`❌ ${error instanceof Error ? error.message : 'No fue posible actualizar el CV.'}`);
    } finally {
      setResumeUpdating(false);
    }
  };

  const counts = {
    todos: candidates.length,
    activo: candidates.filter(c => c.global_status === 'activo').length,
    contratado: candidates.filter(c => c.global_status === 'contratado').length,
    reservado: candidates.filter(c => c.global_status === 'reservado').length,
    descartado: candidates.filter(c => c.global_status === 'descartado').length,
  };

  return (
    <div className="mx-auto min-w-0 max-w-6xl">
      {profileLoading && <ProcessingOverlay title="Abriendo perfil protegido" description="Estamos recuperando los datos completos para esta vista autorizada." />}
      {resumeUpdating && <ProcessingOverlay title="Actualizando CV" description="Estamos validando la identidad y guardando una nueva versión sin perder el historial." />}
      <div className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-[#b91c1c]">Banco de Talento</h1>
            <p className="text-sm text-gray-500 mt-1">Vista resumida. Los datos personales se muestran únicamente al abrir un perfil.</p>
          </div>
          <button onClick={loadTalentBank} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
        </div>
      </div>
      {profileError && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{profileError}</div>}
      {bankError && <div role="alert" className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-bold">Los perfiles siguen guardados, pero no fue posible consultarlos.</p>
        <p className="mt-1">{bankError}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={loadTalentBank} className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 font-semibold hover:bg-amber-100"><RefreshCw size={14} /> Reintentar</button>
          {bankNeedsLogin && <button onClick={() => { logout(); window.location.href = '/login'; }} className="rounded-lg bg-slate-900 px-3 py-2 font-semibold text-white hover:bg-slate-800">Volver a iniciar sesión</button>}
        </div>
      </div>}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        {(['todos','activo','contratado','reservado','descartado'] as const).map(f => {
          const isSelected = filter === f;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-semibold rounded-full border transition-colors flex items-center gap-2 ${isSelected ? 'bg-[#b91c1c] text-white border-[#b91c1c]' : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400 hover:bg-gray-50'}`}
            >
              <span>{f.charAt(0).toUpperCase() + f.slice(1)}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${isSelected ? 'bg-white text-[#b91c1c]' : 'bg-gray-100 text-gray-600'}`}>
                {counts[f]}
              </span>
            </button>
          );
        })}
        <input
          type="text"
          placeholder="Buscar por nombre u origen..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full rounded-sm border border-gray-300 px-3 py-2 text-sm focus:border-[#b91c1c] focus:outline-none sm:ml-auto sm:w-72"
        />
      </div>

      {bankError ? null : loading ? (
        <p className="text-gray-500 text-sm py-10 text-center">Cargando banco de talento...</p>
      ) : (
        <div className="responsive-table-shell rounded-sm border border-gray-200 bg-white shadow-sm">
          <table className="responsive-table min-w-[900px] table-fixed text-sm">
            <thead>
              <tr className="bg-[#b91c1c] text-white text-left">
                <th className="p-3 font-bold w-[30%]">Candidato</th>
                <th className="p-3 font-bold text-center w-[12%]">Origen</th>
                <th className="p-3 font-bold text-center w-[10%]">Vacantes</th>
                <th className="p-3 font-bold text-center w-[12%]">Mejor Match</th>
                <th className="p-3 font-bold text-center w-[12%]">Estado</th>
                <th className="p-3 font-bold text-center w-[24%]">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-gray-400">No hay candidatos que coincidan.</td></tr>
              ) : filtered.map((c, idx) => {
                const sc = statusConfig[c.global_status] || statusConfig.activo;
                const score = c.best_score != null ? Math.round(c.best_score * 100) : null;
                const initials = c.full_name ? c.full_name.substring(0,2).toUpperCase() : 'CA';
                return (
                  <tr key={c.candidate_id} className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}>
                    <td className="p-3 font-bold text-gray-800">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-[#b91c1c] text-white flex items-center justify-center text-xs font-bold shadow-inner flex-shrink-0">{initials}</div>
                        <div className="min-w-0">
                          <div className="truncate">{c.full_name}</div>
                          <div className="text-xs text-gray-400 font-normal">Datos protegidos</div>
                        </div>
                      </div>
                    </td>
                    <td className="p-3 text-center">
                      <div className="flex flex-wrap justify-center gap-1">
                        {(c.origins || ['Sin postulación']).map((origin: string) => <span key={origin} className={`px-2 py-1 rounded text-[10px] font-bold uppercase ${origin.includes('Sourcing') ? 'bg-blue-50 text-blue-700' : origin === 'Desde PRI' ? 'bg-purple-50 text-purple-700' : origin === 'Link de postulación' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-50 text-gray-500'}`}>
                          {origin}
                        </span>)}
                      </div>
                    </td>
                    <td className="p-3 text-center text-gray-600">{c.applications_count}</td>
                    <td className="p-3 text-center">
                      {score != null ? (
                        <span className={`font-bold ${score >= 80 ? 'text-green-700' : 'text-[#f59e0b]'}`}>{score}%</span>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="p-3 text-center">
                      <span className={`px-2 py-1 rounded-full text-xs font-bold ${sc.bg} ${sc.text}`}>{sc.label}</span>
                    </td>
                    <td className="p-3 text-center whitespace-nowrap">
                      <button onClick={() => openTalentProfile(c.candidate_id)} className="inline-flex items-center gap-1.5 text-blue-700 hover:bg-blue-100 font-bold text-xs bg-blue-50 px-3 py-2 rounded mr-1"><Eye size={14} /> Ver perfil</button>
                      <button onClick={() => { setAssignTalent(c); setAssignMessage(''); setAssignOfferId(null); }} className="inline-flex items-center gap-1.5 text-[#b91c1c] hover:bg-red-100 font-bold text-xs bg-red-50 px-3 py-2 rounded"><Plus size={14} /> Agregar a vacante</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedTalent && !assignTalent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-2 sm:p-4">
          <div className="modal-shell relative w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
            {/* Header */}
            <div className="relative rounded-t-2xl bg-gradient-to-r from-[#8a1414] to-[#b91c1c] p-4 sm:p-6">
              <button aria-label="Cerrar" onClick={() => setSelectedTalent(null)} className="absolute top-4 right-4 rounded-full p-2 text-white/70 hover:text-white hover:bg-white/10"><X size={20} /></button>
              <div className="flex items-start gap-3 pr-10 sm:items-center sm:gap-4">
                <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full border-2 border-white/30 bg-white/20 text-lg font-bold text-white sm:h-14 sm:w-14 sm:text-xl">
                  {selectedTalent.full_name ? selectedTalent.full_name.substring(0,2).toUpperCase() : 'CA'}
                </div>
                <div className="min-w-0">
                  <h3 className="break-words text-xl font-bold text-white sm:text-2xl">{selectedTalent.full_name}</h3>
                  <div className="flex flex-wrap gap-3 mt-2 text-sm text-red-100">
                    {selectedTalent.email && selectedTalent.email !== 'No especificado' && <span className="flex min-w-0 items-center gap-1 break-all"><Mail size={14} className="flex-shrink-0" /> {selectedTalent.email}</span>}
                    {selectedTalent.phone && <span className="flex items-center gap-1"><Phone size={14} /> {selectedTalent.phone}</span>}
                    {!selectedTalent.email && !selectedTalent.phone && <span className="text-red-200 italic text-xs">Sin datos de contacto registrados</span>}
                  </div>
                </div>
              </div>
            </div>

            {/* Stats cards */}
            <div className="space-y-6 p-4 sm:p-6">
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="bg-gray-50 p-4 rounded-xl border border-gray-100 text-center">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Experiencia</p>
                  <p className="font-bold text-xl text-gray-800 mt-1">{selectedTalent.years_of_experience != null ? `${selectedTalent.years_of_experience} años` : '—'}</p>
                </div>
                <div className="bg-gray-50 p-4 rounded-xl border border-gray-100 text-center">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Vacantes</p>
                  <p className="font-bold text-xl text-gray-800 mt-1">{selectedTalent.applications_count || 0}</p>
                </div>
                <div className="bg-gray-50 p-4 rounded-xl border border-gray-100 text-center">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Mejor Match</p>
                  <p className={`font-bold text-xl mt-1 ${selectedTalent.best_score != null ? (Math.round(selectedTalent.best_score * 100) >= 80 ? 'text-green-700' : 'text-amber-600') : 'text-gray-300'}`}>
                    {selectedTalent.best_score != null ? `${Math.round(selectedTalent.best_score * 100)}%` : '—'}
                  </p>
                </div>
              </div>

              {/* Tech Stack */}
              {selectedTalent.tech_stack && (
                <div>
                  <h4 className="font-bold text-gray-800 text-sm border-b pb-2 mb-3">Stack Tecnológico</h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedTalent.tech_stack.split(',').map((t: string, i: number) => (
                      <span key={i} className="bg-blue-50 text-blue-700 border border-blue-100 px-3 py-1 rounded-full text-xs font-semibold">{t.trim()}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Career Summary */}
              {selectedTalent.career_summary && (
                <div>
                  <h4 className="font-bold text-gray-800 text-sm border-b pb-2 mb-3">Resumen Profesional</h4>
                  <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedTalent.career_summary}</p>
                </div>
              )}

              {/* Courses */}
              {selectedTalent.courses_and_diplomas && (
                <div>
                  <h4 className="font-bold text-gray-800 text-sm border-b pb-2 mb-3">Formación Adicional</h4>
                  <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedTalent.courses_and_diplomas}</p>
                </div>
              )}

              {/* No data message */}
              {!selectedTalent.tech_stack && !selectedTalent.career_summary && !selectedTalent.courses_and_diplomas && (
                <div className="text-center py-6 text-gray-400">
                  <p className="text-sm">Este perfil aún no tiene información detallada.</p>
                  <p className="text-xs mt-1">Se completará automáticamente cuando suba su CV o postule a una vacante.</p>
                </div>
              )}

              {/* Applications */}
              <div>
                <h4 className="font-bold text-gray-800 text-sm border-b pb-2 mb-3">Postulaciones ({selectedTalent.applications?.length || 0})</h4>
                {selectedTalent.applications?.length ? <div className="space-y-2">
                  {selectedTalent.applications.map((application: any) => {
                    const applicationScore = application.similarity_score == null ? null : Number((application.similarity_score * 100).toFixed(0));
                    return <div key={application.application_id} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 text-sm sm:flex-row sm:items-center sm:justify-between hover:bg-gray-50">
                      <div><p className="font-semibold text-slate-800">{application.job_offer_title}</p><p className="mt-0.5 text-xs text-slate-500">{application.origin_label}</p></div>
                      <div className="flex items-center gap-3"><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{application.outcome || application.status}</span>{applicationScore != null && <strong className="text-amber-700">{applicationScore}%</strong>}</div>
                    </div>;
                  })}
                </div> : <p className="text-sm text-slate-400 italic">Sin postulaciones activas aún.</p>}
              </div>

              {/* Resume history */}
              <div>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b pb-2">
                  <div>
                    <h4 className="flex items-center gap-2 text-sm font-bold text-gray-800"><History size={16} /> Historial de CV</h4>
                    <p className="mt-1 text-xs text-slate-500">El perfil usa la versión más reciente y conserva las anteriores para auditoría.</p>
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-800">
                    <Upload size={15} /> Actualizar CV
                    <input
                      type="file"
                      accept={CV_ACCEPT}
                      disabled={resumeUpdating}
                      onChange={updateResume}
                      className="sr-only"
                    />
                  </label>
                </div>
                <p className="mb-3 text-xs text-slate-500">PDF o Word (.doc o .docx), máximo {MAX_CV_SIZE_LABEL}. Validaremos el formato real y que el contenido corresponda a un currículum.</p>
                {resumeUpdateMessage && <p role="status" className={`mb-3 rounded-lg border p-3 text-sm font-semibold ${resumeUpdateMessage.startsWith('✅') ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>{resumeUpdateMessage}</p>}
                {selectedTalent.resume_versions?.length ? <div className="space-y-2">
                  {selectedTalent.resume_versions.map((version: any) => (
                    <div key={version.id} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-semibold text-slate-800">{version.original_filename}</p>
                          {version.is_current && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700">Actual</span>}
                        </div>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {version.source_label}{version.job_offer_title ? ` · ${version.job_offer_title}` : ''}{version.uploaded_at ? ` · ${new Date(version.uploaded_at).toLocaleDateString('es-CL')}` : ''}
                        </p>
                      </div>
                      <a href={version.resume_url} target="_blank" rel="noreferrer" className="inline-flex flex-shrink-0 items-center gap-1 font-semibold text-blue-700 hover:underline"><ExternalLink size={14} /> Ver versión</a>
                    </div>
                  ))}
                </div> : <p className="text-sm italic text-slate-400">El CV actual se incorporará al historial al inicializar esta versión.</p>}
              </div>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 flex flex-col gap-3 rounded-b-2xl border-t bg-gray-50 p-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:p-5">
              <div className="flex flex-col gap-2 sm:flex-row">
                {selectedTalent.resume_url && selectedTalent.resume_url !== 'pending' ? (
                  <a href={selectedTalent.resume_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2.5 rounded-xl font-bold hover:bg-gray-50 transition-colors shadow-sm text-sm">
                    <ExternalLink size={15} /> Ver CV
                  </a>
                ) : null}
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <button onClick={() => { setAssignTalent(selectedTalent); setAssignMessage(''); setAssignOfferId(null); }} className="flex items-center gap-2 bg-white border border-[#b91c1c] text-[#b91c1c] px-4 py-2.5 rounded-xl font-bold hover:bg-red-50 transition-colors shadow-sm text-sm">
                  <Plus size={15} /> Agregar a vacante
                </button>
                {selectedTalent.email && selectedTalent.email !== 'No especificado' && <a href={`mailto:${selectedTalent.email}?subject=Nueva oportunidad profesional`} className="flex items-center gap-2 bg-[#b91c1c] text-white px-5 py-2.5 rounded-xl font-bold hover:bg-red-800 transition-colors shadow-sm text-sm">
                  <Mail size={15} /> Contactar
                </a>}
              </div>
            </div>
          </div>
        </div>
      )}
      {assignTalent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-2 sm:p-4">
          <div className="modal-shell w-full max-w-md overflow-y-auto rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-3 border-b p-4 sm:p-6">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-red-700">Agregar a vacante</p>
                <h3 className="mt-1 text-xl font-bold text-slate-900">{assignTalent.full_name}</h3>
              </div>
              <button onClick={() => { setAssignTalent(null); setAssignMessage(''); setAssignOfferId(null); }} className="rounded-full p-2 text-slate-500 hover:bg-slate-100"><X size={20} /></button>
            </div>
            <div className="space-y-4 p-4 sm:p-6">
              <label className="block text-sm font-semibold text-slate-700">
                Selecciona la vacante
                <select
                  value={assignOfferId || ''}
                  onChange={e => setAssignOfferId(Number(e.target.value) || null)}
                  className="mt-2 w-full rounded-xl border border-slate-300 p-3 text-sm outline-none focus:border-red-700 focus:ring-2 focus:ring-red-100"
                >
                  <option value="">— Elige una vacante activa —</option>
                  {openOffers.map(o => (
                    <option key={o.id} value={o.id}>{o.title} ({o.company?.name || o.company_name || 'Empresa no informada'})</option>
                  ))}
                </select>
              </label>
              {assignMessage && <p className={`text-sm font-bold ${assignMessage.startsWith('✅') ? 'text-green-700' : 'text-red-700'}`}>{assignMessage}</p>}
            </div>
            <div className="flex flex-col-reverse gap-3 border-t bg-slate-50 p-4 sm:flex-row sm:justify-end sm:p-5">
              <button onClick={() => { setAssignTalent(null); setAssignMessage(''); setAssignOfferId(null); }} className="rounded-xl border border-slate-300 bg-white px-5 py-3 font-semibold text-slate-700">Cancelar</button>
              <button disabled={!assignOfferId || assignSending} onClick={assignToVacancy} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#b91c1c] px-5 py-3 font-bold text-white hover:bg-red-800 disabled:opacity-40">
                <Plus size={17} /> {assignSending ? 'Asignando…' : 'Agregar a vacante'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
