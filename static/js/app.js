import { StatusCard } from './components/statusCard.js';
import { CarouselControls } from './components/carouselControls.js';
import { UploadManager } from './components/uploadManager.js';
import { GalleryManager } from './components/galleryManager.js';
import { CalendarWidget } from './components/calendarWidget.js';
import { SystemNotes } from './components/systemNotes.js';
import { PreviewPanel } from './components/previewPanel.js';

function initClock(clockEl) {
  if (!clockEl) return;
  const update = () => {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  update();
  setInterval(update, 60000);
}

function ready(fn) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn);
  } else {
    fn();
  }
}

ready(() => {
  const statusCard = new StatusCard(document.querySelector('#statusCard'));
  const carousel = new CarouselControls(
    document.querySelector('#carouselForm'),
    document.querySelector('#carouselMessage')
  );
  const preview = new PreviewPanel(
    document.querySelector('#previewPanel'),
    document.querySelector('#previewMeta'),
    document.querySelector('#refreshPreview')
  );
  const gallery = new GalleryManager(
    document.querySelector('#imageGrid'),
    document.querySelector('#galleryEmpty'),
    document.querySelector('#galleryMessage')
  );
  new UploadManager(
    document.querySelector('#uploadForm'),
    document.querySelector('#uploadMessage')
  );
  const calendar = new CalendarWidget(document.querySelector('#calendarWidget'));
  const notes = new SystemNotes(document.querySelector('#systemNotes'));

  initClock(document.querySelector('#clock'));
  calendar.render();
  statusCard.start();
  preview.start();
  gallery.load();

  document.querySelector('#forceStatus')?.addEventListener('click', () => statusCard.refresh());
  document.querySelector('#refreshGallery')?.addEventListener('click', () => gallery.load());

  document.addEventListener('gallery:refresh', () => gallery.load());
  document.addEventListener('status:update', (event) => {
    const detail = event.detail;
    carousel.sync(detail);
    gallery.markCurrent(detail?.carousel?.current_file || null);
    notes.setStatus(detail);
    preview.updateFromStatus(detail);
  });
  document.addEventListener('gallery:updated', (event) => {
    notes.setGalleryCount(event.detail?.count ?? 0);
    preview.refresh(true);
  });
});
