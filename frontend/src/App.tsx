import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import CandidateDashboard from './pages/CandidateDashboard';
import RecruiterDashboard from './pages/RecruiterDashboard';
import LoginPage from './pages/LoginPage';
import { LogOut, User, Briefcase, ArrowRight } from 'lucide-react';

function Navigation() {
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuthStore();
  
  // No mostrar navegación en login
  if (location.pathname === '/login') {
    return null;
  }
  
  return (
    <nav className="bg-white/80 backdrop-blur-md border-b border-gray-100 p-4 flex justify-between items-center px-8 sticky top-0 z-10 transition-all">
      <Link to="/" className="font-extrabold text-2xl tracking-tight transition-transform hover:scale-[1.02]">
        <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">PRI</span>
      </Link>
      
      <div className="flex gap-4 items-center">
        {isAuthenticated && user?.role === 'recruiter' && (
          <div className="flex gap-2">
            <Link 
              to="/recruiter" 
              className={`px-5 py-2 rounded-full font-medium text-sm transition-all duration-300 ${location.pathname.includes('recruiter') ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              Dashboard
            </Link>
          </div>
        )}
        
        {!isAuthenticated && location.pathname !== '/' && (
          <div className="flex gap-2">
            <Link 
              to="/candidate" 
              className={`px-5 py-2 rounded-full font-medium text-sm transition-all duration-300 ${location.pathname.includes('candidate') ? 'bg-blue-50 text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              Vista Candidato
            </Link>
            <Link 
              to="/login" 
              className={`px-5 py-2 rounded-full font-medium text-sm transition-all duration-300 ${location.pathname.includes('login') ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
            >
              Login Reclutador
            </Link>
          </div>
        )}
        
        {isAuthenticated && (
          <div className="flex gap-4 items-center pl-4 ml-2 border-l border-gray-100">
            <span className="text-sm font-medium text-gray-700">{user?.email}</span>
            <button
              onClick={() => {
                logout();
                window.location.href = '/login';
              }}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 text-sm font-medium rounded-full hover:bg-red-100 hover:shadow-sm transition-all"
            >
              <LogOut size={16} />
              Salir
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
            
            {/* Home - Redirecciona según autenticación */}
            <Route path="/" element={
              isAuthenticated ? (
                <Navigate to="/recruiter" replace />
              ) : (
                <div className="flex flex-col items-center justify-center min-h-[85vh] px-4 relative overflow-hidden">
                  {/* Decorative background blobs */}
                  <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob"></div>
                  <div className="absolute top-0 right-1/4 w-96 h-96 bg-indigo-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>
                  <div className="absolute -bottom-32 left-1/2 w-96 h-96 bg-purple-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-4000"></div>

                  <div className="max-w-4xl w-full text-center space-y-6 relative z-10 animate-fade-in-up">
                    <h1 className="text-5xl md:text-6xl lg:text-7xl font-extrabold text-gray-900 tracking-tight leading-tight">
                      Reclutamiento <br/>
                      <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
                        inteligente y simple
                      </span>
                    </h1>
                    <p className="text-lg md:text-xl text-gray-500 max-w-2xl mx-auto font-light leading-relaxed">
                      Conectamos el mejor talento con las oportunidades ideales. <br/> Selecciona tu perfil para comenzar tu experiencia.
                    </p>
                    
                    <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto pt-10">
                      {/* Candidato Card */}
                      <Link 
                        to="/candidate" 
                        className="group relative bg-white p-8 rounded-3xl shadow-sm border border-gray-100 hover:shadow-xl hover:border-blue-100 transition-all duration-500 hover:-translate-y-2 overflow-hidden flex flex-col items-center text-center"
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
                        className="group relative bg-white p-8 rounded-3xl shadow-sm border border-gray-100 hover:shadow-xl hover:border-indigo-100 transition-all duration-500 hover:-translate-y-2 overflow-hidden flex flex-col items-center text-center"
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
