# Arquitectura y Stack Tecnológico

## Stack Tecnológico

- **Frontend**: React + TypeScript + Tailwind CSS (Gestión de estado y peticiones con Zustand/React Query).
- **Backend**: Python + FastAPI.
- **Base de Datos**: PostgreSQL 15+ con la extensión `pgvector` (ORM: SQLAlchemy/SQLModel).
- **Inteligencia Artificial**: OpenAI API (GPT-4o-mini) + LangChain (para extracción de texto de CVs, embeddings y cálculo de similitud/scoring).
- **Almacenamiento y Servicios Externos**: 
  - **AWS S3**: Almacenamiento de archivos PDF de CVs.
  - **SendGrid API**: Envío de notificaciones de estado por correo electrónico.
  - **LinkedIn API**: Login y extracción de datos del perfil del candidato.

## Flujo de Comunicación (Arquitectura)
1. **Frontend (React)**: Interfaz con la que interactúan Candidatos y Reclutadores. Se comunica mediante peticiones HTTP/REST con el Backend.
2. **Backend (FastAPI)**: Orquestador principal del sistema:
   - Recibe y valida las peticiones HTTP del frontend.
   - Sube los CVs (PDFs) a **AWS S3** para almacenamiento seguro.
   - Se conecta con **OpenAI/LangChain** para la extracción de texto estructurado de los documentos y la generación de embeddings semánticos.
   - Gestiona la lógica de negocio y persiste los datos en **PostgreSQL**, guardando perfiles, ofertas de empleo y los vectores (usando `pgvector`).
   - Calcula el scoring de similitud vectorial directamente en base de datos para emparejar candidatos con ofertas.
   - Orquesta llamadas a **SendGrid API** para enviar correos automáticos.
   - Maneja la autenticación y consumo de datos mediante la **LinkedIn API**.
