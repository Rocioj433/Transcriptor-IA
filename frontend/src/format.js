export function formatClock(seconds, { milliseconds = false } = {}) {
  const value = Math.max(0, Number(seconds) || 0);
  const totalMs = Math.round(value * 1000);
  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000);
  const secs = Math.floor((totalMs % 60_000) / 1000);
  const millis = totalMs % 1000;
  const base = [hours, minutes, secs].map((part) => String(part).padStart(2, '0')).join(':');
  return milliseconds ? `${base}.${String(millis).padStart(3, '0')}` : base;
}

export function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${value.toFixed(1)} s`;
  return formatClock(value);
}

export function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function speakerClass(speaker) {
  if (!speaker) return 'speaker-none';
  let hash = 0;
  for (const char of speaker) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return `speaker-${hash}`;
}
