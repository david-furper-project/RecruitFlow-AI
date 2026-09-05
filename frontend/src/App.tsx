import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import CandidateDashboard from './pages/CandidateDashboard';
import RecruiterDashboard from './pages/RecruiterDashboard';
import LoginPage from './pages/LoginPage';
import SourcingInvitationPage from './pages/SourcingInvitationPage';
import { LogOut, User, Briefcase, ArrowRight } from 'lucide-react';

function Navigation() {
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuthStore();
  
  // No mostrar navegación en login
  if (
    location.pathname === '/login'
    || location.pathname.startsWith('/invitations/')
    || location.pathname.startsWith('/postulacion/')
  ) {
    return null;
  }
  
  return (
    <nav className="sticky top-0 z-40 flex min-w-0 items-center justify-between gap-2 border-b border-gray-100 bg-white/90 p-3 backdrop-blur-md transition-all sm:px-6 lg:px-8">
      <Link to="/" className="flex-shrink-0 text-xl font-extrabold tracking-tight transition-transform hover:scale-[1.02] sm:text-2xl">
        <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">PRI</span>
      </Link>
      
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-4">
        {isAuthenticated && user?.role === 'recruiter' && !location.pathname.startsWith('/candidate') && (
          <div className="flex gap-1 sm:gap-2">
            <Link 
              to="/recruiter" 
              className={`rounded-full px-3 py-2 text-sm font-medium transition-all duration-300 sm:px-5 ${location.pathname.includes('recruiter') ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              Dashboard
            </Link>
          </div>
        )}
        
        {!isAuthenticated && location.pathname !== '/' && (
          <div className="flex min-w-0 gap-1 sm:gap-2">
            <Link 
              to="/candidate" 
              className={`rounded-full px-3 py-2 text-sm font-medium transition-all duration-300 sm:px-5 ${location.pathname.includes('candidate') ? 'bg-blue-50 text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              <span className="sm:hidden">Empleos</span><span className="hidden sm:inline">Vista Candidato</span>
            </Link>
            <Link 
              to="/login" 
              className={`rounded-full px-3 py-2 text-sm font-medium transition-all duration-300 sm:px-5 ${location.pathname.includes('login') ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              <span className="sm:hidden">Ingresar</span><span className="hidden sm:inline">Login Reclutador</span>
            </Link>
          </div>
        )}
        
        {isAuthenticated && !location.pathname.startsWith('/candidate') && (
          <div className="ml-1 flex min-w-0 items-center gap-2 border-l border-gray-100 pl-2 sm:ml-2 sm:gap-4 sm:pl-4">
            <span className="hidden max-w-48 truncate text-sm font-medium text-gray-700 sm:block">{user?.email}</span>
            <button
              onClick={() => {
                logout();
                window.location.href = '/login';
              }}
              aria-label="Cerrar sesión"
              className="flex flex-shrink-0 items-center gap-2 rounded-full bg-red-50 p-2.5 text-sm font-medium text-red-600 transition-all hover:bg-red-100 hover:shadow-sm sm:px-4 sm:py-2"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">Salir</span>
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

// Componente para proteger rutas
function ProtectedRoute({ element }: { element: React.ReactNode }) {
  const { isAuthenticated, user } = useAuthStore();
  
  if (!isAuthenticated || user?.role !== 'recruiter') {
    return <Navigate to="/login" replace />;
  }
  
  return <>{element}</>;
}

function App() {
  const { isAuthenticated } = useAuthStore();
  
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-[#f8fafc] font-sans selection:bg-indigo-100 selection:text-indigo-900">
        <Navigation />
        <div className="flex-1">
          <Routes>
            {/* Login */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/invitations/:token" element={<SourcingInvitationPage />} />
            
            {/* Home - Redirecciona según autenticación */}
            <Route path="/" element={
              isAuthenticated ? (
                <Navigate to="/recruiter" replace />
              ) : (
                <div className="relative flex min-h-[85dvh] flex-col items-center justify-center overflow-hidden px-4 py-10 sm:py-14">
                  {/* Decorative background blobs */}
                  <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob"></div>
                  <div className="absolute top-0 right-1/4 w-96 h-96 bg-indigo-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>
                  <div className="absolute -bottom-32 left-1/2 w-96 h-96 bg-purple-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-4000"></div>

                  <div className="max-w-4xl w-full text-center space-y-6 relative z-10 animate-fade-in-up">
                    <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-gray-900 sm:text-5xl md:text-6xl lg:text-7xl">
                      Reclutamiento <br/>
                      <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
                        inteligente y simple
                      </span>
                    </h1>
                    <p className="mx-auto max-w-2xl text-base font-light leading-relaxed text-gray-500 sm:text-lg md:text-xl">
                      Conectamos el mejor talento con las oportunidades ideales. <span className="block sm:inline">Selecciona tu perfil para comenzar tu experiencia.</span>
                    </p>
                    
                    <div className="mx-auto grid max-w-2xl gap-4 pt-8 sm:gap-6 sm:pt-10 md:grid-cols-2">
                      {/* Candidato Card */}
                      <Link 
                        to="/candidate" 
                        className="group relative flex flex-col items-center overflow-hidden rounded-3xl border border-gray-100 bg-white p-6 text-center shadow-sm transition-all duration-500 hover:-translate-y-2 hover:border-blue-100 hover:shadow-xl sm:p-8"
                      >
                        <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                        <div className="bg-blue-50 p-5 rounded-2xl mb-6 group-hover:scale-110 group-hover:bg-blue-100 transition-all duration-500">
                          <User className="w-8 h-8 text-blue-600" />
                        </div>
                        <h3 className="text-2xl font-bold text-gray-900 mb-3 tracking-tight">Soy Candidato</h3>
                        <p className="text-gray-500 mb-8 text-sm leading-relaxed">Busca oportunidades que se adapten a tu perfil y gestiona tu carrera profesional.</p>
                        <span className="inline-flex items-center text-blue-600 font-semibold group-hover:gap-2 transition-all">
                          Explorar ofertas <ArrowRight className="w-4 h-4 ml-1" />
                        </span>
                      </Link>

                      {/* Reclutador Card */}
                      <Link 
                        to="/login" 
                        className="group relative flex flex-col items-center overflow-hidden rounded-3xl border border-gray-100 bg-white p-6 text-center shadow-sm transition-all duration-500 hover:-translate-y-2 hover:border-indigo-100 hover:shadow-xl sm:p-8"
                      >
                        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                        <div className="bg-indigo-50 p-5 rounded-2xl mb-6 group-hover:scale-110 group-hover:bg-indigo-100 transition-all duration-500">
                          <Briefcase className="w-8 h-8 text-indigo-600" />
                        </div>
                        <h3 className="text-2xl font-bold text-gray-900 mb-3 tracking-tight">Soy Reclutador</h3>
                        <p className="text-gray-500 mb-8 text-sm leading-relaxed">Publica ofertas, evalúa perfiles con IA y encuentra al candidato perfecto.</p>
                        <span className="inline-flex items-center text-indigo-600 font-semibold group-hover:gap-2 transition-all">
                          Ir al Dashboard <ArrowRight className="w-4 h-4 ml-1" />
                        </span>
                      </Link>
                    </div>
                  </div>
                </div>
              )
            } />
            
            {/* Candidate Dashboard - sin protección */}
            <Route path="/candidate" element={<CandidateDashboard />} />
            <Route path="/postulacion/:offerPublicId" element={<CandidateDashboard />} />
            
            {/* Recruiter Dashboard - protegido */}
            <Route path="/recruiter" element={
              <ProtectedRoute element={<RecruiterDashboard />} />
            } />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
