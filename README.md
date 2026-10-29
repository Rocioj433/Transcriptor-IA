# Antigravity Studio — Transcriptor con diarización

Estudio de transcripción **local-first** para audio y video. Convierte una grabación en texto,
identifica **quién dice qué** (diarización de hablantes) y exporta el resultado a **8 formatos**
profesionales. Todo corre en tu máquina; la nube es un fallback opcional.

> Proyecto del CV: *Antigravity Studio – Transcriptor con Diarización*  
> Python (FastAPI) · Faster-Whisper · PyAnnote · OpenAI API · pytest

---

## Características

| Capacidad | Detalle |
|---|---|
| Transcripción local | `faster-whisper` (default `large-v3-turbo`), tamaños `tiny` → `large-v3`, Silero VAD, timestamps por palabra |
| Motores alternativos | `openai-whisper` (backup local) y `cloud-transcribe` (OpenAI `gpt-4o-transcribe`, opt-in) |
| Diarización | `pyannote.audio` (`speaker-diarization-3.1`), lock global para serializar GPU/CPU, reconciliación por solapamiento temporal |
| Post-proceso | Limpieza opcional con LLM (Ollama local por defecto u OpenAI). Nunca bloquea: si falla, se conserva el texto crudo |
| Orquestación | FastAPI + cola en proceso + worker pool, progreso `queued → transcribing → diarizing → post → ready`, cancelación cooperativa y SSE |
| Exportación | `txt`, `srt`, `vtt`, `docx`, `pdf`, `json`, `csv`, `md` + bundle ZIP |
| UI | Vite + ES modules vanilla, drag & drop, waveform Web Audio, click-to-seek, selector de modelo y panel de exportación |
| Calidad | pytest (116 tests), goldens byte-stable para exportadores, stubs para correr sin pesos de ML |

## Arquitectura

```
Upload / media_path
        │
        ▼
POST /api/jobs ──► JobRepository (in-memory) ──► Worker pool (threads)
                                                        │
                                        ┌───────────────┴───────────────┐
                                        ▼                               │
                              extract 16 kHz mono (ffmpeg)               │
                                        ▼                               │
                              TranscriptionEngine (SPI)                  │
                            faster-whisper / openai / cloud             │
                                        ▼                               │
                              Diarizer (pyannote + DIARIZE_LOCK)         │
                                        ▼                               │
                              reconcile speakers by overlap             │
                                        ▼                               │
                              PostProcessor (Ollama / OpenAI)            │
                                        ▼                               │
                              JobStatus READY + Transcript              │
                                        ▼                               │
                      GET /api/jobs/{id} · SSE · /export/{fmt} · ZIP ───┘
```

Decisiones clave: motores y diarizador detrás de interfaces (`Protocol`) para poder inyectar
stubs en tests; exportadores como funciones puras `Transcript -> bytes`; una sola instancia de
pyannote serializada con lock global; y errores de diarización/post-proceso tratados como
*degradación elegante* (el job termina `ready` con un warning).

Más detalle en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Requisitos

- **Python 3.11–3.12** (recomendado 3.12; `faster-whisper`/`torch` todavía no publican wheels para 3.15)
- **ffmpeg** en el `PATH` (o `FFMPEG_BINARY=/ruta/a/ffmpeg`)
- **Node 20+** para el frontend
- Opcional: **token de Hugging Face** con acceso aceptado a `pyannote/speaker-diarization-3.1`
- Opcional: **Ollama** para limpieza local o **OpenAI API key** para nube

## Instalación rápida (Windows / PowerShell)

```powershell
# 1. ffmpeg
winget install Gyan.FFmpeg

# 2. Python 3.12 + entorno
uv python install 3.12
uv venv --python 3.12 .venv
.\.venv\Scripts\Activate.ps1

# 3. Dependencias base + tests
uv pip install -e ".[dev]"

# 4. Motores de IA (elegí lo que necesites)
uv pip install faster-whisper            # transcripción local (default)
uv pip install pyannote.audio            # diarización (requiere token HF)
uv pip install openai                    # cloud-transcribe + post OpenAI

# 5. Configuración
Copy-Item .env.example .env
# editá .env: HUGGINGFACE_TOKEN=hf_..., POST__PROVIDER=none
```

> `pip install -e .` (o `uv pip install -e .`) expone el comando `antigravity-studio`.

### Token de Hugging Face

1. Creá un token de **read** en <https://huggingface.co/settings/tokens>.
2. Aceptá los términos del modelo: <https://huggingface.co/pyannote/speaker-diarization-3.1>.
3. Copialo en `.env` como `HUGGINGFACE_TOKEN=hf_...`.

Sin token la app **funciona igual**: transcribe, exporta y avisa `diarization-unavailable`.

## Uso

```powershell
# Backend (API en http://127.0.0.1:8000)
antigravity-studio
# equivalente: .\.venv\Scripts\python.exe -m uvicorn core.app:app --app-dir backend --port 8000

# Frontend en desarrollo (http://127.0.0.1:5173, proxy a :8000)
cd frontend
npm install
npm run dev
```

Para servir todo desde FastAPI:

```powershell
cd frontend
npm run build     # genera frontend/dist
cd ..
antigravity-studio
# abrí http://127.0.0.1:8000
```

### Flujo

1. Arrastrá un archivo (o `POST /api/jobs` con `file` / `media_path`).
2. Mirá el progreso en la barra (`transcribing 20% → diarizing 50% → post 80% → ready 100%`).
3. Hacé clic en una línea o en el waveform para saltar a ese momento.
4. Descargá el formato que quieras o todo en un ZIP.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | Estado, motor, worker, ffmpeg |
| GET | `/api/models` | Motores, tamaños, device, formatos, diarización |
| GET | `/api/formats` | Formatos de exportación disponibles |
| POST | `/api/jobs` | Crea un job (`multipart`: `file`, `language`) o `media_path` |
| GET | `/api/jobs` | Lista de jobs |
| GET | `/api/jobs/{id}` | Estado, progreso y transcripción |
| POST | `/api/jobs/{id}/cancel` | Cancela un job en curso |
| GET | `/api/jobs/{id}/events` | SSE de progreso (si `SSE__ENABLED=true`) |
| GET | `/api/jobs/{id}/export/{fmt}` | Descarga un formato |
| POST | `/api/export` | ZIP con los formatos pedidos |
| DELETE | `/api/jobs/{id}` | Borra el job y su archivo subido |

Ejemplo:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/jobs -F "file=@C:\ruta\entrevista.mp3" -F "language=es"
curl.exe http://127.0.0.1:8000/api/jobs/<id>
curl.exe -OJ http://127.0.0.1:8000/api/jobs/<id>/export/docx
```

## Configuración (`.env`)

| Variable | Default | Notas |
|---|---|---|
| `APP__ENGINE` | `faster-whisper` | `faster-whisper`, `openai-whisper`, `cloud-transcribe` |
| `MODEL__SIZE` | `large-v3-turbo` | `tiny` … `large-v3`, `distil-large-v3` |
| `DEVICE` | `cpu` | `cpu` o `cuda` |
| `COMPUTE_TYPE` | auto | `int8` en CPU, `float16` en CUDA |
| `HUGGINGFACE_TOKEN` | vacío | habilita diarización |
| `DIARIZER_MODEL` | `pyannote/speaker-diarization-3.1` | repo gated de HF |
| `POST__PROVIDER` | `none` | `none`, `ollama`, `openai` |
| `OLLAMA__BASE_URL` / `OLLAMA__MODEL` | `http://localhost:11434` / `llama3.1` | limpieza local |
| `CLOUD__API_KEY` / `CLOUD__MODEL` | vacío / `gpt-4o-transcribe` | motor cloud / post OpenAI |
| `MEDIA__DIR` | `./media` | uploads y modo `media_path` |
| `MAX_UPLOAD_MB` | `512` | límite de subida (HTTP 413) |
| `JOB__WORKERS` | `2` | workers concurrentes (diarización siempre serializada) |
| `SSE__ENABLED` | `true` | stream de progreso |

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --cov=backend --cov-report=term-missing
```

- **116 tests**: schema, config, motores, diarización, reconciliación, pipeline, cola/worker,
  ciclo de vida, API, SSE, cancelación, exportadores (goldens), post-proceso y grounding del blueprint.
- No requieren GPU ni pesos: los tests inyectan stubs. Los goldens se regeneran con
  `pytest --update-goldens`.

## Estructura

```
backend/
  engines/        schema, SPI/registry, faster-whisper, openai-whisper, cloud
  core/           config, audio, job, queue, worker, pipeline, app (FastAPI)
    diarizer/     base SPI, lock global, pyannote, reconcile
    post/         base, ollama, openai
  exporters/      txt, srt, vtt, docx, pdf, json, csv, md
frontend/
  index.html      regiones 1:1 con ui_design.pen
  ui_design.pen   blueprint (JSON) + ui_design.svg exportado
  src/            main.js, api.js, waveform.js, format.js, styles.css
tests/            suite pytest + goldens
docs/             arquitectura
media/            uploads (gitignored)
```

## Troubleshooting

| Síntoma | Causa / solución |
|---|---|
| `ffmpeg is required…` | Instalá ffmpeg y reiniciá la terminal, o definí `FFMPEG_BINARY` |
| `diarization-unavailable: HUGGINGFACE_TOKEN is not configured` | Agregá el token en `.env` |
| `404 Repository Not Found` al cargar pyannote | Aceptá los términos del modelo y usá un token con permiso `read` |
| `faster-whisper is not installed` | `uv pip install faster-whisper` |
| Primera transcripción lenta | El modelo se descarga/compila la primera vez; luego queda cacheado |
| GPU no detectada | `DEVICE=cuda` + CUDA/cuDNN compatibles; si falla, volvé a `cpu` |
| `CLOUD__API_KEY is required` | Configurá la key o cambiá `APP__ENGINE` |

## Estado

Reconstruido a partir del blueprint SDD archivado (proposal / spec / design / tasks / verify)
y de la descripción del CV. 116 tests en verde, 8 exportadores byte-stable, UI grounded en
`ui_design.pen`.
