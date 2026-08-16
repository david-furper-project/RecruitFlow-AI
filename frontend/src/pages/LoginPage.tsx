import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { Lock, Mail, AlertCircle, CheckCircle2 } from 'lucide-react';

// Validación de política de contraseña (cliente)
const PASSWORD_MIN_LEN = 12;
const PASSWORD_MAX_LEN = 128;

interface PasswordRequirement {
  label: string;
  regex: RegExp;
  met: boolean;
}

function validatePasswordPolicy(password: string, email: string): PasswordRequirement[] {
  const requirements: PasswordRequirement[] = [
    { label: 'Mínimo 12 caracteres', regex: new RegExp(`.{${PASSWORD_MIN_LEN},}`), met: false },
    { label: 'Al menos una mayúscula', regex: /[A-ZÁÉÍÓÚÑ]/, met: false },
    { label: 'Al menos una minúscula', regex: /[a-záéíóúñ]/, met: false },
    { label: 'Al menos un número', regex: /\d/, met: false },
  ];

  // Validar cada requisito
  requirements.forEach((req) => {
    req.met = req.regex.test(password);
  });

  // Validar que no contenga email
  const emailLocal = email.split('@')[0].toLowerCase();
  if (emailLocal && password.toLowerCase().includes(emailLocal)) {
    requirements.push({
      label: 'No contiene su correo',
      regex: new RegExp(''),
      met: false,
    });
  }

  return requirements;
}

export default function LoginPage() {
  const [email, setEmail] = useState('admin@ejemplo.com');
  const [password, setPassword] = useState('Admin123456');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showRequirements, setShowRequirements] = useState(false);

  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);

  const passwordRequirements = validatePasswordPolicy(password, email);
  const allRequirementsMet = passwordRequirements.every((r) => r.met);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        if (response.status === 423) {
          setError('Cuenta bloqueada temporalmente. Intente en unos minutos.');
        } else if (response.status === 401) {
          setError('Credenciales inválidas.');
        } else {
          setError(data.detail || 'Error en el login');
        }
        return;
      }

      // Guardar en el store
      login(data.access_token, {
        id: data.user.id,
        email: data.user.email,
        role: data.user.role,
      });

      // Redirigir al dashboard del reclutador
      navigate('/recruiter');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-lg shadow-xl p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">PRI MVP</h1>
            <p className="text-gray-600">Portal de Reclutadores (Bloque 6)</p>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-6">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-3 text-gray-400" size={20} />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@ejemplo.com"
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                  Contraseña
                </label>
                <button
                  type="button"
                  onClick={() => setShowRequirements(!showRequirements)}
                  className="text-xs text-indigo-600 hover:text-indigo-700"
                >
                  {showRequirements ? 'Ocultar' : 'Ver'} requisitos
                </button>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-3 text-gray-400" size={20} />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-12 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? '👁️' : '🚫'}
                </button>
              </div>

              {/* Password Requirements */}
              {showRequirements && (
                <div className="mt-3 bg-gray-50 rounded p-3 space-y-2">
                  {passwordRequirements.map((req, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs">
                      {req.met ? (
                        <CheckCircle2 size={16} className="text-green-500" />
                      ) : (
                        <AlertCircle size={16} className="text-gray-300" />
                      )}
                      <span className={req.met ? 'text-green-700' : 'text-gray-600'}>
                        {req.label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Error message */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-700 text-sm">{error}</p>
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded-lg transition-colors"
            >
              {loading ? 'Ingresando...' : 'Ingresar'}
            </button>
          </form>

          {/* Demo credentials info */}
          <div className="mt-8 pt-6 border-t border-gray-200">
            <p className="text-xs text-gray-500 mb-3 font-semibold">CREDENCIALES DE DEMO</p>
            <div className="bg-gray-50 rounded p-3 space-y-2">
              <p className="text-xs text-gray-600">
                <span className="font-medium">Email:</span> admin@ejemplo.com
              </p>
              <p className="text-xs text-gray-600">
                <span className="font-medium">Contraseña:</span> Admin123456
              </p>
              <p className="text-xs text-gray-500 mt-2">
                ⚠️ Cumple política Bloque 6: 12+ caracteres, mayúscula, minúscula, número
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-gray-600 text-sm">
          <p>Plataforma de Reclutamiento Inteligente (PRI)</p>
        </div>
      </div>
    </div>
  );
}
