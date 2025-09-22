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

function parseDateValue(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

function formatDate(value) {
  return value.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

function formatTime(value) {
  return value.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(value) {
  return value.toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatEventRange(event) {
  const startDate = parseDateValue(event.start);
  const endDate = parseDateValue(event.end);
  if (!startDate) {
    return event.start || '';
  }
  if (event.all_day) {
    if (endDate && endDate > startDate) {
      return `${formatDate(startDate)} – ${formatDate(endDate)}`;
    }
    return formatDate(startDate);
  }
  if (!endDate || endDate <= startDate) {
    return `${formatDate(startDate)} • ${formatTime(startDate)}`;
  }
  const sameDay = startDate.toDateString() === endDate.toDateString();
  if (sameDay) {
    return `${formatDate(startDate)} • ${formatTime(startDate)} – ${formatTime(endDate)}`;
  }
  return `${formatDateTime(startDate)} – ${formatDateTime(endDate)}`;
}

function formatWarnings(warnings) {
  if (!warnings) return '';
  const list = Array.isArray(warnings) ? warnings : [warnings];
  const parts = list
    .map((warning) => {
      if (!warning) return '';
      if (typeof warning === 'string') return warning;
      if (warning.source) {
        const detail = warning.error || warning.message || 'Onbekende fout';
        return `${warning.source}: ${detail}`;
      }
      return warning.error || warning.message || '';
    })
    .filter(Boolean);
  return parts.join(' • ');
}

function formatUpdatedText(value) {
  const date = parseDateValue(value);
  if (!date) return '';
  return `Laatste synchronisatie: ${date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

async function fetchCalendarData() {
  const response = await fetch('/calendar');
  let body;
  try {
    body = await response.json();
  } catch (err) {
    throw new Error('Kon kalendergegevens niet lezen');
  }
  if (!response.ok) {
    throw new Error((body && body.error) || `Serverfout (${response.status})`);
  }
  if (!body || body.ok === false) {
    const warningText = formatWarnings(body ? body.warnings : null);
    const message = (body && body.error) || 'Kalendersynchronisatie mislukt';
    throw new Error(warningText ? `${message} • ${warningText}` : message);
  }
  return body;
}

async function refreshCalendar() {
  const statusEl = document.getElementById('calendarStatus');
  const listEl = document.getElementById('calendarList');
  if (!statusEl || !listEl) return;

  statusEl.textContent = 'Kalender laden…';
  listEl.innerHTML = '';

  try {
    const data = await fetchCalendarData();
    const events = Array.isArray(data.events) ? data.events : [];
    if (!events.length) {
      statusEl.textContent = 'Geen geplande afspraken.';
      return;
    }

    const infoParts = [];
    const updated = formatUpdatedText(data.updated_at);
    if (updated) infoParts.push(updated);
    const warningText = formatWarnings(data.warnings);
    if (warningText) infoParts.push(warningText);
    statusEl.textContent = infoParts.join(' • ');

    const fragment = document.createDocumentFragment();
    events.forEach((event) => {
      const item = document.createElement('li');
      item.className = 'calendar-list__item';

      const date = document.createElement('div');
      date.className = 'calendar-list__date';
      date.textContent = formatEventRange(event);
      item.appendChild(date);

      const title = document.createElement('p');
      title.className = 'calendar-list__title';
      title.textContent = event.title || 'Afspraak';
      item.appendChild(title);

      const metaParts = [];
      if (event.location) {
        metaParts.push(`📍 ${event.location}`);
      }
      if (event.source && data.source_count > 1) {
        metaParts.push(`Bron: ${event.source}`);
      }
      if (metaParts.length) {
        const meta = document.createElement('div');
        meta.className = 'calendar-list__meta';
        meta.textContent = metaParts.join(' • ');
        item.appendChild(meta);
      }

      if (event.description) {
        const description = document.createElement('div');
        description.className = 'calendar-list__description';
        description.textContent = event.description;
        item.appendChild(description);
      }

      fragment.appendChild(item);
    });

    listEl.appendChild(fragment);
  } catch (err) {
    statusEl.textContent = err.message || 'Kalender synchronisatie mislukt';
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
  refreshCalendar();
  setInterval(refreshStatus, 5000);
  setInterval(refreshCalendar, 300000);
});
