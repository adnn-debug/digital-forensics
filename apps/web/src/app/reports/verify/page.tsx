"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { verifyPublicReport, PublicReportVerification } from "@/lib/api";

export default function VerifyReportPage(): React.JSX.Element {
  const [token, setToken] = useState<string | null>(null);
  const [result, setResult] = useState<PublicReportVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
  }, []);

  useEffect(() => {
    let active = true;
    if (token === null) return () => { active = false; };
    if (!token) {
      setError("This verification link is missing its token. Scan the QR code printed on the original report.");
      setLoading(false);
      return () => { active = false; };
    }

    setLoading(true);
    setError(null);
    verifyPublicReport(token)
      .then((response) => { if (active) setResult(response); })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Report verification could not be completed.");
      })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [token]);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-12">
      <div className="rounded-2xl border border-forensic-800 bg-forensic-900 p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-integrity-cyan/30 bg-integrity-cyan/10">
            <ShieldCheck className="h-5 w-5 text-integrity-cyan" />
          </div>
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-integrity-cyan">PS-05 · Public verification</p>
            <h1 className="mt-1 text-xl font-bold text-white sm:text-2xl">Forensic report integrity check</h1>
          </div>
        </div>

        <p className="mt-5 text-sm leading-6 text-forensic-300">
          This page recalculates the SHA-256 hash of the archived PDF and compares it with the
          baseline recorded when the report was generated. It verifies byte-level integrity of
          that PDF; it does not by itself establish the truth of findings or legal admissibility.
        </p>

        {loading && (
          <div role="status" className="mt-8 flex items-center gap-3 rounded-xl border border-forensic-700 p-4 text-sm text-forensic-300">
            <Loader2 className="h-5 w-5 animate-spin text-integrity-cyan" />
            Checking archived report…
          </div>
        )}

        {!loading && error && (
          <div role="alert" className="mt-8 flex items-start gap-3 rounded-xl border border-amber-700/60 bg-amber-950/30 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div>
              <h2 className="font-semibold text-amber-200">Verification could not be completed</h2>
              <p className="mt-1 break-words text-sm text-amber-100/80">{error}</p>
            </div>
          </div>
        )}

        {!loading && result && (
          <section className="mt-8 space-y-5" aria-live="polite">
            <div className={`rounded-xl border p-4 ${result.integrity_valid ? "border-emerald-700/60 bg-emerald-950/30" : "border-rose-700/60 bg-rose-950/30"}`}>
              <div className="flex items-center gap-3">
                {result.integrity_valid
                  ? <CheckCircle2 className="h-6 w-6 text-emerald-400" />
                  : <XCircle className="h-6 w-6 text-rose-400" />}
                <div>
                  <h2 className={`font-semibold ${result.integrity_valid ? "text-emerald-200" : "text-rose-200"}`}>
                    {result.integrity_valid ? "PDF hash matches recorded baseline" : "PDF integrity check failed"}
                  </h2>
                  <p className="mt-1 text-sm text-forensic-300">{result.message}</p>
                </div>
              </div>
            </div>

            <dl className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Report number</dt>
                <dd className="mt-1 break-words font-mono text-sm text-white">{result.report_number}</dd>
              </div>
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Report title</dt>
                <dd className="mt-1 break-words text-sm text-white">{result.title}</dd>
              </div>
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Recorded SHA-256</dt>
                <dd className="mt-1 break-all font-mono text-xs text-forensic-200">{result.expected_sha256}</dd>
              </div>
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Calculated SHA-256</dt>
                <dd className="mt-1 break-all font-mono text-xs text-forensic-200">{result.actual_sha256 ?? "Unavailable"}</dd>
              </div>
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Archived file size</dt>
                <dd className="mt-1 font-mono text-sm text-white">{result.file_size_bytes.toLocaleString()} bytes</dd>
              </div>
              <div className="rounded-lg border border-forensic-800 bg-forensic-950/60 p-4">
                <dt className="text-xs text-forensic-400">Report generated</dt>
                <dd className="mt-1 text-sm text-white">{new Date(result.created_at).toLocaleString()}</dd>
              </div>
            </dl>
          </section>
        )}
      </div>
    </main>
  );
}
