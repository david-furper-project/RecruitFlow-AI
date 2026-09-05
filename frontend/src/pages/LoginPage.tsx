import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { Lock, Mail, AlertCircle, CheckCircle2 } from 'lucide-react';

// Validación de política de contraseña (cliente)
const PASSWORD_MIN_LEN = 12;
const LOGIN_TIMEOUT_MS = 12_000;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || `http://${window.location.hostname || 'localhost'}:8000/api`;

async function readApiResponse(response: Response): Promise<Record<string, unknown>> {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const message = await response.text();
    throw new Error(message || `El servidor respondió con estado ${response.status}.`);
  }
  return response.json() as Promise<Record<string, unknown>>;
}

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

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError('');

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      const data = await readApiResponse(response);

      if (!response.ok) {
        if (response.status === 423) {
          setError('Cuenta bloqueada temporalmente. Intente en unos minutos.');
        } else if (response.status === 401) {
          setError('Credenciales inválidas.');
        } else {
          setError(typeof data.detail === 'string' ? data.detail : 'Error en el login');
        }
        return;
      }

      if (typeof data.access_token !== 'string' || !data.user || typeof data.user !== 'object') {
        throw new Error('La respuesta del servidor no contiene una sesión válida.');
      }
      const user = data.user as { id?: unknown; email?: unknown; role?: unknown };
      if (typeof user.id !== 'number' || typeof user.email !== 'string' || typeof user.role !== 'string') {
        throw new Error('La respuesta del servidor no contiene un usuario válido.');
      }

      // Guardar en el store
      login(data.access_token, {
        id: user.id,
        email: user.email,
        role: user.role,
      });

      // Redirigir al dashboard del reclutador
      navigate('/recruiter', { replace: true });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setError('El servidor tardó demasiado en responder. Verifica que el backend y PostgreSQL estén activos.');
      } else if (err instanceof TypeError) {
        setError(`No se pudo conectar con la API en ${API_BASE_URL}. Verifica que el backend esté activo.`);
      } else {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      }
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen min-h-[100dvh] items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-3 sm:p-4">
      <div className="w-full max-w-md">
        <div className="rounded-2xl bg-white p-5 shadow-xl sm:p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="mb-2 text-2xl font-bold text-gray-900 sm:text-3xl">PRI MVP</h1>
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
