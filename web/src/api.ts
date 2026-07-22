import type {
  AppSettings,
  CanonicalBlock,
  CanonicalPage,
  JobDetails,
  JobListItem,
  Providers,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  providers: () => request<Providers>("/api/providers"),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: Record<string, unknown>) =>
    request<AppSettings>("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  jobs: () => request<JobListItem[]>("/api/jobs"),
  job: (jobId: string) => request<JobDetails>(`/api/jobs/${jobId}`),
  page: (jobId: string, page: number) =>
    request<CanonicalPage>(`/api/jobs/${jobId}/pages/${page}`),
  createJob: (form: FormData) =>
    request<{ job_id: string; state: string; selected_pages: number[] }>("/api/jobs", {
      method: "POST",
      body: form,
    }),
  cancel: (jobId: string) =>
    request<Record<string, unknown>>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  retry: (jobId: string, cloudOptIn: boolean) =>
    request<Record<string, unknown>>(`/api/jobs/${jobId}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cloud_opt_in: cloudOptIn }),
    }),
  patchBlock: (
    jobId: string,
    page: number,
    blockId: string,
    payload: Record<string, unknown>,
  ) =>
    request<CanonicalBlock>(`/api/jobs/${jobId}/pages/${page}/blocks/${blockId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, human_approved: true }),
    }),
  export: (jobId: string) =>
    request<Record<string, string>>(`/api/jobs/${jobId}/export`, { method: "POST" }),
};
