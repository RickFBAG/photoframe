#!/usr/bin/env python3
"""
Single-file web app for Raspberry Pi Zero 2 W + Inky Impression 7.3"

What it does:
- Multi-upload images via browser
- Auto crop-to-fill to Inky LANDSCAPE then save
- List, preview, delete from /image
- Display on Inky (uses the exact boilerplate from Pimoroni guide)
- Carousel with minutes-per-photo
- Runs on LAN

Deps: Pillow, inky
"""

import io
import os
import re
import sys
import json
import time
import html
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ---------- Config ----------
HOST = "0.0.0.0"
PORT = 8080
IMAGE_DIR = Path("/image")  # can be a symlink to ~/photoframe/images
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# If your panel is mounted upside down, set True
ROTATE_180_ON_DISPLAY = False

# ---------- Deps ----------
try:
    from PIL import Image, ImageOps, ImageDraw, ImageFont
except Exception as e:
    print("ERROR: Pillow (PIL) is required:", e, file=sys.stderr)
    sys.exit(1)

# Pimoroni boilerplate, exactly as in the guide
try:
    from inky.auto import auto
    inky_display = auto()
except Exception as e:
    print("ERROR: inky library is required and the display must be connected:", e, file=sys.stderr)
    sys.exit(1)

# ---------- Inky init ----------
INKY_LOCK = threading.Lock()
try:
    DISP_W, DISP_H = inky_display.width, inky_display.height
    # Force landscape numbers for preprocessing and storage
    if DISP_W < DISP_H:
        DISP_W, DISP_H = DISP_H, DISP_W  # expected 800x480 for the 7.3"
    DISPLAY_READY = True
except Exception as e:
    print("ERROR: Could not initialize Inky display:", e, file=sys.stderr)
    DISPLAY_READY = False
    DISP_W, DISP_H = 800, 480  # fallback for preprocessing

# ---------- State ----------
STATE_LOCK = threading.RLock()
CAROUSEL_RUNNING = False
CAROUSEL_MINUTES = 5
CAROUSEL_THREAD = None
CAROUSEL_STOP_EVENT = threading.Event()
CURRENT_INDEX = -1
NEXT_SWITCH_AT = None  # datetime or None

# ---------- Utils ----------
def ensure_dirs():
    try:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"ERROR: Cannot create {IMAGE_DIR}. Check permissions.", file=sys.stderr)
        sys.exit(1)

def list_images_sorted():
    files = []
    if IMAGE_DIR.exists():
        for p in IMAGE_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in ALLOWED_EXT.union({".jpg"}):
                files.append(p)
    return sorted(files, key=lambda p: p.name.lower())

def safe_slug(name: str) -> str:
    base = os.path.basename(name)
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^A-Za-z0-9._-]", "", base)
    return base or "image"

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def parse_multipart_files(rfile, headers, max_bytes=200 * 1024 * 1024):
    """
    Minimal multipart/form-data parser for multiple 'file' fields.
    Returns list[(filename, BytesIO)]
    """
    ctype = headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        raise ValueError("Content-Type must be multipart/form-data")
    m = re.search(r'boundary=([-\w\'()+_,./:=?]+)', ctype)
    if not m:
        raise ValueError("No multipart boundary")
    boundary = m.group(1)
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    boundary = boundary.encode()

    content_len = int(headers.get("Content-Length", "0"))
    if content_len <= 0:
        raise ValueError("Empty request body")
    if content_len > max_bytes:
        raise ValueError("Body too large")

    data = rfile.read(content_len)
    delimiter = b"--" + boundary
    parts = data.split(delimiter)

    out = []
    total_size = 0
    for part in parts:
        if not part or part in (b"--\r\n", b"--"):
            continue
        try:
            header_blob, body = part.split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        if body.endswith(b"\r\n"):
            body = body[:-2]
        if body.endswith(b"--"):
            body = body[:-2]

        headers_lines = header_blob.split(b"\r\n")
        dispo = b""
        for line in headers_lines:
            if line.lower().startswith(b"content-disposition"):
                dispo = line
                break
        if not dispo:
            continue
        disp_text = dispo.decode(errors="ignore")
        if 'name="file"' not in disp_text:
            continue
        m2 = re.search(r'filename="([^"]+)"', disp_text)
        if not m2:
            continue
        filename = m2.group(1)
        total_size += len(body)
        if total_size > max_bytes:
            raise ValueError("Files too large in total")
        out.append((filename, io.BytesIO(body)))

    if not out:
        raise ValueError("No files found in 'file' field")
    return out

def open_image_first_frame(buf: io.BytesIO) -> Image.Image:
    buf.seek(0)
    img = Image.open(buf)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if getattr(img, "is_animated", False):
        try:
            img.seek(0)
        except Exception:
            pass
    return img

def resize_fill_inky(img: Image.Image) -> Image.Image:
    """
    Crop-to-fill to DISP_W x DISP_H then resize.
    We store already sized images to avoid work at display time.
    """
    tw, th = DISP_W, DISP_H
    # Rotate source to landscape if needed
    if img.width < img.height:
        img = img.transpose(Image.Transpose.ROTATE_90)

    target_ratio = tw / th
    w, h = img.width, img.height
    src_ratio = w / h

    if src_ratio > target_ratio:
        # too wide, crop sides
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        # too tall, crop top/bottom
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    return img.convert("RGB").resize((tw, th), Image.Resampling.LANCZOS)

def save_image(img: Image.Image, original_name: str) -> Path:
    name = safe_slug(original_name)
    stem, _ext = os.path.splitext(name)
    ts = time.strftime("%Y%m%d-%H%M%S")
    final_name = f"{ts}_{stem}.jpg"
    out_path = IMAGE_DIR / final_name
    img.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path

def display_on_inky(img: Image.Image):
    """
    Display exactly as in the Pimoroni guide style:
      - Use the inky_display instance from auto()
      - Prepare a PIL image, then call set_image + show
    We still ensure size matches the panel.
    """
    if not DISPLAY_READY:
        raise RuntimeError("Inky display not available")

    # Ensure exact device size the same way as guide examples expect
    # If your images are already sized at upload, this is a no-op.
    need_w, need_h = inky_display.width, inky_display.height
    rgb = img.convert("RGB")
    if rgb.size != (need_w, need_h):
        rgb = rgb.resize((need_w, need_h), Image.Resampling.LANCZOS)

    if ROTATE_180_ON_DISPLAY:
        rgb = rgb.transpose(Image.Transpose.ROTATE_180)

    with INKY_LOCK:
        inky_display.set_image(rgb)
        inky_display.show()

# ---------- Carousel ----------
def carousel_worker():
    global CURRENT_INDEX, NEXT_SWITCH_AT
    while not CAROUSEL_STOP_EVENT.is_set():
        with STATE_LOCK:
            files = list_images_sorted()
            if not files or not CAROUSEL_RUNNING:
                NEXT_SWITCH_AT = None
                break
            if CURRENT_INDEX < 0 or CURRENT_INDEX >= len(files) - 1:
                CURRENT_INDEX = 0
            else:
                CURRENT_INDEX += 1
            path = files[CURRENT_INDEX]
        try:
            with open(path, "rb") as f:
                img = Image.open(f)
                img = ImageOps.exif_transpose(img).convert("RGB")
            display_on_inky(img)
        except Exception as e:
            print(f"Display error for {path.name}: {e}", file=sys.stderr)
        minutes = max(1, int(CAROUSEL_MINUTES))
        NEXT_SWITCH_AT = datetime.now() + timedelta(minutes=minutes)
        for _ in range(minutes * 60):
            if CAROUSEL_STOP_EVENT.is_set() or not CAROUSEL_RUNNING:
                return
            time.sleep(1)

def start_carousel(minutes: int):
    global CAROUSEL_THREAD, CAROUSEL_RUNNING, CAROUSEL_MINUTES
    with STATE_LOCK:
        files = list_images_sorted()
        if not files:
            raise RuntimeError("No images in /image")
        CAROUSEL_MINUTES = max(1, int(minutes))
        if CAROUSEL_RUNNING:
            stop_carousel()
        CAROUSEL_RUNNING = True
        CAROUSEL_STOP_EVENT.clear()
        CAROUSEL_THREAD = threading.Thread(target=carousel_worker, daemon=True)
        CAROUSEL_THREAD.start()

def stop_carousel():
    global CAROUSEL_RUNNING
    with STATE_LOCK:
        CAROUSEL_RUNNING = False
        CAROUSEL_STOP_EVENT.set()

# ---------- HTTP ----------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Inky Photoframe</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:16px;max-width:900px}
  h1{margin:0 0 8px 0}
  .section{margin:16px 0}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
  .card{border:1px solid #ddd;border-radius:8px;padding:8px}
  .thumb{width:100%;height:100px;object-fit:cover;border-radius:6px}
  button{padding:8px 12px;border:1px solid #ccc;border-radius:8px;background:#f6f6f6;cursor:pointer}
  input[type="number"]{width:90px;padding:8px}
  small{color:#666}
</style>
</head>
<body>
  <h1>Inky Photoframe</h1>
  <div class="section">
    <div id="status"><small>Loading status…</small></div>
  </div>

  <div class="section">
    <h2>Upload</h2>
    <form id="uploadForm">
      <input type="file" name="file" accept="image/*" multiple required>
      <button type="submit">Upload</button>
    </form>
    <div id="uploadMsg"></div>
  </div>

  <div class="section">
    <h2>Carousel</h2>
    <div class="row">
      <label>Minutes per photo</label>
      <input id="minutes" type="number" min="1" value="5">
      <button id="startBtn">Start</button>
      <button id="stopBtn">Stop</button>
    </div>
    <div id="carMsg"></div>
  </div>

  <div class="section">
    <h2>Images in /image</h2>
    <div class="grid" id="grid"></div>
  </div>

<script>
async function getJSON(path){ const r=await fetch(path); return r.json(); }

async function refreshStatus(){
  try{
    const j = await getJSON('/status');
    const disp = j.display_ready ? `Display OK (${j.target_size[0]}x${j.target_size[1]})` : 'Display NOT READY';
    const run = j.carousel.running ? 'Running' : 'Stopped';
    const next = j.carousel.next_switch_at || '-';
    document.getElementById('status').innerHTML =
      `Status: ${disp} • Carousel: ${run} • Interval: ${j.carousel.minutes} min • Current: ${j.carousel.current_file || '-'} • Next: ${next}`;
    document.getElementById('minutes').value = j.carousel.minutes;
  }catch(e){ document.getElementById('status').textContent = 'Status error'; }
}

async function refreshList(){
  try{
    const j = await getJSON('/list');
    const g = document.getElementById('grid'); g.innerHTML = '';
    j.items.forEach(it=>{
      const d = document.createElement('div'); d.className='card';
      d.innerHTML = `
        <a href="${it.url}" target="_blank"><img class="thumb" src="${it.url}" alt="${it.name}"></a>
        <div style="font-size:12px;margin-top:6px">${it.name}</div>
        <div class="row" style="margin-top:6px">
          <button data-file="${it.name}" data-act="display">Display on Inky</button>
          <button data-file="${it.name}" data-act="delete">Delete</button>
        </div>`;
      g.appendChild(d);
    });
    g.onclick = async (e)=>{
      const btn = e.target.closest('button'); if(!btn) return;
      const file = btn.dataset.file;
      if(btn.dataset.act==='display'){
        const r = await fetch('/display?file='+encodeURIComponent(file), {method:'POST'});
        const j = await r.json();
        document.getElementById('carMsg').textContent = j.ok ? 'Displayed' : (j.error || 'Error');
        refreshStatus();
      } else if (btn.dataset.act==='delete'){
        if(!confirm('Delete this image?')) return;
        const r = await fetch('/delete?file='+encodeURIComponent(file), {method:'POST'});
        const j = await r.json();
        document.getElementById('uploadMsg').textContent = j.ok ? 'Deleted' : (j.error || 'Error');
        refreshList(); refreshStatus();
      }
    };
  }catch(e){ /* ignore */ }
}

document.getElementById('uploadForm').onsubmit = async (e)=>{
  e.preventDefault();
  const fd = new FormData(e.target); // multiple files included
  const r = await fetch('/upload', {method:'POST', body: fd});
  const j = await r.json();
  if (j.ok) {
    document.getElementById('uploadMsg').textContent = `Uploaded ${j.saved.length} file(s)`;
  } else if (j.saved && j.saved.length) {
    document.getElementById('uploadMsg').textContent = `Partial: ${j.saved.length} saved, ${j.errors.length} failed`;
  } else {
    document.getElementById('uploadMsg').textContent = j.error || 'Upload error';
  }
  refreshList(); refreshStatus();
};

document.getElementById('startBtn').onclick = async ()=>{
  const minutes = parseInt(document.getElementById('minutes').value,10);
  const r = await fetch('/carousel/start?minutes='+minutes, {method:'POST'});
  const j = await r.json();
  document.getElementById('carMsg').textContent = j.ok ? 'Carousel started' : (j.error || 'Error');
  refreshStatus();
};
document.getElementById('stopBtn').onclick = async ()=>{
  const r = await fetch('/carousel/stop', {method:'POST'});
  const j = await r.json();
  document.getElementById('carMsg').textContent = j.ok ? 'Carousel stopped' : (j.error || 'Error');
  refreshStatus();
};

refreshStatus(); refreshList();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    server_version = "InkyPhotoframe/1.3"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._send_html(INDEX_HTML)
            return

        if path == "/status":
            self._json_status()
            return

        if path == "/list":
            self._json_list()
            return

        if path.startswith("/image/"):
            self._serve_image(path[len("/image/"):])
            return

        self._send_json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/upload":
            self._handle_upload()
            return

        if path == "/display":
            self._handle_display(query)
            return

        if path == "/delete":
            self._handle_delete(query)
            return

        if path == "/carousel/start":
            self._carousel_start(query)
            return

        if path == "/carousel/stop":
            self._carousel_stop()
            return

        self._send_json({"ok": False, "error": "Not found"}, 404)

    # ---- endpoints ----
    def _json_status(self):
        with STATE_LOCK:
            files = list_images_sorted()
            current_name = files[CURRENT_INDEX].name if (0 <= CURRENT_INDEX < len(files)) else None
            payload = {
                "ok": True,
                "display_ready": DISPLAY_READY,
                "target_size": [DISP_W, DISP_H],
                "carousel": {
                    "running": CAROUSEL_RUNNING,
                    "minutes": CAROUSEL_MINUTES,
                    "current_index": CURRENT_INDEX,
                    "current_file": current_name,
                    "next_switch_at": NEXT_SWITCH_AT.isoformat(timespec="seconds") if NEXT_SWITCH_AT else None
                }
            }
        self._send_json(payload, 200)

    def _json_list(self):
        items = []
        for p in list_images_sorted():
            try:
                st = p.stat()
                items.append({
                    "name": p.name,
                    "size": st.st_size,
                    "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                    "url": f"/image/{html.escape(p.name)}"
                })
            except Exception:
                pass
        self._send_json({"ok": True, "items": items}, 200)

    def _serve_image(self, name: str):
        name = os.path.basename(unquote(name))
        p = IMAGE_DIR / name
        if not p.exists() or not p.is_file():
            self._send_json({"ok": False, "error": "Not found"}, 404)
            return
        try:
            with open(p, "rb") as f:
                data = f.read()
            self.send_response(200)
            ctype = "image/jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _handle_upload(self):
        try:
            files = parse_multipart_files(self.rfile, self.headers)
            results, errors = [], []
            for filename, buf in files:
                try:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in ALLOWED_EXT:
                        raise ValueError(f"Unsupported file type: {ext}")
                    img = open_image_first_frame(buf)
                    processed = resize_fill_inky(img)
                    out = save_image(processed, filename)
                    results.append({"file": out.name, "url": f"/image/{out.name}"})
                except Exception as e:
                    errors.append({"file": filename, "error": str(e)})

            ok = len(results) > 0 and len(errors) == 0
            status = 200 if ok else (207 if results else 400)  # 207 = partial success
            self._send_json({"ok": ok, "saved": results, "errors": errors}, status)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 400)

    def _handle_display(self, query):
        try:
            if not DISPLAY_READY:
                raise RuntimeError("Inky display not available")
            files = query.get("file")
            if not files:
                raise ValueError("Missing ?file=")
            name = os.path.basename(files[0])
            p = IMAGE_DIR / name
            if not p.exists():
                raise FileNotFoundError("Image not found")
            with open(p, "rb") as f:
                img = Image.open(f)
                img = ImageOps.exif_transpose(img).convert("RGB")
            display_on_inky(img)
            with STATE_LOCK:
                arr = list_images_sorted()
                global CURRENT_INDEX
                CURRENT_INDEX = next((i for i, q in enumerate(arr) if q.name == name), -1)
            self._send_json({"ok": True}, 200)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 503)

    def _handle_delete(self, query):
        try:
            files = query.get("file")
            if not files:
                raise ValueError("Missing ?file=")
            name = os.path.basename(files[0])
            p = IMAGE_DIR / name
            if not p.exists() or not p.is_file():
                raise FileNotFoundError("Image not found")
            p.unlink()
            with STATE_LOCK:
                arr = list_images_sorted()
                global CURRENT_INDEX
                if CURRENT_INDEX >= len(arr):
                    CURRENT_INDEX = len(arr) - 1
            self._send_json({"ok": True}, 200)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 400)

    def _carousel_start(self, query):
        try:
            minutes_raw = query.get("minutes", [""])[0]
            minutes = int(minutes_raw)
            if minutes < 1:
                raise ValueError("Minutes must be >= 1")
            if not DISPLAY_READY:
                raise RuntimeError("Inky display not available")
            start_carousel(minutes)
            self._send_json({"ok": True}, 200)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 400)

    def _carousel_stop(self):
        try:
            stop_carousel()
            self._send_json({"ok": True}, 200)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    # ---- helpers ----
    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html_text: str, status=200):
        data = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

# ---------- Main ----------
def main():
    if not DISPLAY_READY:
        print("WARNING: Inky display is not ready. Upload/list works, display actions will fail.", file=sys.stderr)
    ensure_dirs()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[{now_iso()}] Server running on http://{HOST}:{PORT}  (images in {IMAGE_DIR})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_carousel()
        server.server_close()
        print("\nStopped.")

if __name__ == "__main__":
    main()
