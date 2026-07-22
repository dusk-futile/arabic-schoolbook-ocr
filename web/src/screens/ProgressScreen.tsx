import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  FileImage,
  LoaderCircle,
  OctagonX,
  PauseCircle,
  RotateCcw,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

import { api } from "../api";
import type { JobDetails } from "../types";

interface ProgressScreenProps {
  jobId: string;
  onReview: () => void;
  onDetails: (details: JobDetails) => void;
}

export function ProgressScreen({ jobId, onReview, onDetails }: ProgressScreenProps) {
  const [details, setDetails] = useState<JobDetails | null>(null);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [pollRevision, setPollRevision] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const next = await api.job(jobId);
        if (!active) return;
        setDetails(next);
        onDetails(next);
        setError("");
        const terminal = ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"].includes(next.status.state ?? "");
        if (!terminal) timer = window.setTimeout(poll, 1800);
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "تعذر قراءة حالة المهمة");
        timer = window.setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, onDetails, pollRevision]);

  const total = details?.status.selected_pages?.length ?? details?.status.total_pages ?? 0;
  const processed = details?.status.processed_pages ?? details?.document?.pages.length ?? 0;
  const percent = total ? Math.round((processed / total) * 100) : 0;
  const state = details?.status.state ?? "QUEUED";
  const terminal = ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"].includes(state);
  const failed = details?.status.failed_pages?.length ?? 0;

  const stages = useMemo(() => [
    { label: "حفظ الملف وفحص PDF", done: state !== "QUEUED", active: state === "QUEUED" },
    { label: "تصيير الصفحات محليًا", done: processed > 0, active: state === "RUNNING" && processed === 0 },
    { label: "تحليل التخطيط وOCR", done: terminal, active: state === "RUNNING" && processed < total },
    { label: "إنشاء DOCX والتقارير", done: state.startsWith("COMPLETED"), active: state === "RUNNING" && processed === total },
  ], [processed, state, terminal, total]);

  async function cancel() {
    setCancelling(true);
    try {
      await api.cancel(jobId);
    } finally {
      setCancelling(false);
    }
  }

  async function retry() {
    const cloudMode = ["azure", "hybrid", "ai_verified", "maximum_accuracy"].includes(details?.status.mode ?? "");
    const cloudOptIn = cloudMode
      ? window.confirm("ستُعاد محاولة الصفحات الفاشلة عبر السحابة. هل توافق صراحة؟")
      : false;
    if (cloudMode && !cloudOptIn) return;
    setRetrying(true);
    setError("");
    try {
      await api.retry(jobId, cloudOptIn);
      setPollRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذرت إعادة المحاولة");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <main className="screen-shell progress-screen" dir="rtl">
      <section className="screen-heading">
        <div><span className="eyebrow">المرحلة 2 من 4</span><h1>تقدم المعالجة</h1><p>كل صفحة تُحفظ كنقطة استئناف مستقلة، وتستمر المهمة عند فشل صفحة واحدة.</p></div>
        <div className="policy-chip"><ShieldCheck size={17} /> {details?.status.cloud_opt_in ? "Cloud opt-in" : "المعالجة محلية"}</div>
      </section>

      <section className="card progress-hero">
        <div className="progress-title">
          <div><b>{state === "RUNNING" ? "المعالجة جارية" : state}</b><small>{jobId}</small></div>
          <strong>{percent}%</strong>
        </div>
        <div className="progress-track"><span style={{ width: `${percent}%` }} /></div>
        <div className="progress-meta">
          <span>AI failures: {details?.status.failed_ai_requests ?? 0}</span>
          <span>Unresolved: {details?.status.unresolved_blocks ?? "—"}</span>
          <span>المعالج: {processed} من {total || "—"}</span>
          <span>الصفحة الحالية: {details?.status.current_page ?? "—"}</span>
          <span>الفشل: {failed}</span>
          <span>الوقت: {details?.status.elapsed_seconds?.toFixed(1) ?? "—"} ث</span>
          <span>تحذيرات: {details?.status.warnings ?? 0}</span>
          <span>استدعاءات API: {details?.status.api_calls ?? 0}</span>
          <span>التكلفة المقدرة: ${details?.status.estimated_cloud_cost?.toFixed(4) ?? "0.0000"}</span>
          <span>الدقة: غير مقاسة قبل المراجعة البشرية</span>
        </div>
      </section>

      <div className="progress-grid">
        <section className="card stage-card">
          <div className="card-heading"><ScanLine size={20} /><div><b>مراحل التنفيذ</b><small>المزود: {details?.status.mode ?? "—"}</small></div></div>
          <ol className="stage-list">
            {stages.map((stage) => (
              <li className={stage.done ? "done" : stage.active ? "active" : ""} key={stage.label}>
                {stage.done ? <CheckCircle2 size={20} /> : stage.active ? <LoaderCircle className="spin" size={20} /> : <Circle size={20} />}
                <span><b>{stage.label}</b><small>{stage.done ? "مكتمل" : stage.active ? "جارٍ" : "بانتظار المرحلة السابقة"}</small></span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card live-card">
          <div className="card-heading"><FileImage size={20} /><div><b>الصفحة الحالية</b><small>معاينة حالة التنفيذ</small></div></div>
          <div className="page-placeholder">
            <div className="paper-mini"><ScanLine size={34} /><span>{(details?.status.current_page ?? processed) || "—"}</span></div>
            <div><b>{state === "RUNNING" ? "تحليل النص والتخطيط" : "لا توجد صفحة قيد التنفيذ"}</b><small>تُحفظ الصور والـJSON داخل مجلد المهمة.</small></div>
          </div>
          <dl className="detail-list">
            <div><dt>الصفحات المحددة</dt><dd>{details?.status.selected_pages?.join("، ") ?? "—"}</dd></div>
            <div><dt>الصفحات المكتملة</dt><dd>{processed}</dd></div>
            <div><dt>الصفحات الفاشلة</dt><dd className={failed ? "danger" : "success"}>{failed}</dd></div>
            <div><dt>المرحلة الحالية</dt><dd>{details?.status.current_stage ?? "—"}</dd></div>
            <div><dt>التدريب</dt><dd>معطّل</dd></div>
          </dl>
        </section>
      </div>

      {error && <div className="alert error"><AlertTriangle size={18} /> {error}</div>}
      {details?.status.error && <div className="alert error"><OctagonX size={18} /> {details.status.error}</div>}
      {state === "COMPLETED_WITH_ERRORS" && <div className="alert warning"><AlertTriangle size={18} /> اكتملت المهمة مع صفحات تحتاج إعادة محاولة.</div>}

      <div className="action-bar">
        <span><Clock3 size={17} /> يتم تحديث الحالة تلقائيًا</span>
        <div>
          {!terminal && <button className="secondary-button danger" type="button" onClick={cancel} disabled={cancelling}><PauseCircle size={18} /> {cancelling ? "جارٍ الإيقاف…" : "إيقاف بعد الصفحة الحالية"}</button>}
          {terminal && failed > 0 && <button className="secondary-button" type="button" onClick={retry} disabled={retrying}><RotateCcw size={18} /> {retrying ? "جارٍ البدء…" : "إعادة محاولة الصفحات الفاشلة"}</button>}
          {state.startsWith("COMPLETED") && <button className="primary-button" type="button" onClick={onReview}><ScanLine size={18} /> فتح المراجعة</button>}
        </div>
      </div>
    </main>
  );
}
