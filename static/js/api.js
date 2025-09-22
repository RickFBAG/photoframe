const BASE = '/api';

async function handleResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = { ok: false, error: 'Ongeldig antwoord van server' };
  }
  if (!response.ok || (payload && payload.ok === false)) {
    const message = payload && payload.error ? payload.error : `HTTP ${response.status}`;
    const err = new Error(message);
    err.response = payload;
    err.status = response.status;
    throw err;
  }
  return payload;
}

export async function getJSON(path) {
  const response = await fetch(path.startsWith('http') ? path : `${path}`, {
    cache: 'no-store'
  });
  return handleResponse(response);
}

export async function post(path, options = {}) {
  const response = await fetch(path.startsWith('http') ? path : `${path}`, {
    method: 'POST',
    cache: 'no-store',
    ...options
  });
  return handleResponse(response);
}

export async function postJSON(path, options = {}) {
  return post(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body || JSON.stringify(options.json || {})
  });
}

export async function postForm(path, formData) {
  return post(path, { body: formData });
}

export const endpoints = {
  status: `${BASE}/status`,
  images: `${BASE}/images`,
  upload: `${BASE}/upload`,
  display: `${BASE}/display`,
  delete: `${BASE}/delete`,
  carouselStart: `${BASE}/carousel/start`,
  carouselStop: `${BASE}/carousel/stop`,
  previewImage: '/preview',
  previewMeta: '/preview/meta'
};
