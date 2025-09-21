import { endpoints, getJSON } from '../api.js';

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(s / 60);
  const sec = s % 60;
  if (minutes <= 0) {
    return `${sec}s`;
  }
  return `${minutes}m ${sec.toString().padStart(2, '0')}s`;
}

export class StatusCard {
  constructor(root) {
    this.root = root;
    this.timer = null;
  }

  start() {
    if (!this.root) return;
    this.refresh();
    this.timer = setInterval(() => this.refresh(), 10000);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }

  async refresh() {
    if (!this.root) return;
    try {
      const data = await getJSON(endpoints.status);
      this.render(data);
      document.dispatchEvent(new CustomEvent('status:update', { detail: data }));
    } catch (error) {
      this.root.innerHTML = `<div class="status-card__error">Status niet beschikbaar: ${error.message}</div>`;
    }
  }

  render(data) {
    const now = new Date();
    const nextSwitch = data.carousel.next_switch_at ? new Date(data.carousel.next_switch_at) : null;
    const totalSeconds = Math.max(0, (data.carousel.minutes || 0) * 60);
    let secondsLeft = null;
    let progress = null;

    if (nextSwitch) {
      secondsLeft = Math.round((nextSwitch.getTime() - now.getTime()) / 1000);
    }

    if (data.carousel.running && totalSeconds > 0 && typeof secondsLeft === 'number') {
      const ratio = 1 - secondsLeft / totalSeconds;
      progress = Math.max(0, Math.min(1, ratio));
    }

    const localNext = nextSwitch ? nextSwitch.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
    const resolution = Array.isArray(data.target_size) ? data.target_size.join(' × ') : '—';
    const currentFile = data.carousel.current_file || '—';
    const nextLabel = secondsLeft != null ? formatDuration(secondsLeft) : '—';

    this.root.innerHTML = `
      <div class="status-card__badges">
        <span class="badge ${data.display_ready ? 'badge--ok' : 'badge--warn'}">
          Display ${data.display_ready ? 'actief' : 'offline'}
        </span>
        <span class="badge ${data.carousel.running ? 'badge--ok' : 'badge--idle'}">
          Carousel ${data.carousel.running ? 'actief' : 'gepauzeerd'}
        </span>
      </div>
      <div class="status-card__metrics">
        <dl>
          <div>
            <dt>Resolutie</dt>
            <dd>${resolution}</dd>
          </div>
          <div>
            <dt>Interval</dt>
            <dd>${data.carousel.minutes || 0} minuten</dd>
          </div>
          <div>
            <dt>Huidige foto</dt>
            <dd title="${currentFile}">${currentFile}</dd>
          </div>
          <div>
            <dt>Volgende wissel</dt>
            <dd>${localNext}</dd>
          </div>
        </dl>
      </div>
      ${progress !== null ? `
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress * 100)}">
          <span class="progress__bar" style="width:${(progress * 100).toFixed(0)}%"></span>
        </div>
        <p class="status-card__note">Nog ${nextLabel} tot de volgende wissel</p>
      ` : '<p class="status-card__note">Carousel staat stil</p>'}
      <p class="status-card__timestamp">Bijgewerkt om ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</p>
    `;
  }
}
