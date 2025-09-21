import { endpoints, postForm } from '../api.js';

export class UploadManager {
  constructor(form, messageEl) {
    this.form = form;
    this.messageEl = messageEl;
    this.init();
  }

  init() {
    if (!this.form) return;
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      this.upload();
    });
  }

  async upload() {
    if (!this.form) return;
    const formData = new FormData(this.form);
    try {
      const data = await postForm(endpoints.upload, formData);
      if (data.ok) {
        const count = data.saved?.length || 0;
        this.setMessage(`Upload voltooid: ${count} bestand(en)`);
        this.form.reset();
        document.dispatchEvent(new CustomEvent('gallery:refresh'));
      } else if (data.saved?.length) {
        this.setMessage(`Gedeeltelijk gelukt: ${data.saved.length} opgeslagen, ${data.errors?.length || 0} fouten`);
        document.dispatchEvent(new CustomEvent('gallery:refresh'));
      } else {
        this.setMessage(data.error || 'Upload mislukt');
      }
    } catch (error) {
      this.setMessage(`Upload mislukt: ${error.message}`);
    }
  }

  setMessage(message) {
    if (this.messageEl) {
      this.messageEl.textContent = message;
    }
  }
}
