/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect } from 'react';
import { UploadCloud, CheckCircle, Briefcase, MapPin, DollarSign } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNavigate, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
  CANDIDATE_CV_ACCEPT,
  CANDIDATE_CV_VALIDATION,
  selectSingleCv,
  validateCvFile,
} from '../utils/cvUpload';
import { InlineSpinner, ProcessingOverlay } from '../components/ProcessingState';

export default function CandidateDashboard() {
  const navigate = useNavigate();
  const { offerPublicId } = useParams();
  const isDirectApplication = Boolean(offerPublicId);
  const [offers, setOffers] = useState<any[]>([]);
  const [selectedOffer, setSelectedOffer] = useState<any | null>(null);
  const [offerState, setOfferState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [offerError, setOfferError] = useState('');
  
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success'>('idle');

  // Form states to match the visual prototype
  const [formData, setFormData] = useState({
    nombre: '',
    apellido: '',
    email: '',
    telefono: '',
    pais: 'Chile',
    renta: ''
  });
  const [acceptedTerms, setAcceptedTerms] = useState(false);

  const updateFormField = (field: keyof typeof formData, value: string) => {
    setFormData(current => ({ ...current, [field]: value }));
    setFileError('');
  };

  useEffect(() => {
    setOfferState('loading');
    setOfferError('');
    if (offerPublicId) {
      apiClient.getPublicOffer(offerPublicId)
        .then(data => {
          setSelectedOffer(data);
          setOfferState('ready');
        })
        .catch(error => {
          setSelectedOffer(null);
          setOfferError(error instanceof Error ? error.message : 'La oferta no está disponible.');
          setOfferState('error');
        });
      return;
    }

    setSelectedOffer(null);
    apiClient.getOffers().then(data => {
      setOffers(data.filter((offer: any) => offer.status === 'open'));
      setOfferState('ready');
    }).catch(() => {
      setOfferError('No fue posible cargar las vacantes disponibles.');
      setOfferState('error');
    });
  }, [offerPublicId]);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !selectedOffer) return;
    const validationError = validateCvFile(file, CANDIDATE_CV_VALIDATION);
    if (validationError) {
      setFile(null);
      setFileError(validationError);
      return;
    }
    if (!acceptedTerms) {
      setFileError('Debes autorizar el tratamiento de tus datos personales para continuar.');
      return;
    }
    const fullName = `${formData.nombre} ${formData.apellido}`.trim();
    if (!fullName) {
      setFileError('El nombre es obligatorio.');
      return;
    }
    if (formData.renta && (!Number.isFinite(Number(formData.renta)) || Number(formData.renta) < 0)) {
      setFileError('La pretensión de renta debe ser numérica y no negativa.');
      return;
    }
    
    setFileError('');
    setStatus('uploading');
    try {
      await apiClient.applyForJob(selectedOffer.public_id, formData, file, acceptedTerms);
      setStatus('success');
    } catch (error) {
      setStatus('idle');
      setFileError(error instanceof Error ? error.message : 'No fue posible procesar el CV.');
    }
  };

  if (status === 'success') {
    return (
      <div className="flex min-h-screen min-h-[100dvh] flex-col items-center justify-center bg-gray-50 p-4">
        <motion.div 
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          className="flex w-full max-w-xl flex-col items-center rounded-2xl border border-gray-200 bg-white p-6 shadow-md sm:p-12"
        >
          <CheckCircle size={64} className="mb-4 text-[#b91c1c]" />
          <h2 className="mb-2 text-center text-2xl font-bold text-[#b91c1c]">¡Postulación Enviada!</h2>
          <p className="text-gray-600 text-center max-w-md">Tu currículum ha sido recibido exitosamente. La empresa revisará tu perfil a la brevedad.</p>
        </motion.div>
      </div>
    );
  }

  if (isDirectApplication && offerState === 'loading') {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-gray-50 p-4">
        <InlineSpinner label="Cargando oferta…" />
      </div>
    );
  }

  if (isDirectApplication && offerState === 'error') {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-gray-50 p-4">
        <div role="alert" className="w-full max-w-lg rounded-lg border border-red-200 bg-white p-6 text-center text-red-800 shadow-sm">
          <h1 className="mb-2 text-xl font-bold">Oferta no disponible</h1>
          <p>{offerError}</p>
        </div>
      </div>
    );
  }

  if (!selectedOffer) {
    return (
      <div className="flex min-h-screen min-h-[100dvh] flex-col items-center bg-gray-50 px-4 py-8 font-sans sm:py-12">
        <div className="max-w-4xl w-full">
          <h1 className="text-3xl font-bold text-[#b91c1c] mb-2 text-center">Portal de Empleos</h1>
          <p className="text-gray-600 mb-8 text-center">Encuentra tu próxima gran oportunidad laboral</p>
          <div className="grid gap-4">
            {offerState === 'loading' ? (
              <InlineSpinner label="Cargando vacantes…" />
            ) : offerState === 'error' ? (
              <p role="alert" className="py-12 text-center text-red-700">{offerError}</p>
            ) : offers.length === 0 ? (
              <p className="text-center text-gray-500 py-12">No hay vacantes disponibles en este momento.</p>
            ) : (
              offers.map(offer => (
                <button type="button" key={offer.public_id || offer.id} className="w-full cursor-pointer rounded-xl border border-gray-200 bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md sm:p-6" onClick={() => navigate(`/postulacion/${offer.public_id}`)}>
                  <h2 className="text-xl font-bold text-[#b91c1c] mb-1">{offer.title}</h2>
                  <p className="text-gray-800 font-medium mb-3">{offer.company?.name || 'Empresa Confidencial'}</p>
                  <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
                    <span className="flex items-center gap-1"><Briefcase size={16}/> {offer.seniority}</span>
                    <span className="flex items-center gap-1"><MapPin size={16}/> Remoto / Presencial</span>
                    <span className="flex items-center gap-1"><DollarSign size={16}/> {offer.salary_range}</span>
                  </div>
                  <p className="text-gray-600 text-sm line-clamp-2">{offer.description}</p>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen min-h-[100dvh] flex-col items-center bg-gray-50 px-3 py-6 font-sans sm:px-4 sm:py-12">
      {status === 'uploading' && <ProcessingOverlay title="Estamos procesando tu CV" description="Extraemos tu experiencia y registramos la postulación. Puede tardar unos segundos." />}
      <div className="max-w-3xl w-full">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="bg-[#b91c1c] p-5 text-white sm:p-8">
            <h1 className="mb-1 break-words text-2xl font-bold sm:text-3xl">Postular a {selectedOffer.title}</h1>
            <p className="text-red-100 font-medium mb-2 text-lg">En {selectedOffer.company?.name || 'Empresa Confidencial'}</p>
            <p className="text-red-100 opacity-90">Por favor, completa tus datos y sube tu currículum actualizado.</p>
          </div>

          <form onSubmit={handleUpload} className="p-5 sm:p-8">
            <div className="mb-8 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Nombre *</label>
                <input required type="text" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="Ej. Juan" value={formData.nombre} onChange={e => updateFormField('nombre', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Apellidos *</label>
                <input required type="text" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="Ej. Pérez" value={formData.apellido} onChange={e => updateFormField('apellido', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Correo Electrónico *</label>
                <input required type="email" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="juan@ejemplo.com" value={formData.email} onChange={e => updateFormField('email', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Teléfono (opcional)</label>
                <input type="tel" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="+56 9 1234 5678" value={formData.telefono} onChange={e => updateFormField('telefono', e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Pretensión de renta (opcional)</label>
                <input type="number" min="0" step="1" inputMode="numeric" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="Ej. 1500000" value={formData.renta} onChange={e => updateFormField('renta', e.target.value)} />
              </div>
            </div>

            <div className="mb-8">
              <label className="block text-sm font-bold text-gray-700 mb-2">Currículum Vitae *</label>
              <div className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors sm:p-10 ${file ? 'border-blue-300 bg-blue-50' : 'border-gray-300 bg-gray-50 hover:bg-gray-100'}`}>
                <UploadCloud size={48} className={file ? "text-blue-600 mb-4" : "text-gray-400 mb-4"} />
                <p className="mb-1 max-w-full break-all text-center font-medium text-gray-700">
                  {file ? file.name : "Arrastra tu CV aquí o haz clic para buscar"}
                </p>
                <p className="text-gray-500 text-sm mb-4">Un archivo PDF o Word (.doc o .docx). Tamaño máximo 3 MB.</p>
                <p className="mb-4 text-center text-xs text-gray-500">
                  {file
                    ? 'Archivo seleccionado. Validaremos su contenido al enviar.'
                    : 'Validaremos que sea un currículum, el nombre visible y, si contiene un correo, que coincida con el formulario.'}
                </p>
                <input 
                  type="file" 
                  accept={CANDIDATE_CV_ACCEPT}
                  onChange={(event) => {
                    const selection = selectSingleCv(event.target.files, CANDIDATE_CV_VALIDATION);
                    setFile(selection.file);
                    setFileError(selection.error);
                    setStatus('idle');
                    if (selection.error) event.target.value = '';
                  }}
                  onClick={(event) => {
                    event.currentTarget.value = '';
                  }}
                  className="hidden" 
                  id="cv-upload"
                />
                <label htmlFor="cv-upload" className="cursor-pointer rounded-sm border border-gray-300 bg-white px-4 py-2 text-center font-bold text-gray-700 shadow-sm transition-colors hover:bg-gray-50 sm:px-6">
                  {file ? 'Cambiar archivo' : 'Seleccionar Archivo'}
                </label>
              </div>
              {fileError && <p role="alert" aria-live="polite" className="mt-2 text-sm font-medium text-red-700">{fileError}</p>}
            </div>

            <div className="mb-8 bg-gray-50 p-4 border border-gray-200 rounded-sm">
              <label className="flex items-start gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  className="mt-1 w-5 h-5 text-[#b91c1c] border-gray-300 rounded focus:ring-[#b91c1c]"
                  checked={acceptedTerms}
                  onChange={(e) => {
                    setAcceptedTerms(e.target.checked);
                    setFileError('');
                  }}
                  required
                  aria-required="true"
                />
                <span className="text-sm text-gray-700">
                  <span className="font-bold">Autorizo el tratamiento de mis datos personales.</span>
                  <br />
                  De acuerdo con la legislación vigente de protección de datos, consiento que la información proporcionada, incluidos los datos contenidos en mi currículum, sea almacenada y tratada exclusivamente para fines de procesos de selección y reclutamiento por esta empresa.
                </span>
              </label>
            </div>

            <button 
              type="submit"
              disabled={status === 'uploading' || !file || !acceptedTerms}
              className={`w-full py-4 rounded-sm font-bold text-lg shadow-sm transition-colors ${
                status === 'uploading' || !file || !acceptedTerms
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed' 
                : 'bg-[#b91c1c] text-white hover:bg-red-800'
              }`}
            >
              {status === 'uploading' ? <InlineSpinner label="Procesando postulación…" /> : 'Enviar Postulación'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
