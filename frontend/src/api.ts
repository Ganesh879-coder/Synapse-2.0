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
const ACCESS_KEY_STORAGE = "kavach_access_key";

export function getStoredAccessKey(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(ACCESS_KEY_STORAGE) ?? "";
}

export function setStoredAccessKey(key: string): void {
  if (typeof window === "undefined") return;
  const trimmed = key.trim();
  if (trimmed) {
    window.sessionStorage.setItem(ACCESS_KEY_STORAGE, trimmed);
  } else {
    window.sessionStorage.removeItem(ACCESS_KEY_STORAGE);
  }
}

function authHeaders(): Record<string, string> {
  const key = getStoredAccessKey();
  return key ? { "X-Kavach-Key": key } : {};
}

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
  if (response.status === 401) {
    setStoredAccessKey("");
    throw new ApiError("Access code required or invalid.", 401);
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

export async function loginWithAccessKey(accessKey: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ access_key: accessKey.trim() }),
  });
  if (!response.ok) {
    await parseErrorResponse(response);
  }
  setStoredAccessKey(accessKey);
}

export async function startAnalysis(file: File): Promise<AnalyzeQueuedResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: authHeaders(),
    credentials: "include",
    body: formData,
  });
  if (!response.ok) {
    await parseErrorResponse(response);
  }
  return (await response.json()) as AnalyzeQueuedResponse;
}

export async function pollAnalysisStatus(docId: string): Promise<AnalysisStatusResponse> {
  const response = await fetch(`${API_BASE}/api/analysis/${encodeURIComponent(docId)}`, {
    headers: authHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    await parseErrorResponse(response);
  }
  return (await response.json()) as AnalysisStatusResponse;
}

export async function deleteAnalysis(docId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/analysis/${encodeURIComponent(docId)}`, {
    method: "DELETE",
    headers: authHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    await parseErrorResponse(response);
  }
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
