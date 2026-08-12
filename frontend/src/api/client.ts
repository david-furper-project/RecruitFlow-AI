const BASE_URL = 'http://localhost:8000/api';

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
  scrapeLinkedIn: async (url: string) => {
    const res = await fetch(`${BASE_URL}/recruiter/scrape-linkedin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Error scraping LinkedIn');
    }
    return res.json();
  },
  saveCandidate: async (data: any) => {
    const res = await fetch(`${BASE_URL}/recruiter/save-candidate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Error saving candidate');
    }
    return res.json();
  },
  massUploadCVs: async (files: File[], offerId: number) => {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('offer_id', offerId.toString());
    const res = await fetch(`${BASE_URL}/recruiter/mass-upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('Error on mass upload');
    return res.json();
  },
  getOffers: async () => {
    const res = await fetch(`${BASE_URL}/offers/`);
    if (!res.ok) throw new Error('Error fetching offers');
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
  updateApplicationStatus: async (offerId: number, candidateId: number, status: string) => {
    const res = await fetch(`${BASE_URL}/offers/${offerId}/application/${candidateId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ finalist_id: finalistId })
    });
    if (!res.ok) throw new Error('Error closing offer');
    return res.json();
  },
  applyForJob: async (offerId: number, formData: any, file: File) => {
    const data = new FormData();
    data.append('offer_id', offerId.toString());
    data.append('full_name', `${formData.nombre} ${formData.apellido}`);
    data.append('email', formData.email);
    data.append('phone', formData.telefono);
    data.append('file', file);
    const response = await fetch(`${BASE_URL}/candidates/apply`, {
      method: 'POST',
      body: data,
    });
    if (!response.ok) throw new Error('Failed to apply');
    return response.json();
  },
};
