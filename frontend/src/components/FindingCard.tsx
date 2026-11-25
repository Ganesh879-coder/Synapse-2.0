import { useState } from "react";
import type { Finding, SeverityLevel } from "../types/analysis";

interface FindingCardProps {
  finding: Finding;
  isHighlighted: boolean;
  onFocusRegions: (regionIds: string[]) => void;
  onHoverRegions: (regionIds: string[]) => void;
}

const SEVERITY_BADGES: Record<SeverityLevel, string> = {
  low: "bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
  medium: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/40",
  high: "bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/40",
  critical: "bg-rose-200 text-rose-900 border-rose-400 dark:bg-rose-600/30 dark:text-rose-200 dark:border-rose-500",
};

export function FindingCard({
  finding,
  isHighlighted,
  onFocusRegions,
  onHoverRegions,
}: FindingCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <article
      onMouseEnter={() => onHoverRegions(finding.evidence_region_ids)}
      onMouseLeave={() => onHoverRegions([])}
      onClick={() => {
        if (finding.evidence_region_ids.length > 0) {
          onFocusRegions(finding.evidence_region_ids);
        }
      }}
      className={`rounded-2xl border p-4 transition shadow-sm ${
        finding.evidence_region_ids.length > 0 ? "cursor-pointer" : ""
      } ${
        isHighlighted
          ? "border-indigo-500 bg-indigo-50/60 ring-2 ring-indigo-500/30 dark:border-indigo-400 dark:bg-indigo-950/30"
          : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-900 dark:text-white">{finding.title}</h4>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase ${SEVERITY_BADGES[finding.severity]}`}
        >
          {finding.severity}
        </span>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {finding.plain_explanation}
      </p>

      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((prev) => !prev);
          }}
          aria-expanded={expanded}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:text-indigo-400"
        >
          {expanded ? "Hide technical details" : "Technical details"}
        </button>

        {finding.evidence_region_ids.length > 0 && (
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
            Click to focus region
          </span>
        )}
      </div>

      {expanded && (
        <p className="mt-2 rounded-xl bg-slate-50 p-3 font-mono text-xs text-slate-700 dark:bg-slate-950 dark:text-slate-300">
          {finding.technical_detail}
        </p>
      )}
    </article>
  );
}
