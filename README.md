# PRI MVP - Plataforma de Reclutamiento Inteligente

PRI MVP es una plataforma para gestionar procesos de reclutamiento con:

- captura de candidatos y CV
- ofertas de trabajo
- matching por similitud semántica con embeddings
- evaluación y scoring de candidatos
- decisiones y notificaciones
- dashboard web para candidato y reclutador

La aplicación está construida con:

- Backend: FastAPI + SQLModel + PostgreSQL 15 + pgvector
- Frontend: React + Vite + TypeScript + Tailwind
- Base de datos: PostgreSQL con extensión pgvector
- Contenedores: Docker Compose

---

## 1. Requisitos previos

Necesitas tener instalado en tu máquina:

- Git
- Docker
- Docker Compose
- Python 3.11 o superior
- Node.js 18 o superior
- npm

Verifica:

```bash
git --version
docker --version
docker compose version
python --version
node --version
npm --version
```

---

## 2. Clonar el proyecto

```bash
git clone <url-del-repositorio>
cd pri-mvp
```

---

## 3. Configuración de la base de datos con Docker

El proyecto usa PostgreSQL 15 con pgvector. La base de datos se levanta con Docker.

Desde la raíz del proyecto:

```bash
docker compose up -d db
```

Esto levanta un contenedor PostgreSQL con:

- usuario: `postgres`
- password: `postgres`
- base de datos: `pri_db`
- puerto: `5432`

Puedes verificar que esté corriendo con:

```bash
docker compose ps
```

---

## 4. Instalación del backend

Ve a la carpeta del backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Variables de entorno

El proyecto usa la configuración por defecto en `backend/app/core/config.py`.

Si quieres configurar valores específicos, puedes crear un archivo `.env` dentro de `backend/` con contenido similar:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pri_db
PROJECT_NAME=Plataforma de Reclutamiento Inteligente (PRI)
GEMINI_API_KEY=tu_api_key
OPENAI_API_KEY=tu_api_key_opcional
SENDGRID_API_KEY=tu_sendgrid_key
SENDER_EMAIL=noreply@tu-dominio.com
```

> El proyecto ya tiene valores por defecto para desarrollo local. En muchos casos, no necesitas crear `.env` inicialmente.

### Inicializar la base de datos

Desde `backend/`:

```bash
python recreate_db.py
```

Esto recrea las tablas y configura la extensión `vector` junto con los índices y validaciones necesarias.

### Iniciar el backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

La API queda disponible en:

- http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Redoc: http://localhost:8000/redoc

### Verificar salud del backend

```bash
curl http://localhost:8000/api/health
```

Debe devolver un JSON con `status: "ok"`.

---

## 5. Instalación del frontend

Desde la raíz del proyecto:

```bash
cd frontend
npm install
```

### Iniciar el frontend

```bash
npm run dev
```

El frontend queda disponible en:

- http://localhost:5173

---

## 6. Cómo correr todo junto

En un terminal:

```bash
cd /Users/dfurniel/pri-mvp
docker compose up -d db
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

En otro terminal:

```bash
cd /Users/dfurniel/pri-mvp/frontend
npm install
npm run dev
```

Con esto tendrás:

- backend en `localhost:8000`
- frontend en `localhost:5173`
- PostgreSQL en `localhost:5432`

---

## 7. Arquitectura del proyecto

### Backend

Los componentes principales están en `backend/app`:

- `app/main.py`: arrancador principal de FastAPI
- `app/api/`: endpoints de la API
- `app/models/__init__.py`: modelos SQLModel de dominio
- `app/db/session.py`: conexión a Postgres y configuración inicial
- `app/services/`: lógica de negocio: embeddings, parsing, scoring, notificaciones, almacenamiento, IA
- `app/core/config.py`: configuración central de la app

### Frontend

La parte web está en `frontend/src`:

- `src/App.tsx`: navegación principal y routing
- `src/pages/CandidateDashboard.tsx`: flujo de postulante
- `src/pages/RecruiterDashboard.tsx`: vista del reclutador
- `src/api/client.ts`: cliente para consumir la API del backend

---

## 8. Cómo funciona la aplicación

### Flujo del candidato

1. El candidato entra a la vista de postulante.
2. Busca una oferta disponible.
3. Completa sus datos.
4. Sube su CV (PDF).
5. El backend extrae texto del CV.
6. Se genera un embedding para comparar el perfil con la oferta.
7. El sistema crea una aplicación y guarda el perfil del candidato.
8. El candidato recibe confirmación visual de que su postulación fue enviada.

### Flujo del reclutador

1. El reclutador accede a la vista de reclutador.
2. Puede crear ofertas de trabajo.
3. Puede consultar candidatos por similitud con una oferta.
4. Puede revisar perfil, stack técnico y match score.
5. Puede cerrar ofertas y definir decisiones.

### Matching y scoring

La lógica usa embeddings vectoriales en PostgreSQL con pgvector:

- cada `CandidateProfile` tiene un `embedding`
- cada `JobOffer` tiene un `embedding`
- el sistema calcula similitud por distancia coseno
- se devuelve un ranking de candidatos por afinidad con la oferta

### Reglas de integridad del sistema

El proyecto considera estas reglas:

- PostgreSQL 15 + pgvector
- no se usa Redis
- `user.email` debe ser único
- no se permite sobreescribir historial de `evaluation` y `decision`
- `application.status` se deriva de la última decisión
- no se debe introducir nacionalidad en scoring

---

## 9. Endpoints principales

La API expone endpoints para:

- candidatos
- ofertas
- reclutador
- scoring
- privacidad
- salud

### Ejemplos útiles

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/offers/
curl http://localhost:8000/api/candidates/apply -F "full_name=Ana" -F "email=ana@test.com" -F "offer_id=1" -F "file=@/ruta/al/cv.pdf"
```

---

## 10. Estructura del repositorio

```text
pri-mvp/
├── backend/
│   ├── app/
│   ├── requirements.txt
│   ├── recreate_db.py
│   └── tests/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── docs/
├── .gitignore
├── AGENTS.md
├── .github/
├── README.md
└── ...
```

---

## 11. Solución de problemas comunes

### El backend no conecta a la DB

Verifica que Docker esté corriendo:

```bash
docker compose ps
```

Y que la base esté escuchando en `localhost:5432`.

### Error de `pgvector`

Ejecuta:

```bash
cd backend
source .venv/bin/activate
python recreate_db.py
```

### El frontend no carga la API

Asegúrate de que el backend esté levantado en `http://localhost:8000`.

### El frontend se ve vacío

Confirma que estás en la carpeta `frontend` y que ejecutaste:

```bash
npm install
npm run dev
```

---

## 12. Recomendaciones para desarrollo

- Usa `docker compose up -d db` para la base de datos local.
- Mantén el backend y frontend en terminales separadas.
- Revisa Swagger en `http://localhost:8000/docs` cuando quieras probar endpoints.
- Haz pruebas antes de nuevos cambios importantes.

---

## 13. Estado actual del proyecto

Este repositorio está orientado a un MVP funcional de reclutamiento con:

- flujo de captura de CV
- ofertas y empresas
- matching por embeddings
- dashboard de candidato y reclutador
- decisiones y notificaciones
- soporte base para privacidad y auditoría

---

## 14. Contribución

Si quieres colaborar:

1. crea una rama por feature o bloque
2. desarrolla la parte correspondiente
3. valida localmente
4. abre un PR con una descripción clara

---

## 15. Licencia

Este proyecto se usa con fines de desarrollo y validación del MVP. Ajusta la licencia según el uso final que decidas darle.
