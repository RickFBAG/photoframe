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

function getISOWeekString(date) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNumber = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - dayNumber);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const weekNumber = Math.ceil(((target - yearStart) / 86400000 + 1) / 7);
  return `${target.getUTCFullYear()}-W${String(weekNumber).padStart(2, '0')}`;
}

function updateClock() {
  const clockTime = document.getElementById('clockTime');
  const clockDate = document.getElementById('clockDate');
  const clockWeek = document.getElementById('clockWeek');
  if (!clockTime || !clockDate || !clockWeek) return;

  const now = new Date();
  const locale = navigator.language || undefined;
  const time = now.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  const date = now.toLocaleDateString(locale, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
  const week = getISOWeekString(now);

  clockTime.textContent = time;
  clockDate.textContent = date;
  clockWeek.textContent = week;
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
  updateClock();
  setInterval(refreshStatus, 5000);
  setInterval(updateClock, 60000);
});
