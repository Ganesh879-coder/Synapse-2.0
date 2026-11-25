import type { ScoreContribution } from "../types/analysis";

interface ScoreBreakdownProps {
  items: ScoreContribution[];
}

export function ScoreBreakdown({ items }: ScoreBreakdownProps) {
  if (!items || items.length === 0) return null;

  const sorted = [...items].sort((a, b) => b.contribution - a.contribution);
  const maxVal = Math.max(10, ...sorted.map((item) => item.contribution));

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Why this score</h3>
      <div className="mt-3 space-y-3">
        {sorted.map((item) => {
          const widthPct = Math.max(4, Math.min(100, (item.contribution / maxVal) * 100));
          return (
            <div key={item.signal} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {item.label}
                </span>
                <span className="font-semibold text-slate-900 dark:text-white">
                  +{item.contribution.toFixed(1)}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full bg-indigo-600 dark:bg-indigo-500"
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
