/**
 * Typed client for the PS-05 FastAPI service.
 *
 * Requests use same-origin /api paths. Next.js rewrites those paths to the
 * private API address configured through INTERNAL_API_URL, so browser code
 * never needs a hard-coded backend hostname.
 */

const API_BASE = "/api/v1";
const TOKEN_STORAGE_KEY = "ps05_auth_token";

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CaseItem {
  id: string;
  case_number: string;
  title: string;
  description?: string | null;
  status: string;
  lead_investigator_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceItem {
  id: string;
  case_id: string;
  evidence_number: string;
  original_filename: string;
  stored_filename: string;
  mime_type: string;
  media_type: "IMAGE" | "AUDIO" | "VIDEO" | string;
  file_size_bytes: number;
  primary_hash_sha256: string;
  hash_md5: string;
  hash_sha1: string;
  storage_path: string;
  is_quarantined: boolean;
  uploaded_by_id?: string | null;
  ingested_at: string;
}

export interface HashVerificationResult {
  evidence_id: string;
  evidence_number: string;
  is_intact: boolean;
  expected_sha256: string;
  calculated_sha256: string;
  verification_trigger: string;
  verified_at: string;
  integrity_notice: string;
}

export interface MetadataExtract {
  id: string;
  evidence_id: string;
  tool_name: string;
  tool_version: string;
  raw_metadata: Record<string, unknown>;
  filtered_forensic_metadata: Record<string, unknown>;
  extracted_at: string;
}

export interface EvidenceDetailItem extends EvidenceItem {
  metadata_extracts: MetadataExtract[];
  hash_verifications: HashVerificationResult[];
}

export interface FindingItem {
  id: string;
  analysis_id: string;
  evidence_id: string;
  finding_type: string;
  severity: string;
  title: string;
  description: string;
  confidence_score: number;
  evidence_offset?: string | null;
  finding_metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface AnalysisArtifact {
  id: string;
  analysis_id: string;
  artifact_type: string;
  storage_path: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number;
  hash_sha256: string;
  artifact_metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface ForensicAnalysisJob {
  id: string;
  evidence_id: string;
  analysis_type: string;
  status: string;
  job_id?: string | null;
  idempotency_key?: string | null;
  attempt_count: number;
  max_retries: number;
  timeout_seconds: number;
  error_code?: string | null;
  error_message?: string | null;
  parameters?: Record<string, unknown> | null;
  summary_results?: Record<string, any> | null;
  examiner_notes?: string | null;
  worker_id?: string | null;
  initiated_by_id?: string | null;
  created_at: string;
  started_at?: string | null;
  last_heartbeat_at?: string | null;
  completed_at?: string | null;
  artifacts: AnalysisArtifact[];
  findings: FindingItem[];
}

export interface AnalysisJobCreateResponse {
  job_id: string;
  analysis_id: string;
  evidence_id: string;
  analysis_type: string;
  status: string;
  message: string;
  created_at: string;
}

export interface ImageAnalysisSummary {
  execution_duration_ms?: number;
  pillow_version?: string;
  opencv_version?: string;
  image_properties?: Record<string, any>;
  ela?: Record<string, any>;
  limitations?: string[];
  [key: string]: any;
}

export interface AudioSpectrogramResult {
  is_applicable: boolean;
  inapplicability_reason?: string;
  spectrogram_artifact_id?: string;
  waveform_artifact_id?: string;
  sample_rate?: number;
  duration_seconds?: number;
  channel_count?: number;
  bit_depth?: number;
  rms_db?: number;
  peak_db?: number;
  dynamic_range_db?: number;
  high_freq_cutoff_hz?: number;
  lossy_compression_detected?: boolean;
  clipping_detected?: boolean;
  clipping_ratio?: number;
  [key: string]: any;
}

export interface VideoSceneCut {
  frame_index: number;
  timestamp_s: number;
  diff_score: number;
  artifact_id?: string;
  [key: string]: any;
}

export interface VideoKeyframeResult {
  is_applicable: boolean;
  inapplicability_reason?: string;
  width?: number;
  height?: number;
  fps?: number;
  duration_seconds?: number;
  frame_count?: number;
  codec?: string;
  scene_cut_count?: number;
  keyframe_count?: number;
  engine_version?: string;
  scene_cuts: VideoSceneCut[];
  [key: string]: any;
}

export interface ReportRead {
  id: string;
  case_id: string;
  report_number: string;
  title: string;
  generated_by_id?: string | null;
  storage_path: string;
  file_hash_sha256: string;
  file_size_bytes: number;
  included_evidence_ids?: string[] | null;
  created_at: string;
  // UI-friendly aliases derived from the API's canonical fields.
  sha256_hash: string;
  generated_at: string;
  examiner_name: string;
  evidence_count: number;
  is_sealed: boolean;
  jurisdiction?: string;
  court_name?: string;
  classification_marking?: string;
}

interface ApiErrorBody {
  detail?: string | { message?: string; code?: string };
  message?: string;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail?.message) message = body.detail.message;
      else if (body.message) message = body.message;
    } catch {
      // Keep the generic status message when the response is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function mapReport(report: Omit<ReportRead, "sha256_hash" | "generated_at" | "examiner_name" | "evidence_count" | "is_sealed">): ReportRead {
  return {
    ...report,
    sha256_hash: report.file_hash_sha256,
    generated_at: report.created_at,
    examiner_name: report.generated_by_id ? `Examiner ID: ${report.generated_by_id}` : "Not recorded",
    evidence_count: report.included_evidence_ids?.length ?? 0,
    is_sealed: true,
  };
}

export async function login(email: string, password: string): Promise<void> {
  const result = await apiRequest<{ access_token: string; user: unknown }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (typeof window !== "undefined") {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
  }
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<void>("/auth/logout", { method: "POST" });
  } finally {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }
}

export async function listCases(page = 1, pageSize = 50): Promise<PaginatedResponse<CaseItem>> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiRequest<PaginatedResponse<CaseItem>>(`/cases?${query.toString()}`);
}

export async function createCase(payload: {
  case_number: string;
  title: string;
  description?: string;
}): Promise<CaseItem> {
  return apiRequest<CaseItem>("/cases", { method: "POST", body: JSON.stringify(payload) });
}

export async function listCaseEvidence(caseId: string): Promise<EvidenceItem[]> {
  return apiRequest<EvidenceItem[]>(`/cases/${encodeURIComponent(caseId)}/evidence`);
}

export const listEvidence = listCaseEvidence;

export async function fetchEvidenceDetail(caseId: string, evidenceId: string): Promise<EvidenceDetailItem> {
  return apiRequest<EvidenceDetailItem>(
    `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}`,
  );
}

export async function triggerMetadataExtraction(caseId: string, evidenceId: string): Promise<MetadataExtract[]> {
  return apiRequest<MetadataExtract[]>(
    `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/metadata/extract`,
    { method: "POST" },
  );
}

export async function verifyEvidenceHash(
  caseId: string,
  evidenceId: string,
  trigger = "MANUAL",
): Promise<HashVerificationResult> {
  const validTrigger = trigger === "MANUAL_INSPECTION" ? "MANUAL" : trigger;
  const query = new URLSearchParams({ trigger: validTrigger });
  return apiRequest<HashVerificationResult>(
    `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/verify-hash?${query.toString()}`,
    { method: "POST" },
  );
}

export function getEvidenceContentUrl(caseId: string, evidenceId: string): string {
  return `${API_BASE}/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/content`;
}

export function getArtifactContentUrl(artifactId: string): string {
  return `${API_BASE}/analysis/artifacts/${encodeURIComponent(artifactId)}/content`;
}

export async function fetchAuthenticatedBlobUrl(url: string): Promise<string> {
  const response = await fetch(url, { headers: authHeaders(), cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to retrieve protected file (${response.status}).`);
  }
  return URL.createObjectURL(await response.blob());
}

export async function downloadCourtroomReport(
  caseId: string,
  reportId: string,
  filename: string,
): Promise<void> {
  const blobUrl = await fetchAuthenticatedBlobUrl(getReportDownloadUrl(caseId, reportId));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

export async function uploadEvidenceWithProgress(
  caseId: string,
  file: File,
  evidenceNumber?: string,
  onProgress?: (percent: number) => void,
): Promise<EvidenceItem> {
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams();
    if (evidenceNumber) query.set("evidence_number", evidenceNumber);
    const queryString = query.toString();
    const suffix = queryString ? `?${queryString}` : "";
    const xhr = new XMLHttpRequest();
    xhr.open(
      "POST",
      `${API_BASE}/cases/${encodeURIComponent(caseId)}/evidence/upload${suffix}`,
    );
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onerror = () => reject(new Error("Network error while uploading evidence."));
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        let message = `Upload failed (${xhr.status})`;
        try {
          const body = JSON.parse(xhr.responseText) as ApiErrorBody;
          if (typeof body.detail === "string") message = body.detail;
          else if (body.detail?.message) message = body.detail.message;
        } catch {
          // Keep the generic upload error.
        }
        reject(new Error(message));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as EvidenceItem);
      } catch {
        reject(new Error("The server returned an invalid upload response."));
      }
    };
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}

export async function createAnalysisJob(payload: {
  evidence_id: string;
  analysis_type: string;
  parameters?: Record<string, unknown> | undefined;
  examiner_notes?: string | undefined;
  idempotency_key?: string | undefined;
}): Promise<AnalysisJobCreateResponse> {
  return apiRequest<AnalysisJobCreateResponse>("/analysis/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAnalysisJob(jobId: string): Promise<ForensicAnalysisJob> {
  return apiRequest<ForensicAnalysisJob>(`/analysis/jobs/${encodeURIComponent(jobId)}`);
}

export async function getAnalysisHistory(filters: {
  evidence_id?: string | undefined;
  case_id?: string | undefined;
  status?: string | undefined;
  analysis_type?: string | undefined;
  page?: number | undefined;
  page_size?: number | undefined;
} = {}): Promise<PaginatedResponse<ForensicAnalysisJob>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<PaginatedResponse<ForensicAnalysisJob>>(
    `/analysis/history${queryString ? `?${queryString}` : ""}`,
  );
}

export async function retryAnalysisJob(analysisId: string): Promise<AnalysisJobCreateResponse> {
  return apiRequest<AnalysisJobCreateResponse>(
    `/analysis/jobs/${encodeURIComponent(analysisId)}/retry`,
    { method: "POST" },
  );
}

export async function listCaseReports(caseId: string): Promise<ReportRead[]> {
  const reports = await apiRequest<Array<Omit<ReportRead, "sha256_hash" | "generated_at" | "examiner_name" | "evidence_count" | "is_sealed">>>(
    `/cases/${encodeURIComponent(caseId)}/reports`,
  );
  return reports.map(mapReport);
}

export async function generateCourtroomReport(
  caseId: string,
  payload: {
    title?: string | undefined;
    included_evidence_ids?: string[] | undefined;
    examiner_certification?: string | undefined;
    jurisdiction?: string | undefined;
    court_name?: string | undefined;
    docket_number?: string | undefined;
    classification_marking?: string | undefined;
  },
): Promise<ReportRead> {
  const result = await apiRequest<Omit<ReportRead, "sha256_hash" | "generated_at" | "examiner_name" | "evidence_count" | "is_sealed">>(
    `/cases/${encodeURIComponent(caseId)}/reports/generate`,
    {
      method: "POST",
      // The API currently persists only these schema-supported fields.
      body: JSON.stringify({
        title: payload.title,
        included_evidence_ids: payload.included_evidence_ids,
        examiner_certification: payload.examiner_certification,
        jurisdiction: payload.jurisdiction,
        court_name: payload.court_name,
        docket_number: payload.docket_number,
        classification_marking: payload.classification_marking,
      }),
    },
  );
  return mapReport(result);
}

export function getReportDownloadUrl(caseId: string, reportId: string): string {
  return `${API_BASE}/cases/${encodeURIComponent(caseId)}/reports/${encodeURIComponent(reportId)}/download`;
}
