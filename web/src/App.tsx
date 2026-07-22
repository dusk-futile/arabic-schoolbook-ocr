import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  Check,
  FileText,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Settings,
  Upload,
  X,
} from "lucide-react";

import { api } from "./api";
import { SettingsScreen } from "./screens/SettingsScreen";
import type { JobDetails, Providers } from "./types";

type Phase = "upload" | "processing" | "result";

const TERMINAL_STATES = new Set([
  "COMPLETED",
  "COMPLETED_WITH_ERRORS",
  "FAILED",
  "CANCELLED",
]);

function outputUrls(jobId: string, details: JobDetails): Record<string, string> {
  const existing = details.status.outputs ?? {};
  return Object.fromEntries(
    Object.entries(existing).map(([key, value]) => [
      key,
      `/api/jobs/${jobId}/files/${value}`,
    ]),
  );
}

export default function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [jobId, setJobId] = useState("");
  const [details, setDetails] = useState<JobDetails | null>(null);
  const [outputs, setOutputs] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [, setProviders] = useState<Providers>({});

  useEffect(() => {
    if (phase !== "processing" || !jobId) return;
    let active = true;
    let timer: number | undefined;

    async function poll() {
      try {
        const next = await api.job(jobId);
        if (!active) return;
        setDetails(next);
        const state = next.status.state ?? "RUNNING";
        if (TERMINAL_STATES.has(state)) {
          if (state === "FAILED" || state === "CANCELLED") {
            setError(next.status.error ?? "تعذرت معالجة الملف.");
            setOutputs({});
          } else {
            let nextOutputs = outputUrls(jobId, next);
            if (!Object.keys(nextOutputs).length) nextOutputs = await api.export(jobId);
            if (!active) return;
            setOutputs(nextOutputs);
          }
          setPhase("result");
          return;
        }
        timer = window.setTimeout(() => void poll(), 1100);
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "تعذر قراءة حالة المعالجة.");
        setPhase("result");
      }
    }

    void poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, phase]);

  const progress = useMemo(() => {
    const total = details?.status.selected_pages?.length || details?.status.total_pages || 1;
    const processed = details?.status.processed_pages ?? 0;
    return {
      total,
      processed,
      percent: Math.min(99, Math.max(4, Math.round((processed / total) * 100))),
    };
  }, [details]);

  async function start() {
    if (!file) {
      inputRef.current?.click();
      return;
    }
    setError("");
    setOutputs({});
    setDetails(null);
    setPhase("processing");
    try {
      const form = new FormData();
      form.set("file", file);
      form.set("mode", "local");
      form.set("pages", "all");
      form.set("device", "cpu");
      form.set("cloud_opt_in", "false");
      form.set("full_book_confirmed", "true");
      form.set("ai_verification", "off");
      form.set("ai_formatting", "off");
      form.set("ai_visual_qa", "false");
      form.set("allow_full_page_gemini", "false");
      const created = await api.createJob(form);
      setJobId(created.job_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "تعذر بدء المعالجة.");
      setPhase("result");
    }
  }

  async function cancel() {
    if (jobId) await api.cancel(jobId).catch(() => undefined);
    reset();
  }

  function reset() {
    setPhase("upload");
    setFile(null);
    setJobId("");
    setDetails(null);
    setOutputs({});
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  const downloadUrl = outputs.polished_docx ?? outputs.literal_docx;
  const pageCount = details?.document?.pages.length ?? details?.status.processed_pages ?? 0;

  return (
    <div className="minimal-app" dir="rtl">
      <header className="minimal-header" dir="ltr">
        <strong>Arabic Schoolbook OCR</strong>
        <button
          aria-label="Settings"
          className="icon-button"
          type="button"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings size={22} />
        </button>
      </header>

      <main className="minimal-main" aria-live="polite">
        {phase === "upload" && (
          <section className="minimal-workflow upload-state">
            <div className="minimal-copy">
              <h1>حوّل كتابك إلى Word</h1>
              <p>ارفع ملف PDF وسنعالجه محلياً</p>
            </div>

            <button
              className={`minimal-dropzone${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const dropped = event.dataTransfer.files[0];
                if (dropped?.type === "application/pdf") setFile(dropped);
              }}
            >
              {file ? <FileText size={48} /> : <Upload size={48} />}
              <b>{file ? file.name : "اختر ملف PDF"}</b>
              {file && <span>{(file.size / 1024 / 1024).toFixed(1)} MB</span>}
            </button>
            <input
              ref={inputRef}
              hidden
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />

            <p className="privacy-line"><LockKeyhole size={17} /> محلي وخاص افتراضياً</p>
            <button className="minimal-primary" type="button" onClick={() => void start()}>
              ابدأ
            </button>
          </section>
        )}

        {phase === "processing" && (
          <section className="minimal-workflow processing-state">
            <div className="minimal-copy"><h1>جارٍ معالجة الكتاب</h1></div>
            <div
              className="progress-ring"
              style={{ "--progress": `${progress.percent * 3.6}deg` } as CSSProperties}
            >
              <div><strong>{progress.percent}%</strong><LoaderCircle className="spin" size={22} /></div>
            </div>
            <p className="progress-copy">
              قراءة الصفحة {Math.min(progress.processed + 1, progress.total)} من {progress.total}
            </p>
            <span className="file-name">{file?.name}</span>
            <button className="minimal-secondary" type="button" onClick={() => void cancel()}>
              <X size={18} /> إلغاء
            </button>
          </section>
        )}

        {phase === "result" && (
          <section className="minimal-workflow result-state">
            <div className="minimal-copy"><h1>{error ? "تعذرت المعالجة" : "الملف جاهز"}</h1></div>
            <div className={`result-mark${error ? " is-error" : ""}`}>
              {error ? <X size={52} /> : <Check size={52} />}
            </div>
            <div className="result-file">
              <strong>{file?.name}</strong>
              <span>{error || `${pageCount} صفحة`}</span>
            </div>
            {downloadUrl && (
              <a className="minimal-primary" href={`${downloadUrl}?download=true`}>
                تنزيل Word
              </a>
            )}
            <button className="minimal-text-button" type="button" onClick={reset}>
              <RotateCcw size={17} /> معالجة ملف آخر
            </button>
          </section>
        )}
      </main>

      {settingsOpen && (
        <div className="minimal-settings-overlay" role="dialog" aria-modal="true">
          <SettingsScreen
            onBack={() => setSettingsOpen(false)}
            onProviders={setProviders}
          />
        </div>
      )}
    </div>
  );
}
