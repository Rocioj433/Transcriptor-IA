/**
 * Waveform rendering with Web Audio peaks.
 * Draws the whole file and highlights the playback progress.
 */
export class Waveform {
  constructor(canvas, player, { bars = 320 } = {}) {
    this.canvas = canvas;
    this.player = player;
    this.bars = bars;
    this.peaks = [];
    this.progress = 0;
    this.duration = 0;

    this.context = canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
    canvas.addEventListener('click', (event) => this.seek(event));
    player.addEventListener('timeupdate', () => this.syncProgress());
    player.addEventListener('loadedmetadata', () => {
      this.duration = player.duration || 0;
      this.syncProgress();
    });
  }

  resize() {
    const ratio = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.width = Math.max(1, rect.width);
    this.height = Math.max(1, rect.height);
    this.canvas.width = Math.round(this.width * ratio);
    this.canvas.height = Math.round(this.height * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.draw();
  }

  async load(file) {
    try {
      const buffer = await file.arrayBuffer();
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const context = new AudioContextClass();
      const decoded = await context.decodeAudioData(buffer.slice(0));
      const channel = decoded.getChannelData(0);
      const block = Math.max(1, Math.floor(channel.length / this.bars));
      const peaks = [];
      for (let index = 0; index < this.bars; index += 1) {
        let peak = 0;
        const start = index * block;
        for (let cursor = 0; cursor < block; cursor += 32) {
          const sample = Math.abs(channel[start + cursor] || 0);
          if (sample > peak) peak = sample;
        }
        peaks.push(peak);
      }
      const max = Math.max(...peaks, 0.0001);
      this.peaks = peaks.map((peak) => peak / max);
      this.duration = decoded.duration;
      await context.close();
    } catch {
      this.peaks = Array.from({ length: this.bars }, (_, index) => 0.15 + 0.2 * Math.abs(Math.sin(index / 7)));
      this.duration = this.player.duration || 0;
    }
    this.draw();
  }

  getRatio() {
    const duration = this.duration || this.player.duration || 0;
    if (!duration) return 0;
    return Math.min(1, Math.max(0, (this.player.currentTime || 0) / duration));
  }

  syncProgress() {
    this.progress = this.getRatio();
    this.draw();
  }

  seek(event) {
    const duration = this.duration || this.player.duration || 0;
    if (!duration) return;
    const rect = this.canvas.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    this.player.currentTime = ratio * duration;
    this.syncProgress();
  }

  draw() {
    const { context: ctx, width, height } = this;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#0B0F14';
    ctx.fillRect(0, 0, width, height);
    const peaks = this.peaks.length ? this.peaks : Array.from({ length: this.bars }, () => 0.02);
    const barWidth = width / peaks.length;
    const middle = height / 2;
    peaks.forEach((peak, index) => {
      const amplitude = Math.max(1, peak * (height * 0.42));
      const played = index / peaks.length <= this.progress;
      ctx.fillStyle = played ? '#58A6FF' : '#30363D';
      ctx.fillRect(index * barWidth, middle - amplitude, Math.max(1, barWidth * 0.62), amplitude * 2);
    });
    ctx.strokeStyle = '#58A6FF';
    ctx.beginPath();
    ctx.moveTo(this.progress * width, 0);
    ctx.lineTo(this.progress * width, height);
    ctx.stroke();
  }
}
