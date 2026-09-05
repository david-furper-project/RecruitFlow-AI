import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { BriefcaseBusiness, CheckCircle2, Clock3, FileText, ShieldCheck } from 'lucide-react';
import { apiClient } from '../api/client';
import { CV_ACCEPT, selectSingleCv, validateCvFile } from '../utils/cvUpload';
import { InlineSpinner, ProcessingOverlay } from '../components/ProcessingState';

interface InvitationDetails {
  candidate_name?: string;
  candidate_email?: string;
  candidate_phone?: string;
  company_name?: string;
  title: string;
  description: string;
  requirements?: string;
  expires_at?: string;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Ocurrió un error inesperado.';
}

export default function SourcingInvitationPage() {
  const { token = '' } = useParams();
  const [invitation, setInvitation] = useState<InvitationDetails | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [consent, setConsent] = useState(false);

  useEffect(() => {
    apiClient.getSourcingInvitation(token)
      .then((data) => {
        setInvitation(data);
        setName(data.candidate_name || '');
        setEmail(data.candidate_email || '');
        setPhone(data.candidate_phone || '');
      })
      .catch((cause: unknown) => setError(errorMessage(cause)));
  }, [token]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file || !consent) return;
    const validationError = validateCvFile(file);
    if (validationError) {
      setFile(null);
      setFileError(validationError);
      return;
    }
    setSubmitting(true);
    setError('');
    const data = new FormData();
    data.append('full_name', name);
    data.append('email', email);
    data.append('phone', phone);
    data.append('consent', String(consent));
    data.append('file', file);
    try {
      await apiClient.completeSourcingApplication(token, data);
      setSuccess(true);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  };

  if (error && !invitation) {
    return <main className="flex min-h-screen min-h-[100dvh] items-center justify-center bg-slate-50 p-3 sm:p-6">
      <section className="w-full max-w-lg rounded-2xl border border-red-100 bg-white p-5 text-center shadow-sm sm:p-8">
        <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-red-50 text-red-700 flex items-center justify-center font-bold">!</div>
        <h1 className="text-2xl font-bold text-slate-900">No pudimos abrir esta invitación</h1>
        <p className="mt-3 text-slate-600">{error}</p>
        <p className="mt-5 text-sm text-slate-500">Solicita al equipo de selección un enlace nuevo si éste venció.</p>
      </section>
    </main>;
  }

  if (!invitation) {
    return <main className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-600">Cargando invitación…</main>;
  }

  if (success) {
    return <main className="flex min-h-screen min-h-[100dvh] items-center justify-center bg-slate-50 p-3 sm:p-6">
      <section className="w-full max-w-lg rounded-2xl border border-emerald-100 bg-white p-6 text-center shadow-sm sm:p-10">
        <CheckCircle2 className="mx-auto h-14 w-14 text-emerald-600" />
        <h1 className="mt-5 text-2xl font-bold text-slate-900 sm:text-3xl">Postulación enviada</h1>
        <p className="mt-3 text-slate-600">Recibimos tu CV y tus datos. El equipo de selección continuará el proceso desde aquí.</p>
      </section>
    </main>;
  }

  return <main className="min-h-screen min-h-[100dvh] bg-slate-50 px-3 py-6 sm:px-4 sm:py-10">
    {submitting && <ProcessingOverlay title="Analizando tu CV" description="Estamos completando la postulación y calculando la afinidad con la vacante." />}
    <div className="mx-auto max-w-5xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-200/50 lg:grid lg:grid-cols-[0.9fr_1.1fr]">
      <section className="bg-slate-900 p-5 text-white sm:p-8 lg:p-10">
        <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider">
          <BriefcaseBusiness size={15} /> Invitación privada
        </span>
        <p className="mt-8 text-sm text-slate-300">{invitation.company_name || 'Proceso de selección'}</p>
        <h1 className="mt-2 break-words text-2xl font-bold leading-tight sm:text-3xl">{invitation.title}</h1>
        <p className="mt-5 whitespace-pre-line leading-7 text-slate-300">{invitation.description}</p>
        {invitation.requirements && <div className="mt-7 border-t border-white/10 pt-6">
          <h2 className="text-sm font-semibold text-white">Lo que buscamos</h2>
          <p className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-300">{invitation.requirements}</p>
        </div>}
        {invitation.expires_at && <p className="mt-8 flex items-center gap-2 text-xs text-slate-400">
          <Clock3 size={15} /> Enlace vigente hasta {new Date(invitation.expires_at).toLocaleDateString()}
        </p>}
      </section>

      <section className="p-5 sm:p-8 lg:p-10">
        <p className="text-sm font-semibold text-red-700">Hola {invitation.candidate_name || ''}</p>
        <h2 className="mt-2 text-2xl font-bold text-slate-900">Completa tu postulación</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">Revisa o corrige tus datos y adjunta un CV actualizado. La postulación se crea sólo cuando envías este formulario.</p>
        {error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        <form onSubmit={submit} className="mt-7 space-y-4">
          <label className="block text-sm font-medium text-slate-700">Nombre completo
            <input required className="mt-1 w-full rounded-xl border border-slate-300 p-3 outline-none transition focus:border-red-700 focus:ring-2 focus:ring-red-100" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-slate-700">Correo electrónico
              <input required type="email" className="mt-1 w-full rounded-xl border border-slate-300 p-3 outline-none transition focus:border-red-700 focus:ring-2 focus:ring-red-100" value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label className="block text-sm font-medium text-slate-700">Teléfono
              <input className="mt-1 w-full rounded-xl border border-slate-300 p-3 outline-none transition focus:border-red-700 focus:ring-2 focus:ring-red-100" value={phone} onChange={(event) => setPhone(event.target.value)} />
            </label>
          </div>
          <label className="block rounded-xl border-2 border-dashed border-slate-300 p-4 text-sm font-medium text-slate-700 transition hover:border-red-300">
            <span className="flex items-center gap-2"><FileText size={18} /> {file ? file.name : 'Seleccionar CV actualizado'}</span>
            <span className="mt-1 block text-xs font-normal text-slate-500">Un archivo PDF o Word (.doc o .docx), máximo 3 MB.</span>
            <input required className="mt-3 block w-full text-sm" type="file" accept={CV_ACCEPT} onChange={(event) => {
              const selection = selectSingleCv(event.target.files);
              setFile(selection.file);
              setFileError(selection.error);
              if (selection.error) event.target.value = '';
            }} />
          </label>
          {fileError && <p role="alert" className="text-sm font-medium text-red-700">{fileError}</p>}
          <label className="flex gap-3 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
            <input required type="checkbox" className="mt-1 h-4 w-4 accent-red-700" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
            <span><strong className="flex items-center gap-1"><ShieldCheck size={16} /> Consentimiento</strong> Autorizo el tratamiento de mis datos exclusivamente para esta postulación.</span>
          </label>
          <button disabled={submitting || !file || !consent} className="w-full rounded-xl bg-red-700 p-3.5 font-bold text-white shadow-sm transition hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-50">
            {submitting ? <InlineSpinner label="Procesando postulación…" /> : 'Confirmar y postular'}
          </button>
        </form>
      </section>
    </div>
  </main>;
}
