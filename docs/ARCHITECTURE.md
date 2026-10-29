# Arquitectura — Antigravity Studio

## 1. Vista general

Aplicación monolítica local-first con dos procesos en desarrollo (FastAPI + Vite) y uno solo
en producción (FastAPI sirve `frontend/dist`). No hay base de datos: los jobs viven en memoria
durante la vida del proceso y los archivos en `MEDIA__DIR`.

```
┌────────────────────────── frontend (Vite / ES modules) ──────────────────────────┐
│ dropzone · waveform (Web Audio) · editor click-to-seek · panel de exportación     │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    │ REST + SSE
┌───────────────────────────────────▼──────────────────────────────────────────────┐
│ FastAPI (backend/core/app.py)                                                     │
│  POST /api/jobs → guarda media → JobRepository.create → Worker.submit            │
│  GET  /api/jobs/{id} → estado + transcript                                       │
│  POST /api/jobs/{id}/cancel → threading.Event                                    │
│  GET  /api/jobs/{id}/export/{fmt} · POST /api/export → exportadores              │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    │ cola en proceso (queue.Queue)
┌───────────────────────────────────▼──────────────────────────────────────────────┐
│ Worker pool (backend/core/worker.py)                                             │
│  Pipeline.run(job)                                                               │
│   ├─ ensure_wav (ffmpeg → 16 kHz mono PCM)                                       │
│   ├─ TranscriptionEngine.transcribe (lazy load, cancelable)                      │
│   ├─ Diarizer.diarize (pyannote + DIARIZE_LOCK)                                  │
│   ├─ reconcile_speakers (máximo solapamiento temporal)                           │
│   └─ PostProcessor.cleanup (opcional, no bloqueante)                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## 2. Decisiones de diseño

| # | Decisión | Alternativa descartada | Motivo |
|---|---|---|---|
| D1 | `TranscriptionEngine` como `Protocol` + registry | imports fijos | Cambiar proveedor sin tocar pipeline; stubs en tests |
| D2 | Lock global `DIARIZE_LOCK` | lock por job | pyannote/torch no es thread-safe, especialmente en CUDA |
| D3 | Cola `queue.Queue` + threads en el proceso | Celery/Redis | Local-first, sin infraestructura externa |
| D4 | Post-proceso opcional y tolerante a fallos | bloqueante | Nunca perder la transcripción por un LLM caído |
| D5 | Exportadores puros `Transcript -> bytes` | templates dispersos | Tests golden byte-stable y ZIP trivial |
| D6 | `media_path` confinado a `MEDIA__DIR` | ruta libre | Evita leer archivos arbitrarios del servidor |
| D7 | Upload por chunks con tope | `await file.read()` completo | Cota de memoria y HTTP 413 temprano |

## 3. Modelo de datos

```python
Word(index, word, start, end)
Segment(id, start, end, text, speaker, confidence, words)
Transcript(file_name, duration, language, model_used, segments, raw_segments, warnings)
```

`raw_segments` conserva el texto original cuando el post-proceso lo modifica. `warnings`
transporta degradaciones (diarización/post) sin convertir el job en error.

## 4. Ciclo de vida de un job

```
queued (0)
  └─► transcribing (20) ──► diarizing (50) ──► post (80) ──► ready (100)
              │                    │               │
              └────────────────────┴───────────────┴──► error (-1) / cancelled (-1)
```

`core/job.py` centraliza el mapa `PROGRESS` y `ALLOWED_TRANSITIONS`; toda mutación pasa por
`transition(job, estado)`, que rechaza transiciones ilegales. Cancelar es cooperativo: cada
etapa consulta `job.cancel_event` y lanza `CancelledError`; el worker finaliza en `cancelled`
(y borra el upload) en lugar de `ready`.

## 5. Diarización

1. `PyannoteDiarizer` carga el pipeline de forma lazy (`token=`; fallback `use_auth_token`).
2. Si falta token/dependencia/modelo → `DiarizationUnavailable`.
3. El pipeline captura esa excepción, agrega un warning y continúa sin hablantes.
4. `reconcile_speakers` asigna a cada segmento el hablante con mayor solapamiento; empates →
   span más temprano; sin solapamiento → `speaker=None`.
5. Los labels arbitrarios de pyannote se normalizan a `A`, `B`, … para estabilidad visual.

## 6. Exportadores

| Formato | Implementación | Determinismo |
|---|---|---|
| txt | líneas `[hh:mm:ss] Speaker: texto` | utf-8, orden de segmentos |
| srt | cues `HH:MM:SS,mmm` | formato fijo |
| vtt | `WEBVTT` + `HH:MM:SS.mmm` + `<v Speaker>` | formato fijo |
| json | `Transcript.to_dict()` indentado | claves estables |
| csv | `csv.writer`, `\n` | sin quoting variable |
| md | encabezado + metadata + segmentos | formato fijo |
| docx | python-docx con core properties fijas | bytes estables |
| pdf | reportlab `invariant=1` | sin fecha/ID aleatorios |

El bundle ZIP fija `date_time=(1980,1,1,0,0,0)` para que el archivo también sea reproducible.

## 7. Seguridad y límites

- Uploads en chunks de 1 MiB con tope `MAX_UPLOAD_MB` (413).
- `media_path` resuelto con `strict=True` y validado con `is_relative_to(MEDIA__DIR)`.
- Nombres de archivo saneados; descargas con `Content-Disposition` explícito.
- Sin auth/multiusuario por diseño (herramienta local).
- Secretos solo por entorno (`.env` gitignored).

## 8. Testing

| Capa | Estrategia |
|---|---|
| Schema/config | unitarios puros, `Settings(_env_file=None)` para defaults herméticos |
| Motores | modelos falsos inyectados; nunca se descargan pesos |
| Diarización | pipeline falso + verificación del lock con 2 threads |
| Pipeline | stubs de engine/diarizer/post y extractor de audio falso |
| API | `TestClient` con componentes inyectados, sin worker real salvo en cancelación |
| Exportadores | goldens byte-stable (`--update-goldens`) + casos vacíos |
| Frontend | test de grounding: regiones del `.pen` == ids del HTML |
