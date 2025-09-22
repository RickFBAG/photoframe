async function getJSON(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function refreshStatus() {
  try {
    const data = await getJSON('/status');
    const status = document.getElementById('status');
    const display = data.display_ready
      ? `Display OK (${data.target_size[0]}x${data.target_size[1]})`
      : 'Display NOT READY';
    const running = data.carousel.running ? 'Running' : 'Stopped';
    const next = data.carousel.next_switch_at || '-';
    status.innerHTML = `Status: ${display} • Carousel: ${running} • Interval: ${data.carousel.minutes} min • Current: ${data.carousel.current_file || '-'} • Next: ${next}`;
    document.getElementById('minutes').value = data.carousel.minutes;
  } catch (err) {
    document.getElementById('status').textContent = 'Status error';
  }
}

async function refreshList() {
  try {
    const data = await getJSON('/list');
    const grid = document.getElementById('grid');
    grid.innerHTML = '';
    data.items.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <a href="${item.url}" target="_blank" rel="noopener"><img class="thumb" src="${item.url}" alt="${item.name}"></a>
        <div class="meta">${item.name}</div>
        <div class="row" style="margin-top:6px">
          <button data-file="${item.name}" data-act="display">Display on Inky</button>
          <button data-file="${item.name}" data-act="delete">Delete</button>
        </div>`;
      grid.appendChild(card);
    });
    grid.onclick = async (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      const file = button.dataset.file;
      if (button.dataset.act === 'display') {
        const response = await fetch(`/display?file=${encodeURIComponent(file)}`, { method: 'POST' });
        const body = await response.json();
        document.getElementById('carMsg').textContent = body.ok ? 'Displayed' : (body.error || 'Error');
        refreshStatus();
      } else if (button.dataset.act === 'delete') {
        if (!confirm('Delete this image?')) return;
        const response = await fetch(`/delete?file=${encodeURIComponent(file)}`, { method: 'POST' });
        const body = await response.json();
        document.getElementById('uploadMsg').textContent = body.ok ? 'Deleted' : (body.error || 'Error');
        refreshList();
        refreshStatus();
      }
    };
  } catch (err) {
    // ignore list errors for now
  }
}

class NewsBoard {
  constructor(root) {
    this.root = root;
    this.statusEl = root.querySelector('.news-status');
    this.listEl = root.querySelector('.news-list');
    this.cacheKey = 'photoframe.news.cache.v1';
    this.cacheDuration = 10 * 60 * 1000; // 10 minutes
    this.refreshInterval = 5 * 60 * 1000; // refresh every 5 minutes
    this.cached = this.loadCache();

    if (this.cached && this.cached.items && this.cached.items.length) {
      this.render(this.cached.items, { fromCache: true, stale: false });
    }

    this.refresh(true);
    this.intervalId = window.setInterval(() => {
      this.refresh(false);
    }, this.refreshInterval);
  }

  loadCache() {
    try {
      const stored = window.localStorage.getItem(this.cacheKey);
      if (!stored) return null;
      const parsed = JSON.parse(stored);
      if (!parsed || typeof parsed !== 'object') return null;
      if (!Array.isArray(parsed.items)) return null;
      if (typeof parsed.timestamp !== 'number') return null;
      return parsed;
    } catch (err) {
      return null;
    }
  }

  saveCache(data) {
    try {
      window.localStorage.setItem(this.cacheKey, JSON.stringify(data));
    } catch (err) {
      // ignore storage failures (private browsing, quota, ...)
    }
  }

  setStatus(message) {
    if (this.statusEl) {
      this.statusEl.textContent = message;
    }
  }

  formatRelative(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
      return '';
    }
    const now = Date.now();
    const diff = now - date.getTime();
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < 0) {
      return date.toLocaleString(undefined, {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });
    }
    if (diff < minute) return 'zojuist';
    if (diff < hour) {
      const minutes = Math.max(1, Math.round(diff / minute));
      return `${minutes} min geleden`;
    }
    if (diff < day) {
      const hours = Math.max(1, Math.round(diff / hour));
      return `${hours} uur geleden`;
    }
    if (diff < 14 * day) {
      const days = Math.max(1, Math.round(diff / day));
      return `${days} dagen geleden`;
    }
    return date.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
  }

  formatUpdated(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '';
    const diff = Date.now() - date.getTime();
    if (diff < 60 * 1000) {
      return 'zojuist bijgewerkt';
    }
    if (diff < 3600 * 1000) {
      const minutes = Math.max(1, Math.round(diff / (60 * 1000)));
      return `bijgewerkt ${minutes} min geleden`;
    }
    return `bijgewerkt ${date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    })}`;
  }

  createArticle(item) {
    const article = document.createElement('article');
    article.className = 'news-item';

    const heading = document.createElement('h3');
    const link = document.createElement('a');
    link.href = item.link || '#';
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = item.title || 'Onbekend bericht';
    heading.appendChild(link);
    article.appendChild(heading);

    if (item.summary) {
      const summary = document.createElement('p');
      summary.className = 'news-summary';
      summary.textContent = item.summary;
      article.appendChild(summary);
    }

    const meta = document.createElement('p');
    meta.className = 'news-meta';
    const parts = [];
    if (item.source) {
      parts.push(item.source);
    }
    if (item.published_at) {
      const date = new Date(item.published_at);
      const relative = this.formatRelative(date);
      if (relative) {
        parts.push(relative);
      }
      meta.title = date.toLocaleString();
    }
    meta.textContent = parts.join(' • ');
    article.appendChild(meta);

    return article;
  }

  render(items, options = {}) {
    const { fromCache = false, stale = false } = options;
    if (!this.listEl) return;
    this.listEl.innerHTML = '';

    if (!items || !items.length) {
      const empty = document.createElement('div');
      empty.className = 'news-empty';
      empty.textContent = 'Geen nieuwsartikelen gevonden.';
      this.listEl.appendChild(empty);
    } else {
      const fragment = document.createDocumentFragment();
      items.forEach((item) => {
        fragment.appendChild(this.createArticle(item));
      });
      this.listEl.appendChild(fragment);
    }

    if (this.cached) {
      const label = this.formatUpdated(this.cached.timestamp);
      if (fromCache && stale) {
        this.setStatus(label ? `offline • ${label}` : 'offline • nieuws uit cache');
      } else if (fromCache) {
        this.setStatus(label ? `cache • ${label}` : 'cache • nieuws opgeslagen');
      } else {
        this.setStatus(label || 'Nieuws bijgewerkt');
      }
    } else {
      this.setStatus('Nieuws bijgewerkt');
    }
  }

  async refresh(forceNetwork = false) {
    const now = Date.now();
    if (!forceNetwork && this.cached && now - this.cached.timestamp < this.cacheDuration) {
      this.render(this.cached.items, { fromCache: true, stale: false });
      return;
    }

    this.setStatus('Nieuws laden…');

    try {
      const response = await fetch('/news');
      if (!response.ok) {
        throw new Error(`Nieuwsrequest mislukt: ${response.status}`);
      }
      const payload = await response.json();
      const normalized = {
        timestamp: Date.now(),
        items: Array.isArray(payload.items) ? payload.items.slice(0, 24) : [],
        meta: {
          feeds: payload.feeds || [],
          generated_at: payload.generated_at || null,
        },
      };
      this.cached = normalized;
      this.saveCache(normalized);
      this.render(normalized.items, { fromCache: false, stale: false });
    } catch (err) {
      if (this.cached && this.cached.items && this.cached.items.length) {
        const stale = now - this.cached.timestamp > this.cacheDuration;
        this.render(this.cached.items, { fromCache: true, stale });
      } else {
        this.render([], {});
        this.setStatus('Kan nieuws niet laden.');
      }
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const uploadForm = document.getElementById('uploadForm');
  uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(uploadForm);
    const response = await fetch('/upload', { method: 'POST', body: formData });
    const body = await response.json();
    if (body.ok) {
      document.getElementById('uploadMsg').textContent = `Uploaded ${body.saved.length} file(s)`;
    } else if (body.saved && body.saved.length) {
      document.getElementById('uploadMsg').textContent = `Partial: ${body.saved.length} saved, ${body.errors.length} failed`;
    } else {
      document.getElementById('uploadMsg').textContent = body.error || 'Upload error';
    }
    refreshList();
    refreshStatus();
  });

  document.getElementById('startBtn').addEventListener('click', async () => {
    const minutes = parseInt(document.getElementById('minutes').value, 10);
    const response = await fetch(`/carousel/start?minutes=${minutes}`, { method: 'POST' });
    const body = await response.json();
    document.getElementById('carMsg').textContent = body.ok ? 'Carousel started' : (body.error || 'Error');
    refreshStatus();
  });

  document.getElementById('stopBtn').addEventListener('click', async () => {
    const response = await fetch('/carousel/stop', { method: 'POST' });
    const body = await response.json();
    document.getElementById('carMsg').textContent = body.ok ? 'Carousel stopped' : (body.error || 'Error');
    refreshStatus();
  });

  refreshStatus();
  refreshList();
  setInterval(refreshStatus, 5000);

  const newsRoot = document.getElementById('newsBoard');
  if (newsRoot) {
    // eslint-disable-next-line no-new
    new NewsBoard(newsRoot);
  }
});
