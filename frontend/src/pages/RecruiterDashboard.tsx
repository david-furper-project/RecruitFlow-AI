import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

export default function RecruiterDashboard() {
  const [offers, setOffers] = useState<any[]>([]);
  const [selectedOffer, setSelectedOffer] = useState<any>(null);
  const [loadingOffers, setLoadingOffers] = useState(true);

  // Tab State
  const [currentTab, setCurrentTab] = useState<'Inicio'|'Vacantes'|'Empresas'|'Banco de talento'|'Búsqueda IA'|'Reportes'|'Configuración'>('Vacantes');
  const [offerTab, setOfferTab] = useState<'Activas'|'Inactivas'>('Activas');

  // Create Offer State
  const [isCreatingOffer, setIsCreatingOffer] = useState(false);
  const [newOffer, setNewOffer] = useState({ company_id: '', title: '', description: '', requirements: '', tech_stack: '', salary_range: '', experience_years: 0, seniority: 'Junior' });

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

  // Candidate View Modal State
  const [selectedCandidate, setSelectedCandidate] = useState<any>(null);

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

  useEffect(() => {
    if (selectedOffer) {
      loadMatches(selectedOffer.id);
    }
  }, [selectedOffer]);

  // New feature states
  const [isClosingOffer, setIsClosingOffer] = useState(false);
  const [finalistId, setFinalistId] = useState<number | null>(null);
  const [isExtractingTech, setIsExtractingTech] = useState(false);

  const loadMatches = async (offerId: number) => {
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
  };
  
  // Reload when candidateView changes
  useEffect(() => {
    if (selectedOffer) {
      loadMatches(selectedOffer.id);
    }
  }, [candidateView, activeStageId]);

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

  const handleCloseOffer = async () => {
    if (!selectedOffer) return;
    try {
      await apiClient.closeOffer(selectedOffer.id, finalistId);
      setIsClosingOffer(false);
      setSelectedOffer(null);
      loadOffers();
    } catch (err) {
      console.error(err);
      alert('Error al cerrar vacante');
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
      setNewOffer({ company_id: '', title: '', description: '', requirements: '', tech_stack: '', salary_range: '', experience_years: 0, seniority: 'Junior' });
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
    try {
      await apiClient.massUploadCVs(uploadFiles, selectedOffer.id);
      setUploadStatus('success');
      setUploadFiles([]);
      setTimeout(() => {
        setIsUploading(false);
        setUploadStatus('idle');
        loadMatches(selectedOffer.id);
      }, 2000);
    } catch (err) {
      console.error(err);
      setUploadStatus('error');
    }
  };

  const handleUpdateStatus = async (candidateId: number, status: string) => {
    if (!selectedOffer) return;

    // Check if we are advancing a rejected candidate
    const candidate = matches.find(m => m.candidate_id === candidateId);
    if (status === 'advanced' && candidate?.status === 'rejected') {
      const confirmAdvance = window.confirm("Este candidato ya fue eliminado. ¿Aún así quieres avanzarlo?");
      if (!confirmAdvance) return;
    }

    let discrepancyReason = undefined;
    if (status === 'rejected') {
      discrepancyReason = window.prompt("Opcional: Si este candidato fue recomendado por la IA, debes ingresar una razón para descartarlo. ¿Cuál es el motivo?") || undefined;
    }

    try {
      // Use makeDecision instead of updateApplicationStatus
      // Map legacy status to actions
      let action = 'avanzar';
      if (status === 'rejected') action = 'descartar';
      if (status === 'reservar') action = 'reservar';
      
      // We need applicationId! matches has application_id
      const match = matches.find(m => m.candidate_id === candidateId);
      if (!match) return;
      
      await apiClient.makeDecision(match.application_id, action, discrepancyReason);
      loadMatches(selectedOffer.id);
    } catch (err) {
      console.error(err);
      alert('Error al actualizar estado del candidato. Recuerda ingresar un motivo si estás contradiciendo a la IA.');
    }
  };

  const filteredMatches = matches.filter(match => {
    if (candidateFilter === 'Top 20%') return (match.similarity_score || 0) >= 0.8;
    return true;
  });

  const activeOffers = offers.filter(o => o.status === 'open' || !o.status);
  const inactiveOffers = offers.filter(o => o.status === 'closed');
  let displayedOffers = offerTab === 'Activas' ? activeOffers : inactiveOffers;
  if (selectedCompanyForOffers) {
    displayedOffers = displayedOffers.filter(o => o.company_id === selectedCompanyForOffers.id);
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      {/* Top Bar Falsa estilo MacOS */}
      <div className="bg-[#b91c1c] text-white py-3 px-6 flex items-center shadow-md z-20">
        <div className="flex gap-2 mr-auto">
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
          <div className="w-3 h-3 rounded-full bg-white/70"></div>
        </div>
        <div className="text-sm font-medium opacity-90 mx-auto absolute left-1/2 -translate-x-1/2">
          {selectedOffer ? `pri.empresa.com / vacantes / ${selectedOffer.title.toLowerCase().replace(/\s+/g, '-')}` : 'pri.empresa.com / reclutador / vacantes'}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-gray-100 border-r border-gray-200 flex flex-col pt-4 z-10 hidden md:flex">
          {(['Inicio', 'Vacantes', 'Empresas', 'Banco de talento', 'Búsqueda IA', 'Reportes', 'Configuración'] as const).map(tab => (
            <div 
              key={tab}
              onClick={() => { setCurrentTab(tab); setSelectedOffer(null); setIsCreatingOffer(false); setSelectedCompanyForOffers(null); }}
              className={`px-6 py-4 cursor-pointer text-sm font-medium transition-colors ${currentTab === tab ? 'bg-[#b91c1c] text-white shadow-inner' : 'text-gray-600 hover:bg-gray-200'}`}
            >
              {tab}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 p-8 overflow-y-auto bg-white border-l border-gray-200 shadow-inner">
          {['Inicio', 'Banco de talento', 'Búsqueda IA', 'Reportes', 'Configuración'].includes(currentTab) && (
            <div className="max-w-6xl mx-auto flex flex-col items-center justify-center py-20 text-center">
              <h1 className="text-3xl font-bold text-[#b91c1c] mb-4">{currentTab}</h1>
              <p className="text-gray-500 text-lg">Esta sección está en construcción para el MVP.</p>
            </div>
          )}

          {currentTab === 'Vacantes' && (
            <div className="max-w-6xl mx-auto">
              {!selectedCompanyForOffers ? (
                <div className="bg-white p-6 rounded-sm shadow-sm border border-gray-200">
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
                  <div className="flex justify-between items-end mb-6 border-b border-gray-200 pb-4 mt-4">
                    <div>
                      <h1 className="text-2xl font-bold text-[#b91c1c] mb-2">Vacantes de {selectedCompanyForOffers.name}</h1>
                      <div className="flex bg-gray-100 w-max rounded-sm overflow-hidden border border-gray-200">
                        <button onClick={() => setOfferTab('Activas')} className={`px-8 py-2 font-medium text-sm transition-colors ${offerTab === 'Activas' ? 'bg-[#b91c1c] text-white' : 'text-gray-600 hover:bg-gray-200'}`}>Activas</button>
                        <button onClick={() => setOfferTab('Inactivas')} className={`px-8 py-2 font-medium text-sm border-l border-gray-200 transition-colors ${offerTab === 'Inactivas' ? 'bg-[#b91c1c] text-white' : 'text-gray-600 hover:bg-gray-200'}`}>Inactivas</button>
                      </div>
                    </div>
                    <button 
                      onClick={() => setIsCreatingOffer(!isCreatingOffer)}
                      className="px-6 py-2.5 bg-[#f59e0b] text-black font-bold text-sm shadow-sm hover:bg-amber-400 transition-colors rounded-sm"
                    >
                      {isCreatingOffer ? 'Cancelar' : '+ Nueva vacante'}
                    </button>
                  </div>

                  {isCreatingOffer && (
                    <div className="mb-6 p-6 border border-gray-200 rounded-sm bg-gray-50 flex flex-col gap-4">
                      <h3 className="font-bold text-[#b91c1c] mb-2">Crear nueva oferta laboral en {selectedCompanyForOffers.name}</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input type="text" placeholder="Título (ej. Frontend Developer) *" className="p-2 border rounded text-sm md:col-span-2" value={newOffer.title} onChange={e => setNewOffer({ ...newOffer, title: e.target.value })} />
                        <div className="flex gap-2 md:col-span-2">
                          <input type="text" placeholder="Stack Tecnológico *" className="p-2 border rounded text-sm flex-1" value={newOffer.tech_stack} onChange={e => setNewOffer({ ...newOffer, tech_stack: e.target.value })} />
                          <button onClick={handleExtractTechStack} disabled={isExtractingTech} className="px-4 py-2 bg-[#f59e0b] text-black font-bold rounded text-sm whitespace-nowrap hover:bg-amber-400 shadow-sm disabled:opacity-50">
                            {isExtractingTech ? 'Procesando...' : '✨ Extraer'}
                          </button>
                        </div>
                        <textarea placeholder="Descripción *" className="p-2 border rounded text-sm md:col-span-2" value={newOffer.description} onChange={e => setNewOffer({ ...newOffer, description: e.target.value })} />
                        <textarea placeholder="Requerimientos *" className="p-2 border rounded text-sm md:col-span-2" value={newOffer.requirements} onChange={e => setNewOffer({ ...newOffer, requirements: e.target.value })} />
                        <input type="text" placeholder="Rango Salarial *" className="p-2 border rounded text-sm" value={newOffer.salary_range} onChange={e => setNewOffer({ ...newOffer, salary_range: e.target.value })} />
                        <div className="flex gap-2">
                          <input type="number" min="0" placeholder="Exp. (años) *" className="w-1/2 p-2 border rounded text-sm" value={newOffer.experience_years} onChange={e => setNewOffer({ ...newOffer, experience_years: parseInt(e.target.value) || 0 })} />
                          <select className="w-1/2 p-2 border rounded text-sm bg-white" value={newOffer.seniority} onChange={e => setNewOffer({ ...newOffer, seniority: e.target.value })}>
                            <option value="Junior">Junior</option><option value="Semi-Senior">Semi-Senior</option><option value="Senior">Senior</option><option value="Lead">Lead</option>
                          </select>
                        </div>
                      </div>
                      <button onClick={handleCreateOffer} className="w-full py-2 mt-2 bg-[#b91c1c] text-white rounded font-bold hover:bg-red-800 transition-colors">Guardar Vacante</button>
                    </div>
                  )}

              {loadingOffers ? (
                 <p className="text-center py-10 text-gray-400">Cargando vacantes...</p>
              ) : (
                <div className="border border-gray-200 rounded-sm overflow-hidden">
                  <table className="w-full text-left border-collapse">
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
                              <span className={`${offer.status === 'closed' ? 'bg-gray-500' : 'bg-green-700'} text-white text-xs px-3 py-1 font-bold rounded-sm`}>
                                {offer.status === 'closed' ? 'Cerrada' : 'Abierta'}
                              </span>
                            </td>
                            <td className="p-4 text-center font-bold text-gray-800">0</td>
                            <td className="p-4 text-center font-bold text-[#b91c1c]">-</td>
                            <td className="p-4 text-center text-gray-600 font-medium">1 día</td>
                            <td className="p-4 text-center">
                              <button 
                                onClick={() => setSelectedOffer(offer)}
                                className="bg-[#b91c1c] text-white text-xs px-4 py-2 font-bold hover:bg-red-800 transition-colors rounded-sm shadow-sm"
                              >
                                Ver candidatos
                              </button>
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
                <div className="flex justify-between items-start">
                  <div>
                    <div className="text-sm text-gray-400 font-medium mb-2 cursor-pointer hover:text-gray-600 flex items-center gap-2" onClick={() => { setSelectedOffer(null); setIsUploading(false); }}>
                      Volver a vacantes · {selectedOffer.title}
                    </div>
                    <h1 className="text-2xl font-bold text-[#b91c1c]">Candidatos ({filteredMatches.length})</h1>
                  </div>
                </div>

                <div className="flex flex-col gap-4 w-full border-b border-gray-200 pb-4">
                  {/* Pipeline Stages Tabs */}
                  <div className="flex gap-2 w-full overflow-x-auto">
                    <button
                      onClick={() => { setCandidateView('all'); setActiveStageId(null); }}
                      className={`px-4 py-2 font-bold text-sm whitespace-nowrap border-b-2 transition-colors ${candidateView === 'all' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800'}`}
                    >
                      Todos ({pipelineCounts.all_active || 0})
                    </button>
                    {pipelineStages.map(stage => (
                      <button
                        key={stage.id}
                        onClick={() => { setCandidateView('stage'); setActiveStageId(stage.id); }}
                        className={`px-4 py-2 font-bold text-sm whitespace-nowrap border-b-2 transition-colors ${candidateView === 'stage' && activeStageId === stage.id ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800'}`}
                      >
                        {stage.name} ({stage.count || 0})
                      </button>
                    ))}
                    <button
                      onClick={() => { setCandidateView('discarded'); setActiveStageId(null); }}
                      className={`px-4 py-2 font-bold text-sm whitespace-nowrap border-b-2 transition-colors ${candidateView === 'discarded' ? 'border-[#b91c1c] text-[#b91c1c]' : 'border-transparent text-gray-500 hover:text-gray-800'}`}
                    >
                      Descartados ({pipelineCounts.discarded || 0})
                    </button>
                  </div>
                  
                  {/* Filters & Actions row */}
                  <div className="flex justify-between items-center w-full">
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
                    <div className="flex gap-2">
                      <button 
                        onClick={() => setIsUploading(!isUploading)}
                        className="bg-[#f59e0b] text-black font-bold text-xs px-6 py-2.5 rounded-sm shadow-sm hover:bg-amber-400 transition-colors"
                      >
                        {isUploading ? 'Cancelar' : '+ Cargar CVs'}
                      </button>
                      {selectedOffer.status !== 'closed' && (
                        <button 
                          onClick={() => setIsClosingOffer(true)}
                          className="bg-red-900 text-white font-bold text-xs px-6 py-2.5 rounded-sm shadow-sm hover:bg-red-700 transition-colors"
                        >
                          Cerrar Vacante
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {isUploading && (
                <div className="mb-6 p-6 border border-gray-200 rounded-sm bg-gray-50 shadow-inner">
                  <h3 className="font-bold text-[#b91c1c] mb-4">Carga de CVs (individual o masiva)</h3>
                  <label className="w-full h-32 border-2 border-dashed border-red-300 rounded-sm flex flex-col items-center justify-center cursor-pointer hover:bg-white transition-colors bg-white mb-4">
                    <span className="text-sm text-[#b91c1c] font-medium px-4 text-center">
                      {uploadFiles.length > 0 ? `${uploadFiles.length} archivo(s) seleccionado(s).` : 'Haz clic o arrastra archivos PDF aquí'}
                    </span>
                    <input 
                      type="file" 
                      accept=".pdf" 
                      multiple 
                      className="hidden" 
                      onChange={(e) => setUploadFiles(Array.from(e.target.files || []))}
                    />
                  </label>
                  {uploadFiles.length > 0 && (
                    <button 
                      onClick={handleMassiveUpload}
                      disabled={uploadStatus === 'uploading'}
                      className="w-full py-3 bg-[#b91c1c] text-white font-bold rounded-sm hover:bg-red-800 disabled:opacity-50 transition-colors"
                    >
                      {uploadStatus === 'uploading' ? 'Procesando con IA, por favor espera...' : uploadStatus === 'success' ? '¡CVs cargados exitosamente!' : 'Procesar CVs seleccionados'}
                    </button>
                  )}
                  {uploadStatus === 'error' && <p className="text-red-500 mt-2 text-sm text-center font-bold">Ocurrió un error al procesar algunos archivos. Revisa la consola o intenta de nuevo.</p>}
                </div>
              )}

              {loadingMatches ? (
                 <p className="text-center py-10 text-gray-400">Cargando candidatos...</p>
              ) : (
                <div className="border border-gray-200 rounded-sm overflow-hidden shadow-sm">
                  <table className="w-full text-left border-collapse">
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
                          const matchScore = match.similarity_score !== undefined ? Math.round(match.similarity_score * 100) : 0;
                          const isHigh = matchScore >= 80;
                          const initials = match.full_name ? match.full_name.substring(0, 2).toUpperCase() : 'CA';
                          return (
                            <tr key={match.candidate_id || idx} className={`border-b border-gray-200 text-sm ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}>
                              <td className="p-4 font-bold text-gray-800 flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-[#b91c1c] text-white flex items-center justify-center text-xs shadow-inner">
                                  {initials}
                                </div>
                                {match.full_name || `Candidato #${match.candidate_id}`}
                              </td>
                              <td className="p-4 text-center text-gray-600 font-medium">Plataforma</td>
                              <td className="p-4 text-center">
                                <div className="flex items-center justify-center gap-3 w-48 mx-auto">
                                  <div className="h-3 w-full bg-gray-200 rounded-sm overflow-hidden border border-gray-300">
                                    <div className={`h-full ${isHigh ? 'bg-green-700' : 'bg-[#f59e0b]'}`} style={{ width: `${matchScore}%` }}></div>
                                  </div>
                                  <span className={`font-bold w-10 text-right ${isHigh ? 'text-green-700' : 'text-[#f59e0b]'}`}>{matchScore}%</span>
                                </div>
                              </td>
                              <td className="p-4 text-center">
                                <div className="flex justify-center items-center gap-2">
                                  <button onClick={() => setSelectedCandidate(match)} className="bg-[#b91c1c] text-white text-xs px-4 py-2 font-bold hover:bg-red-800 transition-colors rounded-sm shadow-sm">Ver</button>
                                  {match.outcome === 'descartado' ? (
                                    <div className="flex items-center gap-1 text-xs px-3 py-1 font-bold text-gray-500 bg-gray-100 rounded-full cursor-not-allowed">
                                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                      Descartado
                                    </div>
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
              )}
            </div>
          )}
        </div>
      )}

          {currentTab === 'Empresas' && (
            <div className="bg-white p-6 rounded-sm shadow-sm border border-gray-200">
              <h2 className="text-xl font-bold text-[#b91c1c] mb-6">Empresas Clientes</h2>
              
              <div className="mb-8 p-6 border border-gray-200 rounded-sm bg-gray-50 flex flex-col gap-4">
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
        </div>
      </div>

      {/* Candidate Modal */}
      {selectedCandidate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm shadow-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="flex justify-between items-center p-6 border-b border-gray-200">
              <h2 className="text-xl font-bold text-[#b91c1c]">Perfil de {selectedCandidate.full_name}</h2>
              <button onClick={() => setSelectedCandidate(null)} className="text-gray-400 hover:text-gray-600 font-bold">✕</button>
            </div>
            <div className="p-6 overflow-y-auto flex-1 text-sm text-gray-700">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Porcentaje de Match</p>
                  <p className="text-xl font-bold text-green-700">{selectedCandidate.match_percentage || 0}%</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Años de Experiencia</p>
                  <p className="text-gray-900 font-medium">{selectedCandidate.years_of_experience || 'No especificada'}</p>
                </div>
                <div>
                  <p className="font-bold text-gray-500 mb-1 text-xs uppercase tracking-wider">Datos Personales y Académicos</p>
                  <p className="text-gray-900 font-medium">{selectedCandidate.nationality || 'Nacionalidad no especificada'}</p>
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
            <div className="p-6 border-t border-gray-200 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => setSelectedCandidate(null)} className="px-6 py-2 bg-white border border-gray-300 text-gray-700 font-bold rounded-sm hover:bg-gray-100">Cerrar</button>
              <button onClick={() => { handleUpdateStatus(selectedCandidate.candidate_id, 'advanced'); setSelectedCandidate(null); }} className="px-6 py-2 bg-[#f59e0b] text-black font-bold rounded-sm hover:bg-amber-400 shadow-sm">Avanzar Candidato</button>
            </div>
          </div>
        </div>
      )}

      {/* Close Offer Modal */}
      {isClosingOffer && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm shadow-lg w-full max-w-md flex flex-col">
            <div className="p-6 border-b border-gray-200">
              <h2 className="text-xl font-bold text-[#b91c1c]">Cerrar Vacante</h2>
              <p className="text-sm text-gray-500 mt-2">Esta vacante pasará a la pestaña de inactivas.</p>
            </div>
            <div className="p-6 flex-1 text-sm text-gray-700">
              <label className="font-bold text-gray-700 block mb-2">Seleccionar Finalista (Opcional)</label>
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
            <div className="p-6 border-t border-gray-200 flex justify-end gap-3 bg-gray-50">
              <button onClick={() => { setIsClosingOffer(false); setFinalistId(null); }} className="px-6 py-2 bg-white border border-gray-300 text-gray-700 font-bold rounded-sm hover:bg-gray-100">Cancelar</button>
              <button onClick={handleCloseOffer} className="px-6 py-2 bg-red-900 text-white font-bold rounded-sm hover:bg-red-700 shadow-sm">Confirmar y Cerrar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
