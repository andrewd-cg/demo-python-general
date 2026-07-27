import base64
import datetime
import io
import os
import socket
import ssl
import sys
from urllib.parse import urlparse

import jwt
import requests
from flask import Flask, jsonify, render_template_string, request
from mistralai.client import Mistral
from PIL import Image, ExifTags

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 3000))
JWT_SECRET = os.environ.get("JWT_SECRET", "demo-secret-key")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "pixtral-12b-2409")


def get_os_release():
    try:
        fields = {}
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep:
                    fields[key.strip()] = value.strip().strip('"')
        return fields.get("PRETTY_NAME") or fields.get("NAME") or "unknown"
    except OSError:
        return "unavailable"


def get_tls_info(host, port=443):
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.create_connection((host, port), timeout=10), server_hostname=host) as ssock:
            cert = ssock.getpeercert()

        not_after = cert.get("notAfter", "")
        not_before = cert.get("notBefore", "")
        expiry = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
        issued = datetime.datetime.strptime(not_before, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
        days_remaining = (expiry - datetime.datetime.now(datetime.timezone.utc)).days

        subject = dict(x[0] for x in cert.get("subject", []))
        issuer = dict(x[0] for x in cert.get("issuer", []))
        sans = [f"{t}: {v}" for t, v in cert.get("subjectAltName", [])][:6]

        return {
            "ok": True,
            "subject_cn": subject.get("commonName", "—"),
            "issuer_cn": issuer.get("commonName", "—"),
            "issuer_o": issuer.get("organizationName", "—"),
            "expires": expiry.strftime("%Y-%m-%d"),
            "issued": issued.strftime("%Y-%m-%d"),
            "days_remaining": days_remaining,
            "serial": cert.get("serialNumber", "—"),
            "sans": sans,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def analyze_image(url):
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    data = resp.content

    img = Image.open(io.BytesIO(data))

    exif_data = {}
    try:
        raw_exif = img.getexif()
        if raw_exif:
            for tag_id, value in raw_exif.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                if isinstance(value, (str, int, float)) and len(str(value)) < 80:
                    exif_data[str(tag)] = str(value)
    except Exception:
        pass

    thumb = img.copy()
    thumb.thumbnail((520, 520))
    if thumb.mode in ("RGBA", "P", "LA"):
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    thumb_b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "format": img.format or "unknown",
        "mode": img.mode,
        "width": img.width,
        "height": img.height,
        "frames": getattr(img, "n_frames", 1),
        "file_size": len(data),
        "exif": dict(list(exif_data.items())[:10]),
        "thumb_b64": thumb_b64,
    }


def get_ai_caption(url, api_key=None):
    if not api_key:
        return None, "No Mistral API key configured"
    try:
        client = Mistral(api_key=api_key)
        resp = client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Describe this image in 2-3 concise sentences."},
                ],
            }],
        )
        return resp.choices[0].message.content.strip(), None
    except Exception as exc:
        return None, str(exc)


def verify_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, "Missing or invalid Authorization header"
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "Token expired"
    except jwt.InvalidTokenError as exc:
        return None, str(exc)


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Image Analyzer</title>
  <style>
    :root {
      --bg: #0d1117; --surface: #161b22; --surface2: #1c2128;
      --border: #30363d; --text: #e6edf3; --muted: #8b949e;
      --green: #3fb950; --green-dim: #1a4226;
      --yellow: #e3b341; --yellow-dim: #3d2f00;
      --red: #f85149; --red-dim: #3d1117;
      --accent: #58a6ff; --purple: #bc8cff; --radius: 10px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg); color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; min-height: 100vh; padding: 2rem 1rem;
    }
    .wrap { max-width: 960px; margin: 0 auto; }
    .header { margin-bottom: 2rem; }
    .header h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0.75rem; }
    .header h1 span { color: var(--accent); }
    .sys-badges { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .badge {
      display: inline-flex; align-items: center; gap: 0.35rem;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 6px; padding: 0.3rem 0.6rem; font-size: 11px; color: var(--muted);
    }
    .badge .label { color: var(--accent); font-weight: 600; }

    .input-row { display: flex; gap: 0.5rem; margin-bottom: 2rem; }
    .url-input {
      flex: 1; background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); color: var(--text); font: inherit;
      padding: 0.7rem 1rem; outline: none; transition: border-color 0.15s;
    }
    .url-input:focus { border-color: var(--accent); }
    .url-input::placeholder { color: var(--muted); }
    .btn {
      background: var(--accent); color: #0d1117; border: none;
      border-radius: var(--radius); font: inherit; font-weight: 700;
      padding: 0.7rem 1.4rem; cursor: pointer; transition: opacity 0.15s; white-space: nowrap;
    }
    .btn:hover { opacity: 0.85; }
    .btn:disabled { opacity: 0.4; cursor: default; }
    /* Settings */
    .settings {
      display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem;
    }
    .api-input {
      flex: 1; background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); color: var(--text); font: inherit;
      padding: 0.55rem 1rem; outline: none; transition: border-color 0.15s;
    }
    .api-input:focus { border-color: var(--accent); }
    .api-input::placeholder { color: var(--muted); }
    .api-label { color: var(--muted); font-size: 11px; white-space: nowrap; }
    .saved-pill {
      font-size: 11px; color: var(--green); display: none; white-space: nowrap;
    }

    .error-banner {
      background: var(--red-dim); border: 1px solid var(--red);
      border-radius: var(--radius); color: var(--red);
      padding: 0.8rem 1rem; margin-bottom: 1.5rem; display: none;
    }
    .loading {
      display: none; align-items: center; gap: 0.75rem;
      color: var(--muted); margin-bottom: 1.5rem; font-size: 12px;
    }
    .spinner {
      width: 16px; height: 16px; border: 2px solid var(--border);
      border-top-color: var(--accent); border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .results { display: none; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    .card-header {
      padding: 0.65rem 1rem; border-bottom: 1px solid var(--border);
      font-weight: 600; font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--muted);
      display: flex; align-items: center; justify-content: space-between;
    }
    .card-body { padding: 1rem; }
    .img-preview { width: 100%; height: auto; display: block; }
    .img-meta { padding: 0.75rem 1rem; border-top: 1px solid var(--border); }
    .kv { width: 100%; border-collapse: collapse; }
    .kv tr + tr td { border-top: 1px solid var(--border); }
    .kv td { padding: 0.45rem 0; vertical-align: top; line-height: 1.5; }
    .kv td:first-child { color: var(--muted); width: 40%; padding-right: 0.75rem; }
    .kv td:last-child { color: var(--text); word-break: break-all; }
    .pill {
      display: inline-flex; align-items: center; gap: 0.3rem;
      border-radius: 20px; padding: 0.15rem 0.55rem; font-size: 11px; font-weight: 600;
    }
    .pill.green { background: var(--green-dim); color: var(--green); }
    .pill.yellow { background: var(--yellow-dim); color: var(--yellow); }
    .pill.red { background: var(--red-dim); color: var(--red); }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    .caption-text { color: var(--text); line-height: 1.7; }
    .caption-error { color: var(--muted); font-style: italic; }
    .san-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.5rem; }
    .san {
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: 4px; padding: 0.15rem 0.45rem; font-size: 11px; color: var(--muted);
    }
    .divider { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>Secure Image <span>Analyzer</span></h1>
    <div class="sys-badges">
      <div class="badge"><span class="label">os</span> {{ os_name }}</div>
      <div class="badge"><span class="label">uid</span> {{ uid }}</div>
      <div class="badge"><span class="label">host</span> {{ hostname }}</div>
      <div class="badge"><span class="label">python</span> {{ python_version }}</div>
    </div>
  </div>

  <div class="settings">
    <span class="api-label">Mistral API key</span>
    <input id="api-key-input" class="api-input" type="password"
           placeholder="sk-..." autocomplete="off" oninput="saveApiKey()">
    <span class="saved-pill" id="saved-pill">saved</span>
  </div>

  <div class="input-row">
    <input id="url-input" class="url-input" type="url"
           value="https://img.americasbestpics.com/images/d510ae18091c20aed1b092cd6614bf7302d9899780ab4f3386888e98afe3b8e6_1.jpg">
    <button class="btn" id="analyze-btn" onclick="analyze()">Analyze</button>
  </div>

  <div class="error-banner" id="error-banner"></div>
  <div class="loading" id="loading">
    <div class="spinner"></div>
    <span>Fetching image and inspecting TLS...</span>
  </div>

  <div class="results" id="results">
    <div class="card" style="margin-bottom:1rem;">
      <div class="card-header">
        <span>AI Caption</span>
        <span style="color:var(--accent);font-size:10px;text-transform:none;letter-spacing:0">via Mistral</span>
      </div>
      <div class="card-body">
        <div id="caption-content"></div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <div class="card-header">Image Preview</div>
        <img id="img-preview" class="img-preview" src="" alt="preview">
        <div class="img-meta">
          <table class="kv" id="img-meta-table"></table>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:1rem;">
        <div class="card">
          <div class="card-header">
            <span>TLS Certificate</span>
            <span id="tls-pill"></span>
          </div>
          <div class="card-body">
            <table class="kv" id="tls-table"></table>
            <div id="sans-section" style="display:none">
              <hr class="divider">
              <div style="color:var(--muted);font-size:11px;margin-bottom:0.4rem;">Subject Alt Names</div>
              <div class="san-list" id="sans-list"></div>
            </div>
          </div>
        </div>
        <div class="card" id="exif-card" style="display:none">
          <div class="card-header">EXIF Metadata</div>
          <div class="card-body">
            <table class="kv" id="exif-table"></table>
          </div>
        </div>
      </div>
    </div>
  </div>

</div>
<script>
const LS_KEY = 'mistral_api_key';

function saveApiKey() {
  const val = document.getElementById('api-key-input').value;
  if (val) localStorage.setItem(LS_KEY, val);
  else localStorage.removeItem(LS_KEY);
  const pill = document.getElementById('saved-pill');
  pill.style.display = 'inline';
  setTimeout(() => pill.style.display = 'none', 1500);
}

function loadApiKey() {
  const val = localStorage.getItem(LS_KEY);
  if (val) document.getElementById('api-key-input').value = val;
}

loadApiKey();

function fmt_bytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(2) + ' MB';
}

function kv_rows(data, table) {
  table.innerHTML = '';
  for (const [k, v] of data) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${k}</td><td>${v}</td>`;
    table.appendChild(tr);
  }
}

function pill(days) {
  if (days > 30) return `<span class="pill green"><span class="dot"></span>Valid (${days}d)</span>`;
  if (days > 0)  return `<span class="pill yellow"><span class="dot"></span>Expiring (${days}d)</span>`;
  return `<span class="pill red"><span class="dot"></span>Expired</span>`;
}

async function analyze() {
  const url = document.getElementById('url-input').value.trim();
  if (!url) return;

  const btn = document.getElementById('analyze-btn');
  const loading = document.getElementById('loading');
  const results = document.getElementById('results');
  const errorBanner = document.getElementById('error-banner');

  btn.disabled = true;
  loading.style.display = 'flex';
  results.style.display = 'none';
  errorBanner.style.display = 'none';

  try {
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, mistral_key: localStorage.getItem(LS_KEY) || '' }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    document.getElementById('img-preview').src = 'data:image/jpeg;base64,' + data.image.thumb_b64;
    kv_rows([
      ['format', data.image.format],
      ['dimensions', `${data.image.width} x ${data.image.height} px`],
      ['mode', data.image.mode],
      ['frames', data.image.frames],
      ['file size', fmt_bytes(data.image.file_size)],
    ], document.getElementById('img-meta-table'));

    const tls = data.tls;
    document.getElementById('tls-pill').innerHTML = tls.ok
      ? pill(tls.days_remaining)
      : `<span class="pill red"><span class="dot"></span>Error</span>`;
    if (tls.ok) {
      kv_rows([
        ['subject', tls.subject_cn], ['issuer', tls.issuer_cn], ['org', tls.issuer_o],
        ['issued', tls.issued], ['expires', tls.expires], ['serial', tls.serial],
      ], document.getElementById('tls-table'));
      if (tls.sans && tls.sans.length) {
        document.getElementById('sans-list').innerHTML = tls.sans.map(s => `<span class="san">${s}</span>`).join('');
        document.getElementById('sans-section').style.display = 'block';
      }
    } else {
      kv_rows([['error', tls.error]], document.getElementById('tls-table'));
    }

    const exifCard = document.getElementById('exif-card');
    if (data.image.exif && Object.keys(data.image.exif).length > 0) {
      kv_rows(Object.entries(data.image.exif), document.getElementById('exif-table'));
      exifCard.style.display = 'block';
    } else {
      exifCard.style.display = 'none';
    }

    document.getElementById('caption-content').innerHTML = data.caption
      ? `<p class="caption-text">${data.caption}</p>`
      : `<p class="caption-error">${data.caption_error || 'No caption available'}</p>`;

    results.style.display = 'block';
  } catch (err) {
    errorBanner.textContent = err.message;
    errorBanner.style.display = 'block';
  } finally {
    btn.disabled = false;
    loading.style.display = 'none';
  }
}

document.getElementById('url-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') analyze();
});
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(
        PAGE,
        uid=os.getuid(),
        os_name=get_os_release(),
        hostname=socket.gethostname(),
        python_version=sys.version.split()[0],
    )


@app.post("/token")
def token():
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "demo-user",
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
    }
    token_str = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return jsonify(token=token_str)


@app.post("/analyze")
def analyze():
    body = request.get_json(force=True) or {}
    url = body.get("url", "").strip()
    if not url.startswith("https://"):
        return jsonify(error="URL must start with https://"), 400

    parsed = urlparse(url)
    tls = get_tls_info(parsed.hostname, parsed.port or 443)

    try:
        image_info = analyze_image(url)
    except Exception as exc:
        return jsonify(error=f"Image fetch failed: {exc}"), 502

    mistral_key = body.get("mistral_key") or MISTRAL_API_KEY
    caption, caption_error = get_ai_caption(url, mistral_key)
    return jsonify(tls=tls, image=image_info, caption=caption, caption_error=caption_error)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    print(f"Server running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
