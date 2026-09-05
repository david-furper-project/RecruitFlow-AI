/* eslint-disable @typescript-eslint/no-explicit-any */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');
const recruiterHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export const apiClient = {
  getCompanies: async () => {
    const res = await fetch(`${BASE_URL}/companies/`);
    if (!res.ok) throw new Error('Error fetching companies');
    return res.json();
  },
  createCompany: async (company: any) => {
    const res = await fetch(`${BASE_URL}/companies/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(company)
    });
    if (!res.ok) throw new Error('Error creating company');
    return res.json();
  },
  uploadCV: async (candidateId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/candidates/${candidateId}/upload-cv`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Error uploading CV');
    return res.json();
  },
  getMatches: async (offerId: number) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/match?limit=10`);
    if (!res.ok) throw new Error('Error fetching matches');
    return res.json();
  },
  previewSourcingProspect: async (file: File, source: string, jobOfferId: number, sourceUrl?: string, contactNotes?: string) => {
    const data = new FormData();
    data.append('file', file);
    data.append('source', source);
    data.append('job_offer_id', String(jobOfferId));
    if (sourceUrl) data.append('source_url', sourceUrl);
    if (contactNotes) data.append('contact_notes', contactNotes);
    const res = await fetch(`${BASE_URL}/sourcing/prospects/import`, { method: 'POST', headers: recruiterHeaders(), body: data });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error analizando el perfil'); }
    return res.json();
  },
  previewSourcingProspects: async (files: File[], source: string, jobOfferId: number, sourceUrl?: string, contactNotes?: string) => {
    const data = new FormData();
    files.forEach(file => data.append('files', file));
    data.append('source', source);
    data.append('job_offer_id', String(jobOfferId));
    if (sourceUrl) data.append('source_url', sourceUrl);
    if (contactNotes) data.append('contact_notes', contactNotes);
    const res = await fetch(`${BASE_URL}/sourcing/prospects/import/bulk`, { method: 'POST', headers: recruiterHeaders(), body: data });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Error analizando los perfiles');
    }
    return res.json();
  },
  confirmSourcingProspect: async (previewToken: string) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects/import/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ preview_token: previewToken })
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error guardando el prospecto'); }
    return res.json();
  },
  getSourcingProspects: async (jobOfferId: number) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects?job_offer_id=${jobOfferId}`, { headers: recruiterHeaders() });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error obteniendo prospectos'); }
    return res.json();
  },
  recordSourcingContact: async (prospectId: number, channel: string, value?: string, notes?: string, message?: string) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects/${prospectId}/contact`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ channel, value: value || undefined, notes, message })
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error registrando contacto'); }
    return res.json();
  },
  recordSourcingResponse: async (prospectId: number, response: string, notes?: string) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects/${prospectId}/response`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ response, notes })
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error registrando respuesta'); }
    return res.json();
  },
  inviteSourcingProspect: async (prospectId: number, email?: string) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects/${prospectId}/invite`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ email: email || undefined, send_email: Boolean(email) })
    });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error creando invitación'); }
    return res.json();
  },
  convertSourcingProspect: async (prospectId: number, data: FormData) => {
    const res = await fetch(`${BASE_URL}/sourcing/prospects/${prospectId}/convert`, { method: 'POST', headers: recruiterHeaders(), body: data });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error convirtiendo el prospecto'); }
    return res.json();
  },
  getSourcingInvitation: async (token: string) => {
    const res = await fetch(`${BASE_URL}/sourcing/invitations/${token}`);
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Invitación inválida'); }
    return res.json();
  },
  completeSourcingApplication: async (token: string, data: FormData) => {
    const res = await fetch(`${BASE_URL}/sourcing/invitations/${token}/apply`, { method: 'POST', body: data });
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'No fue posible completar la postulación'); }
    return res.json();
  },
  massUploadCVs: async (files: File[], offerId: number, originMode = 'authorized_application', authorizationConfirmed = false) => {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('offer_id', offerId.toString());
    formData.append('origin_mode', originMode);
    formData.append('authorization_confirmed', String(authorizationConfirmed));
    const res = await fetch(`${BASE_URL}/recruiter/mass-upload`, {
      method: 'POST',
      headers: recruiterHeaders(),
      body: formData
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'No fue posible procesar los CV.');
    }
    return res.json();
  },
  getOffers: async () => {
    const res = await fetch(`${BASE_URL}/offers/`);
    if (!res.ok) throw new Error('Error fetching offers');
    return res.json();
  },
  getPublicOffer: async (publicId: string) => {
    const res = await fetch(`${BASE_URL}/candidates/offers/${encodeURIComponent(publicId)}`);
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'La oferta no existe o ya no está disponible.');
    }
    return res.json();
  },
  createOffer: async (data: { company_id: number, title: string, description: string, requirements: string, tech_stack: string, salary_range: string, experience_years: number, seniority: string }) => {
    const res = await fetch(`${BASE_URL}/offers/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Error creating offer');
    return res.json();
  },
  updateApplicationStatus: async (offerId: number, candidateId: number, status: string, discrepancyReason?: string, feedback?: string) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/application/${candidateId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ status, discrepancy_reason: discrepancyReason, feedback })
    });
    if (!res.ok) throw new Error('Error updating application status');
    return res.json();
  },
  extractTechStack: async (text: string) => {
    const res = await fetch(`${BASE_URL}/offers/extract-tech-stack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!res.ok) throw new Error('Error extracting tech stack');
    return res.json();
  },
  closeOffer: async (offerId: number, finalistId: number | null) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/close`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ finalist_id: finalistId })
    });
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Error closing offer'); }
    return res.json();
  },
  reopenOffer: async (offerId: number) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/reopen`, {
      method: 'PUT', headers: recruiterHeaders()
    });
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Error reopening offer'); }
    return res.json();
  },
  closeOfferDefinitively: async (offerId: number) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/close-final`, {
      method: 'PUT', headers: recruiterHeaders()
    });
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Error closing offer definitively'); }
    return res.json();
  },
  applyForJob: async (offerPublicId: string, formData: any, file: File, consent: boolean) => {
    const data = new FormData();
    data.append('full_name', `${formData.nombre} ${formData.apellido}`);
    data.append('email', formData.email);
    data.append('phone', formData.telefono);
    if (formData.renta) data.append('salary_expectation', formData.renta);
    data.append('consent', String(consent));
    data.append('file', file);
    const response = await fetch(`${BASE_URL}/candidates/offers/${encodeURIComponent(offerPublicId)}/applications`, {
      method: 'POST',
      body: data,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'No fue posible completar la postulación');
    }
    return response.json();
  },
  getStages: async (offerId: number) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/stages`);
    if (!res.ok) throw new Error('Error fetching stages');
    return res.json();
  },
  updateStages: async (offerId: number, stages: any[]) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/stages`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stages })
    });
    if (!res.ok) throw new Error('Error updating stages');
    return res.json();
  },
  getCandidates: async (offerId: number, stageId?: number, outcome?: string) => {
    let url = `${BASE_URL}/job-offers/${offerId}/candidates`;
    const params = new URLSearchParams();
    if (stageId) params.append('stage_id', stageId.toString());
    if (outcome) params.append('outcome', outcome);
    if (params.toString()) url += `?${params.toString()}`;
    
    const res = await fetch(url);
    if (!res.ok) throw new Error('Error fetching candidates');
    return res.json();
  },
  reEvaluateCandidates: async (offerId: number) => {
    const res = await fetch(`${BASE_URL}/job-offers/${offerId}/re-evaluate-all`, {
      method: 'POST',
      headers: recruiterHeaders(),
    });
    if (!res.ok) throw new Error('No fue posible recalcular la afinidad.');
    return res.json();
  },
  getTalentBank: async () => {
    const res = await fetch(`${BASE_URL}/recruiter/talent-bank`, { headers: recruiterHeaders() });
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      const message = res.status === 401
        ? 'Tu sesión de reclutador venció. Vuelve a iniciar sesión para consultar el Banco de Talento.'
        : payload.detail || 'No fue posible cargar el Banco de Talento.';
      const error = new Error(message) as Error & { status?: number };
      error.status = res.status;
      throw error;
    }
    return res.json();
  },
  getTalentProfile: async (candidateId: number) => {
    const res = await fetch(`${BASE_URL}/recruiter/talent-bank/${candidateId}`, { headers: recruiterHeaders() });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'No fue posible abrir el perfil.');
    }
    return res.json();
  },
  updateTalentResume: async (candidateId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/recruiter/talent-bank/${candidateId}/resume`, {
      method: 'POST',
      headers: recruiterHeaders(),
      body: formData,
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'No fue posible actualizar el CV.');
    }
    return res.json();
  },
  makeDecision: async (applicationId: number, action: string, feedback?: string, discrepancyReason?: string) => {
    const res = await fetch(`${BASE_URL}/applications/${applicationId}/decision`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...recruiterHeaders() },
      body: JSON.stringify({ action, feedback, discrepancy_reason: discrepancyReason })
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Error making decision');
    }
    return res.json();
  },
  getCompanyReports: async () => {
    const res = await fetch(`${BASE_URL}/reports/companies`, { headers: recruiterHeaders() });
    if (!res.ok) throw new Error("Error fetching company reports");
    return res.json();
  },
  getOfferReports: async () => {
    const res = await fetch(`${BASE_URL}/reports/offers`, { headers: recruiterHeaders() });
    if (!res.ok) throw new Error("Error fetching offer reports");
    return res.json();
  },
  downloadExecutiveReport: async () => {
    const res = await fetch(`${BASE_URL}/reports/executive.pdf`, { headers: recruiterHeaders() });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || "No fue posible generar el reporte PDF");
    }
    return res.blob();
  },
};
