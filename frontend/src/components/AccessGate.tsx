import { FormEvent, useState } from "react";
import { loginWithAccessKey } from "../api";

interface AccessGateProps {
  onAuthenticated: () => void;
}

export function AccessGate({ onAuthenticated }: AccessGateProps) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await loginWithAccessKey(code);
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid access code.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Enter access code</h2>
      <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
        Kavach requires an authorized access key to upload and inspect documents.
      </p>

      <form onSubmit={handleSubmit} className="mt-5 space-y-4">
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium text-slate-700 dark:text-slate-300">
            Access key
          </span>
          <input
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Paste your access code"
            autoComplete="off"
            className="block w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>

        {error && (
          <p
            role="alert"
            className="rounded-xl border border-rose-300 bg-rose-50 px-3.5 py-2 text-xs text-rose-700 dark:border-rose-500/40 dark:bg-rose-950/40 dark:text-rose-300"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={!code.trim() || loading}
          className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Verifying..." : "Continue"}
        </button>
      </form>
    </section>
  );
}
