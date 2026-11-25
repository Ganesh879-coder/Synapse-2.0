export type FindingCategory = "visual" | "metadata" | "consistency" | "format";
export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type CheckStatus = "pass" | "fail" | "warn" | "skipped";
export type JobStatus = "queued" | "processing" | "done" | "failed";
export type PipelineStage = "reading" | "edits" | "numbers" | "scoring";

export type KnownDocType =
  | "GST_CERT"
  | "INVOICE_BILL"
  | "BANK_UPI_STATEMENT"
  | "PAYMENT_RECEIPT"
  | "UNKNOWN";

export interface Region {
  id: string;
  page: number;
  bbox: [number, number, number, number];
  score: number;
  reason: string;
}

export interface Finding {
  id: string;
  category: FindingCategory;
  severity: SeverityLevel;
  title: string;
  plain_explanation: string;
  technical_detail: string;
  evidence_region_ids: string[];
}

export interface CheckResult {
  name: string;
  status: CheckStatus;
  detail: string;
}

export interface ExtractedFieldValue {
  value: unknown;
  page?: number;
  bbox?: [number, number, number, number] | null;
}

export interface ScoreContribution {
  signal: string;
  label: string;
  contribution: number;
}

export interface ExplanationSummary {
  verdict: string;
  top_reasons: string[];
  next_actions: string[];
  disclaimer: string;
}

export interface PageArtifact {
  page: number;
  width: number;
  height: number;
  image_url: string;
  heatmap_url: string | null;
}

export interface AnalysisResult {
  doc_id: string;
  doc_type: string;
  risk_score: number;
  risk_level: RiskLevel;
  verdict: string;
  findings: Finding[];
  regions: Region[];
  extracted_fields: Record<string, ExtractedFieldValue | unknown>;
  checks: CheckResult[];
  heatmap_url: string | null;
  processing_ms: number;
  pages?: PageArtifact[];
  confidence?: number;
  score_breakdown?: ScoreContribution[];
  summary?: ExplanationSummary | null;
}

export interface AnalyzeQueuedResponse {
  doc_id: string;
  status: "queued";
}

export interface AnalysisStatusResponse {
  status: JobStatus;
  stage?: PipelineStage | null;
  result?: AnalysisResult | null;
  error?: string | null;
}

export type MockSampleId =
  | "clean_bill"
  | "tampered_gst"
  | "tampered_upi"
  | "noisy_screenshot";
