import { DragEvent, useEffect, useRef, useState } from "react";
import { IS_MOCK_MODE, validateUploadFile } from "../api";
import type { MockSampleId } from "../types/analysis";

interface UploadZoneProps {
  onFileSelected: (file: File) => void;
  onSampleSelected: (sampleId: MockSampleId) => void;
}

const SAMPLE_BUTTONS: { id: MockSampleId; label: string; hint: string; fileName: string }[] = [
  { id: "clean_bill", label: "Clean Restaurant Bill", hint: "Low risk", fileName: "bill_clean.jpg" },
  { id: "tampered_gst", label: "Edited GST Certificate", hint: "High risk", fileName: "gst_tampered.jpg" },
  { id: "tampered_upi", label: "Edited UPI Statement", hint: "High risk", fileName: "upi_tampered.png" },
  { id: "noisy_screenshot", label: "Receipt Screenshot", hint: "Low confidence", fileName: "receipt_ss.png" },
];

export function UploadZone({ onFileSelected, onSampleSelected }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const [publicSamplesAvailable, setPublicSamplesAvailable] = useState(IS_MOCK_MODE);
  const browseRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (IS_MOCK_MODE) {
      setPublicSamplesAvailable(true);
      return;
    }
    let active = true;
    fetch("/samples-public/manifest.json", { method: "HEAD" })
      .then((res) => {
        if (active && res.ok) setPublicSamplesAvailable(true);
      })
      .catch(() => {
        // Hide sample buttons in real mode when /samples-public/ is absent.
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSampleClick(sample: (typeof SAMPLE_BUTTONS)[number]) {
    if (IS_MOCK_MODE) {
      onSampleSelected(sample.id);
      return;
    }
    try {
      const resp = await fetch(`/samples-public/${sample.fileName}`);
      if (!resp.ok) throw new Error("Sample not found");
      const blob = await resp.blob();
      onFileSelected(new File([blob], sample.fileName, { type: blob.type || "image/jpeg" }));
    } catch {
      setClientError("Sample file could not be loaded.");
    }
  }

  function processFile(file: File | undefined) {
    if (!file) return;
    const err = validateUploadFile(file);
    if (err) {
      setClientError(err);
      return;
    }
    setClientError(null);
    onFileSelected(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    processFile(event.dataTransfer.files?.[0]);
  }

  return (
    <section className="space-y-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`rounded-2xl border-2 border-dashed p-8 text-center transition-colors sm:p-12 ${
          dragActive
            ? "border-indigo-500 bg-indigo-50/70 dark:bg-indigo-950/30"
            : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900/70"
        }`}
      >
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-400">
          <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.8}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>

        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
          Drop your document here to check for indicators of tampering
        </h2>
        <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
          Supports GST certificates, invoices/bills, bank or UPI statements, and payment receipts
          (JPG, PNG, PDF up to 15 MB).
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => browseRef.current?.click()}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
          >
            Choose a file
          </button>

          <button
            type="button"
            onClick={() => cameraRef.current?.click()}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 sm:hidden dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            Take photo
          </button>
        </div>

        <input
          ref={browseRef}
          type="file"
          accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
          className="hidden"
          onChange={(e) => {
            processFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => {
            processFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />

        {clientError && (
          <p
            role="alert"
            className="mx-auto mt-4 max-w-md rounded-xl border border-rose-300 bg-rose-50 px-4 py-2.5 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-950/40 dark:text-rose-300"
          >
            {clientError}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Files are deleted after 1 hour
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-indigo-500" />
          Defence-only: helps you verify, never accuses
        </span>
      </div>

      {publicSamplesAvailable && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Try a sample
          </p>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {SAMPLE_BUTTONS.map((sample) => (
              <button
                key={sample.id}
                type="button"
                onClick={() => void handleSampleClick(sample)}
                className="flex flex-col items-start rounded-xl border border-slate-200 bg-white p-3.5 text-left shadow-sm transition hover:border-indigo-400 hover:shadow focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-500"
              >
                <span className="text-sm font-semibold text-slate-900 dark:text-white">
                  {sample.label}
                </span>
                <span className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {sample.hint}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
