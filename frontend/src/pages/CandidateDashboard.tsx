import { useState, useEffect } from 'react';
import { UploadCloud, CheckCircle, Briefcase, MapPin, DollarSign, ChevronLeft } from 'lucide-react';
import { motion } from 'framer-motion';
import { apiClient } from '../api/client';

export default function CandidateDashboard() {
  const [offers, setOffers] = useState<any[]>([]);
  const [selectedOffer, setSelectedOffer] = useState<any | null>(null);
  
  const [file, setFile] = useState<File | null>(null);
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

  useEffect(() => {
    apiClient.getOffers().then(data => {
      setOffers(data.filter((o: any) => o.status !== 'closed'));
    }).catch(console.error);
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !selectedOffer) return;
    if (!acceptedTerms) {
      alert("Debes aceptar los Términos y Condiciones para continuar.");
      return;
    }
    
    setStatus('uploading');
    try {
      await apiClient.applyForJob(selectedOffer.id, formData, file);
      setStatus('success');
    } catch (error) {
      console.error(error);
      setStatus('idle');
      alert("Error al procesar el archivo. ¿Está encendido el Backend?");
    }
  };

  if (status === 'success') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
        <motion.div 
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          className="flex flex-col items-center bg-white p-12 rounded-lg shadow-md border border-gray-200"
        >
          <CheckCircle size={64} className="mb-4 text-[#b91c1c]" />
          <h2 className="text-2xl font-bold text-[#b91c1c] mb-2">¡Postulación Enviada!</h2>
          <p className="text-gray-600 text-center max-w-md">Tu currículum ha sido recibido exitosamente. La empresa revisará tu perfil a la brevedad.</p>
        </motion.div>
      </div>
    );
  }

  if (!selectedOffer) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center py-12 px-4 font-sans">
        <div className="max-w-4xl w-full">
          <h1 className="text-3xl font-bold text-[#b91c1c] mb-2 text-center">Portal de Empleos</h1>
          <p className="text-gray-600 mb-8 text-center">Encuentra tu próxima gran oportunidad laboral</p>
          <div className="grid gap-4">
            {offers.length === 0 ? (
              <p className="text-center text-gray-500 py-12">No hay vacantes disponibles en este momento.</p>
            ) : (
              offers.map(offer => (
                <div key={offer.id} className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow cursor-pointer" onClick={() => setSelectedOffer(offer)}>
                  <h2 className="text-xl font-bold text-[#b91c1c] mb-1">{offer.title}</h2>
                  <p className="text-gray-800 font-medium mb-3">{offer.company?.name || 'Empresa Confidencial'}</p>
                  <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
                    <span className="flex items-center gap-1"><Briefcase size={16}/> {offer.seniority}</span>
                    <span className="flex items-center gap-1"><MapPin size={16}/> Remoto / Presencial</span>
                    <span className="flex items-center gap-1"><DollarSign size={16}/> {offer.salary_range}</span>
                  </div>
                  <p className="text-gray-600 text-sm line-clamp-2">{offer.description}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center py-12 px-4 font-sans">
      <div className="max-w-3xl w-full">
        <button onClick={() => setSelectedOffer(null)} className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6 font-medium transition-colors">
          <ChevronLeft size={20} /> Volver a vacantes
        </button>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="bg-[#b91c1c] p-8 text-white">
            <h1 className="text-3xl font-bold mb-1">Postular a {selectedOffer.title}</h1>
            <p className="text-red-100 font-medium mb-2 text-lg">En {selectedOffer.company?.name || 'Empresa Confidencial'}</p>
            <p className="text-red-100 opacity-90">Por favor, completa tus datos y sube tu currículum actualizado.</p>
          </div>

          <form onSubmit={handleUpload} className="p-8">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Nombre *</label>
                <input required type="text" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="Ej. Juan" value={formData.nombre} onChange={e => setFormData({...formData, nombre: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Apellidos *</label>
                <input required type="text" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="Ej. Pérez" value={formData.apellido} onChange={e => setFormData({...formData, apellido: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Correo Electrónico *</label>
                <input required type="email" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="juan@ejemplo.com" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Teléfono *</label>
                <input required type="tel" className="w-full p-3 border border-gray-300 rounded-sm focus:outline-none focus:border-[#b91c1c] focus:ring-1 focus:ring-[#b91c1c] bg-gray-50" placeholder="+56 9 1234 5678" value={formData.telefono} onChange={e => setFormData({...formData, telefono: e.target.value})} />
              </div>
            </div>

            <div className="mb-8">
              <label className="block text-sm font-bold text-gray-700 mb-2">Currículum Vitae (PDF) *</label>
              <div className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center justify-center transition-colors ${file ? 'border-green-500 bg-green-50' : 'border-gray-300 bg-gray-50 hover:bg-gray-100'}`}>
                <UploadCloud size={48} className={file ? "text-green-500 mb-4" : "text-gray-400 mb-4"} />
                <p className="text-gray-700 font-medium mb-1">
                  {file ? file.name : "Arrastra tu CV aquí o haz clic para buscar"}
                </p>
                <p className="text-gray-500 text-sm mb-4">Solo formato PDF. Tamaño máximo 5MB.</p>
                <input 
                  type="file" 
                  accept=".pdf" 
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="hidden" 
                  id="cv-upload"
                  required
                />
                <label htmlFor="cv-upload" className="cursor-pointer bg-white border border-gray-300 text-gray-700 px-6 py-2 rounded-sm font-bold hover:bg-gray-50 transition-colors shadow-sm">
                  {file ? 'Cambiar archivo' : 'Seleccionar Archivo'}
                </label>
              </div>
            </div>

            <div className="mb-8 bg-gray-50 p-4 border border-gray-200 rounded-sm">
              <label className="flex items-start gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  className="mt-1 w-5 h-5 text-[#b91c1c] border-gray-300 rounded focus:ring-[#b91c1c]"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                />
                <span className="text-sm text-gray-700">
                  <span className="font-bold">Autorizo el tratamiento de mis datos personales.</span>
                  <br />
                  De acuerdo con la legislación vigente de protección de datos, consiento que la información proporcionada (incluyendo los datos contenidos en mi currículum) sea almacenada y tratada exclusivamente para fines de procesos de selección y reclutamiento por esta empresa.
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
              {status === 'uploading' ? 'Enviando Postulación...' : 'Enviar Postulación'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
