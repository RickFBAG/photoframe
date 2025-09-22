import { endpoints } from '../api.js';

function formatTimestamp(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }
  return date.toLocaleString();
}

export class PreviewPanel {
  constructor(panelEl, metaEl, refreshButton) {
    this.panelEl = panelEl;
    this.metaEl = metaEl;
    this.refreshButton = refreshButton;
    this.imageEl = panelEl ? panelEl.querySelector('img') : null;
    this.layout = panelEl?.dataset?.layout || 'default';
    this.theme = panelEl?.dataset?.theme || 'ink';
    this.objectUrl = null;
    this.loading = false;
    this.lastSource = Symbol('initial');
    this.handleRefreshClick = () => this.refresh(true);

    if (this.refreshButton) {
      this.refreshButton.addEventListener('click', this.handleRefreshClick);
    }
  }

  start() {
    if (!this.panelEl) return;
    this.refresh();
  }

  updateFromStatus(status) {
    const current = status?.carousel?.current_file || null;
    if (this.lastSource !== current) {
      this.lastSource = current;
      this.refresh();
    }
  }

  async refresh(force = false) {
    if (!this.imageEl) return;
    if (this.loading && !force) return;
    this.loading = true;
    try {
      if (this.metaEl) {
        this.metaEl.textContent = 'Preview laden…';
      }
      const url = this.buildUrl(endpoints.previewImage);
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const generatedAt = response.headers.get('x-preview-generated-at');
      const stale = response.headers.get('x-preview-stale') === 'true';
      const source = response.headers.get('x-preview-source');
      const cache = response.headers.get('x-preview-cache');
      const blob = await response.blob();
      this.assignImage(blob);
      this.updateMeta({ generatedAt, stale, source, cache });
    } catch (error) {
      if (this.metaEl) {
        this.metaEl.textContent = `Preview mislukt: ${error.message}`;
      }
    } finally {
      this.loading = false;
    }
  }

  assignImage(blob) {
    if (!this.imageEl) return;
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
    }
    this.objectUrl = URL.createObjectURL(blob);
    this.imageEl.src = this.objectUrl;
  }

  updateMeta({ generatedAt, stale, source, cache }) {
    if (!this.metaEl) return;
    const parts = [];
    if (source) {
      parts.push(source);
    }
    if (generatedAt) {
      parts.push(`gerenderd ${formatTimestamp(generatedAt)}`);
    }
    parts.push(stale ? 'verouderde preview' : 'actueel');
    if (cache) {
      parts.push(`cache ${cache}`);
    }
    this.metaEl.textContent = parts.join(' • ');
  }

  buildUrl(base) {
    const url = new URL(base, window.location.origin);
    if (this.layout) {
      url.searchParams.set('layout', this.layout);
    }
    if (this.theme) {
      url.searchParams.set('theme', this.theme);
    }
    return url.toString();
  }

  destroy() {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
    if (this.refreshButton) {
      this.refreshButton.removeEventListener('click', this.handleRefreshClick);
    }
  }
}
