
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import CandidateDashboard from './pages/CandidateDashboard';
import RecruiterDashboard from './pages/RecruiterDashboard';
import LoginPage from './pages/LoginPage';
import { LogOut } from 'lucide-react';

function Navigation() {
  const location = useLocation();
  const { isAuthenticated, user, logout } = useAuthStore();
  
  // No mostrar navegación en login
  if (location.pathname === '/login') {
    return null;
  }
  
  return (
    <nav className="bg-card shadow-sm border-b p-4 flex justify-between items-center px-8 sticky top-0 z-10">
      <div className="font-bold text-2xl text-primary tracking-tight">PRI <span className="text-gray-800 font-medium text-lg">MVP</span></div>
      <div className="flex gap-4 items-center">
        {isAuthenticated && user?.role === 'recruiter' && (
          <div className="flex gap-4 bg-gray-50 p-1 rounded-lg border border-gray-100">
            <Link 
              to="/recruiter" 
              className={`px-4 py-2 rounded-md font-medium transition-colors ${location.pathname.includes('recruiter') ? 'bg-white shadow-sm text-primary' : 'text-gray-500 hover:text-gray-900'}`}
            >
              Dashboard
            </Link>
          </div>
        )}
        
        {!isAuthenticated && (
          <div className="flex gap-4 bg-gray-50 p-1 rounded-lg border border-gray-100">
            <Link 
              to="/candidate" 
              className={`px-4 py-2 rounded-md font-medium transition-colors ${location.pathname.includes('candidate') ? 'bg-white shadow-sm text-primary' : 'text-gray-500 hover:text-gray-900'}`}
            >
              Vista Candidato
            </Link>
            <Link 
              to="/login" 
              className={`px-4 py-2 rounded-md font-medium transition-colors ${location.pathname.includes('login') ? 'bg-white shadow-sm text-primary' : 'text-gray-500 hover:text-gray-900'}`}
            >
              Login Reclutador
            </Link>
          </div>
        )}
        
        {isAuthenticated && (
          <div className="flex gap-4 items-center ml-4">
            <span className="text-sm text-gray-600">{user?.email}</span>
            <button
              onClick={() => {
                logout();
                window.location.href = '/login';
              }}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors"
            >
              <LogOut size={18} />
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
      <div className="min-h-screen flex flex-col bg-background">
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
                <div className="p-8 text-center mt-20">
                  <h2 className="text-4xl font-bold text-gray-800 mb-4">Bienvenido a la Plataforma de Reclutamiento</h2>
                  <p className="text-gray-500 text-lg mb-8">Selecciona un rol en el menú superior para comenzar.</p>
                  <Link 
                    to="/login" 
                    className="inline-block bg-indigo-600 text-white px-6 py-3 rounded-lg hover:bg-indigo-700 transition-colors"
                  >
                    Ir al Login de Reclutador
                  </Link>
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
