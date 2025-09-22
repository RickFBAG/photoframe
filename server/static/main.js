const WEATHER_CACHE_KEY = 'weather:last-response';
const WEATHER_CACHE_TTL = 10 * 60 * 1000; // 10 minuten
const WEATHER_CACHE_MAX_AGE = WEATHER_CACHE_TTL * 3;

const WEATHER_CODES = {
  0: { icon: '☀', label: 'Helder' },
  1: { icon: '🌤', label: 'Meestal helder' },
  2: { icon: '⛅', label: 'Gedeeltelijk bewolkt' },
  3: { icon: '☁', label: 'Bewolkt' },
  45: { icon: '🌫', label: 'Mist' },
  48: { icon: '🌫', label: 'IJsmist' },
  51: { icon: '🌦', label: 'Motregen licht' },
  53: { icon: '🌦', label: 'Motregen' },
  55: { icon: '🌧', label: 'Motregen zwaar' },
  56: { icon: '🌧', label: 'Motregen ijzel' },
  57: { icon: '🌧', label: 'Motregen zware ijzel' },
  61: { icon: '🌦', label: 'Lichte regen' },
  63: { icon: '🌧', label: 'Regen' },
  65: { icon: '🌧', label: 'Zware regen' },
  66: { icon: '🌧', label: 'IJzel' },
  67: { icon: '🌧', label: 'Zware ijzel' },
  71: { icon: '🌨', label: 'Lichte sneeuw' },
  73: { icon: '🌨', label: 'Sneeuw' },
  75: { icon: '❄', label: 'Zware sneeuw' },
  77: { icon: '❄', label: 'Sneeuwkorrels' },
  80: { icon: '🌦', label: 'Lichte buien' },
  81: { icon: '🌧', label: 'Regenbuien' },
  82: { icon: '🌧', label: 'Zware regenbuien' },
  85: { icon: '🌨', label: 'Sneeuwbuien' },
  86: { icon: '🌨', label: 'Zware sneeuwbuien' },
  95: { icon: '⛈', label: 'Onweer' },
  96: { icon: '⛈', label: 'Onweer met hagel' },
  99: { icon: '⛈', label: 'Zwaar onweer' },
};

function describeWeather(code) {
  return WEATHER_CODES[code] || { icon: '☁', label: 'Onbekend' };
}

function formatTime(value, timezone = 'UTC') {
  if (!value) return '—';
  try {
    const date = new Date(value);
    return date.toLocaleString('nl-NL', {
      hour: '2-digit',
      minute: '2-digit',
      day: 'numeric',
      month: 'short',
      timeZone: timezone,
    });
  } catch (err) {
    return value;
  }
}

function formatDay(value, timezone = 'UTC') {
  if (!value) return '—';
  try {
    const date = new Date(value);
    return date.toLocaleDateString('nl-NL', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone: timezone,
    });
  } catch (err) {
    return value;
  }
}

function loadWeatherCache() {
  try {
    const raw = localStorage.getItem(WEATHER_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || !parsed.data) return null;
    return parsed;
  } catch (err) {
    return null;
  }
}

function saveWeatherCache(data) {
  try {
    const payload = { timestamp: Date.now(), data };
    localStorage.setItem(WEATHER_CACHE_KEY, JSON.stringify(payload));
  } catch (err) {
    // Ignore storage errors (e.g. private browsing)
  }
}

function renderWeather(data, options = {}) {
  const panel = document.getElementById('weatherPanel');
  if (!panel || !data) return;

  const { stale = false, error = null } = options;
  const statusEl = panel.querySelector('.weather-status');
  const iconEl = panel.querySelector('.weather-icon');
  const tempEl = panel.querySelector('.weather-temp');
  const descEl = panel.querySelector('.weather-description');
  const metaEl = panel.querySelector('.weather-meta');
  const updatedEl = panel.querySelector('.weather-updated');
  const forecastEl = panel.querySelector('.weather-forecast');
  const units = data.units || {};

  panel.classList.toggle('is-stale', Boolean(stale));

  const descriptor = describeWeather(data.current?.weathercode);
  const locationLabel = data.location_label || `${Number.parseFloat(data.latitude || 0).toFixed(2)}°, ${Number.parseFloat(data.longitude || 0).toFixed(2)}°`;

  if (statusEl) {
    const info = [`Bron: ${data.source || 'onbekend'}`, `Locatie ${locationLabel}`];
    if (stale) info.push('Toont cache');
    if (error) info.push(`Fout: ${error}`);
    statusEl.textContent = info.join(' • ');
  }
  if (iconEl) iconEl.textContent = descriptor.icon;
  if (tempEl) {
    const temp = typeof data.current?.temperature === 'number'
      ? `${Math.round(data.current.temperature)}${units.temperature || '°C'}`
      : '—';
    tempEl.textContent = temp;
  }
  if (descEl) descEl.textContent = descriptor.label;
  if (metaEl) {
    const parts = [];
    if (typeof data.current?.windspeed === 'number') {
      parts.push(`Wind ${Math.round(data.current.windspeed)} ${units.windspeed || 'km/h'}`);
    }
    if (data.current?.time) {
      parts.push(`Gemeten ${formatTime(data.current.time, data.timezone)}`);
    }
    metaEl.textContent = parts.join(' • ') || 'Geen details beschikbaar';
  }
  if (updatedEl) {
    updatedEl.textContent = `Laatst bijgewerkt: ${formatTime(data.fetched_at, data.timezone)}`;
  }
  if (forecastEl) {
    forecastEl.innerHTML = '';
    (data.daily || []).forEach((day) => {
      const item = document.createElement('li');
      item.className = 'weather-day';

      const dayLabel = document.createElement('div');
      dayLabel.className = 'day-label';
      dayLabel.textContent = formatDay(day.date, data.timezone);

      const dayIcon = document.createElement('div');
      dayIcon.className = 'day-icon';
      const dayDescriptor = describeWeather(day.weathercode);
      dayIcon.textContent = dayDescriptor.icon;

      const dayDesc = document.createElement('div');
      dayDesc.className = 'day-desc';
      dayDesc.textContent = dayDescriptor.label;

      const dayTemp = document.createElement('div');
      dayTemp.className = 'day-temp';
      const max = typeof day.temperature_max === 'number'
        ? `${Math.round(day.temperature_max)}${units.temperature || '°C'}`
        : '—';
      const min = typeof day.temperature_min === 'number'
        ? `${Math.round(day.temperature_min)}${units.temperature || '°C'}`
        : '—';
      const precip = typeof day.precipitation_probability === 'number'
        ? ` • Neerslag ${Math.round(day.precipitation_probability)}${units.precipitation_probability || '%'}`
        : '';
      dayTemp.textContent = `${max} / ${min}${precip}`;

      item.appendChild(dayLabel);
      item.appendChild(dayIcon);
      item.appendChild(dayDesc);
      item.appendChild(dayTemp);
      forecastEl.appendChild(item);
    });
    if (!forecastEl.children.length) {
      const empty = document.createElement('li');
      empty.className = 'weather-day';
      empty.textContent = 'Geen verwachting beschikbaar';
      forecastEl.appendChild(empty);
    }
  }
}

async function refreshWeather(force = false) {
  const panel = document.getElementById('weatherPanel');
  if (!panel) return;

  const lat = Number.parseFloat(panel.dataset.lat || '52.37');
  const lon = Number.parseFloat(panel.dataset.lon || '4.89');
  const days = Number.parseInt(panel.dataset.days || '5', 10);
  const cached = loadWeatherCache();
  const now = Date.now();

  if (!force && cached && now - cached.timestamp < WEATHER_CACHE_TTL) {
    renderWeather(cached.data);
    return;
  }

  const statusEl = panel.querySelector('.weather-status');
  if (statusEl) {
    statusEl.textContent = 'Weersinformatie wordt bijgewerkt…';
  }

  try {
    const url = `/weather?latitude=${lat}&longitude=${lon}&days=${days}`;
    const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const data = await response.json();
    renderWeather(data);
    saveWeatherCache(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'onbekende fout';
    if (cached && now - cached.timestamp < WEATHER_CACHE_MAX_AGE) {
      renderWeather(cached.data, { stale: true, error: message });
    } else if (statusEl) {
      statusEl.textContent = `Geen weerdata beschikbaar (${message})`;
    }
  }
}

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

  const cachedWeather = loadWeatherCache();
  if (cachedWeather && Date.now() - cachedWeather.timestamp < WEATHER_CACHE_MAX_AGE) {
    renderWeather(cachedWeather.data, { stale: true });
  }
  const refreshButton = document.getElementById('weatherRefresh');
  if (refreshButton) {
    refreshButton.addEventListener('click', () => refreshWeather(true));
  }
  refreshWeather();
  setInterval(() => refreshWeather(), 15 * 60 * 1000);

});
