import {
  CheckCircle2,
  CloudOff,
  FileCheck2,
  Gauge,
  ScanText,
  Settings,
  ShieldCheck,
  Upload,
} from "lucide-react";

import type { Screen } from "../types";

const steps: Array<{ key: Screen; ar: string; en: string; icon: typeof Upload }> = [
  { key: "upload", ar: "رفع", en: "Upload", icon: Upload },
  { key: "progress", ar: "التقدم", en: "Progress", icon: Gauge },
  { key: "review", ar: "المراجعة", en: "Review", icon: ScanText },
  { key: "export", ar: "التصدير", en: "Export", icon: FileCheck2 },
];

interface HeaderProps {
  screen: Screen;
  onScreen: (screen: Screen) => void;
  hasJob: boolean;
  providerLabel: string;
  cloudOptIn: boolean;
  onSettings: () => void;
}

export function Header({
  screen,
  onScreen,
  hasJob,
  providerLabel,
  cloudOptIn,
  onSettings,
}: HeaderProps) {
  return (
    <header className="app-header" dir="ltr">
      <div className="brand" title="Arabic Schoolbook OCR">
        <div className="brand-mark"><ScanText size={20} /></div>
        <div>
          <strong>Arabic Schoolbook OCR</strong>
          <span>نسخ ومراجعة الكتب العربية</span>
        </div>
      </div>

      <nav className="steps" aria-label="مراحل سير العمل">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const active = screen === step.key;
          const blocked = !hasJob && step.key !== "upload";
          return (
            <button
              className={`step ${active ? "active" : ""}`}
              disabled={blocked}
              key={step.key}
              onClick={() => onScreen(step.key)}
              title={blocked ? "ابدأ برفع ملف" : `${step.en} — ${step.ar}`}
              type="button"
            >
              <span className="step-number">{active ? <Icon size={15} /> : index + 1}</span>
              <span><b>{step.en}</b><small>{step.ar}</small></span>
            </button>
          );
        })}
      </nav>

      <div className="header-status">
        <div className="privacy-badge" title="لا تُرفع الملفات إلى السحابة دون موافقة صريحة">
          <ShieldCheck size={18} />
          <span><b>Local / Private</b><small>التدريب معطّل</small></span>
        </div>
        <div className="provider-pill" title="المزوّد المحدد">
          <CheckCircle2 size={15} /> {providerLabel}
        </div>
        <div className={`cloud-pill ${cloudOptIn ? "on" : ""}`} title="حالة الموافقة السحابية">
          <CloudOff size={15} /> {cloudOptIn ? "Cloud opt-in" : "Cloud off"}
        </div>
        <button
          className={`icon-button ${screen === "settings" ? "active" : ""}`}
          title="Settings — keys remain process-local"
          type="button"
          onClick={onSettings}
        >
          <Settings size={18} />
        </button>
      </div>
    </header>
  );
}
