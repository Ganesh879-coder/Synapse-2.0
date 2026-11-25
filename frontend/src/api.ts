import type {
  AnalysisResult,
  AnalysisStatusResponse,
  AnalyzeQueuedResponse,
  MockSampleId,
} from "./types/analysis";

export const IS_MOCK_MODE = import.meta.env.VITE_MOCK === "1";
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export const MAX_FILE_BYTES = 15 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf"];
const ALLOWED_MIMES = new Set(["image/jpeg", "image/png", "application/pdf"]);

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function validateUploadFile(file: File): string | null {
  if (file.size === 0) {
    return "The selected file is empty.";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "File is larger than 15 MB. Please upload a smaller JPG, PNG, or PDF.";
  }
  const lower = file.name.toLowerCase();
  const extOk = ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  const mimeOk = !file.type || ALLOWED_MIMES.has(file.type);
  if (!extOk || !mimeOk) {
    return "Unsupported file type. Please upload a JPG, PNG, or PDF document.";
  }
  return null;
}

async function parseErrorResponse(response: Response): Promise<never> {
  if (response.status === 429) {
    throw new ApiError("Too many requests, please wait a moment.", 429);
  }
  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { error?: string; detail?: string };
    message = body.detail || body.error || message;
  } catch {
    // Use default status message when response body is not JSON.
  }
  throw new ApiError(message, response.status);
}

export async function startAnalysis(file: File): Promise<AnalyzeQueuedResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    await parseErrorResponse(response);
  }
  return (await response.json()) as AnalyzeQueuedResponse;
}

export async function pollAnalysisStatus(docId: string): Promise<AnalysisStatusResponse> {
  const response = await fetch(`${API_BASE}/api/analysis/${encodeURIComponent(docId)}`);
  if (!response.ok) {
    await parseErrorResponse(response);
  }
  return (await response.json()) as AnalysisStatusResponse;
}

export async function loadMockFixture(sampleId: MockSampleId): Promise<AnalysisResult> {
  const response = await fetch(`/mock/${sampleId}.json`);
  if (!response.ok) {
    throw new ApiError(`Mock fixture '${sampleId}' could not be loaded.`, response.status);
  }
  return (await response.json()) as AnalysisResult;
}

export function resolveArtifactUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return "";
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  return `${API_BASE}${pathOrUrl}`;
}

export function getReportPdfUrl(docId: string): string {
  return `${API_BASE}/api/analysis/${encodeURIComponent(docId)}/report.pdf`;
}
