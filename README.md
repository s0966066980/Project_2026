# Smart Ordering POS Platform

An AI-assisted smart ordering and point-of-sale platform for kiosk-style food ordering. The project combines a FastAPI backend, a browser-based POS/admin UI, local or cloud AI model integrations, voice assistance, recommendation workflows, member personalization, RAG-backed knowledge retrieval, and optional multimodal emotion analysis.

The active application lives in `UI_API/`. Supporting model projects such as `Emotion-LLaMA/` and `R1-Omni/` are included for advanced emotion or multimodal analysis workflows.

## Features

- Kiosk POS ordering interface with cart, checkout, payment countdown, and order completion flows
- Admin dashboard for settings, logs, testing, members, and system monitoring
- AI recommendation push cards for customer-facing suggestions
- Voice ordering and voice assistant flow with STT, LLM, and TTS support
- Member login, registration, personalization, and usual-order recommendations
- Interaction event tracking for hesitation, payment confusion, and assistance triggers
- RAG provider for menu and knowledge retrieval
- Realtime WebSocket event broadcasting
- Optional Emotion-LLaMA and R1-Omni integrations
- Configurable runtime settings through JSON and environment variables
- Layered backend structure for API, bootstrap, services, repositories, models, utilities, and constants

## Planning Documents

- `MEMBERSHIP_RECOMMENDATION_IMPROVEMENTS.md`：會員推薦與語音個人化改進項目。

## Screenshots

> Add production screenshots or demo captures here.

| POS Kiosk | Admin Dashboard |
| --- | --- |
| `docs/screenshots/pos.png` | `docs/screenshots/admin.png` |

| Voice Assistant | AI Recommendation |
| --- | --- |
| `docs/screenshots/voice.png` | `docs/screenshots/ai-push.png` |

## Folder Structure

```text
.
├── UI_API/
│   ├── main.py                     # FastAPI application entrypoint
│   ├── config.py                   # Environment and runtime settings
│   ├── backend/
│   │   ├── api/                    # Router registration and API composition
│   │   ├── bootstrap/              # Startup, server, and process helpers
│   │   ├── core/                   # Shared backend constants and primitives
│   │   ├── models/                 # Backend data models and dependency types
│   │   ├── prompts/                # Default AI prompts
│   │   ├── realtime/               # WebSocket connection and event bus
│   │   ├── repositories/           # File-backed data access layer
│   │   ├── routes/                 # FastAPI route modules
│   │   ├── services/               # Business logic and AI workflows
│   │   └── utils/                  # Shared backend utility functions
│   ├── frontend/
│   │   ├── admin/                  # Admin dashboard UI
│   │   ├── pos/                    # POS kiosk UI modules
│   │   │   └── constants/          # POS constants and display text
│   │   ├── shared/                 # Shared API client, UI helpers, hooks, components
│   │   ├── mcd_categories/         # Category images
│   │   └── menu_images/            # Menu item images
│   ├── learning_data/              # Runtime logs, settings, RAG data, member data
│   ├── menu_data/                  # Menu JSON data
│   ├── rag_documents/              # Versioned RAG source documents
│   └── tests/                      # Backend tests
├── Emotion-LLaMA/                  # Optional emotion analysis service
├── R1-Omni/                        # Optional multimodal emotion service
├── scripts/                        # Local startup scripts
└── logs/                           # Runtime logs
```

## Tech Stack

### Backend

- Python 3
- FastAPI
- Uvicorn
- WebSockets
- File-backed JSON repositories
- ChromaDB and LangChain integrations for RAG
- Ollama-compatible local LLM workflows
- Google GenAI integration option

### Frontend

- HTML, CSS, and vanilla JavaScript ES modules
- Tailwind CDN usage in POS UI
- Font Awesome icons
- Browser media APIs for microphone/camera capture

### AI and Media

- Ollama local model serving
- Faster Whisper or OpenAI-compatible STT
- Edge TTS, MeloTTS, or OpenAI-compatible TTS
- Optional Emotion-LLaMA
- Optional R1-Omni

## Installation

Clone the repository and create a Python environment for the main UI/API service.

```bash
git clone <repository-url>
cd Project_2026

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r UI_API/requirements.txt
```

If you use the optional emotion model services, install their dependencies separately according to the environment requirements of `Emotion-LLaMA/` and `R1-Omni/`.

## Environment Variables

Create a `.env` file in `UI_API/` when local overrides are needed.

```bash
cd UI_API
cp .env.example .env  # if an example file exists
```

Common variables:

| Variable | Description | Default |
| --- | --- | --- |
| `APP_HOST` | Host for the FastAPI server | `0.0.0.0` |
| `APP_PORT` | POS/API port | `8000` |
| `ADMIN_PORT` | Admin entry port | `8001` |
| `OLLAMA_API_URL` | Ollama generate API endpoint | `http://localhost:11434/api/generate` |
| `OLLAMA_BASE_URL` | Ollama base URL | Derived from `OLLAMA_API_URL` |
| `GEMINI_API_KEY` | Google Gemini API key | Empty |
| `GOOGLE_API_KEY` | Alternative Gemini API key variable | Empty |
| `EMOTION_LLAMA_GRADIO_URL` | Emotion-LLaMA service URL | `http://127.0.0.1:7889` |
| `R1_OMNI_GRADIO_URL` | R1-Omni service URL | `http://127.0.0.1:7890` |
| `ENABLE_NGROK` | Enable ngrok tunnel startup | `true` |
| `NGROK_AUTHTOKEN` | ngrok authentication token | Empty |
| `POS_DEMO_TOKEN` | Optional POS demo token | Empty |
| `ADMIN_DEMO_TOKEN` | Optional admin demo token | Empty |
| `WS_DEMO_TOKEN` | Optional WebSocket demo token | Empty |
| `PUBLIC_POS_ORIGIN` | Public POS origin for CORS | Empty |
| `PUBLIC_ADMIN_ORIGIN` | Public admin origin for CORS | Empty |
| `CORS_ORIGINS` | Comma-separated allowed origins | Localhost defaults |

Runtime settings are also stored in `UI_API/learning_data/settings.json` and can be updated through the admin interface or backend settings API.

## RAG Knowledge Base

RAG source documents should be kept in `UI_API/rag_documents/` and committed to Git. The generated Chroma vector database is stored under `UI_API/learning_data/chroma_rag/` and is runtime data.

Recommended source formats:

- Markdown for FAQ, policies, menu notes, SOP, and customer-service knowledge.
- JSON for structured promotions, member offers, and rule-like content.
- CSV for tabular nutrition, allergen, pricing, or store-policy data.

Manage RAG from the Admin dashboard:

1. Open Admin and go to `RAG 知識庫`.
2. Add or update text directly from the form. Supplying the same document ID overwrites that document.
3. Use `清空 Chroma 並重新讀取 RAG 文件` to clear the current Chroma collection and rebuild it from `UI_API/rag_documents/`.

No manual Python import command is required.

## Running Locally

Start the main application:

```bash
cd UI_API
python main.py
```

Default local URLs depend on `APP_PORT` and `ADMIN_PORT`.

- POS: `http://127.0.0.1:8000/pos`
- Admin: `http://127.0.0.1:8001/admin`

The repository also includes helper scripts for optional model-backed startup flows:

```bash
bash scripts/start_emotion_llama.sh
bash scripts/start_r1_omni.sh
```

Those scripts start Ollama, the selected emotion model service, and `UI_API`, then open POS/Admin in the browser when possible. They default to `APP_PORT=9000` and `ADMIN_PORT=9001`; override ports or disable browser opening when needed:

```bash
APP_PORT=8000 ADMIN_PORT=8001 OPEN_BROWSER=false bash scripts/start_emotion_llama.sh
```

The scripts assume local Python environment paths and model services are available on the host machine. Adjust environment variables before using them on a different workstation or server.

## Build

The current frontend is served as static HTML/CSS/JavaScript by FastAPI and does not require a Node build step.

Recommended validation before release:

```bash
python3 -m py_compile UI_API/main.py $(find UI_API/backend -type f -name '*.py' -not -path '*/__pycache__/*')
find UI_API/frontend -type f -name '*.js' -print | sort | xargs -n 1 node --check
```

If packaging for production, build a deployment artifact that includes:

- `UI_API/main.py`
- `UI_API/backend/`
- `UI_API/frontend/`
- `UI_API/menu_data/`
- required runtime settings and seed data
- installed Python dependencies from `UI_API/requirements.txt`

## Testing

Run the backend test suite:

```bash
cd UI_API
python -m pytest tests
```

Run static validation:

```bash
python -m py_compile main.py $(find backend -type f -name '*.py' -not -path '*/__pycache__/*')
find frontend -type f -name '*.js' -print | sort | xargs -n 1 node --check
```

Recommended test coverage areas:

- Route registration and API response contracts
- Member login, registration, and personalization
- Checkout and session logging
- AI push recommendation fallback behavior
- RAG provider behavior with empty and populated document stores
- Voice ordering request and error handling
- Interaction event scoring and intervention triggers

## Deployment

Recommended production deployment pattern:

1. Provision a Python runtime with dependencies from `UI_API/requirements.txt`.
2. Configure `.env` and `learning_data/settings.json` for the target environment.
3. Run the app behind a process manager such as `systemd`, `supervisord`, or a platform-native service manager.
4. Place a reverse proxy such as Nginx or Caddy in front of Uvicorn for TLS, compression, and public routing.
5. Run optional AI model services separately and expose them on internal network URLs.
6. Persist `UI_API/learning_data/` and any vector database files across deployments.
7. Restrict admin access with tokens and network controls.

Example Uvicorn command:

```bash
cd UI_API
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Overview

The backend exposes REST and WebSocket endpoints through FastAPI route modules.

| Module | Responsibility |
| --- | --- |
| `core_routes.py` | Frontend pages, settings, logs, checkout, session stats |
| `menu_routes.py` | Menu retrieval and admin menu updates |
| `voice_routes.py` | Voice assistant and voice ordering |
| `ai_push_routes.py` | AI recommendation push |
| `emotion_routes.py` | Emotion and multimodal event analysis |
| `interaction_routes.py` | Interaction events and barrier state |
| `realtime_routes.py` | WebSocket realtime updates |
| `member_routes.py` | Member login, registration, history, and admin operations |
| `rag_routes.py` | RAG document and retrieval operations |
| `passive_voice_routes.py` | Passive voice keyword detection |
| `demo_routes.py` | Demo scenario tooling |
| `debug_routes.py` | Optional debug endpoints controlled by settings |
| `test_routes.py` | Test and diagnostics endpoints |

Important endpoint groups:

- `GET /pos` - POS kiosk UI
- `GET /admin` - admin dashboard UI
- `GET /api/menu` - menu data
- `POST /api/checkout` - checkout processing
- `GET /api/settings` - admin settings
- `POST /api/settings` - update admin settings
- `POST /api/ai_push` - AI push recommendation
- `POST /api/member/login` - member login
- `POST /api/member/register` - member registration
- WebSocket routes are defined in `backend/routes/realtime_routes.py`

## Coding Conventions

- Keep API routes thin. Put business behavior in `backend/services/`.
- Keep persistence concerns in `backend/repositories/`.
- Keep shared backend primitives in `backend/core/`, `backend/models/`, and `backend/utils/`.
- Avoid importing route modules from services or repositories.
- Avoid circular frontend imports. Shared POS dependencies should flow through `frontend/pos/runtime.js` or dedicated shared modules.
- Keep customer-facing UI text concise and avoid exposing internal AI reasoning.
- Prefer explicit, small modules over large cross-cutting files.
- Preserve existing endpoint contracts unless a migration is planned.
- Run Python and JavaScript static checks before submitting changes.
- Do not commit runtime logs, cache files, local credentials, or generated media artifacts.

## Future Roadmap

- Add a formal release packaging workflow for repeatable deployment
- Add CI for Python tests, JavaScript syntax checks, and import-cycle checks
- Add OpenAPI documentation examples for key request/response payloads
- Add Playwright smoke tests for POS and admin workflows
- Add role-based admin authentication
- Add database-backed persistence for production workloads
- Improve observability with structured logs and metrics
- Add migration tooling for settings, menu data, and member data
- Expand multilingual UI coverage
- Add screenshot assets and demo videos to documentation

## License

No license file is currently included in this repository. Add a `LICENSE` file before distributing or publishing the project. If this is intended to be open source, choose an appropriate license such as MIT, Apache-2.0, or GPL-3.0.
