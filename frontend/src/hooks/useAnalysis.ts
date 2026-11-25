import { useCallback, useEffect, useRef, useState } from "react";
import {
  IS_MOCK_MODE,
  loadMockFixture,
  pollAnalysisStatus,
  startAnalysis,
  validateUploadFile,
} from "../api";
import type { AnalysisResult, MockSampleId, PipelineStage } from "../types/analysis";

export type AppPhase = "upload" | "analysing" | "result" | "error";

const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 90_000;
const MOCK_STAGES: PipelineStage[] = ["reading", "numbers", "edits", "scoring"];

export function useAnalysis() {
  const [phase, setPhase] = useState<AppPhase>("upload");
  const [stage, setStage] = useState<PipelineStage | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<{ cancelled: boolean }>({ cancelled: false });

  const reset = useCallback(() => {
    abortRef.current.cancelled = true;
    setPhase("upload");
    setStage(null);
    setResult(null);
    setError(null);
  }, []);

  useEffect(() => {
    const current = abortRef.current;
    return () => {
      current.cancelled = true;
    };
  }, []);

  const runMock = useCallback(async (sampleId: MockSampleId) => {
    abortRef.current.cancelled = true;
    const token = { cancelled: false };
    abortRef.current = token;

    setPhase("analysing");
    setError(null);
    setResult(null);

    try {
      for (const step of MOCK_STAGES) {
        if (token.cancelled) return;
        setStage(step);
        await new Promise((resolve) => setTimeout(resolve, 750));
      }
      if (token.cancelled) return;
      const fixture = await loadMockFixture(sampleId);
      if (token.cancelled) return;
      setResult(fixture);
      setPhase("result");
    } catch (err) {
      if (token.cancelled) return;
      setError(err instanceof Error ? err.message : "Could not load sample result.");
      setPhase("error");
    }
  }, []);

  const analyzeFile = useCallback(
    async (file: File) => {
      const validationError = validateUploadFile(file);
      if (validationError) {
        setError(validationError);
        setPhase("error");
        return;
      }

      if (IS_MOCK_MODE) {
        await runMock("clean_bill");
        return;
      }

      abortRef.current.cancelled = true;
      const token = { cancelled: false };
      abortRef.current = token;

      setPhase("analysing");
      setStage("reading");
      setError(null);
      setResult(null);

      try {
        const queued = await startAnalysis(file);
        const startedAt = Date.now();

        while (!token.cancelled) {
          if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
            throw new Error(
              "The check is taking longer than expected (90s timeout). Please try again."
            );
          }

          const statusResp = await pollAnalysisStatus(queued.doc_id);
          if (token.cancelled) return;

          if (statusResp.stage) {
            setStage(statusResp.stage);
          }
          if (statusResp.status === "done" && statusResp.result) {
            setResult(statusResp.result);
            setPhase("result");
            return;
          }
          if (statusResp.status === "failed") {
            throw new Error(
              statusResp.error || "Unable to read or verify this document. Please try another file."
            );
          }

          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        }
      } catch (err) {
        if (token.cancelled) return;
        setError(err instanceof Error ? err.message : "Analysis failed. Please try again.");
        setPhase("error");
      }
    },
    [runMock]
  );

  return {
    phase,
    stage,
    result,
    error,
    analyzeFile,
    runMock,
    reset,
  };
}
