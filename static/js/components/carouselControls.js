import { endpoints, post } from '../api.js';

export class CarouselControls {
  constructor(form, messageEl) {
    this.form = form;
    this.messageEl = messageEl;
    this.minutesInput = form ? form.querySelector('input[name="minutes"]') : null;
    this.startButton = form ? form.querySelector('[data-action="start"]') : null;
    this.stopButton = form ? form.querySelector('[data-action="stop"]') : null;
    this.init();
  }

  init() {
    if (!this.form) return;
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      this.start();
    });
    if (this.stopButton) {
      this.stopButton.addEventListener('click', () => this.stop());
    }
  }

  async start() {
    if (!this.minutesInput) return;
    const minutes = Math.max(1, parseInt(this.minutesInput.value, 10) || 1);
    try {
      const data = await post(`${endpoints.carouselStart}?minutes=${encodeURIComponent(minutes)}`);
      this.setMessage(data.ok ? 'Carousel gestart' : data.error || 'Onbekende fout');
    } catch (error) {
      this.setMessage(`Start mislukt: ${error.message}`);
    }
  }

  async stop() {
    try {
      const data = await post(endpoints.carouselStop);
      this.setMessage(data.ok ? 'Carousel gestopt' : data.error || 'Onbekende fout');
    } catch (error) {
      this.setMessage(`Stop mislukt: ${error.message}`);
    }
  }

  sync(status) {
    if (!status || !this.minutesInput) return;
    if (typeof status.carousel?.minutes === 'number') {
      this.minutesInput.value = status.carousel.minutes;
    }
    const running = Boolean(status.carousel?.running);
    if (this.startButton) {
      this.startButton.disabled = running;
    }
    if (this.stopButton) {
      this.stopButton.disabled = !running;
    }
  }

  setMessage(message) {
    if (!this.messageEl) return;
    this.messageEl.textContent = message;
  }
}
