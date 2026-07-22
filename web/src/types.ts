export type Screen = "upload" | "progress" | "review" | "export" | "settings";

export interface AppSettings {
  azure_endpoint_configured: boolean;
  azure_key_configured: boolean;
  gemini_key_configured: boolean;
  gemini_model: string;
  enable_gemini_verification: boolean;
  enable_gemini_formatting: boolean;
  enable_gemini_visual_qa: boolean;
  gemini_verify_confidence_threshold: number;
  gemini_max_retries: number;
  gemini_max_parallel_requests: number;
  secrets_persisted: boolean;
  note: string;
}

export interface ProviderState {
  available: boolean;
  private?: boolean;
  requires_cloud_opt_in?: boolean;
  reason?: string;
  mode?: string;
  gpu_memory_mb?: number | null;
  versions?: Record<string, string | null>;
  gemini_scope?: string;
  model?: string;
  verification_enabled?: boolean;
  formatting_enabled?: boolean;
  visual_qa_enabled?: boolean;
}

export type Providers = Record<string, ProviderState>;

export interface JobStatus {
  state?: string;
  mode?: string;
  total_pages?: number;
  selected_pages?: number[];
  processed_pages?: number;
  failed_pages?: number[];
  current_page?: number | null;
  error?: string;
  outputs?: Record<string, string>;
  accuracy_status?: string;
  cloud_opt_in?: boolean;
  current_stage?: string;
  elapsed_seconds?: number;
  warnings?: number;
  api_calls?: number;
  estimated_cloud_cost?: number;
  failed_ai_requests?: number;
  unresolved_blocks?: number;
}

export interface JobListItem {
  job_id: string;
  status: JobStatus;
  summary: Record<string, unknown>;
  manifest: Record<string, unknown>;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CanonicalBlock {
  id: string;
  block_type: string;
  bbox: BoundingBox;
  reading_order: number;
  literal_text: string;
  unicode_normalized_text: string;
  approved_corrected_text: string | null;
  confidence: number;
  paragraph_direction: string;
  paragraph_group_id?: string | null;
  runs: Array<Record<string, unknown>>;
  boundaries: Array<Record<string, unknown>>;
  unresolved: boolean;
  source_crop?: string | null;
  evidence: Record<string, unknown>;
  table?: {
    rows: number;
    columns: number;
    cells: Array<{ row: number; column: number; text: string }>;
  } | null;
}

export interface CanonicalPage {
  page_number: number;
  width: number;
  height: number;
  status: string;
  warnings: string[];
  error?: string | null;
  timings_ms: Record<string, number>;
  blocks: CanonicalBlock[];
  assets: {
    source: string;
    preprocessed: string;
    layout_overlay: string;
    reading_order_overlay: string;
  };
}

export interface DocumentSummary {
  title: string;
  source_filename: string;
  classification: string;
  pages: Array<{ page_number: number; status: string; blocks: CanonicalBlock[] }>;
}

export interface JobDetails {
  job_id: string;
  status: JobStatus;
  manifest: Record<string, unknown>;
  summary: Record<string, unknown>;
  document: DocumentSummary | null;
}
