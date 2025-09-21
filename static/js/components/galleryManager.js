import { endpoints, getJSON, post } from '../api.js';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}

export class GalleryManager {
  constructor(gridEl, emptyStateEl, messageEl) {
    this.gridEl = gridEl;
    this.emptyStateEl = emptyStateEl;
    this.messageEl = messageEl;
    this.items = [];
    this.currentFile = null;
    this.gridEl?.addEventListener('click', (event) => this.onClick(event));
  }

  async load() {
    if (!this.gridEl) return;
    try {
      const data = await getJSON(endpoints.images);
      this.items = data.items || [];
      this.render();
    } catch (error) {
      this.setMessage(`Kan lijst niet laden: ${error.message}`);
    }
  }

  render() {
    if (!this.gridEl) return;
    this.gridEl.innerHTML = '';
    if (!this.items.length) {
      if (this.emptyStateEl) {
        this.emptyStateEl.hidden = false;
      }
      document.dispatchEvent(new CustomEvent('gallery:updated', { detail: { count: 0 } }));
      return;
    }
    if (this.emptyStateEl) {
      this.emptyStateEl.hidden = true;
    }
    const fragment = document.createDocumentFragment();
    this.items.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'image-card';
      card.dataset.file = item.name;
      card.innerHTML = `
        <a href="${item.url}" target="_blank" rel="noopener" class="image-card__link">
          <img src="${item.url}" alt="${item.name}" class="image-card__thumb" loading="lazy">
        </a>
        <div class="image-card__meta">
          <strong title="${item.name}">${item.name}</strong>
          <span>${formatBytes(item.size)}</span>
          <span>${formatDate(item.created_at)}</span>
        </div>
        <div class="image-card__actions">
          <button type="button" class="action-button" data-action="display" data-file="${item.name}">Toon</button>
          <button type="button" class="ghost-button" data-action="delete" data-file="${item.name}">Verwijder</button>
        </div>
      `;
      fragment.appendChild(card);
    });
    this.gridEl.appendChild(fragment);
    this.applyCurrentHighlight();
    document.dispatchEvent(new CustomEvent('gallery:updated', { detail: { count: this.items.length } }));
  }

  markCurrent(fileName) {
    this.currentFile = fileName;
    this.applyCurrentHighlight();
  }

  applyCurrentHighlight() {
    if (!this.gridEl) return;
    [...this.gridEl.querySelectorAll('.image-card')].forEach((card) => {
      card.classList.toggle('is-current', Boolean(this.currentFile) && card.dataset.file === this.currentFile);
    });
  }

  async onClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const file = button.dataset.file;
    if (!file) return;
    if (button.dataset.action === 'display') {
      await this.display(file);
    } else if (button.dataset.action === 'delete') {
      if (confirm(`Weet je zeker dat je ${file} wilt verwijderen?`)) {
        await this.remove(file);
      }
    }
  }

  async display(file) {
    try {
      const data = await post(`${endpoints.display}?file=${encodeURIComponent(file)}`);
      this.setMessage(data.ok ? `${file} weergegeven` : data.error || 'Onbekende fout');
    } catch (error) {
      this.setMessage(`Tonen mislukt: ${error.message}`);
    }
  }

  async remove(file) {
    try {
      const data = await post(`${endpoints.delete}?file=${encodeURIComponent(file)}`);
      if (data.ok) {
        this.setMessage(`${file} verwijderd`);
        await this.load();
      } else {
        this.setMessage(data.error || 'Verwijderen mislukt');
      }
    } catch (error) {
      this.setMessage(`Verwijderen mislukt: ${error.message}`);
    }
  }

  setMessage(message) {
    if (this.messageEl) {
      this.messageEl.textContent = message;
    }
  }
}
