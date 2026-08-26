"""Offline single-window interface, served on localhost.

A browser page rather than a Tk window on purpose: the people running this
include blind and partially sighted volunteers, and screen readers (NVDA,
JAWS, VoiceOver) support browser content far better than they support Tk.
Everything is inlined, nothing is fetched from the network, and the server
binds to 127.0.0.1 only.
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import traceback
import urllib.parse
import uuid
import webbrowser
from typing import Dict

from .cli import process_one
from .pipeline import Options

JOBS: Dict[str, dict] = {}
ROOT = os.getcwd()
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")

PAGE = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مُبصِر - تحويل الوثائق العربية</title>
<style>
 :root{--bg:#0f1115;--fg:#f2f4f8;--mut:#aab2c0;--acc:#4da3ff;--ok:#31c48d;
       --warn:#f5a623;--card:#181c24;--line:#2a3140;}
 @media (prefers-color-scheme: light){
   :root{--bg:#fbfcfe;--fg:#12151b;--mut:#4a5262;--acc:#0b5fbe;--ok:#0a7a52;
         --warn:#9a5b00;--card:#fff;--line:#d6dbe4;}}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);font-size:19px;line-height:1.7;
      font-family:"Segoe UI","Noto Naskh Arabic",system-ui,-apple-system,sans-serif;}
 .wrap{max-width:940px;margin:0 auto;padding:2rem 1.25rem 4rem}
 h1{font-size:2.1rem;margin:.2em 0}
 .sub{color:var(--mut);margin:0 0 1.6rem}
 .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
       padding:1.5rem;margin-bottom:1.25rem}
 #drop{border:3px dashed var(--line);border-radius:14px;padding:2.4rem 1.25rem;
       text-align:center;transition:.15s;cursor:pointer}
 #drop:hover,#drop:focus-visible,#drop.hot{border-color:var(--acc);background:rgba(77,163,255,.09)}
 #drop:focus-visible{outline:3px solid var(--acc);outline-offset:3px}
 .big{font-size:1.35rem;font-weight:600}
 button{font:inherit;font-weight:600;background:var(--acc);color:#fff;border:0;
        border-radius:10px;padding:.85rem 1.6rem;cursor:pointer;min-height:52px}
 button:focus-visible{outline:3px solid var(--fg);outline-offset:3px}
 button[disabled]{opacity:.5;cursor:not-allowed}
 .bar{height:26px;background:var(--line);border-radius:13px;overflow:hidden;margin:.9rem 0}
 .bar>i{display:block;height:100%;width:0;background:var(--ok);transition:width .3s}
 .en{color:var(--mut);font-size:.85em;direction:ltr;unicode-bidi:isolate}
 ul.files{list-style:none;padding:0;margin:.5rem 0 0}
 ul.files li{border-top:1px solid var(--line);padding:.75rem 0}
 a.dl{display:inline-block;margin:.3rem .6rem .3rem 0;padding:.6rem 1.1rem;
      background:transparent;border:2px solid var(--acc);color:var(--acc);
      border-radius:10px;text-decoration:none;font-weight:600}
 a.dl:focus-visible{outline:3px solid var(--fg);outline-offset:2px}
 table{width:100%;border-collapse:collapse;margin-top:.8rem}
 th,td{text-align:right;padding:.45rem .6rem;border-bottom:1px solid var(--line);font-size:.95rem}
 .err{color:#ff6b6b;white-space:pre-wrap;font-size:.9rem}
 .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
</style></head><body>
<div class="wrap">
 <h1>مُبصِر</h1>
 <p class="sub">تحويل الوثائق العربية الممسوحة إلى ملف Word نظيف
   <span class="en">— Arabic documents to a clean Word file, fully offline</span></p>

 <div class="card">
  <div id="drop" tabindex="0" role="button"
       aria-describedby="drophint">
    <div class="big">اسحب الملف هنا، أو اضغط للاختيار</div>
    <div class="en">Drag a PDF or image here, or press to choose</div>
  </div>
  <p id="drophint" class="en">PDF, PNG, JPG, TIFF. Nothing leaves this computer.</p>
  <input id="file" type="file" class="vh" multiple
         accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.txt">
  <button id="scan" type="button">أو عالج مجلد input <span class="en">(process ./input)</span></button>
 </div>

 <div class="card" role="status" aria-live="polite" id="statuscard">
  <div id="msg">جاهز <span class="en">Ready</span></div>
  <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"
       aria-valuenow="0" aria-label="التقدم Progress" id="pbar"><i id="pfill"></i></div>
 </div>

 <div class="card" id="results" hidden>
  <h2>النتائج <span class="en">Results</span></h2>
  <ul class="files" id="filelist"></ul>
 </div>
</div>
<script>
const $=s=>document.querySelector(s);
const drop=$("#drop"), fileInput=$("#file");
drop.onclick=()=>fileInput.click();
drop.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();fileInput.click();}};
["dragenter","dragover"].forEach(t=>drop.addEventListener(t,e=>{
  e.preventDefault();drop.classList.add("hot");}));
["dragleave","drop"].forEach(t=>drop.addEventListener(t,e=>{
  e.preventDefault();drop.classList.remove("hot");}));
drop.addEventListener("drop",e=>{if(e.dataTransfer.files.length)send(e.dataTransfer.files);});
fileInput.onchange=()=>{if(fileInput.files.length)send(fileInput.files);};
$("#scan").onclick=()=>fetch("/api/scan",{method:"POST"}).then(r=>r.json()).then(track);

function setProgress(p,text){
  $("#pfill").style.width=(p*100).toFixed(0)+"%";
  $("#pbar").setAttribute("aria-valuenow",(p*100).toFixed(0));
  if(text) $("#msg").textContent=text;
}
async function send(files){
  setProgress(0,"جارٍ الرفع… Uploading…");
  let job=null;
  for(const f of files){
    const r=await fetch("/api/upload",{method:"POST",
      headers:{"X-Filename":encodeURIComponent(f.name)},body:f});
    job=await r.json();
  }
  track(job);
}
function track(job){
  if(!job||!job.job){setProgress(0,"لا توجد ملفات No files");return;}
  const id=job.job;
  const t=setInterval(async()=>{
    const s=await (await fetch("/api/status?job="+id)).json();
    setProgress(s.frac||0,(s.ar||"")+"  "+(s.en||""));
    if(s.done){clearInterval(t);show(s);}
  },600);
}
function show(s){
  $("#results").hidden=false;
  const ul=$("#filelist"); ul.innerHTML="";
  (s.results||[]).forEach(r=>{
    const li=document.createElement("li");
    if(r.error){
      li.innerHTML=`<strong>${r.name}</strong><div class="err">${r.error}</div>`;
    }else{
      li.innerHTML=`<strong>${r.name}</strong>
        <table><tr><th>صفحات</th><td>${r.pages}</td><th>فقرات</th><td>${r.paragraphs}</td>
        <th>بحاجة مراجعة</th><td>${r.flagged}</td><th>ثانية</th><td>${r.seconds}</td></tr></table>
        <a class="dl" href="/api/download?job=${s.job}&i=${r.i}&kind=docx">تنزيل Word</a>
        <a class="dl" href="/api/download?job=${s.job}&i=${r.i}&kind=txt">نص</a>
        <a class="dl" href="/api/download?job=${s.job}&i=${r.i}&kind=report" target="_blank">تقرير المراجعة</a>`;
    }
    ul.appendChild(li);
  });
  setProgress(1,"تم ✓ Done");
}
</script></body></html>"""


def _run_job(job_id: str, paths):
    job = JOBS[job_id]
    opts = Options()
    results = []
    total = max(len(paths), 1)
    for i, path in enumerate(paths):
        name = os.path.basename(path)

        def prog(en, ar, frac, i=i, name=name):
            job["frac"] = (i + min(frac, 1.0)) / total
            job["en"] = f"{name}: {en}"
            job["ar"] = ar

        try:
            from .pipeline import Pipeline
            pipe = Pipeline(opts, progress=prog)
            res = pipe.run(path)
            from .docx_out import build_docx, build_plain_text
            from .report import write_report
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            stem = os.path.splitext(name)[0]
            out = {
                "docx": os.path.join(OUTPUT_DIR, f"{stem}.docx"),
                "txt": os.path.join(OUTPUT_DIR, f"{stem}.txt"),
                "report": os.path.join(OUTPUT_DIR, f"{stem}.review.html"),
            }
            build_docx(res.paras, out["docx"])
            build_plain_text(res.paras, out["txt"])
            write_report(res, out["report"], source_name=name)
            results.append({"i": i, "name": name, "paths": out, **res.stats})
        except Exception as e:
            results.append({"i": i, "name": name,
                            "error": f"{type(e).__name__}: {e}",
                            "trace": traceback.format_exc()[-800:]})
    job.update(done=True, frac=1.0, en="Done", ar="تم", results=results)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/status":
            job = JOBS.get(q.get("job", [""])[0])
            return self._send(200 if job else 404,
                              json.dumps(job or {"error": "no job"}, ensure_ascii=False).encode())
        if u.path == "/api/download":
            job = JOBS.get(q.get("job", [""])[0]) or {}
            try:
                i = int(q.get("i", ["0"])[0])
                kind = q.get("kind", ["docx"])[0]
                path = job["results"][i]["paths"][kind]
                data = open(path, "rb").read()
            except Exception:
                return self._send(404, b'{"error":"not found"}')
            ctype = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "txt": "text/plain; charset=utf-8",
                     "report": "text/html; charset=utf-8"}[kind]
            disp = "inline" if kind == "report" else "attachment"
            return self._send(200, data, ctype,
                              {"Content-Disposition": f'{disp}; filename="{os.path.basename(path)}"'})
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/upload":
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            name = urllib.parse.unquote(self.headers.get("X-Filename", "upload.pdf"))
            name = os.path.basename(name).replace("\x00", "") or "upload.pdf"
            os.makedirs(INPUT_DIR, exist_ok=True)
            dest = os.path.join(INPUT_DIR, name)
            with open(dest, "wb") as f:
                f.write(raw)
            return self._start([dest])
        if u.path == "/api/scan":
            paths = []
            if os.path.isdir(INPUT_DIR):
                for f in sorted(os.listdir(INPUT_DIR)):
                    if f.startswith("."):
                        continue
                    p = os.path.join(INPUT_DIR, f)
                    if os.path.isfile(p):
                        paths.append(p)
            return self._start(paths)
        return self._send(404, b'{"error":"not found"}')

    def _start(self, paths):
        if not paths:
            return self._send(200, json.dumps({"job": None}).encode())
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"job": job_id, "frac": 0.0, "en": "Queued", "ar": "في الانتظار",
                        "done": False, "results": []}
        threading.Thread(target=_run_job, args=(job_id, paths), daemon=True).start()
        return self._send(200, json.dumps({"job": job_id}).encode())


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port: int = 8765, open_browser: bool = True) -> None:
    for p in range(port, port + 20):
        try:
            httpd = Server(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit("no free port in range")
    url = f"http://127.0.0.1:{p}/"
    print(f"مُبصِر يعمل على  {url}\nmubsir is running at {url}\nCtrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    serve()
