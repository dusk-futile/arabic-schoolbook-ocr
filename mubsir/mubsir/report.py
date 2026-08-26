"""The review report: what a human should look at, and in what order.

The tool is not trying to be perfect. It is trying to make review fast and
targeted, so this file sorts by risk and points at page numbers.
"""
from __future__ import annotations

import html
import os
from typing import List

from .model import DocResult, Para


def _risk(p: Para) -> float:
    r = 1.0 - p.conf
    if "low-ocr-confidence" in p.flags:
        r += 0.5
    if "uncertain-join" in p.flags:
        r += 0.3
    if p.n_lines == 1 and len(p.text) < 25:
        r += 0.1
    return r


def write_report(res: DocResult, out_path: str, source_name: str = "") -> str:
    flagged = sorted([p for p in res.paras if p.flags or p.conf < 0.85],
                     key=_risk, reverse=True)
    s = res.stats
    rows = []
    for p in flagged[:400]:
        rows.append(
            f"<tr><td>{p.page}</td><td>{p.kind}</td><td>{p.conf:.2f}</td>"
            f"<td>{html.escape(', '.join(p.flags) or '-')}</td>"
            f"<td dir='rtl' lang='ar'>{html.escape(p.text[:300])}</td></tr>"
        )
    notes = []
    for pg in res.pages:
        if pg.notes:
            notes.append(f"<li>Page {pg.number}: {html.escape('; '.join(pg.notes))}</li>")

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Review report - {html.escape(source_name)}</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem;line-height:1.5;color:#111}}
 h1,h2{{margin:.6em 0 .3em}}
 table{{border-collapse:collapse;width:100%;margin-top:1rem}}
 th,td{{border:1px solid #ccc;padding:.4rem .5rem;text-align:left;vertical-align:top;font-size:.92rem}}
 th{{background:#f2f2f2}}
 td[dir=rtl]{{font-size:1.05rem;line-height:1.9}}
 .k{{display:inline-block;background:#eef;border:1px solid #99c;border-radius:4px;
     padding:.3rem .6rem;margin:.2rem .4rem .2rem 0}}
 .ok{{color:#060}} .warn{{color:#a60}}
</style></head><body>
<h1>Review report / تقرير المراجعة</h1>
<p><strong>{html.escape(source_name)}</strong></p>
<p>
 <span class="k">Pages: {s.get('pages',0)}</span>
 <span class="k">Paragraphs: {s.get('paragraphs',0)}</span>
 <span class="k">Lines: {s.get('lines',0)}</span>
 <span class="k">Digital pages: {s.get('digital_pages',0)}</span>
 <span class="k">OCR pages: {s.get('ocr_pages',0)}</span>
 <span class="k">Time: {s.get('seconds',0)}s</span>
 <span class="k {'warn' if s.get('flagged') else 'ok'}">Flagged: {s.get('flagged',0)}</span>
 {"<span class='k'>Lexicon fixes: %d</span>" % s['lexicon_edits'] if 'lexicon_edits' in s else ""}
</p>
<h2>Paragraphs to check first / فقرات تحتاج مراجعة</h2>
<p>Sorted by risk. These are highlighted in yellow in the Word file.</p>
<table><tr><th>Page</th><th>Kind</th><th>Conf</th><th>Flags</th><th>Text</th></tr>
{''.join(rows) if rows else '<tr><td colspan="5">Nothing flagged.</td></tr>'}
</table>
<h2>Per-page notes</h2>
<ul>{''.join(notes) if notes else '<li>None</li>'}</ul>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return out_path
