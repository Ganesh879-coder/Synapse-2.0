import { PointerEvent, useEffect, useRef, useState } from "react";
import { resolveArtifactUrl } from "../api";
import type { PageArtifact, Region } from "../types/analysis";

export type ViewerMode = "original" | "heatmap" | "boxes";

interface DocumentViewerProps {
  pages: PageArtifact[];
  regions: Region[];
  fallbackHeatmapUrl: string | null;
  highlightedRegionIds: string[];
  focusedRegionId: string | null;
  onHoverRegion: (regionId: string | null) => void;
  onSelectRegion: (regionId: string) => void;
}

function regionColor(score: number): string {
  if (score >= 0.7) return "#ef4444";
  if (score >= 0.4) return "#f59e0b";
  return "#6366f1";
}

export function DocumentViewer({
  pages,
  regions,
  fallbackHeatmapUrl,
  highlightedRegionIds,
  focusedRegionId,
  onHoverRegion,
  onSelectRegion,
}: DocumentViewerProps) {
  const [mode, setMode] = useState<ViewerMode>(regions.length > 0 ? "boxes" : "original");
  const [activePage, setActivePage] = useState<number>(pages[0]?.page ?? 1);
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [heatmapOpacity, setHeatmapOpacity] = useState<number>(0.65);
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; origX: number; origY: number }>({
    active: false,
    startX: 0,
    startY: 0,
    origX: 0,
    origY: 0,
  });

  useEffect(() => {
    setActivePage(pages[0]?.page ?? 1);
    setMode(regions.length > 0 ? "boxes" : "original");
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [pages, regions.length]);

  useEffect(() => {
    if (!focusedRegionId) return;
    const target = regions.find((r) => r.id === focusedRegionId);
    if (!target) return;
    setActivePage(target.page);
    setMode("boxes");
    setZoom(1.65);
    const cx = (target.bbox[0] + target.bbox[2]) / 2;
    const cy = (target.bbox[1] + target.bbox[3]) / 2;
    setPan({
      x: Math.round((0.5 - cx) * 220),
      y: Math.round((0.5 - cy) * 220),
    });
  }, [focusedRegionId, regions]);

  const currentPage = pages.find((p) => p.page === activePage) ?? pages[0];
  const pageRegions = regions.filter((r) => r.page === (currentPage?.page ?? 1));
  const imageSrc = currentPage ? resolveArtifactUrl(currentPage.image_url) : "";
  const heatmapSrc = currentPage?.heatmap_url
    ? resolveArtifactUrl(currentPage.heatmap_url)
    : fallbackHeatmapUrl
      ? resolveArtifactUrl(fallbackHeatmapUrl)
      : "";

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      origX: pan.x,
      origY: pan.y,
    };
  }

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragRef.current.active) return;
    setPan({
      x: dragRef.current.origX + (e.clientX - dragRef.current.startX),
      y: dragRef.current.origY + (e.clientY - dragRef.current.startY),
    });
  }

  function handlePointerUp() {
    dragRef.current.active = false;
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div
          role="group"
          aria-label="Viewer overlay mode"
          className="inline-flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800"
        >
          {(["original", "heatmap", "boxes"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setMode(item)}
              aria-pressed={mode === item}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                mode === item
                  ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                  : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            aria-label="Zoom out"
            onClick={() => setZoom((z) => Math.max(0.75, Number((z - 0.25).toFixed(2))))}
            className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            -
          </button>
          <span className="min-w-[3rem] text-center text-xs font-medium text-slate-600 dark:text-slate-400">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            aria-label="Zoom in"
            onClick={() => setZoom((z) => Math.min(3, Number((z + 0.25).toFixed(2))))}
            className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            +
          </button>
          <button
            type="button"
            aria-label="Reset zoom and pan"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Reset
          </button>
        </div>
      </div>

      {mode === "heatmap" && heatmapSrc && (
        <div className="mb-3 flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/60">
          <label htmlFor="heatmap-opacity" className="font-medium text-slate-600 dark:text-slate-300">
            Heatmap opacity
          </label>
          <input
            id="heatmap-opacity"
            type="range"
            min={0.15}
            max={1}
            step={0.05}
            value={heatmapOpacity}
            onChange={(e) => setHeatmapOpacity(Number(e.target.value))}
            className="flex-1 accent-indigo-600"
          />
          <span className="w-9 text-right text-slate-500 dark:text-slate-400">
            {Math.round(heatmapOpacity * 100)}%
          </span>
        </div>
      )}

      {pages.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Document pages">
          {pages.map((p) => (
            <button
              key={p.page}
              type="button"
              role="tab"
              aria-selected={p.page === activePage}
              onClick={() => setActivePage(p.page)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                p.page === activePage
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              Page {p.page}
            </button>
          ))}
        </div>
      )}

      <div
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        className="relative h-[420px] cursor-grab overflow-hidden rounded-xl border border-slate-200 bg-slate-100 active:cursor-grabbing sm:h-[540px] dark:border-slate-800 dark:bg-slate-950"
      >
        {imageSrc ? (
          <div
            className="flex h-full w-full items-center justify-center transition-transform duration-150 ease-out"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            }}
          >
            <div className="relative inline-block max-h-full max-w-full">
              <img
                src={imageSrc}
                alt={`Uploaded document page ${currentPage?.page ?? 1}`}
                draggable={false}
                className="max-h-[400px] w-auto select-none rounded shadow sm:max-h-[520px]"
              />

              {mode === "heatmap" && heatmapSrc && (
                <img
                  src={heatmapSrc}
                  alt="Tampering indicator heatmap overlay"
                  draggable={false}
                  style={{ opacity: heatmapOpacity }}
                  className="pointer-events-none absolute inset-0 h-full w-full select-none rounded object-contain"
                />
              )}

              {mode === "boxes" && pageRegions.length > 0 && (
                <svg
                  viewBox="0 0 100 100"
                  preserveAspectRatio="none"
                  className="absolute inset-0 h-full w-full"
                >
                  {pageRegions.map((reg) => {
                    const [x0, y0, x1, y1] = reg.bbox;
                    const highlighted =
                      highlightedRegionIds.includes(reg.id) || focusedRegionId === reg.id;
                    const color = regionColor(reg.score);
                    return (
                      <rect
                        key={reg.id}
                        x={x0 * 100}
                        y={y0 * 100}
                        width={Math.max(0.8, (x1 - x0) * 100)}
                        height={Math.max(0.8, (y1 - y0) * 100)}
                        fill={color}
                        fillOpacity={highlighted ? 0.34 : 0.16}
                        stroke={color}
                        strokeWidth={highlighted ? 1.1 : 0.6}
                        className="cursor-pointer transition-all"
                        onMouseEnter={() => onHoverRegion(reg.id)}
                        onMouseLeave={() => onHoverRegion(null)}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRegion(reg.id);
                        }}
                      >
                        <title>{reg.reason}</title>
                      </rect>
                    );
                  })}
                </svg>
              )}
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            No page preview available.
          </div>
        )}
      </div>
    </div>
  );
}
