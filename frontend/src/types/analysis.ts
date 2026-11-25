export type FindingCategory = "visual" | "metadata" | "consistency" | "format";
export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type CheckStatus = "pass" | "fail" | "warn" | "skipped";

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

export interface AnalysisResult {
  doc_id: string;
  doc_type: string;
  risk_score: number;
  risk_level: RiskLevel;
  verdict: string;
  findings: Finding[];
  regions: Region[];
  extracted_fields: Record<string, unknown>;
  checks: CheckResult[];
  heatmap_url: string | null;
  processing_ms: number;
}
