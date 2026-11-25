import type { PipelineStage } from "../types/analysis";

interface ProgressStepsProps {
  activeStage: PipelineStage | null;
}

const STAGES: { key: PipelineStage; label: string; sub: string }[] = [
  { key: "reading", label: "Reading the document", sub: "Extracting text and layout" },
  { key: "numbers", label: "Verifying the numbers", sub: "Checking totals, tax, and IDs" },
  { key: "edits", label: "Checking for edits", sub: "Inspecting visual consistency" },
  { key: "scoring", label: "Scoring the risk", sub: "Summarizing indicators" },
];

export function ProgressSteps({ activeStage }: ProgressStepsProps) {
  return (
    <section
      aria-label="Document analysis in progress"
      className="mx-auto max-w-2xl space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-3">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
          Analyzing your document...
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {STAGES.map((step) => {
          const isActive = activeStage === step.key;
          return (
            <div
              key={step.key}
              className={`rounded-xl border p-4 transition-colors ${
                isActive
                  ? "border-indigo-500 bg-indigo-50/70 dark:border-indigo-400 dark:bg-indigo-950/30"
                  : "border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-950/40"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    isActive
                      ? "animate-pulse bg-indigo-600 dark:bg-indigo-400"
                      : "bg-slate-300 dark:bg-slate-700"
                  }`}
                />
                <span
                  className={`text-sm font-semibold ${
                    isActive
                      ? "text-indigo-900 dark:text-indigo-200"
                      : "text-slate-700 dark:text-slate-300"
                  }`}
                >
                  {step.label}
                </span>
              </div>
              <p className="mt-1 pl-5 text-xs text-slate-500 dark:text-slate-400">{step.sub}</p>
            </div>
          );
        })}
      </div>

      <div className="space-y-3 pt-2" aria-hidden="true">
        <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
        <div className="h-4 w-1/2 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
      </div>
    </section>
  );
}
