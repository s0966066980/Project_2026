# Deployment Assets

Process and image boundaries for Project_2026 commercial runtimes.

| Asset | Role |
| --- | --- |
| `Dockerfile.api` | FastAPI API process only |
| `Dockerfile.worker` | Background worker / outbox consumer |
| `compose.staging.yml` | Staging-like API + Worker + PostgreSQL + Redis |
| `env-templates/*.example` | Environment contract templates (no real secrets) |

GPU AI runtimes (`Emotion-LLaMA`, `R1-Omni`, Ollama) are **not** packaged into API/Worker images.

See [docs/operations/DEPLOYMENT.md](../docs/operations/DEPLOYMENT.md).
