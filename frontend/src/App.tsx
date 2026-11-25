import { FormEvent, useState } from "react";
import type { AnalysisResult, RiskLevel } from "./types/analysis";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const RISK_BADGE_STYLES: Record<RiskLevel, string> = {
  LOW: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  MEDIUM: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  HIGH: "bg-rose-500/20 text-rose-300 border-rose-500/40",
};

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<string>("unknown");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("doc_type", docType);

      const response = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `Request failed (${response.status})`);
      }

      const data = (await response.json()) as AnalysisResult;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze document.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8 border-b border-slate-800 pb-6">
        <h1 className="text-3xl font-bold tracking-tight text-white">Kavach</h1>
        <p className="mt-2 text-sm text-slate-400">
          Defence-only document screening for tampering indicators across GST certificates,
          invoices, bank/UPI statements, and payment receipts.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 space-y-4"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-slate-300">Document (JPG, PNG, PDF, max 15 MB)</span>
            <input
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-slate-300">Document Type</span>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              <option value="unknown">Auto-detect</option>
              <option value="gst_certificate">GST Certificate</option>
              <option value="invoice">Invoice / Bill</option>
              <option value="bank_statement">Bank / UPI Statement</option>
              <option value="payment_receipt">Payment Receipt</option>
            </select>
          </label>
        </div>

        <button
          type="submit"
          disabled={!file || loading}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "Analyze Document"}
        </button>

        {error && (
          <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">
            {error}
          </p>
        )}
      </form>

      {result && (
        <section className="mt-8 space-y-6 rounded-xl border border-slate-800 bg-slate-900/60 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400">
                Document ID: {result.doc_id} • {result.processing_ms} ms
              </p>
              <h2 className="mt-1 text-xl font-semibold text-white">
                Risk Score: {result.risk_score}/100
              </h2>
            </div>
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${RISK_BADGE_STYLES[result.risk_level]}`}
            >
              {result.risk_level} RISK
            </span>
          </div>

          <p className="rounded-lg bg-slate-950/70 p-4 text-sm text-slate-200">
            {result.verdict}
          </p>

          <div>
            <h3 className="text-sm font-semibold text-slate-300">
              Findings ({result.findings.length})
            </h3>
            {result.findings.length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">No tampering indicators reported.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {result.findings.map((finding) => (
                  <li
                    key={finding.id}
                    className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm"
                  >
                    <div className="font-medium text-white">{finding.title}</div>
                    <p className="mt-1 text-slate-300">{finding.plain_explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
