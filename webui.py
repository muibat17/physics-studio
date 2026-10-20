#!/usr/bin/env python3
"""Physics Studio dashboard: fill a form in your browser, get a finished video.

Run:  python3 webui.py            (serves on http://localhost:8000)
      python3 webui.py --port 9000

Stdlib only. Builds run in the background; the job page polls until the
MP4 is ready, then offers it for download and inline preview.
"""
import argparse
import html
import json
import subprocess
import sys
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
TOPICS = ROOT / "topics"
JOBS = {}  # id -> {"status", "log", "path"}

VOICES = [
    ("en-US-AndrewNeural", "Andrew (US, default)"),
    ("en-NG-AbeoNeural", "Abeo (Nigerian, male)"),
    ("en-NG-EzinneNeural", "Ezinne (Nigerian, female)"),
    ("en-GB-RyanNeural", "Ryan (UK, male)"),
    ("en-GB-SoniaNeural", "Sonia (UK, female)"),
    ("en-US-JennyNeural", "Jenny (US, female)"),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Physics Studio</title><style>
body{background:#0e1628;color:#e8ecf5;font-family:system-ui,sans-serif;margin:0;padding:16px;max-width:680px;margin-inline:auto}
h1{color:#f6b93d;font-size:1.5rem}h2{color:#f6b93d;font-size:1.05rem;margin-top:28px}
input,select,textarea{width:100%;box-sizing:border-box;background:#1b2740;color:#e8ecf5;border:1px solid #2c3a58;border-radius:10px;padding:10px;font-size:1rem;margin:4px 0 10px}
textarea{min-height:64px}
label{font-size:.85rem;color:#9fb0cc}
.card{background:#141f36;border:1px solid #2c3a58;border-radius:14px;padding:14px;margin:12px 0}
.row2{display:flex;gap:8px}.row2>div{flex:1}
button{background:#f6b93d;color:#0e1628;border:0;border-radius:10px;padding:10px 16px;font-weight:700;font-size:1rem;cursor:pointer}
.ghost{background:#1b2740;color:#9fb0cc;border:1px solid #2c3a58}
#buildbtn{width:100%;padding:14px;margin-top:8px;font-size:1.1rem}
.tone{width:auto}
</style></head><body>
<h1>Physics Studio</h1>
<p style="color:#9fb0cc">Real-life physics explainers, one topic at a time.</p>
<form method="post" action="/build">
<label>Video title</label><input name="title" required value="TOPIC_TITLE">
<div class="row2"><div><label>Voice</label><select name="voice">VOICES</select></div>
<div><label>Pace (%): -8 = slower</label><input name="voice_rate" value="-8%"></div></div>
<div class="row2"><div><label>Card hold after voice (s)</label><input name="card_hold" value="2.0"></div>
<div><label>Hook video file (optional)</label><input name="hook_video" placeholder="photos/my_hook.mp4"></div></div>
<label>Hook narration (first 5 seconds)</label><textarea name="hook_narration" required></textarea>

<h2>Cards</h2>
<div id="cards">FIRSTCARD</div>
<button type="button" class="ghost" onclick="addCard()">+ Add card</button>
<br><br><button id="buildbtn" type="submit">Build video</button>
</form>
<template id="tpl"><div class="card">
  <div class="row2"><div><label>Badge (e.g. KEY IDEA)</label><input name="c_i_label"></div>
  <div><label>Photo (optional)</label><select name="c_i_photo"><option value="">none</option>PHOTOS</select></div></div>
  <label>Card heading</label><input name="c_i_title" required>
  <div class="row2"><div><label>Row 1 text</label><input name="c_i_r1"></div>
  <div><label>Row 1 badge</label><input name="c_i_r1b"></div></div>
  <div class="row2"><div><label>Row 2 text</label><input name="c_i_r2"></div>
  <div><label>Row 2 badge</label><input name="c_i_r2b"></div></div>
  <div class="row2"><div><label>Row 2 tone</label><select class="tone" name="c_i_r2t"><option value="">-</option><option>good</option><option>bad</option></select></div>
  <div><label>Row 1 tone</label><select class="tone" name="c_i_r1t"><option value="">-</option><option>good</option><option>bad</option></select></div></div>
  <label>Bottom line</label><input name="c_i_note">
  <label>Voice script (what it says)</label><textarea name="c_i_narr" required></textarea>
  <button type="button" class="ghost" onclick="this.parentElement.remove()">Remove card</button>
</div></template>
<script>
let i = 1;
function fill(block, n){ block.querySelectorAll('[name]').forEach(el => {
  el.name = el.name.replace('_i_', '_' + n + '_'); }); }
function addCard(){ const t = document.getElementById('tpl');
  const b = t.content.cloneNode(true); fill(b, i++); i++;
  document.getElementById('cards').appendChild(b); }
</script>
</body></html>"""


def page():
    photos = "".join(f'<option>{html.escape(str(p.name))}</option>'
                     for p in sorted((ROOT / "photos").glob("*")))
    voices = "".join(f'<option value="{v}">{t}</option>' for v, t in VOICES)
    tpl = PAGE.replace("@PHOTOS@", photos).replace("@VOICES@", voices)
    tpl = tpl.replace("TOPIC_TITLE", "Next topic (Physics Foundation #N)")
    first = tpl.split("FIRSTCARD")[1].split("</div>\n<script>")[0]
    tpl = tpl.replace("FIRSTCARD", "")
    return tpl.replace("</div>\n<script>", first + "</div>\n<script>", 1) \
              .replace("<template", '<template id="tpl"')


def build_topic(form):
    idxs = sorted({int(k.split("_")[1]) for k in form if k.startswith("c_")})
    cards = []
    for i in idxs:
        g = lambda f: form.get(f"c_{i}_{f}", [""])[0].strip()
        rows = []
        for r in ("r1", "r2"):
            text = g(r)
            if text:
                row = {"text": text}
                if g(r + "b"):
                    row["badge"] = g(r + "b")
                    if g(r + "t"):
                        row["tone"] = g(r + "t")
                rows.append(row)
        narr = g("narr")
        if not narr:
            narr = ". ".join([g("title")] + [r["text"] for r in rows] + [g("note")])
        card = {"label": g("label") or "KEY IDEA", "title": g("title"),
                "rows": rows, "narration": narr}
        if g("note"):
            card["note"] = g("note")
        if g("photo"):
            card["photo"] = g("photo")
        cards.append(card)
    topic = {"title": form["title"][0].strip(),
             "voice": form.get("voice", ["en-US-AndrewNeural"])[0],
             "voice_rate": form.get("voice_rate", ["-8%"])[0] or "-8%",
             "card_hold": float(form.get("card_hold", ["2.0"])[0] or 2.0),
             "cards": cards}
    if form.get("hook_narration", [""])[0].strip():
        topic["hook"] = {"narration": form["hook_narration"][0].strip()}
        if form.get("hook_video", [""])[0].strip():
            topic["hook_video"] = form["hook_video"][0].strip()
    return topic


def run_job(jid, topic):
    OUT.mkdir(exist_ok=True)
    tp = TOPICS / f"web_{jid}.json"
    tp.write_text(json.dumps(topic, indent=2))
    op = OUT / f"web_{jid}.mp4"
    p = subprocess.run([sys.executable, str(ROOT / "physics_studio.py"),
                        "video", str(tp), "-o", str(op)],
                       capture_output=True, text=True, timeout=1800)
    log = (p.stdout + p.stderr)[-4000:]
    ok = p.returncode == 0 and op.exists()
    JOBS[jid].update(status="done" if ok else "error", log=log,
                     path=str(op) if ok else "")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, page().encode())
        elif self.path.startswith("/status/"):
            jid = self.path.split("/status/")[1].removesuffix(".json")
            j = JOBS.get(jid, {"status": "unknown"})
            self._send(200, json.dumps(j).encode(), "application/json")
        elif self.path.startswith("/video/"):
            jid = self.path.split("/video/")[1].removesuffix(".mp4")
            p = Path(JOBS.get(jid, {}).get("path", ""))
            if p.exists():
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition",
                                 'attachment; filename="physics_video.mp4"')
                self.send_header("Content-Length", str(p.stat().st_size))
                self.end_headers()
                with p.open("rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        self.wfile.write(chunk)
            else:
                self._send(404, b"not ready")
        elif self.path.startswith("/job/"):
            jid = self.path.split("/job/")[1]
            body = JOBPAGE.replace("@ID@", jid).encode()
            self._send(200, body)
        else:
            self._send(404, b"not found")

    def do_POST(self):
        if self.path != "/build":
            return self._send(404, b"not found")
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        topic = build_topic(form)
        jid = uuid.uuid4().hex[:10]
        JOBS[jid] = {"status": "running", "log": "building...", "path": ""}
        threading.Thread(target=run_job, args=(jid, topic), daemon=True).start()
        self.send_response(303)
        self.send_header("Location", f"/job/{jid}")
        self.end_headers()


JOBPAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Building...</title><style>body{background:#0e1628;color:#e8ecf5;
font-family:system-ui,sans-serif;padding:24px;max-width:680px;margin-inline:auto}
a,button{background:#f6b93d;color:#0e1628;border:0;border-radius:10px;
padding:12px 20px;font-weight:700;font-size:1rem;text-decoration:none;cursor:pointer}
pre{background:#141f36;padding:12px;border-radius:10px;white-space:pre-wrap;
font-size:.8rem;color:#9fb0cc}video{width:100%;border-radius:12px}</style></head>
<body><h1 id="s">Building your video...</h1><p id="m">This takes about a minute per card.</p>
<div id="done" style="display:none"><p><a id="dl" href="#">Download the MP4</a></p>
<video id="v" controls></video></div>
<pre id="log"></pre>
<script>const id="@ID@";const poll=setInterval(async()=>{const r=await fetch('/status/'+id);
const j=await r.json();document.getElementById('log').textContent=j.log||'';
if(j.status==='done'){clearInterval(poll);document.getElementById('s').textContent='Done!';
document.getElementById('done').style.display='block';
document.getElementById('dl').href='/video/'+id;
document.getElementById('v').src='/video/'+id;document.getElementById('m').textContent='';}
if(j.status==='error'){clearInterval(poll);document.getElementById('s').textContent='Build failed';
document.getElementById('m').textContent='Check the log below.';}},3000);</script>
</body></html>"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    ThreadingHTTPServer(("0.0.0.0", args.port), H).serve_forever()
