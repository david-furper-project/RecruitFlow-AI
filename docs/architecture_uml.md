# Arquitectura del Sistema: Plataforma de Reclutamiento Inteligente (PRI MVP)

A continuación se presentan los diagramas UML (Secuencia y Componentes) diseñados específicamente para la arquitectura MVP de tu proyecto de título, reflejando fielmente que **no se utiliza Redis ni Kubernetes**, manteniendo el stack moderno, ligero y altamente funcional.

## 1. Descripción del Proyecto (Alineación para el Informe)

### Resumen del Sistema
La **Plataforma de Reclutamiento Inteligente (PRI)** es una solución de software orientada a resolver la fricción operativa en los procesos de selección de personal. Su objetivo principal es automatizar el filtrado de candidatos y eliminar la captura manual y duplicada de datos utilizando Inteligencia Artificial Generativa y búsquedas vectoriales por similitud semántica.

### Módulos y Funcionalidades Actuales (MVP)
1. **Portal de Candidatos:** Permite a los postulantes subir su Currículum Vitae (PDF). El sistema procesa el documento automáticamente sin requerir llenado manual de formularios tediosos.
2. **Dashboard de Reclutador (Sourcing Avanzado):** 
   - **Ranking de CVs:** Muestra a los candidatos ordenados automáticamente según el porcentaje de "Match" o afinidad semántica con la oferta laboral.
   - **Caza LinkedIn (Sourcing):** Herramienta que permite ingresar la URL de un perfil de LinkedIn, extraer su información profesional en formato estructurado (mediante simulador seguro) e integrarlo instantáneamente a la base de datos de talento.
   - **Carga Masiva:** Permite al reclutador subir múltiples CVs en PDF de forma simultánea. El sistema extrae y clasifica cada documento en bloque mediante IA.
3. **Motor de Inteligencia Artificial:** 
   - **Extracción Estructurada (LLM):** Utiliza OpenAI (GPT-4o-mini) y LangChain para leer texto desestructurado (PDFs) y categorizarlo en: Nombre, Nacionalidad, Stack Tecnológico, Años de Experiencia, Cursos y Resumen de Carrera.
   - **Motor de Similitud Vectorial:** Genera "Embeddings" (vectores de 1536 dimensiones) de los perfiles y los compara matemáticamente usando la extensión `pgvector` de PostgreSQL, logrando búsquedas por contexto (semántica) y no solo por coincidencia exacta de palabras clave.

### Stack Tecnológico Justificado
- **Frontend:** React + TypeScript + Vite + Tailwind CSS. Provee una interfaz moderna, de carga instantánea y componentes reactivos gestionados por Zustand.
- **Backend:** Python + FastAPI. Elegido por su altísimo rendimiento y su estándar en la industria como el mejor ecosistema para integrar herramientas de Inteligencia Artificial (LangChain/OpenAI).
- **Base de Datos:** PostgreSQL 15 + pgvector (mediante SQLModel). Combina la robustez de una base de datos relacional tradicional con las capacidades de vanguardia de una base de datos vectorial para IA en una misma infraestructura.
- **Servicios Cloud:** Integración preparada para AWS S3 (Almacenamiento de archivos PDF) y SendGrid (Notificaciones).

---

## 2. Diagrama de Componentes (Arquitectura General)
Muestra cómo se conectan los grandes bloques del sistema.

```mermaid
graph TD
    %% Frontend
    subgraph Frontend ["Frontend (React + Vite + Tailwind)"]
        UI[Interfaces de Usuario]
        Zustand[Gestor de Estado Zustand]
        APIClient[Cliente Axios / Fetch API]
    end

    %% Backend
    subgraph Backend ["Backend (FastAPI + Python)"]
        Router[API Routers]
        AI_Service[Servicios IA / LangChain]
        DB_Session[SQLModel / SQLAlchemy ORM]
    end

    %% Base de Datos
    subgraph Database ["Base de Datos (Docker)"]
        PostgreSQL[(PostgreSQL 15)]
        PGVector[Extensión pgvector]
    end

    %% Servicios Externos Cloud
    subgraph Cloud ["Servicios Cloud & APIs Externas"]
        OpenAI((OpenAI API))
        S3((AWS S3 - Almacenamiento))
        SendGrid((SendGrid API - Correos))
        LinkedIn((LinkedIn Mock API))
    end

    %% Conexiones
    UI <--> |Interacciones del Usuario| Zustand
    Zustand <--> |Peticiones de Datos| APIClient
    APIClient <--> |HTTP REST / JSON| Router
    
    Router <--> |Lógica de Negocio| AI_Service
    Router <--> |Persistencia| DB_Session
    
    DB_Session <--> |Conexión TCP| PostgreSQL
    PostgreSQL --- PGVector
    
    AI_Service <--> |Llamadas API| OpenAI
    Router --> |Subida de PDFs| S3
    Router --> |Notificaciones| SendGrid
    Router --> |Sourcing Perfiles| LinkedIn
```

---

## 3. Diagrama de Secuencia: Flujo Principal (Carga de CV y Matching)
Muestra el paso a paso ("conversación") desde que se sube un currículum hasta que se guarda como un vector en la base de datos.

```mermaid
sequenceDiagram
    actor C as Candidato / Reclutador
    participant F as Frontend (React)
    participant B as Backend (FastAPI)
    participant S3 as AWS S3
    participant GPT as OpenAI (IA)
    participant DB as PostgreSQL (pgvector)

    C->>F: 1. Selecciona y sube archivo PDF (CV)
    F->>B: 2. POST /api/.../upload-cv (multipart/form-data)
    
    activate B
    B->>B: 3. Extrae texto del PDF en memoria
    
    B->>S3: 4. Sube archivo físico (.pdf)
    S3-->>B: 5. Retorna URL segura del archivo
    
    B->>GPT: 6. Envía texto crudo para Estructurar (Prompt)
    GPT-->>B: 7. Retorna JSON (Nombre, Stack, Experiencia, etc.)
    
    B->>GPT: 8. Solicita Vector Matemático (Embeddings)
    GPT-->>B: 9. Retorna Vector [0.012, -0.04...] de 1536 dimensiones
    
    B->>DB: 10. INSERT CandidateProfile (Datos + Vector)
    DB-->>B: 11. Confirmación de guardado
    
    B-->>F: 12. HTTP 200 OK (Mensaje de éxito)
    deactivate B
    
    F-->>C: 13. Muestra alerta de éxito en pantalla
```

## Recomendaciones para la Defensa
- **Justificación de no usar Redis:** En tu defensa puedes mencionar que al ser un MVP enfocado en demostrar el valor del "Vector Matching", la complejidad y sobrecosto de un sistema de caché en memoria como Redis no era justificable para el volumen inicial de datos.
- **Justificación de no usar Kubernetes:** Menciona que el despliegue está pensado inicialmente sobre contenedores simples (Docker Compose o servicios serverless como AWS ECS/AppRunner o Render), manteniendo la agilidad técnica de la startup sin la gigantesca sobrecarga operativa que requiere orquestar Kubernetes (K8s).
