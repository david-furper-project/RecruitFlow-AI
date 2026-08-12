# Roadmap de Desarrollo (MVP)

El desarrollo del MVP de la Plataforma de Reclutamiento Inteligente se divide en las siguientes fases:

- [ ] **Fase 1: Setup Backend**
  - Configuración inicial del proyecto en FastAPI.
  - Configuración de la base de datos PostgreSQL y activación de la extensión `pgvector`.
  - Definición de modelos de base de datos usando SQLAlchemy/SQLModel (Usuarios, Candidatos, Ofertas, Postulaciones).

- [ ] **Fase 2: Endpoint subida de CVs y extracción de texto**
  - Integración con AWS S3 para almacenamiento de archivos PDF.
  - Creación de endpoints para la carga y descarga de CVs.
  - Procesamiento inicial para leer el texto de los PDFs.

- [ ] **Fase 3: Lógica IA**
  - Integración con LangChain y OpenAI API (GPT-4o-mini).
  - Procesamiento del texto extraído del CV en un formato estructurado.
  - Generación de embeddings para los perfiles y las ofertas de trabajo.
  - Implementación del sistema de scoring de similitud vectorial para el filtrado inteligente.

- [ ] **Fase 4: Setup Frontend**
  - Inicialización del proyecto con React + TypeScript + Tailwind CSS.
  - Desarrollo de la vista del Candidato (Postulación, visualización de estado, subida de documentos).
  - Desarrollo de la vista del Reclutador (Dashboard de ofertas, lista de candidatos rankeados, detalles del scoring).

- [ ] **Fase 5: Integración de notificaciones y LinkedIn**
  - Implementación del login y extracción de datos mediante la LinkedIn API.
  - Integración con SendGrid API para la automatización de correos electrónicos de notificación sobre el estado de postulación.
