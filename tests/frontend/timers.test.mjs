import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Script, createContext } from 'node:vm';
import test from 'node:test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const scriptPath = path.resolve(__dirname, '../../server/static/main.js');
const scriptSource = readFileSync(scriptPath, 'utf8');

class ElementStub {
  constructor(id = '') {
    this.id = id;
    this._innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.className = '';
    this.classList = {
      toggle() {},
      add() {},
      remove() {},
    };
    this._listeners = {};
    this._queries = {};
  }

  set innerHTML(value) {
    this._innerHTML = value;
    this.children = [];
  }

  get innerHTML() {
    return this._innerHTML;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(type, handler) {
    this._listeners[type] = handler;
  }

  querySelector(selector) {
    if (!this._queries[selector]) {
      this._queries[selector] = new ElementStub(`${this.id || 'node'}:${selector}`);
    }
    return this._queries[selector];
  }

  querySelectorAll() {
    return [];
  }

  set onclick(handler) {
    this._listeners.click = handler;
  }

  get onclick() {
    return this._listeners.click;
  }
}

test('status polling is coalesced and clock updates on an interval', async () => {
  const intervals = [];
  const recordInterval = (fn, delay) => {
    intervals.push({ fn, delay });
    return intervals.length;
  };

  const elements = new Map();

  const createWeatherPanel = () => {
    const panel = new ElementStub('weatherPanel');
    panel.dataset = { lat: '52.37', lon: '4.89', days: '5' };
    const selectors = [
      '.weather-status',
      '.weather-icon',
      '.weather-temp',
      '.weather-description',
      '.weather-meta',
      '.weather-updated',
      '.weather-forecast',
    ];
    selectors.forEach((selector) => {
      panel._queries[selector] = new ElementStub(`weatherPanel:${selector}`);
    });
    return panel;
  };

  const getElement = (id) => {
    if (id === 'newsBoard') {
      return null;
    }
    if (!elements.has(id)) {
      let element;
      if (id === 'weatherPanel') {
        element = createWeatherPanel();
      } else {
        element = new ElementStub(id);
      }
      elements.set(id, element);
    }
    return elements.get(id) || null;
  };

  const eventHandlers = {};

  const documentStub = {
    addEventListener(type, handler) {
      eventHandlers[type] = handler;
    },
    getElementById(id) {
      return getElement(id);
    },
    createElement(tag) {
      return new ElementStub(tag);
    },
    createDocumentFragment() {
      return new ElementStub('fragment');
    },
  };

  const storage = {
    _data: new Map(),
    getItem(key) {
      return this._data.has(key) ? this._data.get(key) : null;
    },
    setItem(key, value) {
      this._data.set(key, String(value));
    },
    removeItem(key) {
      this._data.delete(key);
    },
    clear() {
      this._data.clear();
    },
  };

  const okResponse = (body) => ({
    ok: true,
    async json() {
      return body;
    },
  });

  const fetchStub = async (url) => {
    if (typeof url === 'object' && url !== null && 'url' in url) {
      // Request object support is not needed for these tests
      url = url.url;
    }
    if (typeof url !== 'string') {
      return okResponse({});
    }
    if (url.startsWith('/status')) {
      return okResponse({
        display_ready: true,
        target_size: [600, 448],
        carousel: {
          running: true,
          minutes: 5,
          next_switch_at: 'soon',
          current_file: 'image.jpg',
        },
      });
    }
    if (url.startsWith('/list')) {
      return okResponse({ items: [] });
    }
    if (url.startsWith('/calendar')) {
      return okResponse({
        ok: true,
        events: [],
        warnings: [],
        updated_at: new Date().toISOString(),
        source_count: 1,
      });
    }
    if (url.startsWith('/weather')) {
      const now = new Date().toISOString();
      return okResponse({
        source: 'test',
        location_label: 'Test',
        latitude: 0,
        longitude: 0,
        timezone: 'UTC',
        fetched_at: now,
        current: { weathercode: 1, temperature: 12, windspeed: 5, time: now },
        daily: [],
        units: { temperature: '°C', windspeed: 'km/h' },
      });
    }
    return okResponse({});
  };

  const sandbox = {
    console,
    setInterval: recordInterval,
    clearInterval() {},
    setTimeout() {},
    clearTimeout() {},
    document: documentStub,
    navigator: { language: 'en-US' },
    fetch: fetchStub,
    localStorage: storage,
  };

  sandbox.window = {
    setInterval: recordInterval,
    clearInterval() {},
    setTimeout() {},
    clearTimeout() {},
    document: documentStub,
    navigator: sandbox.navigator,
    fetch: fetchStub,
    localStorage: storage,
    confirm: () => true,
  };

  sandbox.window.window = sandbox.window;

  const context = createContext(sandbox);
  context.window = sandbox.window;
  context.document = documentStub;
  context.navigator = sandbox.navigator;
  context.fetch = fetchStub;
  context.localStorage = storage;
  context.setInterval = recordInterval;
  context.clearInterval = () => {};
  context.setTimeout = () => {};
  context.clearTimeout = () => {};

  const script = new Script(scriptSource, { filename: 'server/static/main.js' });
  script.runInContext(context);

  assert.equal(typeof eventHandlers.DOMContentLoaded, 'function');
  eventHandlers.DOMContentLoaded();

  // Allow any pending microtasks to run
  await Promise.resolve();

  const statusIntervals = intervals.filter((entry) => entry.fn === context.refreshStatus);
  assert.equal(statusIntervals.length, 1);
  const expectedStatusDelay =
    typeof context.STATUS_REFRESH_INTERVAL === 'number' ? context.STATUS_REFRESH_INTERVAL : 5000;
  assert.equal(statusIntervals[0].delay, expectedStatusDelay);

  const clockIntervals = intervals.filter(
    (entry) => entry.fn === context.updateClock && entry.delay === 60000,
  );
  assert.equal(clockIntervals.length, 1);

  const beforeEnsure = intervals.length;
  context.ensureStatusPolling();
  assert.equal(intervals.length, beforeEnsure);
});
