
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import CandidateDashboard from './pages/CandidateDashboard';
import RecruiterDashboard from './pages/RecruiterDashboard';

function Navigation() {
  const location = useLocation();
  
  return (
    <nav className="bg-card shadow-sm border-b p-4 flex justify-between items-center px-8 sticky top-0 z-10">
      <div className="font-bold text-2xl text-primary tracking-tight">PRI <span className="text-gray-800 font-medium text-lg">MVP</span></div>
      <div className="flex gap-4 bg-gray-50 p-1 rounded-lg border border-gray-100">
        <Link 
          to="/candidate" 
          className={`px-4 py-2 rounded-md font-medium transition-colors ${location.pathname.includes('candidate') ? 'bg-white shadow-sm text-primary' : 'text-gray-500 hover:text-gray-900'}`}
        >
          Vista Candidato
        </Link>
        <Link 
          to="/recruiter" 
          className={`px-4 py-2 rounded-md font-medium transition-colors ${location.pathname.includes('recruiter') ? 'bg-white shadow-sm text-primary' : 'text-gray-500 hover:text-gray-900'}`}
        >
          Vista Reclutador
        </Link>
      </div>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-background">
        <Navigation />
        <div className="flex-1">
          <Routes>
            <Route path="/" element={
              <div className="p-8 text-center mt-20">
                <h2 className="text-4xl font-bold text-gray-800 mb-4">Bienvenido a la Plataforma de Reclutamiento</h2>
                <p className="text-gray-500 text-lg">Selecciona un rol en el menú superior para comenzar.</p>
              </div>
            } />
            <Route path="/candidate" element={<CandidateDashboard />} />
            <Route path="/recruiter" element={<RecruiterDashboard />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
