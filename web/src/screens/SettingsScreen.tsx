import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Check,
  CloudCog,
  Eye,
  FileKey2,
  KeyRound,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";

import { api } from "../api";
import type { AppSettings, Providers } from "../types";

interface SettingsScreenProps {
  onBack: () => void;
  onProviders: (providers: Providers) => void;
}

export function SettingsScreen({ onBack, onProviders }: SettingsScreenProps) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureKey, setAzureKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-3.6-flash");
  const [verification, setVerification] = useState(false);
  const [formatting, setFormatting] = useState(false);
  const [visualQa, setVisualQa] = useState(false);
  const [clearAzure, setClearAzure] = useState(false);
  const [clearGemini, setClearGemini] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api.settings().then((value) => {
      if (!active) return;
      setSettings(value);
      setGeminiModel(value.gemini_model);
      setVerification(value.enable_gemini_verification);
      setFormatting(value.enable_gemini_formatting);
      setVisualQa(value.enable_gemini_visual_qa);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Settings unavailable"));
    return () => { active = false; };
  }, []);

  async function save() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const next = await api.updateSettings({
        azure_document_intelligence_endpoint: azureEndpoint || undefined,
        azure_document_intelligence_key: azureKey || undefined,
        gemini_api_key: geminiKey || undefined,
        gemini_model: geminiModel,
        enable_gemini_verification: verification,
        enable_gemini_formatting: formatting,
        enable_gemini_visual_qa: visualQa,
        clear_azure_key: clearAzure,
        clear_gemini_key: clearGemini,
      });
      setSettings(next);
      setAzureKey("");
      setGeminiKey("");
      setClearAzure(false);
      setClearGemini(false);
      onProviders(await api.providers());
      setMessage("Settings applied to this local server process. Secret values were not returned.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save settings");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="screen-shell settings-screen" dir="rtl">
      <section className="screen-heading">
        <div>
          <h1>إعدادات المزود والخصوصية</h1>
          <p>Local mode needs no key. Cloud features remain off until both the capability and job consent are enabled.</p>
        </div>
        <button className="secondary-button" type="button" onClick={onBack}>
          <ArrowLeft size={16} /> العودة
        </button>
      </section>

      <div className="settings-layout">
        <section className="card settings-card">
          <div className="card-heading"><KeyRound size={19} /><div><b>API configuration</b><small>Process-local secrets</small></div></div>
          <div className="settings-section">
            <div className="settings-section-title"><CloudCog size={18} /><div><b>Azure Document Intelligence</b><small>{settings?.azure_key_configured ? "Key configured" : "No key configured"}</small></div></div>
            <label className="field-label">Endpoint
              <input value={azureEndpoint} onChange={(event) => setAzureEndpoint(event.target.value)} placeholder={settings?.azure_endpoint_configured ? "Configured — enter only to replace" : "https://…cognitiveservices.azure.com"} dir="ltr" />
            </label>
            <label className="field-label">API key
              <input type="password" autoComplete="off" value={azureKey} onChange={(event) => setAzureKey(event.target.value)} placeholder={settings?.azure_key_configured ? "•••••••• configured" : "Optional"} dir="ltr" />
            </label>
            <label className="confirmation-row muted-setting">
              <input type="checkbox" checked={clearAzure} onChange={(event) => setClearAzure(event.target.checked)} />
              <span><b>Clear the process-local Azure key</b><small>The endpoint is not called by this action.</small></span>
            </label>
          </div>

          <div className="settings-section">
            <div className="settings-section-title"><FileKey2 size={18} /><div><b>Google Gemini</b><small>{settings?.gemini_key_configured ? "Key configured" : "No key configured"}</small></div></div>
            <div className="form-row two compact-settings-row">
              <label className="field-label">Model
                <input value={geminiModel} onChange={(event) => setGeminiModel(event.target.value)} dir="ltr" />
              </label>
              <label className="field-label">API key
                <input type="password" autoComplete="off" value={geminiKey} onChange={(event) => setGeminiKey(event.target.value)} placeholder={settings?.gemini_key_configured ? "•••••••• configured" : "Optional"} dir="ltr" />
              </label>
            </div>
            <div className="capability-list">
              <label><input type="checkbox" checked={verification} onChange={(event) => setVerification(event.target.checked)} /><span><b>Visual OCR verification</b><small>Selected image crops only, subject to job consent.</small></span></label>
              <label><input type="checkbox" checked={formatting} onChange={(event) => setFormatting(event.target.checked)} /><span><b>Structural formatting</b><small>Selected full pages require a second explicit confirmation.</small></span></label>
              <label><input type="checkbox" checked={visualQa} onChange={(event) => setVisualQa(event.target.checked)} /><span><b>Rendered Word visual QA</b><small>Compares selected source and rendered pages; reports only.</small></span></label>
            </div>
            <label className="confirmation-row muted-setting">
              <input type="checkbox" checked={clearGemini} onChange={(event) => setClearGemini(event.target.checked)} />
              <span><b>Clear the process-local Gemini key</b><small>No request is made while saving settings.</small></span>
            </label>
          </div>

          {error && <div className="alert error">{error}</div>}
          {message && <div className="alert success-message"><Check size={17} />{message}</div>}
          <button className="primary-button large" type="button" onClick={() => void save()} disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={18} /> : <ShieldCheck size={18} />}
            {busy ? "Saving…" : "Apply process-local settings"}
          </button>
        </section>

        <aside className="card settings-aside">
          <div className="aside-heading"><Eye size={19} /><div><b>Privacy contract</b><small>Fail closed</small></div></div>
          <ul>
            <li>Keys are never returned by the API after submission.</li>
            <li>Settings-page keys live only until this server process exits.</li>
            <li>Use <code>.env</code> for restart-persistent local configuration; it is Git-ignored.</li>
            <li>Enabling a capability does not grant document consent.</li>
            <li>Every cloud job records provider, page scope, request counts, failures, and cost when pricing is configured.</li>
          </ul>
          <div className="settings-facts">
            <div><span>Verification threshold</span><b>{settings?.gemini_verify_confidence_threshold ?? 0.85}</b></div>
            <div><span>Safe retries</span><b>{settings?.gemini_max_retries ?? 2}</b></div>
            <div><span>Parallel requests</span><b>{settings?.gemini_max_parallel_requests ?? 4}</b></div>
            <div><span>Training</span><b>Disabled</b></div>
          </div>
        </aside>
      </div>
    </main>
  );
}
