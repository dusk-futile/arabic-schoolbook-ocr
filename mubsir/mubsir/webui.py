"""The local site: drop files in, get a clean Word document out.

Served from 127.0.0.1 only, with nothing loaded from the network - no fonts,
no scripts, no analytics. A browser page rather than a desktop window on
purpose: the people running this include blind and partially sighted
volunteers, and screen readers support browser content far better than they
support Tk. Every control is reachable by keyboard, progress is announced
through an ARIA live region, and the interface is Arabic-first.
"""
from __future__ import annotations

import html as _html
import http.server
import json
import os
import socketserver
import threading
import traceback
import urllib.parse
import uuid
import webbrowser
from typing import Dict, List

from .pipeline import Options

JOBS: Dict[str, dict] = {}
ROOT = os.getcwd()
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")

ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp,.txt"

PAGE = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مُبصِر — من ملفات مبعثرة إلى ملف Word نظيف</title>
<style>
 :root{--bg:#0e1116;--fg:#eef1f6;--mut:#9aa4b4;--acc:#4d9dff;--ok:#31c48d;
       --warn:#f5a623;--card:#161b23;--line:#28313f;--shadow:rgba(0,0,0,.4);}
 @media (prefers-color-scheme: light){
   :root{--bg:#f7f9fc;--fg:#11151c;--mut:#5a6474;--acc:#0b5fbe;--ok:#0a7a52;
         --warn:#8a5200;--card:#fff;--line:#dbe1ea;--shadow:rgba(15,25,45,.08);}}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);font-size:18px;line-height:1.7;
   font-family:"Segoe UI","Noto Naskh Arabic",system-ui,-apple-system,sans-serif;}
 .wrap{max-width:900px;margin:0 auto;padding:2rem 1.1rem 5rem}
 header{text-align:center;margin-bottom:1.8rem}
 h1{font-size:2.4rem;margin:.1em 0}
 .sub{color:var(--mut);margin:.2rem 0 .1rem}
 .en{color:var(--mut);font-size:.84em;direction:ltr;unicode-bidi:isolate}
 .card{background:var(--card);border:1px solid var(--line);border-radius:16px;
   padding:1.4rem;margin-bottom:1.1rem;box-shadow:0 1px 3px var(--shadow)}
 #drop{border:3px dashed var(--line);border-radius:16px;padding:2.6rem 1.2rem;
   text-align:center;cursor:pointer;transition:.15s}
 #drop:hover,#drop:focus-visible,#drop.hot{border-color:var(--acc);
   background:color-mix(in srgb,var(--acc) 9%,transparent)}
 #drop:focus-visible{outline:3px solid var(--acc);outline-offset:3px}
 .big{font-size:1.4rem;font-weight:600}
 button{font:inherit;font-weight:600;background:var(--acc);color:#fff;border:0;
   border-radius:11px;padding:.8rem 1.5rem;cursor:pointer;min-height:52px}
 button.ghost{background:transparent;color:var(--acc);border:2px solid var(--acc)}
 button:focus-visible{outline:3px solid var(--fg);outline-offset:3px}
 button[disabled]{opacity:.45;cursor:not-allowed}
 .row{display:flex;gap:.7rem;flex-wrap:wrap;align-items:center}
 .bar{height:24px;background:var(--line);border-radius:12px;overflow:hidden;margin:.8rem 0}
 .bar>i{display:block;height:100%;width:0;background:var(--ok);transition:width .35s}
 ul.files{list-style:none;padding:0;margin:.4rem 0 0}
 ul.files li{border-top:1px solid var(--line);padding:1rem 0}
 ul.files li:first-child{border-top:0}
 a.dl{display:inline-block;margin:.35rem .5rem .35rem 0;padding:.65rem 1.15rem;
   border:2px solid var(--acc);color:var(--acc);border-radius:11px;
   text-decoration:none;font-weight:600}
 a.dl.primary{background:var(--acc);color:#fff}
 a.dl:focus-visible{outline:3px solid var(--fg);outline-offset:2px}
 table.stats{width:100%;border-collapse:collapse;margin:.6rem 0 .2rem;font-size:.9rem}
 table.stats td,table.stats th{padding:.3rem .5rem;text-align:right;
   border-bottom:1px solid var(--line)}
 table.stats th{color:var(--mut);font-weight:500}
 details{margin-top:.7rem}
 summary{cursor:pointer;color:var(--acc);font-weight:600}
 pre.peek{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);
   border-radius:10px;padding:.9rem;max-height:260px;overflow:auto;
   font-family:inherit;font-size:.95rem;line-height:2}
 .err{color:#ff7676;white-space:pre-wrap;font-size:.9rem}
 label.opt{display:inline-flex;align-items:center;gap:.45rem;margin:.2rem 1rem .2rem 0}
 .vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
 .hint{color:var(--mut);font-size:.86rem;margin:.5rem 0 0}
</style></head><body>
<div class="wrap">
 <header>
   <h1>مُبصِر</h1>
   <p class="sub">ضع أي ملفات — تحصل على ملف Word واحد نظيف ومنسّق</p>
   <p class="en">Drop in anything. Get one clean, formatted Word file. Fully offline.</p>
 </header>

 <div class="card">
  <div id="drop" tabindex="0" role="button" aria-describedby="hint">
    <div class="big">اسحب الملفات هنا، أو اضغط للاختيار</div>
    <div class="en">PDF · scans · photos — drag here or press to choose</div>
  </div>
  <p id="hint" class="hint">لا شيء يغادر هذا الجهاز.
    <span class="en">Nothing leaves this computer.</span></p>
  <input id="file" type="file" class="vh" multiple accept="ACCEPT_LIST">
  <div class="row" style="margin-top:.9rem">
    <button id="scan" type="button" class="ghost">عالج مجلد input
      <span class="en">(process ./input)</span></button>
  </div>
  <details>
    <summary>خيارات <span class="en">Options</span></summary>
    <div style="margin-top:.6rem">
      <label class="opt"><input type="checkbox" id="opt_tashkeel" checked>
        الاحتفاظ بالتشكيل <span class="en">keep diacritics</span></label>
      <label class="opt"><input type="checkbox" id="opt_forceocr">
        فرض القراءة الضوئية <span class="en">force OCR</span></label>
      <label class="opt">الأرقام <span class="en">digits</span>
        <select id="opt_digits">
          <option value="keep">كما هي</option>
          <option value="arabic_indic">٠١٢٣</option>
          <option value="western">0123</option>
        </select></label>
    </div>
  </details>
 </div>

 <div class="card" role="status" aria-live="polite">
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
["dragenter","dragover"].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add("hot");}));
["dragleave","drop"].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove("hot");}));
drop.addEventListener("drop",e=>{if(e.dataTransfer.files.length)send(e.dataTransfer.files);});
fileInput.onchange=()=>{if(fileInput.files.length)send(fileInput.files);};
$("#scan").onclick=()=>post("/api/scan",{}).then(track);

function opts(){return{keep_tashkeel:$("#opt_tashkeel").checked,
  force_ocr:$("#opt_forceocr").checked,digits:$("#opt_digits").value};}
function post(url,body){return fetch(url,{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(r=>r.json());}
function setProgress(p,text){$("#pfill").style.width=(p*100).toFixed(0)+"%";
  $("#pbar").setAttribute("aria-valuenow",(p*100).toFixed(0));
  if(text)$("#msg").textContent=text;}

async function send(files){
  setProgress(0,"جارٍ الرفع… Uploading…");
  const names=[];
  for(const f of files){
    await fetch("/api/upload",{method:"POST",
      headers:{"X-Filename":encodeURIComponent(f.name)},body:f});
    names.push(f.name);
  }
  track(await post("/api/start",{names:names,options:opts()}));
}
function track(job){
  if(!job||!job.job){setProgress(0,"لا توجد ملفات No files");return;}
  const t=setInterval(async()=>{
    const s=await (await fetch("/api/status?job="+job.job)).json();
    setProgress(s.frac||0,(s.ar||"")+"  "+(s.en||""));
    if(s.done){clearInterval(t);show(s);}
  },700);
}
function esc(x){return String(x==null?"":x);}
function show(s){
  $("#results").hidden=false;
  const ul=$("#filelist"); ul.innerHTML="";
  (s.results||[]).forEach(r=>{
    const li=document.createElement("li");
    if(r.error){
      li.innerHTML=`<strong>${esc(r.name)}</strong><div class="err">${esc(r.error)}</div>`;
    }else{
      const q=`job=${s.job}&i=${r.i}`;
      li.innerHTML=`<strong>${esc(r.name)}</strong>
        <table class="stats"><tr>
          <th>صفحات</th><td>${esc(r.pages)}</td>
          <th>فقرات</th><td>${esc(r.paragraphs)}</td>
          <th>كلمات</th><td>${esc(r.words||"—")}</td>
          <th>بحاجة مراجعة</th><td>${esc(r.flagged)}</td>
          <th>ثانية</th><td>${esc(r.seconds)}</td></tr></table>
        <a class="dl primary" href="/api/download?${q}&kind=docx">⬇ تنزيل ملف Word</a>
        <a class="dl" href="/api/download?${q}&kind=pdf" target="_blank">PDF للمراجعة</a>
        <a class="dl" href="/api/download?${q}&kind=txt">نص</a>
        <a class="dl" href="/api/download?${q}&kind=report" target="_blank">تقرير</a>
        <details><summary>معاينة النص <span class="en">preview</span></summary>
          <pre class="peek" dir="rtl">${esc(r.preview||"")}</pre></details>`;
    }
    ul.appendChild(li);
  });
  setProgress(1,"تم ✓ Done");
}
</script></body></html>""".replace("ACCEPT_LIST", ACCEPT)


def _run_job(job_id: str, paths: List[str], opt: dict) -> None:
    job = JOBS[job_id]
    options = Options(
        keep_tashkeel=bool(opt.get("keep_tashkeel", True)),
        force_ocr=bool(opt.get("force_ocr", False)),
        digits=opt.get("digits", "keep") or "keep",
    )
    results = []
    total = max(len(paths), 1)
    for i, path in enumerate(paths):
        name = os.path.basename(path)

        def prog(en, ar, frac, i=i, name=name):
            job["frac"] = (i + min(frac, 1.0)) / total
            job["en"] = f"{name}: {en}"
            job["ar"] = ar

        try:
            from .docx_out import build_docx, build_plain_text
            from .pipeline import Pipeline
            from .report import write_report
            res = Pipeline(options, progress=prog).run(path)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            stem = os.path.splitext(name)[0]
            out = {
                "docx": os.path.join(OUTPUT_DIR, f"{stem}.docx"),
                "txt": os.path.join(OUTPUT_DIR, f"{stem}.txt"),
                "pdf": os.path.join(OUTPUT_DIR, f"{stem}.review.pdf"),
                "report": os.path.join(OUTPUT_DIR, f"{stem}.review.html"),
            }
            build_docx(res.paras, out["docx"])
            build_plain_text(res.paras, out["txt"])
            try:
                from .pdf_out import build_review_pdf
                build_review_pdf(res.paras, out["pdf"])
            except Exception:
                out.pop("pdf", None)
            write_report(res, out["report"], source_name=name)
            preview = "\n\n".join(p.text for p in res.paras[:6])[:1400]
            results.append({"i": i, "name": name, "paths": out,
                            "preview": preview,
                            "words": sum(len(p.text.split()) for p in res.paras),
                            **res.stats})
        except Exception as e:
            results.append({"i": i, "name": name,
                            "error": f"{type(e).__name__}: {e}",
                            "trace": traceback.format_exc()[-700:]})
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
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/status":
            job = JOBS.get(q.get("job", [""])[0])
            safe = None
            if job:
                safe = {k: v for k, v in job.items()}
                if safe.get("results"):
                    safe["results"] = [{k: v for k, v in r.items() if k != "paths"}
                                       for r in safe["results"]]
            return self._send(200 if job else 404,
                              json.dumps(safe or {"error": "no job"},
                                         ensure_ascii=False, default=str).encode())
        if u.path == "/api/download":
            job = JOBS.get(q.get("job", [""])[0]) or {}
            try:
                i = int(q.get("i", ["0"])[0])
                kind = q.get("kind", ["docx"])[0]
                path = job["results"][i]["paths"][kind]
                data = open(path, "rb").read()
            except Exception:
                return self._send(404, b'{"error":"not found"}')
            ctype = {
                "docx": "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document",
                "txt": "text/plain; charset=utf-8",
                "pdf": "application/pdf",
                "report": "text/html; charset=utf-8",
            }[kind]
            disp = "inline" if kind in ("report", "pdf") else "attachment"
            fn = os.path.basename(path)
            return self._send(200, data, ctype,
                              {"Content-Disposition": f'{disp}; filename="{fn}"'})
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/upload":
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            name = urllib.parse.unquote(self.headers.get("X-Filename", "upload.pdf"))
            name = os.path.basename(name).replace("\x00", "") or "upload.pdf"
            os.makedirs(INPUT_DIR, exist_ok=True)
            with open(os.path.join(INPUT_DIR, name), "wb") as f:
                f.write(raw)
            return self._send(200, json.dumps({"saved": name}).encode())
        if u.path == "/api/start":
            body = self._json_body()
            names = [os.path.basename(str(x)) for x in (body.get("names") or [])]
            paths = [os.path.join(INPUT_DIR, n) for n in names
                     if os.path.isfile(os.path.join(INPUT_DIR, n))]
            return self._start(paths, body.get("options") or {})
        if u.path == "/api/scan":
            body = self._json_body()
            paths = []
            if os.path.isdir(INPUT_DIR):
                for f in sorted(os.listdir(INPUT_DIR)):
                    p = os.path.join(INPUT_DIR, f)
                    if not f.startswith(".") and os.path.isfile(p):
                        paths.append(p)
            return self._start(paths, body.get("options") or {})
        return self._send(404, b'{"error":"not found"}')

    def _start(self, paths, options):
        if not paths:
            return self._send(200, json.dumps({"job": None}).encode())
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"job": job_id, "frac": 0.0, "en": "Queued",
                        "ar": "في الانتظار", "done": False, "results": []}
        threading.Thread(target=_run_job, args=(job_id, paths, options),
                         daemon=True).start()
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
