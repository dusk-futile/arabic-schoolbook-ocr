import { useRef, useState } from "react";
import {
  AlertCircle,
  BookOpenCheck,
  BrainCircuit,
  Check,
  Cloud,
  Cpu,
  FileText,
  FlaskConical,
  FolderLock,
  HardDrive,
  History,
  LoaderCircle,
  ScanEye,
  UploadCloud,
  WandSparkles,
} from "lucide-react";

import { api } from "../api";
import type { JobListItem, Providers } from "../types";

const providerCards = [
  {
    key: "local",
    name: "Local Paddle",
    ar: "محلي وخاص",
    description: "PaddleOCR عربي + تحليل تخطيط محلي، دون إرسال الملف.",
    icon: Cpu,
  },
  {
    key: "windows",
    name: "Windows baseline",
    ar: "خط أساس",
    description: "قراءة محلية سريعة للمقارنة، بتفاصيل تخطيط محدودة.",
    icon: HardDrive,
  },
  {
    key: "ai_verified",
    name: "AI Verified",
    ar: "تحقق بصري اختياري",
    description: "Paddle محلي مع Windows، وإرسال المناطق المحددة فقط إلى Gemini بعد الموافقة.",
    icon: BrainCircuit,
  },
  {
    key: "azure",
    name: "Azure Accurate",
    ar: "سحابي بموافقة",
    description: "Document Intelligence؛ يتطلب مفتاحًا وموافقة صريحة.",
    icon: Cloud,
  },
  {
    key: "hybrid",
    name: "Hybrid Review",
    ar: "سحابي + محلي",
    description: "Azure مع محقق محلي وGemini لقصاصات الخلاف فقط.",
    icon: BookOpenCheck,
  },
  {
    key: "maximum_accuracy",
    name: "Maximum Accuracy",
    ar: "أقصى دقة بموافقة",
    description: "Azure + Paddle + Gemini verification/formatting/QA وفق النطاق المختار.",
    icon: WandSparkles,
  },
  {
    key: "unlimited",
    name: "Unlimited research",
    ar: "تجريبي",
    description: "اختياري وغير حاجب؛ يتوقف مبكرًا عند عدم توافق العتاد.",
    icon: FlaskConical,
  },
];

interface UploadScreenProps {
  providers: Providers;
  jobs: JobListItem[];
  mode: string;
  cloudOptIn: boolean;
  onMode: (mode: string) => void;
  onCloudOptIn: (enabled: boolean) => void;
  onStarted: (jobId: string) => void;
  onOpenJob: (jobId: string) => void;
}

export function UploadScreen({
  providers,
  jobs,
  mode,
  cloudOptIn,
  onMode,
  onCloudOptIn,
  onStarted,
  onOpenJob,
}: UploadScreenProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pages, setPages] = useState("first5");
  const [customPages, setCustomPages] = useState("4,36,53,184,209");
  const [device, setDevice] = useState("cpu");
  const [fullConfirmed, setFullConfirmed] = useState(false);
  const [aiVerification, setAiVerification] = useState("off");
  const [aiFormatting, setAiFormatting] = useState("off");
  const [aiVisualQa, setAiVisualQa] = useState(false);
  const [allowFullPageGemini, setAllowFullPageGemini] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const aiEnabled = aiVerification !== "off" || aiFormatting !== "off" || aiVisualQa;
  const cloudMode = ["azure", "hybrid", "ai_verified", "maximum_accuracy"].includes(mode) || aiEnabled;
  const fullPageAi = aiFormatting !== "off" || aiVisualQa;
  const selectedAvailability = providers[mode]?.available ?? mode === "local";
  const gemini = providers.gemini;
  const aiReady = !aiEnabled || Boolean(
    gemini?.available
    && (aiVerification === "off" || gemini.verification_enabled)
    && (aiFormatting === "off" || gemini.formatting_enabled)
    && (!aiVisualQa || gemini.visual_qa_enabled),
  );

  async function start() {
    if (!file) {
      setError("اختر ملف PDF أولًا.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("mode", mode);
      form.append("pages", pages === "custom" ? customPages : pages);
      form.append("device", device);
      form.append("cloud_opt_in", String(cloudOptIn));
      form.append("full_book_confirmed", String(fullConfirmed));
      form.append("ai_verification", aiVerification);
      form.append("ai_formatting", aiFormatting);
      form.append("ai_visual_qa", String(aiVisualQa));
      form.append("allow_full_page_gemini", String(allowFullPageGemini));
      const created = await api.createJob(form);
      onStarted(created.job_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر بدء المهمة");
    } finally {
      setBusy(false);
    }
  }

  function choose(candidate: File | undefined) {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) {
      setError("الملف المطلوب يجب أن يكون PDF.");
      return;
    }
    setFile(candidate);
    setError("");
  }

  function chooseProvider(provider: string) {
    onMode(provider);
    if (provider === "ai_verified") {
      setAiVerification("important");
      setAiFormatting("off");
      setAiVisualQa(false);
    } else if (provider === "maximum_accuracy") {
      setAiVerification("every");
      setAiFormatting("structural_suggestions");
      setAiVisualQa(true);
    }
  }

  return (
    <main className="screen-shell upload-screen" dir="rtl">
      <section className="screen-heading">
        <div>
          <span className="eyebrow">المرحلة 1 من 4</span>
          <h1>رفع الكتاب وإعداد المعالجة</h1>
          <p>يبقى الملف على هذا الجهاز في الوضع المحلي. كل كتاب مرفوع يُصنّف EVALUATION_ONLY.</p>
        </div>
        <div className="policy-chip"><FolderLock size={17} /> لا تدريب · لا رفع سحابي تلقائي</div>
      </section>

      <div className="upload-layout">
        <section className="card upload-card">
          <div
            className={`drop-zone ${file ? "has-file" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              choose(event.dataTransfer.files[0]);
            }}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(event) => choose(event.target.files?.[0])}
            />
            {file ? <FileText size={34} /> : <UploadCloud size={38} />}
            <strong>{file ? file.name : "اسحب ملف PDF هنا أو اضغط للاختيار"}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "PDF فقط · الحد من إعدادات الخادم"}</span>
          </div>

          <div className="form-section">
            <div className="section-title"><span>1</span><div><b>نطاق الصفحات</b><small>ابدأ بعينة من خمس صفحات قبل الكتاب الكامل</small></div></div>
            <div className="segmented-control">
              <button className={pages === "first5" ? "selected" : ""} onClick={() => setPages("first5")} type="button">أول 5 صفحات</button>
              <button className={pages === "custom" ? "selected" : ""} onClick={() => setPages("custom")} type="button">صفحات محددة</button>
              <button className={pages === "all" ? "selected" : ""} onClick={() => setPages("all")} type="button">كل الصفحات</button>
            </div>
            {pages === "custom" && (
              <label className="field-label">أرقام مفصولة بفواصل
                <input value={customPages} onChange={(event) => setCustomPages(event.target.value)} dir="ltr" />
              </label>
            )}
            {pages === "all" && (
              <label className="confirmation-row warning">
                <input type="checkbox" checked={fullConfirmed} onChange={(event) => setFullConfirmed(event.target.checked)} />
                <span><b>أؤكد تشغيل الكتاب الكامل</b><small>هذا تأكيد مستقل عن موافقة السحابة.</small></span>
              </label>
            )}
          </div>

          <div className="form-section">
            <div className="section-title"><span>2</span><div><b>مزوّد OCR</b><small>الخيارات غير الجاهزة توضح سبب التعطيل</small></div></div>
            <div className="provider-grid">
              {providerCards.map((provider) => {
                const state = providers[provider.key];
                const available = state?.available ?? provider.key === "local";
                const Icon = provider.icon;
                return (
                  <button
                    type="button"
                    key={provider.key}
                    className={`provider-card ${mode === provider.key ? "selected" : ""}`}
                    onClick={() => chooseProvider(provider.key)}
                    title={available ? provider.description : state?.reason ?? "غير متاح"}
                  >
                    <Icon size={21} />
                    <span><b>{provider.name}</b><small>{provider.ar}</small></span>
                    <i className={available ? "ready" : "not-ready"}>{available ? "جاهز" : "غير جاهز"}</i>
                    <p>{available ? provider.description : state?.reason ?? provider.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="form-section ai-layer-section">
            <div className="section-title"><span>3</span><div><b>AI verification and formatting</b><small>All cloud actions are optional, scoped, and recorded</small></div></div>
            <div className="ai-control-grid">
              <label className="field-label">AI verification
                <select value={aiVerification} onChange={(event) => setAiVerification(event.target.value)}>
                  <option value="off">Off</option>
                  <option value="uncertain">Uncertain regions only</option>
                  <option value="important">Important regions</option>
                  <option value="every">Every text block</option>
                </select>
              </label>
              <label className="field-label">AI formatting
                <select value={aiFormatting} onChange={(event) => setAiFormatting(event.target.value)}>
                  <option value="off">Off</option>
                  <option value="structural">Structural formatting only</option>
                  <option value="structural_suggestions">Structural formatting plus suggested corrections</option>
                </select>
              </label>
              <label className="confirmation-row compact-consent">
                <input type="checkbox" checked={aiVisualQa} onChange={(event) => setAiVisualQa(event.target.checked)} />
                <span><b><ScanEye size={15} /> Rendered Word visual QA</b><small>Reports reconstruction issues; never edits DOCX directly.</small></span>
              </label>
            </div>
            {fullPageAi && (
              <label className="confirmation-row cloud full-page-consent">
                <input type="checkbox" checked={allowFullPageGemini} onChange={(event) => setAllowFullPageGemini(event.target.checked)} />
                <span><b>I allow the selected full pages to be sent to Gemini</b><small>Required because formatting and rendered visual QA compare complete selected pages.</small></span>
              </label>
            )}
          </div>

          <div className="form-row two">
            <label className="field-label">جهاز التنفيذ
              <select value={device} onChange={(event) => setDevice(event.target.value)}>
                <option value="cpu">CPU — متوافق</option>
                <option value="gpu">GPU — يتطلب إعداد Paddle مناسب</option>
              </select>
            </label>
            <label className={`confirmation-row ${cloudMode ? "cloud" : "muted"}`}>
              <input
                type="checkbox"
                checked={cloudOptIn}
                disabled={!cloudMode}
                onChange={(event) => onCloudOptIn(event.target.checked)}
              />
              <span><b>I allow selected page regions to be sent to the configured cloud provider</b><small>{cloudMode ? "Only the selected pages/regions and enabled AI jobs are in scope." : "Not required for the selected local-only configuration."}</small></span>
            </label>
          </div>

          {error && <div className="alert error"><AlertCircle size={18} /> {error}</div>}
          {!aiReady && aiEnabled && <div className="alert warning"><AlertCircle size={18} />Configure the Gemini key and enable each selected capability in Settings.</div>}
          {!selectedAvailability && <div className="alert warning"><AlertCircle size={18} /> هذا المزوّد غير جاهز؛ اختر مزوّدًا متاحًا.</div>}

          <button
            className="primary-button large"
            type="button"
            disabled={busy || !file || !selectedAvailability || !aiReady || (cloudMode && !cloudOptIn) || (fullPageAi && !allowFullPageGemini) || (pages === "all" && !fullConfirmed)}
            onClick={start}
          >
            {busy ? <LoaderCircle className="spin" size={19} /> : <Check size={19} />}
            {busy ? "جارٍ إنشاء المهمة…" : "بدء الفحص والمعالجة"}
          </button>
        </section>

        <aside className="card recent-jobs">
          <div className="aside-heading"><History size={19} /><div><b>المهام المحلية</b><small>الأحدث أولًا</small></div></div>
          {jobs.length === 0 ? (
            <div className="empty-state"><FolderLock size={28} /><p>لا توجد مهام بعد.</p></div>
          ) : jobs.slice(0, 8).map((job) => {
            const title = String(job.manifest.source_filename ?? job.job_id);
            const state = job.status.state ?? "COMPLETED";
            const processed = Number(job.status.processed_pages ?? 0);
            return (
              <button className="recent-job" type="button" key={job.job_id} onClick={() => onOpenJob(job.job_id)}>
                <FileText size={18} />
                <span><b>{title}</b><small>{job.job_id}</small></span>
                <i className={state.startsWith("COMPLETED") ? "complete" : ""}>{state}</i>
                <em>{processed ? `${processed} صفحة` : "عرض"}</em>
              </button>
            );
          })}
          <div className="local-note"><FolderLock size={17} /><p><b>خصوصية على مستوى الجهاز</b><br />المجلدات والنتائج ليست ضمن Git ولا تُرفع تلقائيًا.</p></div>
        </aside>
      </div>
    </main>
  );
}
