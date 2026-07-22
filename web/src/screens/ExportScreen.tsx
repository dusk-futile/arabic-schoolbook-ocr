import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileArchive,
  FileCheck2,
  FileJson2,
  FileText,
  FolderOpen,
  LoaderCircle,
  RefreshCcw,
  ShieldCheck,
  Table2,
} from "lucide-react";

import { api } from "../api";
import type { JobDetails } from "../types";

interface ExportScreenProps {
  jobId: string;
  details: JobDetails | null;
  onReview: () => void;
}

const outputMeta: Record<string, { label: string; detail: string; icon: typeof FileText }> = {
  literal_docx: { label: "Literal DOCX", detail: "نص حرفي مع بنية RTL دلالية", icon: FileText },
  polished_docx: { label: "Polished DOCX", detail: "التصحيحات البشرية المعتمدة فقط", icon: FileCheck2 },
  rendered_pdf: { label: "Rendered PDF", detail: "يتطلب LibreOffice محليًا للتحقق البصري", icon: FileCheck2 },
  correction_json: { label: "Correction JSON", detail: "سجل تعديلات قابل للتدقيق", icon: FileJson2 },
  correction_html: { label: "Correction report", detail: "مقارنة الحرفي والمصحح", icon: FileArchive },
  review_report: { label: "Review report", detail: "مصدر، معالجة، وكتل OCR", icon: FolderOpen },
};

export function ExportScreen({ jobId, details, onReview }: ExportScreenProps) {
  const [outputs, setOutputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const existing = details?.status.outputs ?? {};
    if (Object.keys(existing).length) {
      setOutputs(Object.fromEntries(Object.entries(existing).map(([key, value]) => [key, `/api/jobs/${jobId}/files/${value}`])));
    }
  }, [details, jobId]);

  async function exportNow() {
    setBusy(true);
    setError("");
    try {
      setOutputs(await api.export(jobId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر إنشاء ملفات التصدير");
    } finally {
      setBusy(false);
    }
  }

  const pages = details?.document?.pages ?? [];
  const totalBlocks = pages.reduce((sum, page) => sum + page.blocks.length, 0);
  const unresolved = pages.reduce((sum, page) => sum + page.blocks.filter((block) => block.unresolved).length, 0);
  const tables = pages.reduce((sum, page) => sum + page.blocks.filter((block) => block.table).length, 0);
  const failed = pages.filter((page) => page.status === "FAILED").length;

  return (
    <main className="screen-shell export-screen" dir="rtl">
      <section className="screen-heading">
        <div><span className="eyebrow">المرحلة 4 من 4</span><h1>تصدير النتائج</h1><p>تُعاد قراءة الوثيقة القانونية المحفوظة لحظة التصدير، بما في ذلك التصحيحات البشرية.</p></div>
        <div className="policy-chip"><ShieldCheck size={17} /> لا توجد كتابة فوق النص الحرفي</div>
      </section>

      <div className="export-grid">
        <section className="card export-options">
          <div className="card-heading"><Download size={20} /><div><b>ملفات الإخراج</b><small>تنزيل محلي مع Cache-Control: no-store</small></div></div>
          <div className="output-list">
            {Object.entries(outputMeta).map(([key, meta]) => {
              const Icon = meta.icon;
              const href = outputs[key];
              return (
                <div className="output-row" key={key}>
                  <Icon size={22} />
                  <span><b>{meta.label}</b><small>{meta.detail}</small></span>
                  {href ? <a className="download-button" href={`${href}?download=true`}><Download size={16} /> تنزيل</a> : <i>يُنشأ عند التصدير</i>}
                </div>
              );
            })}
          </div>
          {error && <div className="alert error"><AlertTriangle size={18} /> {error}</div>}
          <div className="export-actions">
            <button className="primary-button large" type="button" onClick={exportNow} disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <RefreshCcw size={18} />}{busy ? "جارٍ إنشاء الملفات…" : Object.keys(outputs).length ? "إعادة التصدير" : "إنشاء ملفات التصدير"}</button>
            <button className="secondary-button" type="button" onClick={onReview}>العودة إلى المراجعة</button>
          </div>
        </section>

        <aside className="card validation-card">
          <div className="card-heading"><CheckCircle2 size={20} /><div><b>حالة التحقق البنيوي</b><small>لا تمثل قياسًا للدقة النصية</small></div></div>
          <dl className="validation-list">
            <div><dt>الصفحات المعالجة</dt><dd><CheckCircle2 size={16} /> {pages.length}</dd></div>
            <div><dt>الكتل القانونية</dt><dd><CheckCircle2 size={16} /> {totalBlocks}</dd></div>
            <div><dt>الجداول الحقيقية</dt><dd><Table2 size={16} /> {tables}</dd></div>
            <div><dt>الصفحات الفاشلة</dt><dd className={failed ? "danger" : "success"}>{failed}</dd></div>
            <div><dt>كتل تحتاج مراجعة</dt><dd className={unresolved ? "warning-text" : "success"}>{unresolved}</dd></div>
          </dl>
          <div className="validation-success"><CheckCircle2 size={24} /><div><b>الفحص البنيوي متاح مع كل DOCX</b><small>ZIP/XML وإعادة الفتح وRTL والجداول والكتل المتوقعة.</small></div></div>
          {unresolved > 0 && <div className="alert warning"><AlertTriangle size={17} /> يمكن التصدير الآن، لكن الدقة ما زالت UNMEASURED_PENDING_HUMAN_GROUND_TRUTH.</div>}
          <div className="export-note"><FileArchive size={18} /><p>تظل ملفات المصدر والنتائج داخل مجلد المهمة المستبعد من Git.</p></div>
        </aside>
      </div>
    </main>
  );
}
