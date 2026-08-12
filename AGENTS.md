# AGENTS.md

## Proyecto: PRI MVP

Estas instrucciones son obligatorias para cualquier cambio que haga el agente en este repositorio. Deben considerarse antes de generar código, consultas, modelos, migraciones o pruebas.

## Bloque 0: Base de datos (prioridad máxima)

- Stack permitido: PostgreSQL 15 + pgvector, accedido con SQLModel.
- Si el usuario solicita explícitamente cambiar el proveedor de IA, priorizar Gemini en lugar de ChatGPT/OpenAI para ese ajuste puntual.
- Embeddings: Gemini embedding 2 con dimensiones compatibles con el modelo elegido.
- No Redis y no se debe introducir caché de sesión/estado para este bloque.
- El bloque 0 se ejecuta antes que cualquier otra funcionalidad.

## Reglas de integridad y seguridad

- `candidateprofile` no debe incluir la columna `nationality`.
- Si se necesita nacionalidad por motivos administrativos, debe capturarse después de la contratación y nunca antes de la evaluación.
- El texto enviado al modelo de scoring no debe incluir ni inferir nacionalidad.
- `user.email` debe conservar restricción de unicidad.
- `application.status` debe derivarse de la última `decision` y no debe quedar contradictorio con el historial.
- `evaluation` es append-only: nunca debe haber `UPDATE` ni `DELETE` sobre filas existentes.
- `decision` es append-only: una fila por cambio de estado, sin sobrescrituras.
- `notification` es de auditoría/registro; no debe ser reescrito de forma silenciosa.
- No debe existir un estado final de aplicación sin una fila en `decision`.

## Tablas obligatorias

- `evaluation`
  - columnas requeridas: `id`, `application_id`, `suggested_category`, `explanation`, `model_version`, `prompt_version`, `excluded_fields`, `created_at`
  - `suggested_category` solo acepta `apto`, `en_revision`, `no_apto`
- `decision`
  - columnas requeridas: `id`, `application_id`, `user_id`, `action`, `discrepancy_reason`, `decided_at`
  - `action` solo acepta `avanzar`, `descartar`, `reservar`
- `notification`
  - columnas requeridas: `id`, `application_id`, `type`, `send_status`, `sent_at`
  - `type` solo acepta `recepcion`, `avance`, `descarte`
  - `send_status` solo acepta `enviado`, `fallido`, `reintento`

## Índices vectoriales obligatorios

- `candidateprofile` debe tener índice HNSW usando `vector_cosine_ops`.
- `joboffer` debe tener índice HNSW usando `vector_cosine_ops`.
- La búsqueda por similitud no debe recorrer la tabla completa en volumen real.

## Modelos SQLModel esperados

- Deben existir clases para las siete tablas del dominio principal:
  - `user`
  - `candidateprofile`
  - `joboffer`
  - `application`
  - `evaluation`
  - `decision`
  - `notification`
- Mantener el estilo de entidades ya existentes en [backend/app/models/__init__.py](backend/app/models/__init__.py).
- Los modelos nuevos deben usar `Relationship` hacia `Application` y `User` cuando corresponda.

## Reglas de implementación para el agente

- No introducir `nationality` en modelos, prompts, extracción estructurada ni en APIs de matching.
- No crear campos de scoring que dependan de nacionalidad.
- No hacer `UPDATE` directo sobre `evaluation` ni `decision` en SQL ni en ORM.
- No reutilizar o redefinir columnas de `CandidateProfile` para datos sensibles no permitidos.
- No introducir Redis, Celery o infraestructura auxiliar no pedida.
- Si hay dudas sobre compatibilidad de versiones, priorizar PostgreSQL 15 + pgvector + SQLModel.
- Antes de entregar cambios, validar que no rompen el bloque 0 ni la integridad del historial de decisiones.

## Entregable mínimo aceptable

- Esquema SQLModel actualizado con los modelos nuevos.
- `nationality` eliminado o no usado en scoring.
- Índices HNSW creados.
- Restricciones append-only en `evaluation` y `decision`.
- Prueba que demuestre que los `UPDATE` sobre estas tablas fallan.

## Prohibido

- Añadir discriminación por nacionalidad al scoring o a los embeddings.
- Hacer cambios de estado con `UPDATE` sobre `evaluation` o `decision`.
- Traer dependencias no pedidas para este bloque, especialmente Redis.
- Romper el contrato de PostgreSQL 15 + pgvector.
