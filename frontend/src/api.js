const BASE = '';

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (payload && payload.detail) detail = payload.detail;
    } catch {
      /* keep the status message */
    }
    throw new Error(detail);
  }
  return response;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export const api = {
  async getModels() {
    return (await request('/api/models')).json();
  },

  async createJob(file, language) {
    const form = new FormData();
    form.append('file', file);
    if (language) form.append('language', language);
    return (await request('/api/jobs', { method: 'POST', body: form })).json();
  },

  async getJob(jobId) {
    return (await request(`/api/jobs/${jobId}`)).json();
  },

  async cancelJob(jobId) {
    return (await request(`/api/jobs/${jobId}/cancel`, { method: 'POST' })).json();
  },

  async downloadExport(jobId, format, fallbackName) {
    const response = await request(`/api/jobs/${jobId}/export/${format}`);
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    triggerDownload(await response.blob(), match ? match[1] : fallbackName);
  },

  async downloadBundle(jobId, formats) {
    const response = await request('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, formats }),
    });
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    triggerDownload(await response.blob(), match ? match[1] : 'transcripts.zip');
  },
};
