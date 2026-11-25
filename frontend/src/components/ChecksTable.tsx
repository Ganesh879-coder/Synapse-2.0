import type { CheckResult, CheckStatus } from "../types/analysis";

interface ChecksTableProps {
  checks: CheckResult[];
  onCheckSelect: (check: CheckResult) => void;
}

const STATUS_BADGE: Record<CheckStatus, { icon: string; style: string; label: string }> = {
  pass: {
    icon: "✓",
    style: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300",
    label: "Pass",
  },
  warn: {
    icon: "!",
    style: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300",
    label: "Warn",
  },
  fail: {
    icon: "✕",
    style: "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300",
    label: "Fail",
  },
  skipped: {
    icon: "–",
    style: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
    label: "Skipped",
  },
};

export function ChecksTable({ checks, onCheckSelect }: ChecksTableProps) {
  if (!checks || checks.length === 0) return null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Consistency checks</h3>
      <div className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
        {checks.map((chk, idx) => {
          const badge = STATUS_BADGE[chk.status];
          const clickable = chk.status === "fail" || chk.status === "warn";
          return (
            <button
              key={`${chk.name}-${idx}`}
              type="button"
              disabled={!clickable}
              onClick={() => {
                if (clickable) onCheckSelect(chk);
              }}
              className={`flex w-full items-start gap-3 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                clickable
                  ? "cursor-pointer rounded-lg px-2 -mx-2 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                  : "cursor-default"
              }`}
            >
              <span
                aria-label={badge.label}
                className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${badge.style}`}
              >
                {badge.icon}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {chk.name.replace(/^[a-z]+:/, "").replaceAll("_", " ")}
                </p>
                <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{chk.detail}</p>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
