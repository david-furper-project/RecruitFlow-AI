# Diagrama de Base de Datos (PRI MVP)

Este diagrama representa la estructura de las tablas de PostgreSQL (con la extensión pgvector) para la Plataforma de Reclutamiento Inteligente. Puedes utilizar este diagrama para incluirlo directamente en tu informe de título.

## Entidad-Relación (Mermaid)

```mermaid
erDiagram
    USER ||--o| CANDIDATEPROFILE : "tiene (1:1)"
    CANDIDATEPROFILE ||--o{ APPLICATION : "postula (1:N)"
    JOBOFFER ||--o{ APPLICATION : "recibe (1:N)"

    USER {
        int id PK
        string email "Unique, Index"
        string role "default: 'candidate'"
        string password_hash
    }

    CANDIDATEPROFILE {
        int id PK
        int user_id FK
        string full_name
        string resume_url
        string extracted_text
        string nationality "Extraído por IA"
        string tech_stack "Extraído por IA"
        int years_of_experience "Extraído por IA"
        string courses_and_diplomas "Extraído por IA"
        string career_summary "Extraído por IA"
        vector embedding "Vector(1536) pgvector"
    }

    JOBOFFER {
        int id PK
        string title
        string description
        string requirements
        vector embedding "Vector(1536) pgvector"
    }

    APPLICATION {
        int id PK
        int candidate_id FK
        int job_offer_id FK
        string status "default: 'pending'"
        float similarity_score "Distancia Coseno"
    }
```

## Diccionario de Datos Breve

### Tabla `user`
Almacena las credenciales y el tipo de rol de la persona (Candidato o Reclutador).

### Tabla `candidateprofile`
Almacena el perfil profesional. Destacan las columnas extraídas mediante Inteligencia Artificial Generativa (`nationality`, `tech_stack`, `years_of_experience`, `courses_and_diplomas`, `career_summary`) y la columna especial `embedding` que usa **pgvector** para indexar matemáticamente el perfil.

### Tabla `joboffer`
Almacena las ofertas laborales publicadas. Al igual que el perfil del candidato, cuenta con un `embedding` matemático para permitir búsquedas por similitud semántica.

### Tabla `application`
Tabla transaccional o pivote que registra cuando un candidato hace match o postula a una oferta. Guarda el estado del flujo de contratación y el puntaje de similitud (`similarity_score`) calculado por el motor vectorial.
