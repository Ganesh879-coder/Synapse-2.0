import { useMemo, useState } from "react";
import {
  deleteAnalysis,
  getPageImageUrl,
  getReportPdfUrl,
  IS_MOCK_MODE,
} from "./api";
import { ChecksTable } from "./components/ChecksTable";
import { DocumentViewer } from "./components/DocumentViewer";
import { FindingCard } from "./components/FindingCard";
import { Gauge } from "./components/Gauge";
import { ProgressSteps } from "./components/ProgressSteps";
import { ScoreBreakdown } from "./components/ScoreBreakdown";
import { UploadZone } from "./components/UploadZone";
import { useAnalysis } from "./hooks/useAnalysis";
import { useTheme } from "./hooks/useTheme";
import type { CheckResult, ExtractedFieldValue, PageArtifact } from "./types/analysis";

const I18N = {
  en: {
    subtitle: "Document verification for buyers & finance teams",
    verdictHeading: "Assessment summary",
    nextActionsHeading: "What to do next",
    findingsHeading: "Findings",
    extractedHeading: "Extracted fields",
    noFindings: "No indicators of tampering found.",
  },
  hi: {
    subtitle: "खरीदारों और वित्त टीमों के लिए दस्तावेज़ जांच",
    verdictHeading: "जांच का सारांश",
    nextActionsHeading: "आगे क्या करें",
    findingsHeading: "मुख्य संकेत",
    extractedHeading: "निकाले गए विवरण",
    noFindings: "छेड़छाड़ के कोई संकेत नहीं मिले।",
  },
} as const;

function formatFieldValue(raw: unknown): string {
  if (raw !== null && typeof raw === "object" && "value" in (raw as Record<string, unknown>)) {
    const val = (raw as ExtractedFieldValue).value;
    if (typeof val === "object" && val !== null) return JSON.stringify(val);
    return String(val ?? "");
  }
  if (typeof raw === "object" && raw !== null) return JSON.stringify(raw);
  return String(raw ?? "");
}

function isFieldFlagged(fieldKey: string, checks: CheckResult[]): boolean {
  const tokens = fieldKey.toLowerCase().split("_").filter((t) => t.length > 2);
  return checks.some(
    (chk) =>
      chk.status === "fail" &&
      (chk.name.toLowerCase().includes(fieldKey.toLowerCase()) ||
        tokens.some((tok) => chk.name.toLowerCase().includes(tok)))
  );
}

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const { phase, stage, result, error, analyzeFile, runMock, reset } = useAnalysis();
  const [deleting, setDeleting] = useState<boolean>(false);
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [hoveredRegionIds, setHoveredRegionIds] = useState<string[]>([]);
  const [focusedRegionId, setFocusedRegionId] = useState<string | null>(null);

  const t = I18N[lang];

  const viewerPages: PageArtifact[] = useMemo(() => {
    if (!result) return [];
    if (result.pages && result.pages.length > 0) return result.pages;
    return [
      {
        page: 1,
        width: 700,
        height: 900,
        image_url: getPageImageUrl(result.doc_id, 1),
        heatmap_url: result.heatmap_url,
      },
    ];
  }, [result]);

  function handleCheckSelect(check: CheckResult) {
    if (!result) return;
    const keyPart = check.name.split(":").pop() ?? "";
    const matchedFinding = result.findings.find(
      (f) =>
        f.evidence_region_ids.length > 0 &&
        (f.title.toLowerCase().includes(keyPart.replaceAll("_", " ")) ||
          f.category === "consistency")
    );
    const targetId = matchedFinding?.evidence_region_ids[0] ?? result.regions[0]?.id ?? null;
    if (targetId) {
      setFocusedRegionId(targetId);
      setHoveredRegionIds([targetId]);
    }
  }

  const confidence = result?.confidence ?? 1;
  const verdictText = result?.summary?.verdict || result?.verdict || "";
  const nextActions = result?.summary?.next_actions ?? [];
  const disclaimerText =
    result?.summary?.disclaimer ||
    "This automated assessment highlights statistical and structural indicators only. It does not constitute legal proof of forgery or authenticity.";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-2.5 text-left focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded-lg"
          >
            <svg
              className="h-8 w-8 text-indigo-600 dark:text-indigo-400"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M12 2L4 5.5V11.5C4 16.75 7.4 21.55 12 23C16.6 21.55 20 16.75 20 11.5V5.5L12 2Z"
                fill="currentColor"
                fillOpacity="0.15"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path
                d="M9.5 12.2L11.2 13.9L14.8 10.3"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div>
              <span className="block text-base font-bold tracking-tight text-slate-900 dark:text-white">
                Kavach
              </span>
              <span className="hidden text-xs text-slate-500 sm:block dark:text-slate-400">
                {t.subtitle}
              </span>
            </div>
          </button>

          <div className="flex items-center gap-2">
            {IS_MOCK_MODE && (
              <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300">
                Demo mode
              </span>
            )}

            <button
              type="button"
              onClick={() => setLang((prev) => (prev === "en" ? "hi" : "en"))}
              aria-label="Toggle language"
              className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {lang === "en" ? "EN | हिं" : "हिं | EN"}
            </button>

            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {phase === "upload" && (
          <UploadZone onFileSelected={analyzeFile} onSampleSelected={runMock} />
        )}

        {phase === "analysing" && <ProgressSteps activeStage={stage} />}

        {phase === "error" && (
          <section
            role="alert"
            className="mx-auto max-w-lg rounded-2xl border border-rose-200 bg-white p-6 text-center shadow-sm dark:border-rose-500/30 dark:bg-slate-900"
          >
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Could not complete verification
            </h2>
            <p className="mt-2 text-sm text-rose-700 dark:text-rose-300">{error}</p>
            <div className="mt-5 flex justify-center gap-3">
              <button
                type="button"
                onClick={reset}
                className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                Try again
              </button>
            </div>
          </section>
        )}

        {phase === "result" && result && (
          <div className="space-y-6">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 dark:border-slate-800 dark:bg-slate-900">
              <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
                  <Gauge score={result.risk_score} level={result.risk_level} />
                  <div className="space-y-2.5 text-center sm:text-left">
                    <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                      <span className="rounded-lg bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        {result.doc_type.replaceAll("_", " ")}
                      </span>
                      {confidence < 0.5 && (
                        <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-0.5 text-xs font-medium text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300">
                          Low confidence: image quality limits this check
                        </span>
                      )}
                    </div>

                    <h2 className="text-base font-semibold text-slate-900 dark:text-white">
                      {t.verdictHeading}
                    </h2>
                    <p className="max-w-2xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                      {verdictText}
                    </p>

                    {nextActions.length > 0 && (
                      <div className="pt-1">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          {t.nextActionsHeading}
                        </h3>
                        <ul className="mt-1.5 space-y-1 text-sm text-slate-700 dark:text-slate-300">
                          {nextActions.map((act, idx) => (
                            <li key={idx} className="flex items-start gap-2">
                              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />
                              <span>{act}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-center gap-2.5 md:flex-col md:items-stretch">
                  {!IS_MOCK_MODE ? (
                    <a
                      href={getReportPdfUrl(result.doc_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-xl bg-indigo-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      Download PDF report
                    </a>
                  ) : (
                    <button
                      type="button"
                      disabled
                      title="PDF export requires the live backend"
                      className="cursor-not-allowed rounded-xl bg-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-500"
                    >
                      Download PDF report
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={reset}
                    className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    Analyse another
                  </button>

                  {!IS_MOCK_MODE && (
                    <button
                      type="button"
                      disabled={deleting}
                      onClick={async () => {
                        setDeleting(true);
                        try {
                          await deleteAnalysis(result.doc_id);
                        } finally {
                          setDeleting(false);
                          reset();
                        }
                      }}
                      className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 focus:outline-none focus:ring-2 focus:ring-rose-500 disabled:opacity-50 dark:border-rose-500/40 dark:bg-rose-950/30 dark:text-rose-300"
                    >
                      {deleting ? "Deleting..." : "Delete this analysis now"}
                    </button>
                  )}
                </div>
              </div>
            </section>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-6 lg:sticky lg:top-6 lg:self-start">
                <DocumentViewer
                  pages={viewerPages}
                  regions={result.regions}
                  fallbackHeatmapUrl={result.heatmap_url}
                  highlightedRegionIds={hoveredRegionIds}
                  focusedRegionId={focusedRegionId}
                  onHoverRegion={(id) => setHoveredRegionIds(id ? [id] : [])}
                  onSelectRegion={(id) => {
                    setFocusedRegionId(id);
                    setHoveredRegionIds([id]);
                  }}
                />
              </div>

              <div className="space-y-6 lg:col-span-6">
                {result.score_breakdown && result.score_breakdown.length > 0 && (
                  <ScoreBreakdown items={result.score_breakdown} />
                )}

                <section className="space-y-3">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                    {t.findingsHeading} ({result.findings.length})
                  </h3>
                  {result.findings.length === 0 ? (
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-950/30 dark:text-emerald-300">
                      {t.noFindings}
                    </div>
                  ) : (
                    result.findings.map((finding) => {
                      const highlighted = finding.evidence_region_ids.some(
                        (rid) => hoveredRegionIds.includes(rid) || focusedRegionId === rid
                      );
                      return (
                        <FindingCard
                          key={finding.id}
                          finding={finding}
                          isHighlighted={highlighted}
                          onHoverRegions={setHoveredRegionIds}
                          onFocusRegions={(ids) => {
                            if (ids.length > 0) {
                              setFocusedRegionId(ids[0]);
                              setHoveredRegionIds(ids);
                            }
                          }}
                        />
                      );
                    })
                  )}
                </section>

                <ChecksTable checks={result.checks} onCheckSelect={handleCheckSelect} />

                {Object.keys(result.extracted_fields).length > 0 && (
                  <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {t.extractedHeading}
                    </h3>
                    <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {Object.entries(result.extracted_fields).map(([key, rawVal]) => {
                        const flagged = isFieldFlagged(key, result.checks);
                        return (
                          <div
                            key={key}
                            className={`rounded-xl border px-3 py-2 ${
                              flagged
                                ? "border-rose-300 bg-rose-50/70 dark:border-rose-500/40 dark:bg-rose-950/30"
                                : "border-slate-100 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/50"
                            }`}
                          >
                            <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                              {key.replaceAll("_", " ")}
                            </dt>
                            <dd className="mt-0.5 break-words text-xs font-medium text-slate-900 dark:text-slate-100">
                              {formatFieldValue(rawVal)}
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                  </section>
                )}

                <aside className="space-y-2 rounded-2xl border border-slate-200 bg-slate-100/80 p-4 text-xs leading-relaxed text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400">
                  <p>{disclaimerText}</p>
                  <p className="border-t border-slate-200 pt-2 dark:border-slate-800">
                    <strong>Privacy notice:</strong> Uploaded documents and extracted fields are
                    stored temporarily only for processing, automatically deleted after 60 minutes
                    (or immediately via &ldquo;Delete this analysis now&rdquo;), and are accessible
                    only to your authenticated session.
                  </p>
                </aside>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
