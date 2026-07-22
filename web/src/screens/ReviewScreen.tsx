import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Eye,
  GripVertical,
  Languages,
  LoaderCircle,
  Save,
  Search,
  ShieldCheck,
  Table2,
  TextCursorInput,
} from "lucide-react";

import { api } from "../api";
import type { CanonicalPage, JobDetails } from "../types";

const blockTypes = [
  "DOCUMENT_TITLE", "CHAPTER_TITLE", "HEADING_1", "HEADING_2", "HEADING_3",
  "BODY_PARAGRAPH", "QUESTION", "ANSWER_OPTION", "BULLET_LIST", "NUMBERED_LIST",
  "DEFINITION_BOX", "EXAMPLE_BOX", "NOTE_BOX", "TABLE", "FIGURE", "CAPTION",
  "EQUATION_IMAGE", "HEADER", "FOOTER", "PAGE_NUMBER", "UNKNOWN",
];

interface ReviewScreenProps {
  jobId: string;
  details: JobDetails | null;
  onExport: () => void;
}

export function ReviewScreen({ jobId, details, onExport }: ReviewScreenProps) {
  const pageNumbers = useMemo(
    () => (details?.document?.pages ?? []).map((page) => page.page_number).sort((a, b) => a - b),
    [details],
  );
  const [pageNumber, setPageNumber] = useState(pageNumbers[0] ?? 1);
  const [page, setPage] = useState<CanonicalPage | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [view, setView] = useState<"source" | "overlay" | "reconstructed">("overlay");
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [blockType, setBlockType] = useState("BODY_PARAGRAPH");
  const [order, setOrder] = useState(0);
  const [bbox, setBbox] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const [direction, setDirection] = useState("RTL");
  const [paragraphGroup, setParagraphGroup] = useState("");
  const [boundariesJson, setBoundariesJson] = useState("[]");
  const [runsJson, setRunsJson] = useState("[]");
  const [tableJson, setTableJson] = useState("");
  const [reason, setReason] = useState("Compared with the source page");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (pageNumbers.length && !pageNumbers.includes(pageNumber)) setPageNumber(pageNumbers[0]);
  }, [pageNumber, pageNumbers]);

  useEffect(() => {
    let active = true;
    setPage(null);
    api.page(jobId, pageNumber).then((next) => {
      if (!active) return;
      setPage(next);
      const first = [...next.blocks].sort((a, b) => a.reading_order - b.reading_order)[0];
      setSelectedId(first?.id ?? "");
      setError("");
    }).catch((reasonValue) => {
      if (active) setError(reasonValue instanceof Error ? reasonValue.message : "تعذر تحميل الصفحة");
    });
    return () => { active = false; };
  }, [jobId, pageNumber]);

  const selected = page?.blocks.find((block) => block.id === selectedId) ?? null;
  const candidates = selected && Array.isArray(selected.evidence.candidates)
    ? selected.evidence.candidates as Array<{ provider?: string; text?: string; confidence?: number }>
    : [];
  const adjudication = selected && typeof selected.evidence.adjudication === "object"
    ? selected.evidence.adjudication as { provider?: string; selected_text?: string; rationale?: string; unresolved?: boolean }
    : null;
  useEffect(() => {
    if (!selected) return;
    setText(selected.approved_corrected_text ?? selected.unicode_normalized_text);
    setBlockType(selected.block_type);
    setOrder(selected.reading_order);
    setBbox(selected.bbox);
    setDirection(selected.paragraph_direction);
    setParagraphGroup(selected.paragraph_group_id ?? `page-${pageNumber}-block-${selected.reading_order + 1}`);
    setBoundariesJson(JSON.stringify(selected.boundaries ?? [], null, 2));
    setRunsJson(JSON.stringify(selected.runs ?? [], null, 2));
    setTableJson(selected.table ? JSON.stringify(selected.table, null, 2) : "");
    setSaved(false);
  }, [pageNumber, selected]);

  const sortedBlocks = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return [...(page?.blocks ?? [])]
      .sort((a, b) => a.reading_order - b.reading_order)
      .filter((block) => !normalized || block.literal_text.toLowerCase().includes(normalized) || block.block_type.toLowerCase().includes(normalized));
  }, [page, query]);

  const currentIndex = Math.max(0, pageNumbers.indexOf(pageNumber));

  async function save() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const boundaries = JSON.parse(boundariesJson) as unknown;
      const runs = JSON.parse(runsJson) as unknown;
      const table = tableJson.trim() ? JSON.parse(tableJson) as unknown : undefined;
      if (!Array.isArray(boundaries) || !Array.isArray(runs)) {
        throw new Error("يجب أن تكون الحدود والمقاطع قائمتين بصيغة JSON");
      }
      const updated = await api.patchBlock(jobId, pageNumber, selected.id, {
        approved_corrected_text: text,
        block_type: blockType,
        reading_order: order,
        bbox,
        paragraph_direction: direction,
        paragraph_group_id: paragraphGroup,
        boundaries,
        runs,
        ...(table === undefined ? {} : { table }),
        reason,
      });
      setPage((current) => current ? {
        ...current,
        blocks: current.blocks.map((block) => block.id === updated.id ? updated : block),
      } : current);
      setSaved(true);
    } catch (reasonValue) {
      setError(reasonValue instanceof Error ? reasonValue.message : "تعذر حفظ التصحيح");
    } finally {
      setBusy(false);
    }
  }

  function move(delta: number) {
    const target = pageNumbers[currentIndex + delta];
    if (target) setPageNumber(target);
  }

  return (
    <main className="review-screen" dir="rtl">
      <div className="review-toolbar">
        <div><b>{details?.document?.title ?? "مراجعة الكتاب"}</b><small>{details?.document?.classification ?? "EVALUATION_ONLY"} · {pageNumbers.length} صفحات معالجة</small></div>
        <div className="toolbar-actions">
          <button className={view === "source" ? "selected" : ""} type="button" onClick={() => setView("source")}><Eye size={17} /> المصدر</button>
          <button className={view === "overlay" ? "selected" : ""} type="button" onClick={() => setView("overlay")}><GripVertical size={17} /> الحدود والترتيب</button>
          <button className={view === "reconstructed" ? "selected" : ""} type="button" onClick={() => setView("reconstructed")}><TextCursorInput size={17} /> الصفحة المعاد بناؤها</button>
          <span className="policy-chip"><ShieldCheck size={16} /> حفظ محلي</span>
          <button className="primary-button compact" type="button" onClick={onExport}>التصدير <ArrowLeft size={17} /></button>
        </div>
      </div>

      <div className="review-workspace">
        <aside className="page-rail">
          <div className="rail-title"><b>صفحات المهمة</b><small>{pageNumbers.length} صفحة</small></div>
          <label className="rail-search"><Search size={15} /><input placeholder="رقم الصفحة" dir="ltr" onChange={(event) => {
            const candidate = Number(event.target.value);
            if (pageNumbers.includes(candidate)) setPageNumber(candidate);
          }} /></label>
          <div className="page-thumbnails">
            {pageNumbers.map((number) => (
              <button type="button" className={number === pageNumber ? "active" : ""} key={number} onClick={() => setPageNumber(number)}>
                <span>{number}</span>
                <img src={`/api/jobs/${jobId}/files/pages/${String(number).padStart(4, "0")}/source.png`} alt={`الصفحة ${number}`} />
                {details?.document?.pages.find((item) => item.page_number === number)?.blocks.some((block) => block.unresolved) && <i title="تحتاج مراجعة" />}
              </button>
            ))}
          </div>
        </aside>

        <section className="page-canvas-panel">
          <div className="panel-bar"><span>الصفحة {pageNumber}</span><div><button type="button" title="الصفحة السابقة" onClick={() => move(-1)} disabled={currentIndex === 0}><ChevronRight size={18} /></button><b>{currentIndex + 1} / {pageNumbers.length}</b><button type="button" title="الصفحة التالية" onClick={() => move(1)} disabled={currentIndex >= pageNumbers.length - 1}><ChevronLeft size={18} /></button></div></div>
          <div className="page-canvas">
            {!page ? <LoaderCircle className="spin canvas-loader" size={30} /> : (
              view === "reconstructed" ? <div className="reconstructed-preview">
                {[...page.blocks].sort((a, b) => a.reading_order - b.reading_order).map((block) => block.table ? (
                  <table key={block.id}><tbody>{Array.from({ length: block.table.rows }, (_, row) => <tr key={row}>{Array.from({ length: block.table?.columns ?? 0 }, (_, column) => <td key={column}>{block.table?.cells.find((cell) => cell.row === row && cell.column === column)?.text ?? ""}</td>)}</tr>)}</tbody></table>
                ) : block.block_type === "FIGURE" && block.source_crop ? (
                  <img key={block.id} src={`/api/jobs/${jobId}/files/${block.source_crop}`} alt="شكل مستخرج" />
                ) : (
                  <div className={`reconstructed-block ${block.block_type.toLowerCase()}`} key={block.id}>{(block.approved_corrected_text ?? block.unicode_normalized_text) || `[${block.block_type}]`}</div>
                ))}
              </div> : <img src={view === "overlay" ? page.assets.reading_order_overlay : page.assets.source} alt={`معاينة الصفحة ${pageNumber}`} />
            )}
          </div>
          <div className="canvas-footer"><span>{view === "overlay" ? "ترتيب الكتل وحدودها ظاهرة" : view === "source" ? "صورة المصدر دون تراكب" : "معاينة من البنية القانونية المصححة"}</span><button type="button" onClick={() => setView(view === "overlay" ? "source" : "overlay")}>{view === "overlay" ? "إخفاء" : "إظهار"} الحدود</button></div>
        </section>

        <section className="block-list-panel">
          <div className="panel-tabs"><button className="active" type="button">النص — الترتيب المنطقي</button><button type="button">النص الخام (OCR)</button></div>
          <label className="block-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="بحث في الكتل" /></label>
          {page?.warnings.length ? <div className="inline-warning"><AlertTriangle size={17} /><span>{page.warnings.join(" · ")}</span></div> : null}
          <div className="block-list">
            {sortedBlocks.map((block) => (
              <button type="button" className={`block-row ${block.id === selectedId ? "selected" : ""}`} onClick={() => setSelectedId(block.id)} key={block.id}>
                <GripVertical size={16} />
                <span className="order-number">{block.reading_order + 1}</span>
                <span className={`type-badge ${block.block_type.toLowerCase()}`}>{block.table ? <Table2 size={13} /> : null}{block.block_type}</span>
                <p>{(block.approved_corrected_text ?? block.unicode_normalized_text) || "[كتلة بلا نص]"}</p>
                <i className={block.unresolved ? "unresolved" : "approved"}>{block.unresolved ? "مراجعة" : <Check size={14} />}</i>
              </button>
            ))}
          </div>
          <div className="block-count">الكتل: {page?.blocks.length ?? 0} · غير المحسومة: {page?.blocks.filter((block) => block.unresolved).length ?? 0}</div>
        </section>

        <aside className="inspector-panel">
          <div className="inspector-tabs"><button className="active" type="button">خصائص الكتلة</button><button type="button">الحدود والثقة</button></div>
          {selected ? (
            <div className="inspector-form">
              <div className="selected-summary"><TextCursorInput size={19} /><div><b>الكتلة {selected.reading_order + 1}</b><small>ثقة OCR {(selected.confidence * 100).toFixed(1)}%</small></div><span className={selected.unresolved ? "needs-review" : "approved"}>{selected.unresolved ? "تحتاج مراجعة" : "معتمدة"}</span></div>
              <label className="field-label">نوع الكتلة<select value={blockType} onChange={(event) => setBlockType(event.target.value)}>{blockTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
              <label className="field-label">النص المصحح<textarea dir="rtl" rows={9} value={text} onChange={(event) => { setText(event.target.value); setSaved(false); }} /></label>
              <div className="literal-box"><span>النص الحرفي — للقراءة فقط</span><p>{selected.literal_text || "[لا نص من المزوّد الأساسي]"}</p></div>
              {selected.source_crop && <div className="literal-box"><span>القصاصة محل النزاع</span><img className="evidence-crop" src={`/api/jobs/${jobId}/files/${selected.source_crop}`} alt="قصاصة الدليل البصري" /></div>}
              {candidates.map((candidate, index) => <div className="literal-box" key={`${candidate.provider}-${index}`}><span>{candidate.provider ?? "مزوّد"} · {typeof candidate.confidence === "number" ? `${(candidate.confidence * 100).toFixed(1)}%` : "دون ثقة"}</span><p>{candidate.text || "[لا نص]"}</p></div>)}
              {adjudication && <div className="literal-box"><span>نتيجة المحكّم: {adjudication.provider ?? "—"} · {adjudication.unresolved ? "غير محسومة" : "محسومة"}</span><p>{adjudication.selected_text || adjudication.rationale || "[لا نتيجة]"}</p></div>}
              <div className="form-row two compact-fields">
                <label className="field-label">ترتيب القراءة<input type="number" min={0} value={order} onChange={(event) => setOrder(Number(event.target.value))} /></label>
                <label className="field-label">اتجاه النص<select value={direction} onChange={(event) => setDirection(event.target.value)}><option value="RTL">RTL — من اليمين</option><option value="LTR">LTR — من اليسار</option><option value="NEUTRAL">محايد</option></select></label>
              </div>
              <label className="field-label">مجموعة الفقرة<input value={paragraphGroup} onChange={(event) => setParagraphGroup(event.target.value)} /></label>
              <div className="form-row two compact-fields">
                <label className="field-label">X<input type="number" min={0} value={bbox.x} onChange={(event) => setBbox((value) => ({ ...value, x: Number(event.target.value) }))} /></label>
                <label className="field-label">Y<input type="number" min={0} value={bbox.y} onChange={(event) => setBbox((value) => ({ ...value, y: Number(event.target.value) }))} /></label>
                <label className="field-label">العرض<input type="number" min={0} value={bbox.width} onChange={(event) => setBbox((value) => ({ ...value, width: Number(event.target.value) }))} /></label>
                <label className="field-label">الارتفاع<input type="number" min={0} value={bbox.height} onChange={(event) => setBbox((value) => ({ ...value, height: Number(event.target.value) }))} /></label>
              </div>
              <label className="field-label">حدود الأسطر — JSON<textarea dir="ltr" rows={4} value={boundariesJson} onChange={(event) => setBoundariesJson(event.target.value)} /></label>
              <label className="field-label">المقاطع العربية/الإنجليزية — JSON<textarea dir="ltr" rows={4} value={runsJson} onChange={(event) => setRunsJson(event.target.value)} /></label>
              <label className="field-label">بنية الجدول والخلايا — JSON<textarea dir="ltr" rows={5} value={tableJson} onChange={(event) => setTableJson(event.target.value)} placeholder="اتركه فارغًا للكتل غير الجدولية" /></label>
              <label className="field-label">سبب التصحيح<input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
              <div className="evidence-row"><Languages size={17} /><span>يُحفظ النص الحرفي منفصلًا، ولا تعتمد أدلة الآلة التصحيح.</span></div>
              {error && <div className="alert error compact"><AlertTriangle size={16} /> {error}</div>}
              <button className="primary-button" type="button" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}{busy ? "جارٍ الحفظ…" : saved ? "تم الحفظ" : "اعتماد وحفظ"}</button>
            </div>
          ) : <div className="empty-state"><TextCursorInput size={28} /><p>اختر كتلة لمراجعتها.</p></div>}
        </aside>
      </div>

      <footer className="review-footer">
        <button type="button" onClick={() => move(-1)} disabled={currentIndex === 0}><ArrowRight size={17} /> الصفحة السابقة</button>
        <span>الصفحة {pageNumber} · حالة الدقة: غير مقاسة حتى اكتمال الحقيقة المرجعية البشرية</span>
        <button className="primary-button compact" type="button" onClick={() => move(1)} disabled={currentIndex >= pageNumbers.length - 1}>الصفحة التالية <ArrowLeft size={17} /></button>
      </footer>
    </main>
  );
}
