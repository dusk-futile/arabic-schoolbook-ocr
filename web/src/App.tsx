import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { Header } from "./components/Header";
import { ExportScreen } from "./screens/ExportScreen";
import { ProgressScreen } from "./screens/ProgressScreen";
import { ReviewScreen } from "./screens/ReviewScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { UploadScreen } from "./screens/UploadScreen";
import type { JobDetails, JobListItem, Providers, Screen } from "./types";

const providerNames: Record<string, string> = {
  local: "Local Paddle",
  windows: "Windows baseline",
  azure: "Azure Accurate",
  hybrid: "Hybrid Review",
  ai_verified: "AI Verified",
  maximum_accuracy: "Maximum Accuracy",
  unlimited: "Unlimited research",
  mock: "Mock",
};

export default function App() {
  const [screen, setScreen] = useState<Screen>("upload");
  const [providers, setProviders] = useState<Providers>({});
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [mode, setMode] = useState("local");
  const [cloudOptIn, setCloudOptIn] = useState(false);
  const [activeJob, setActiveJob] = useState("");
  const [details, setDetails] = useState<JobDetails | null>(null);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await api.jobs());
    } catch {
      setJobs([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([api.providers(), api.jobs()]).then(([providerResult, jobResult]) => {
      if (!active) return;
      setProviders(providerResult.status === "fulfilled" ? providerResult.value : {});
      setJobs(jobResult.status === "fulfilled" ? jobResult.value : []);
    });
    return () => { active = false; };
  }, []);

  const updateDetails = useCallback((next: JobDetails) => {
    setDetails(next);
    const detectedMode = String(next.status.mode ?? next.manifest.mode ?? "local");
    if (providerNames[detectedMode]) setMode(detectedMode);
  }, []);

  const openJob = useCallback(async (jobId: string) => {
    setActiveJob(jobId);
    window.localStorage.setItem("arabic-ocr-active-job", jobId);
    try {
      const next = await api.job(jobId);
      updateDetails(next);
      const state = next.status.state ?? "COMPLETED";
      setScreen(["QUEUED", "RUNNING"].includes(state) ? "progress" : "review");
    } catch {
      setScreen("progress");
    }
  }, [updateDetails]);

  useEffect(() => {
    const remembered = window.localStorage.getItem("arabic-ocr-active-job");
    if (!remembered) return;
    let active = true;
    void api.job(remembered).then((next) => {
      if (!active) return;
      setActiveJob(remembered);
      setDetails(next);
      const detectedMode = String(next.status.mode ?? next.manifest.mode ?? "local");
      if (providerNames[detectedMode]) setMode(detectedMode);
      const state = next.status.state ?? "COMPLETED";
      setScreen(["QUEUED", "RUNNING"].includes(state) ? "progress" : "review");
    }).catch(() => window.localStorage.removeItem("arabic-ocr-active-job"));
    return () => { active = false; };
  }, []);

  function chooseMode(next: string) {
    setMode(next);
    if (!["azure", "hybrid", "ai_verified", "maximum_accuracy"].includes(next)) {
      setCloudOptIn(false);
    }
  }

  function started(jobId: string) {
    setActiveJob(jobId);
    setDetails(null);
    window.localStorage.setItem("arabic-ocr-active-job", jobId);
    setScreen("progress");
    void refreshJobs();
  }

  const providerLabel = useMemo(() => providerNames[mode] ?? mode, [mode]);

  return (
    <div className="app-root">
      <Header
        screen={screen}
        onScreen={setScreen}
        hasJob={Boolean(activeJob)}
        providerLabel={providerLabel}
        cloudOptIn={cloudOptIn}
        onSettings={() => setScreen("settings")}
      />
      {screen === "upload" && (
        <UploadScreen
          providers={providers}
          jobs={jobs}
          mode={mode}
          cloudOptIn={cloudOptIn}
          onMode={chooseMode}
          onCloudOptIn={setCloudOptIn}
          onStarted={started}
          onOpenJob={(jobId) => void openJob(jobId)}
        />
      )}
      {screen === "progress" && activeJob && (
        <ProgressScreen
          jobId={activeJob}
          onReview={() => setScreen("review")}
          onDetails={updateDetails}
        />
      )}
      {screen === "review" && activeJob && (
        <ReviewScreen jobId={activeJob} details={details} onExport={() => setScreen("export")} />
      )}
      {screen === "export" && activeJob && (
        <ExportScreen jobId={activeJob} details={details} onReview={() => setScreen("review")} />
      )}
      {screen === "settings" && (
        <SettingsScreen
          onBack={() => setScreen(activeJob ? "review" : "upload")}
          onProviders={setProviders}
        />
      )}
    </div>
  );
}
