import { api } from './api.js';
import { escapeHtml, formatClock, formatDuration } from './format.js';
import { Waveform } from './waveform.js';

const STATUS_LABELS = {
  queued: 'En cola',
  transcribing: 'Transcribiendo…',
  diarizing: 'Identificando hablantes…',
  post: 'Limpiando texto…',
  ready: 'Listo',
  error: 'Error',
  cancelled: 'Cancelado',
};

const ACTIVE_STATES = new Set(['queued', 'transcribing', 'diarizing', 'post']);

const refs = {
  modelSelect: document.querySelector('#model-select'),
  engineBadge: document.querySelector('#engine-badge'),
  dropzone: document.querySelector('#upload-media-dropzone'),
  dropzoneHint: document.querySelector('#dropzone-hint'),
  fileInput: document.querySelector('#file-input'),
  browseButton: document.querySelector('#browse-button'),
  statusLabel: document.querySelector('#status-label'),
  progressTrack: document.querySelector('#progress-track'),
  progressFill: document.querySelector('#progress-fill'),
  progressPercent: document.querySelector('#progress-percent'),
  cancelButton: document.querySelector('#cancel-button'),
  notice: document.querySelector('#notice'),
  mediaName: document.querySelector('#media-name'),
  player: document.querySelector('#media-player'),
  waveform: document.querySelector('#waveform'),
  transcript: document.querySelector('#transcript-segments'),
  speakerCount: document.querySelector('#speaker-count'),
  exportButtons: document.querySelector('#export-buttons'),
};

const state = {
  job: null,
  formats: [],
  maxUploadMb: 512,
  polling: null,
  objectUrl: null,
  segments: [],
  activeIndex: -1,
  speakerIds: new Map(),
};

const waveform = new Waveform(refs.waveform, refs.player, { bars: 280 });

function speakerHue(speaker) {
  if (!speaker) return 210;
  if (!state.speakerIds.has(speaker)) {
    state.speakerIds.set(speaker, (state.speakerIds.size * 137 + 40) % 360);
  }
  return state.speakerIds.get(speaker);
}

function showNotice(message, kind = 'info') {
  refs.notice.textContent = message;
  refs.notice.dataset.kind = kind;
  refs.notice.hidden = false;
}

function hideNotice() {
  refs.notice.hidden = true;
  refs.notice.textContent = '';
}

function setProgress(job) {
  const progress = job.progress < 0 ? 0 : job.progress;
  refs.progressFill.style.width = `${progress}%`;
  refs.progressTrack.setAttribute('aria-valuenow', String(progress));
  refs.progressPercent.textContent = `${progress}%`;
  refs.statusLabel.textContent = STATUS_LABELS[job.status] || job.status;
  refs.statusLabel.dataset.status = job.status;
}

function renderModels(models) {
  refs.modelSelect.innerHTML = '';
  for (const size of models.model_sizes) {
    const option = document.createElement('option');
    option.value = size;
    option.textContent = size;
    option.selected = size === models.model;
    refs.modelSelect.append(option);
  }
  refs.modelSelect.disabled = true;
  refs.modelSelect.title = 'Se configura en el servidor (.env → MODEL__SIZE)';
  refs.engineBadge.textContent = models.engine;
  refs.dropzoneHint.textContent = `mp3 · wav · m4a · mp4 · mkv — hasta ${models.max_upload_mb} MB`;
  state.formats = models.formats;
  state.maxUploadMb = models.max_upload_mb;
  if (!models.diarization.enabled) {
    showNotice('Sin HUGGINGFACE_TOKEN: la transcripción funcionará, pero sin identificar hablantes.', 'info');
  }
  renderExports();
}

function renderExports() {
  refs.exportButtons.innerHTML = '';
  for (const format of state.formats) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button export';
    button.dataset.format = format.key;
    button.textContent = format.key.toUpperCase();
    button.disabled = true;
    button.addEventListener('click', () => download(format.key));
    refs.exportButtons.append(button);
  }
  const bundle = document.createElement('button');
  bundle.type = 'button';
  bundle.id = 'export-bundle';
  bundle.className = 'button primary';
  bundle.textContent = 'ZIP (todo)';
  bundle.disabled = true;
  bundle.addEventListener('click', downloadBundle);
  refs.exportButtons.append(bundle);
}

function enableExports(enabled) {
  refs.exportButtons.querySelectorAll('button').forEach((button) => {
    button.disabled = !enabled;
  });
}

function renderTranscript(transcript) {
  state.segments = transcript.segments || [];
  state.activeIndex = -1;
  state.speakerIds.clear();
  refs.transcript.innerHTML = '';

  if (!state.segments.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'La transcripción está vacía.';
    refs.transcript.append(empty);
    refs.speakerCount.textContent = '0 segmentos';
    return;
  }

  state.segments.forEach((segment, index) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'segment';
    row.dataset.index = String(index);
    row.style.setProperty('--speaker-hue', String(speakerHue(segment.speaker)));

    const time = document.createElement('span');
    time.className = 'segment-time';
    time.textContent = formatClock(segment.start, { milliseconds: true });

    const speaker = document.createElement('span');
    speaker.className = `speaker ${segment.speaker ? '' : 'speaker-none'}`;
    speaker.textContent = segment.speaker || '—';

    const text = document.createElement('span');
    text.className = 'segment-text';
    text.textContent = segment.text;

    row.append(time, speaker, text);
    row.addEventListener('click', () => seekTo(segment.start, index));
    refs.transcript.append(row);
  });

  const speakers = new Set(state.segments.map((segment) => segment.speaker).filter(Boolean));
  refs.speakerCount.textContent = `${state.segments.length} segmentos · ${speakers.size} hablantes · ${formatDuration(transcript.duration)}`;
}

function seekTo(start, index) {
  refs.player.currentTime = Math.max(0, start);
  refs.player.play().catch(() => {});
  markActive(index);
}

function markActive(index) {
  if (index === state.activeIndex) return;
  refs.transcript.querySelectorAll('.segment.active').forEach((row) => row.classList.remove('active'));
  const row = refs.transcript.querySelector(`.segment[data-index="${index}"]`);
  if (row) {
    row.classList.add('active');
    row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  state.activeIndex = index;
}

refs.player.addEventListener('timeupdate', () => {
  const current = refs.player.currentTime;
  const index = state.segments.findIndex(
    (segment) => current >= segment.start && current < segment.end,
  );
  if (index !== -1) markActive(index);
});

function applyJob(job) {
  state.job = job;
  setProgress(job);

  if (job.status === 'ready' && job.transcript) {
    renderTranscript(job.transcript);
    enableExports(true);
    hideNotice();
  }

  if (job.message && job.status === 'ready') {
    showNotice(job.message, 'warn');
  }

  if (job.status === 'error') {
    showNotice(job.error || 'La transcripción falló.', 'error');
    enableExports(false);
  }

  if (job.status === 'cancelled') {
    showNotice('Trabajo cancelado.', 'warn');
    enableExports(false);
  }

  if (!ACTIVE_STATES.has(job.status)) {
    stopPolling();
    refs.cancelButton.hidden = true;
  }
}

function stopPolling() {
  if (state.polling) {
    clearInterval(state.polling);
    state.polling = null;
  }
}

async function poll() {
  if (!state.job) return;
  try {
    const job = await api.getJob(state.job.id);
    applyJob(job);
  } catch (error) {
    stopPolling();
    showNotice(`No se pudo consultar el trabajo: ${error.message}`, 'error');
  }
}

function startPolling() {
  stopPolling();
  state.polling = setInterval(poll, 700);
}

function resetForNewJob(file) {
  stopPolling();
  state.segments = [];
  state.activeIndex = -1;
  refs.transcript.innerHTML = '<p class="empty">Procesando…</p>';
  refs.speakerCount.textContent = '—';
  refs.mediaName.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
  enableExports(false);
  hideNotice();
  refs.cancelButton.hidden = true;
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.objectUrl = URL.createObjectURL(file);
  refs.player.src = state.objectUrl;
  waveform.load(file);
}

async function handleFile(file) {
  if (!file) return;
  if (file.size > state.maxUploadMb * 1024 * 1024) {
    showNotice(`El archivo supera el límite de ${state.maxUploadMb} MB.`, 'error');
    return;
  }
  resetForNewJob(file);
  setProgress({ status: 'queued', progress: 0 });
  refs.statusLabel.textContent = 'Subiendo archivo…';
  try {
    const job = await api.createJob(file);
    state.job = job;
    refs.cancelButton.hidden = false;
    applyJob(job);
    startPolling();
  } catch (error) {
    showNotice(`No se pudo subir el archivo: ${error.message}`, 'error');
    refs.statusLabel.textContent = 'Error';
    refs.cancelButton.hidden = true;
  }
}

async function download(format) {
  if (!state.job) return;
  try {
    await api.downloadExport(state.job.id, format, `transcript.${format}`);
  } catch (error) {
    showNotice(`No se pudo exportar ${format}: ${error.message}`, 'error');
  }
}

async function downloadBundle() {
  if (!state.job) return;
  try {
    await api.downloadBundle(state.job.id, state.formats.map((format) => format.key));
  } catch (error) {
    showNotice(`No se pudo exportar el ZIP: ${error.message}`, 'error');
  }
}

async function cancel() {
  if (!state.job) return;
  try {
    await api.cancelJob(state.job.id);
    showNotice('Cancelando…', 'warn');
    refs.cancelButton.hidden = true;
  } catch (error) {
    showNotice(error.message, 'error');
  }
}

function bindEvents() {
  refs.browseButton.addEventListener('click', () => refs.fileInput.click());
  refs.fileInput.addEventListener('change', () => {
    const [file] = refs.fileInput.files;
    handleFile(file);
    refs.fileInput.value = '';
  });

  ['dragenter', 'dragover'].forEach((eventName) => {
    refs.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      refs.dropzone.classList.add('dragging');
    });
  });
  ['dragleave', 'drop'].forEach((eventName) => {
    refs.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      refs.dropzone.classList.remove('dragging');
    });
  });
  refs.dropzone.addEventListener('drop', (event) => {
    const [file] = event.dataTransfer.files;
    handleFile(file);
  });
  refs.dropzone.addEventListener('click', (event) => {
    if (event.target === refs.dropzone || event.target.closest('.dropzone-content')) {
      if (event.target !== refs.browseButton) refs.fileInput.click();
    }
  });

  refs.cancelButton.addEventListener('click', cancel);

  document.addEventListener('keydown', (event) => {
    if (event.code !== 'Space') return;
    if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(event.target.tagName)) return;
    event.preventDefault();
    if (refs.player.paused) refs.player.play().catch(() => {});
    else refs.player.pause();
  });
}

async function boot() {
  bindEvents();
  renderExports();
  try {
    renderModels(await api.getModels());
  } catch (error) {
    showNotice(`Sin conexión con la API (${error.message}). ¿Está corriendo uvicorn?`, 'error');
  }
}

boot();

// Re-export helpers for potential unit tests / debugging.
export { escapeHtml, formatClock };
