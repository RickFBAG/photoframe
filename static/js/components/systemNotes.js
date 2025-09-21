const BASE_NOTES = [
  'Gebruik het dashboard op hetzelfde netwerk als de Raspberry Pi.',
  'Uploads worden automatisch bijgesneden voor het Inky-scherm.'
];

export class SystemNotes {
  constructor(listEl) {
    this.listEl = listEl;
    this.state = {
      status: null,
      galleryCount: null
    };
    this.render();
  }

  setStatus(status) {
    this.state.status = status;
    this.render();
  }

  setGalleryCount(count) {
    this.state.galleryCount = count;
    this.render();
  }

  render() {
    if (!this.listEl) return;
    const items = [...BASE_NOTES];

    if (this.state.status) {
      const { display_ready: displayReady, carousel } = this.state.status;
      items.unshift(
        displayReady ? 'Display gereed voor nieuwe afbeeldingen.' : 'Display niet gedetecteerd: controleer kabel en voeding.'
      );
      const nextSwitch = carousel?.next_switch_at
        ? new Date(carousel.next_switch_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '—';
      items.push(`Carousel: ${carousel?.running ? 'actief' : 'gepauzeerd'} (interval ${carousel?.minutes || 0} min, volgende ${nextSwitch}).`);
    }

    if (typeof this.state.galleryCount === 'number') {
      items.push(`Galerij bevat ${this.state.galleryCount} bestand(en).`);
    }

    this.listEl.innerHTML = '';
    items.forEach((note) => {
      const li = document.createElement('li');
      li.textContent = note;
      this.listEl.appendChild(li);
    });
  }
}
