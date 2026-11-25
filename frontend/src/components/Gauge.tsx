import { useEffect, useState } from "react";
import type { RiskLevel } from "../types/analysis";

interface GaugeProps {
  score: number;
  level: RiskLevel;
}

const LEVEL_STYLES: Record<RiskLevel, { stroke: string; badge: string; label: string }> = {
  LOW: {
    stroke: "#10b981",
    badge: "bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/40",
    label: "LOW RISK",
  },
  MEDIUM: {
    stroke: "#f59e0b",
    badge: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/40",
    label: "MEDIUM RISK",
  },
  HIGH: {
    stroke: "#ef4444",
    badge: "bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/40",
    label: "HIGH RISK",
  },
};

export function Gauge({ score, level }: GaugeProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const [displayScore, setDisplayScore] = useState(0);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => setDisplayScore(clamped));
    return () => window.cancelAnimationFrame(id);
  }, [clamped]);

  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (displayScore / 100) * circumference;
  const style = LEVEL_STYLES[level];

  return (
    <div
      className="flex flex-col items-center gap-2"
      role="img"
      aria-label={`Risk score ${clamped} out of 100, ${style.label}`}
    >
      <div className="relative h-32 w-32">
        <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
          <circle
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            className="text-slate-200 dark:text-slate-800"
          />
          <circle
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            stroke={style.stroke}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            {clamped}
          </span>
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
            / 100
          </span>
        </div>
      </div>
      <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${style.badge}`}>
        {style.label}
      </span>
    </div>
  );
}
