"use client";

import React, { use, useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Copy,
  Check,
  Layers,
  Sliders,
  Eye,
  AlertTriangle,
  Info,
  CheckCircle2,
  Sparkles,
  Play,
  FileImage,
  Cpu,
  BarChart2,
  Download,
  AlertCircle,
} from "lucide-react";
import {
  fetchEvidenceDetail,
  getEvidenceContentUrl,
  getArtifactContentUrl,
  createAnalysisJob,
  getAnalysisJob,
  getAnalysisHistory,
  verifyEvidenceHash,
  EvidenceDetailItem,
  ForensicAnalysisJob,
  HashVerificationResult,
  ImageAnalysisSummary,
  FindingItem,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ caseId: string; evidenceId: string }>;
}

export default function ImageAnalysisResultsPage({ params }: PageProps): React.JSX.Element {
  const resolvedParams = use(params);
  const { caseId, evidenceId } = resolvedParams;

  // Evidence state
  const [evidence, setEvidence] = useState<EvidenceDetailItem | null>(null);
  const [loadingEvidence, setLoadingEvidence] = useState<boolean>(true);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  // Analysis job state
  const [activeJob, setActiveJob] = useState<ForensicAnalysisJob | null>(null);
  const [loadingJob, setLoadingJob] = useState<boolean>(true);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [submittingJob, setSubmittingJob] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Analysis parameters form state
  const [qualitySetting, setQualitySetting] = useState<number>(95);
  const [amplificationScale, setAmplificationScale] = useState<number>(15);

  // Comparison Visualizer state
  const [viewMode, setViewMode] = useState<"side-by-side" | "blend" | "original" | "heatmap">("side-by-side");
  const [blendOpacity, setBlendOpacity] = useState<number>(50);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  // Independent verification state
  const [verifyingHash, setVerifyingHash] = useState<boolean>(false);
  const [verificationResult, setVerificationResult] = useState<HashVerificationResult | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Load evidence details
  const loadEvidence = useCallback(async () => {
    setLoadingEvidence(true);
    setEvidenceError(null);
    try {
      const data = await fetchEvidenceDetail(caseId, evidenceId);
      setEvidence(data);
    } catch (err) {
      setEvidenceError(err instanceof Error ? err.message : "Failed to load evidence bitstream details.");
    } finally {
      setLoadingEvidence(false);
    }
  }, [caseId, evidenceId]);

  // Polling controller
  const startPolling = useCallback((jobId: string) => {
    setIsPolling(true);
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);

    const poll = async () => {
      try {
        const updated = await getAnalysisJob(jobId);
        setActiveJob(updated);

        if (updated.status === "COMPLETED" || updated.status === "FAILED" || updated.status === "SKIPPED") {
          setIsPolling(false);
          return;
        }

        pollTimerRef.current = setTimeout(poll, 2000);
      } catch (err) {
        console.warn("Error polling job status:", err);
        setIsPolling(false);
      }
    };

    poll();
  }, []);

  // Find latest JPEG_ELA analysis job for this evidence
  const loadLatestJob = useCallback(async () => {
    setLoadingJob(true);
    try {
      const history = await getAnalysisHistory({
        evidence_id: evidenceId,
        analysis_type: "JPEG_ELA",
        page: 1,
        page_size: 1,
      });

      if (history.items && history.items.length > 0) {
        const latest = history.items[0];
        if (latest) {
          // Fetch full job with artifacts & findings
          const fullJob = await getAnalysisJob(latest.id);
          setActiveJob(fullJob);

          if (fullJob.status === "QUEUED" || fullJob.status === "PROCESSING") {
            startPolling(fullJob.id);
          }
        }
      } else {
        setActiveJob(null);
      }
    } catch (err) {
      console.warn("Failed to retrieve analysis job history:", err);
    } finally {
      setLoadingJob(false);
    }
  }, [evidenceId, startPolling]);

  useEffect(() => {
    loadEvidence();
    loadLatestJob();

    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [loadEvidence, loadLatestJob]);

  // Trigger analysis execution
  const handleTriggerAnalysis = async () => {
    setSubmittingJob(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      const resp = await createAnalysisJob({
        evidence_id: evidenceId,
        analysis_type: "JPEG_ELA",
        parameters: {
          recompression_quality: qualitySetting,
          amplification_scale: amplificationScale,
        },
        examiner_notes: `Manual analysis requested at quality=${qualitySetting}, scale=${amplificationScale}`,
      });

      setActionSuccess(`Analysis job ${resp.status.toLowerCase()}: ID ${resp.analysis_id.slice(0, 8)}...`);
      startPolling(resp.analysis_id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to trigger image analysis task.");
    } finally {
      setSubmittingJob(false);
    }
  };

  // Re-verify cryptographic hash
  const handleVerifyHash = async () => {
    setVerifyingHash(true);
    setVerificationError(null);
    try {
      const res = await verifyEvidenceHash(caseId, evidenceId, "MANUAL");
      setVerificationResult(res);
    } catch (err) {
      setVerificationError(err instanceof Error ? err.message : "Cryptographic hash verification failed.");
    } finally {
      setVerifyingHash(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  // Extract structured summary from job
  const summary: ImageAnalysisSummary | undefined = activeJob?.summary_results as ImageAnalysisSummary | undefined;
  const imageProps = summary?.image_properties;
  const elaResult = summary?.ela;
  const limitations = summary?.limitations || [];
  const findings: FindingItem[] = activeJob?.findings || [];

  // Find heatmap artifact
  const heatmapArtifact = activeJob?.artifacts?.find(
    (a) => a.artifact_type === "ELA_HEATMAP"
  );

  const originalImageUrl = evidence ? getEvidenceContentUrl(caseId, evidenceId) : "";
  const heatmapImageUrl = heatmapArtifact ? getArtifactContentUrl(heatmapArtifact.id) : "";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Breadcrumb & Navigation Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-20 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href={`/cases/${caseId}/evidence/${evidenceId}`}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              title="Return to Evidence Detail"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                <span>CASES</span>
                <span>/</span>
                <span className="text-cyan-400">{caseId.slice(0, 8)}...</span>
                <span>/</span>
                <span>EVIDENCE</span>
                <span>/</span>
                <span className="text-cyan-400">{evidence?.evidence_number || evidenceId.slice(0, 8)}</span>
              </div>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                <FileImage className="w-5 h-5 text-indigo-400" />
                Image Forensics & Error Level Analysis (ELA)
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                loadEvidence();
                loadLatestJob();
              }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-750 text-xs font-medium text-slate-300 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isPolling || loadingJob || loadingEvidence ? "animate-spin text-cyan-400" : ""}`} />
              Refresh
            </button>
            <Link
              href="/analysis"
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition-colors"
            >
              Task Queue
            </Link>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Alerts / Notifications */}
        {evidenceError && (
          <div className="p-4 rounded-xl bg-rose-950/70 border border-rose-600/40 text-rose-300 flex items-center justify-between text-sm animate-in fade-in">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{evidenceError}</span>
            </div>
          </div>
        )}
        {actionSuccess && (
          <div className="p-4 rounded-xl bg-emerald-950/70 border border-emerald-600/40 text-emerald-300 flex items-center justify-between text-sm animate-in fade-in">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{actionSuccess}</span>
            </div>
            <button onClick={() => setActionSuccess(null)} className="text-emerald-400 hover:text-emerald-200 text-xs font-mono">
              Dismiss
            </button>
          </div>
        )}
        {actionError && (
          <div className="p-4 rounded-xl bg-rose-950/70 border border-rose-600/40 text-rose-300 flex items-center justify-between text-sm animate-in fade-in">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{actionError}</span>
            </div>
            <button onClick={() => setActionError(null)} className="text-rose-400 hover:text-rose-200 text-xs font-mono">
              Dismiss
            </button>
          </div>
        )}

        {/* 1. Header Overview & Job Status Banner */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-950/80 border border-indigo-700/50 text-indigo-300">
                  {evidence?.media_type || "IMAGE"}
                </span>
                <span className="font-mono text-xs text-slate-400">
                  {evidence?.original_filename}
                </span>
                <span className="text-slate-600">•</span>
                <span className="text-xs text-slate-400 font-mono">
                  {evidence ? `${(evidence.file_size_bytes / 1024).toFixed(1)} KB` : "..."}
                </span>
              </div>
              <h2 className="text-lg font-semibold text-white">
                {activeJob ? `Forensic Job: ${activeJob.analysis_type}` : "No Analysis Job Recorded"}
              </h2>
              <p className="text-xs text-slate-400">
                Non-destructive discrete cosine transform error quantization analysis and technical image profiling.
              </p>
            </div>

            {/* Execution Controls & Status */}
            <div className="flex flex-wrap items-center gap-4">
              {activeJob && (
                <div className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-950/70 border border-slate-800 text-xs">
                  <span className="text-slate-400 font-mono">STATUS:</span>
                  <span
                    className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
                      activeJob.status === "COMPLETED"
                        ? "bg-emerald-950 border border-emerald-600/40 text-emerald-400"
                        : activeJob.status === "PROCESSING"
                        ? "bg-amber-950 border border-amber-600/40 text-amber-400 animate-pulse"
                        : activeJob.status === "FAILED"
                        ? "bg-rose-950 border border-rose-600/40 text-rose-400"
                        : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {activeJob.status}
                  </span>
                  {isPolling && (
                    <span className="flex h-2 w-2 relative ml-1">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                    </span>
                  )}
                </div>
              )}

              {/* Quality & Scale Selector */}
              <div className="flex items-center gap-2 bg-slate-950/70 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
                <span className="text-slate-400 font-mono">Recompress Q:</span>
                <select
                  value={qualitySetting}
                  onChange={(e) => setQualitySetting(Number(e.target.value))}
                  className="bg-slate-900 border border-slate-700 text-slate-200 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                >
                  <option value={95}>95 (Standard)</option>
                  <option value={90}>90</option>
                  <option value={85}>85</option>
                  <option value={80}>80</option>
                </select>

                <span className="text-slate-400 font-mono ml-2">Scale:</span>
                <select
                  value={amplificationScale}
                  onChange={(e) => setAmplificationScale(Number(e.target.value))}
                  className="bg-slate-900 border border-slate-700 text-slate-200 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                >
                  <option value={15}>15x (Default)</option>
                  <option value={10}>10x</option>
                  <option value={20}>20x</option>
                  <option value={25}>25x</option>
                </select>
              </div>

              <button
                onClick={handleTriggerAnalysis}
                disabled={submittingJob || isPolling}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-medium text-xs shadow-lg shadow-indigo-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submittingJob ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Enqueuing...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    {activeJob ? "Re-Run Analysis" : "Run Image Analysis"}
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Job Provenance Bar */}
          {activeJob && (
            <div className="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-xs font-mono text-slate-400">
              <div>
                <span className="text-slate-500 block">JOB ID:</span>
                <span className="text-slate-200">{activeJob.job_id?.slice(0, 10) || activeJob.id.slice(0, 10)}</span>
              </div>
              <div>
                <span className="text-slate-500 block">WORKER:</span>
                <span className="text-slate-200">{activeJob.worker_id || "rq-worker"}</span>
              </div>
              <div>
                <span className="text-slate-500 block">ATTEMPTS:</span>
                <span className="text-slate-200">{activeJob.attempt_count} / {activeJob.max_retries}</span>
              </div>
              <div>
                <span className="text-slate-500 block">DURATION:</span>
                <span className="text-slate-200">
                  {summary?.execution_duration_ms ? `${summary.execution_duration_ms} ms` : "—"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">COMPLETED:</span>
                <span className="text-slate-200">
                  {activeJob.completed_at ? new Date(activeJob.completed_at).toLocaleTimeString() : "In Progress"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">ENGINE:</span>
                <span className="text-cyan-400">
                  PIL {summary?.pillow_version || "13.0"} / CV {summary?.opencv_version || "4.8"}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* 2. Cryptographic Intake Hash Display & Live Verification */}
        <section className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-lg backdrop-blur">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
                  Cryptographic Intake Hash Baseline
                </h3>
              </div>
              <p className="text-xs text-slate-400">
                Authoritative reference hash registered at evidence intake. Verification confirms the stored vault bytes match bit-for-bit without alteration.
              </p>
            </div>

            <button
              onClick={handleVerifyHash}
              disabled={verifyingHash}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-emerald-600/40 bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-300 text-xs font-mono font-medium transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${verifyingHash ? "animate-spin text-emerald-400" : ""}`} />
              {verifyingHash ? "Verifying Stored Bytes..." : "Verify Current Hash"}
            </button>
          </div>

          <div className="mt-4 p-3.5 bg-slate-950/80 rounded-xl border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 font-mono text-xs">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <span className="text-slate-500 font-semibold flex-shrink-0">SHA-256 (INTAKE):</span>
              <span className="text-emerald-400 truncate select-all">
                {evidence?.primary_hash_sha256 || "Calculating baseline..."}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => evidence && copyToClipboard(evidence.primary_hash_sha256)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                title="Copy full hash"
              >
                {copiedHash ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedHash ? "Copied" : "Copy"}</span>
              </button>
            </div>
          </div>

          {/* Verification Audit Result Badge */}
          {verificationResult && (
            <div
              className={`mt-3 p-3.5 rounded-xl border flex items-center justify-between gap-4 text-xs font-mono ${
                verificationResult.is_intact
                  ? "bg-emerald-950/50 border-emerald-600/40 text-emerald-300"
                  : "bg-rose-950/50 border-rose-600/40 text-rose-300"
              }`}
            >
              <div className="flex items-center gap-2">
                {verificationResult.is_intact ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                ) : (
                  <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" />
                )}
                <span>
                  {verificationResult.is_intact
                    ? "LIVE AUDIT PASSED: Stored bitstream in vault exactly matches the reference SHA-256."
                    : "TAMPER DETECTED: Stored bitstream diverges from reference SHA-256 baseline!"}
                </span>
              </div>
              <span className="text-slate-400 flex-shrink-0">
                Verified: {new Date(verificationResult.verified_at).toLocaleTimeString()}
              </span>
            </div>
          )}
          {verificationError && (
            <div className="mt-3 p-3 rounded-xl bg-rose-950/50 border border-rose-600/40 text-rose-300 text-xs font-mono">
              Verification Error: {verificationError}
            </div>
          )}
        </section>

        {/* 3. Non-JPEG Applicability Notice (if format is not JPEG) */}
        {elaResult && !elaResult.is_applicable && (
          <section className="bg-amber-950/40 border border-amber-600/40 rounded-2xl p-5 text-amber-200">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <h4 className="font-semibold text-sm text-amber-100 uppercase tracking-wide">
                  Format Notice: ELA Not Applicable for {imageProps?.format || "Non-JPEG"} Media
                </h4>
                <p className="text-xs leading-relaxed text-amber-200/90">
                  {elaResult.inapplicability_reason ||
                    "Error Level Analysis operates by measuring the quantization variance across 8x8 discrete cosine transform (DCT) blocks introduced during lossy JPEG recompression. Formats such as PNG, BMP, GIF, and TIFF utilize lossless compression or alternative algorithms where JPEG DCT quantization error cannot be mathematically evaluated."}
                </p>
              </div>
            </div>
          </section>
        )}

        {/* 4. Dual Image Visualizer & ELA Heatmap Comparison */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Layers className="w-5 h-5 text-cyan-400" />
                Visual Comparison & Artifact Inspector
              </h3>
              <p className="text-xs text-slate-400">
                Interactive comparison of evidentiary source bitstream and derivative ELA heatmap artifact.
              </p>
            </div>

            {/* View Mode Controls */}
            {heatmapArtifact && (
              <div className="flex items-center gap-2 bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
                <button
                  onClick={() => setViewMode("side-by-side")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    viewMode === "side-by-side" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Side-by-Side
                </button>
                <button
                  onClick={() => setViewMode("blend")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    viewMode === "blend" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Overlay Blend
                </button>
                <button
                  onClick={() => setViewMode("heatmap")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    viewMode === "heatmap" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Heatmap Only
                </button>
                <button
                  onClick={() => setViewMode("original")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                    viewMode === "original" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  Original Only
                </button>
              </div>
            )}
          </div>

          {/* Opacity slider for blend mode */}
          {viewMode === "blend" && heatmapArtifact && (
            <div className="flex items-center gap-4 bg-slate-950/60 p-3 rounded-xl border border-slate-800 text-xs font-mono">
              <span className="text-slate-400 flex items-center gap-1.5 flex-shrink-0">
                <Sliders className="w-4 h-4 text-cyan-400" />
                Heatmap Opacity:
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={blendOpacity}
                onChange={(e) => setBlendOpacity(Number(e.target.value))}
                className="flex-1 accent-cyan-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-cyan-400 font-bold w-12 text-right">{blendOpacity}%</span>
            </div>
          )}

          {/* Viewer Display Frame */}
          <div className="relative min-h-[380px] rounded-xl bg-slate-950 border border-slate-800/80 p-4 flex items-center justify-center overflow-hidden">
            {/* View Mode: Side by Side */}
            {viewMode === "side-by-side" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
                {/* Left: Original Preview */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
                    <span className="flex items-center gap-1.5 text-slate-300 font-semibold">
                      <Eye className="w-3.5 h-3.5 text-indigo-400" />
                      Original Evidentiary Bitstream
                    </span>
                    <span>Format: {imageProps?.format || "JPEG"}</span>
                  </div>
                  <div className="aspect-video w-full rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center overflow-hidden relative group">
                    {originalImageUrl ? (
                      <img
                        src={originalImageUrl}
                        alt="Original evidentiary media"
                        className="max-h-[360px] max-w-full object-contain"
                      />
                    ) : (
                      <span className="text-xs text-slate-500 font-mono">Loading original media...</span>
                    )}
                  </div>
                </div>

                {/* Right: Heatmap Preview */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400 px-1">
                    <span className="flex items-center gap-1.5 text-cyan-300 font-semibold">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                      ELA Heatmap Artifact (OpenCV Jet)
                    </span>
                    <span>Q={elaResult?.recompression_quality || 95} / Scale={elaResult?.amplification_scale || 15}x</span>
                  </div>
                  <div className="aspect-video w-full rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center overflow-hidden relative">
                    {heatmapImageUrl ? (
                      <img
                        src={heatmapImageUrl}
                        alt="ELA Heatmap Artifact"
                        className="max-h-[360px] max-w-full object-contain"
                      />
                    ) : (
                      <div className="text-center p-6 space-y-2 text-slate-500 text-xs font-mono">
                        <AlertTriangle className="w-6 h-6 mx-auto text-slate-600" />
                        <p>
                          {elaResult && !elaResult.is_applicable
                            ? "Heatmap not applicable for non-JPEG bitstreams."
                            : "Heatmap artifact will be generated upon analysis execution."}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* View Mode: Blend Overlay */}
            {viewMode === "blend" && heatmapArtifact && (
              <div className="relative w-full max-h-[500px] flex items-center justify-center">
                {originalImageUrl && (
                  <img
                    src={originalImageUrl}
                    alt="Original layer"
                    className="max-h-[480px] max-w-full object-contain rounded-xl"
                  />
                )}
                {heatmapImageUrl && (
                  <img
                    src={heatmapImageUrl}
                    alt="Heatmap overlay layer"
                    style={{ opacity: blendOpacity / 100 }}
                    className="absolute max-h-[480px] max-w-full object-contain rounded-xl transition-opacity pointer-events-none"
                  />
                )}
              </div>
            )}

            {/* View Mode: Original Only */}
            {viewMode === "original" && originalImageUrl && (
              <div className="w-full flex items-center justify-center">
                <img
                  src={originalImageUrl}
                  alt="Original evidentiary media"
                  className="max-h-[500px] max-w-full object-contain rounded-xl"
                />
              </div>
            )}

            {/* View Mode: Heatmap Only */}
            {viewMode === "heatmap" && heatmapImageUrl && (
              <div className="w-full flex items-center justify-center">
                <img
                  src={heatmapImageUrl}
                  alt="Heatmap artifact"
                  className="max-h-[500px] max-w-full object-contain rounded-xl"
                />
              </div>
            )}
          </div>

          {/* Artifact Download & Metadata Bar */}
          {heatmapArtifact && (
            <div className="p-3 bg-slate-950/70 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs font-mono text-slate-400">
              <div className="flex items-center gap-3">
                <span className="text-slate-500 font-semibold">ARTIFACT KEY:</span>
                <span className="text-slate-300">{heatmapArtifact.file_name}</span>
                <span className="text-slate-600">•</span>
                <span className="text-cyan-400">{heatmapArtifact.hash_sha256.slice(0, 16)}...</span>
              </div>
              <a
                href={heatmapImageUrl}
                download={heatmapArtifact.file_name}
                className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download Heatmap PNG
              </a>
            </div>
          )}
        </section>

        {/* 5. Image Properties & Technical Metadata Grid */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-3 mb-4">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">Physical & Geometric Image Properties</h3>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">FORMAT</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.format || evidence?.mime_type || "JPEG"}</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">DIMENSIONS</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.dimensions || "—"}</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">ASPECT RATIO</span>
              <span className="text-slate-200 font-bold text-sm">
                {imageProps?.aspect_ratio || "—"} ({imageProps?.aspect_ratio_float || "—"})
              </span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">COLOR MODE</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.color_mode || "RGB"}</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">CHANNELS</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.channels || 3} channels</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">COLOR DEPTH</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.color_depth_bits || 24}-bit total</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">ALPHA CHANNEL</span>
              <span className="text-slate-200 font-bold text-sm">{imageProps?.has_alpha ? "Present" : "None"}</span>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-slate-500 block mb-1">OPENCV MATRIX SHAPE</span>
              <span className="text-slate-200 font-bold text-sm">
                {imageProps?.opencv_shape ? imageProps.opencv_shape.join(" × ") : "—"}
              </span>
            </div>
          </div>

          {/* ELA Statistical Quantization Disparity Table */}
          {elaResult && elaResult.is_applicable && (
            <div className="mt-4 pt-4 border-t border-slate-800">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-cyan-400" />
                Quantization Error Statistics (NumPy)
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs font-mono">
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <span className="text-slate-500 block">MEAN ERROR</span>
                  <span className="text-cyan-400 font-bold">{elaResult.mean_error ?? "—"}</span>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <span className="text-slate-500 block">STD DEV</span>
                  <span className="text-cyan-400 font-bold">{elaResult.std_error ?? "—"}</span>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <span className="text-slate-500 block">MAX ERROR</span>
                  <span className="text-cyan-400 font-bold">{elaResult.max_error ?? "—"}</span>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <span className="text-slate-500 block">MIN ERROR</span>
                  <span className="text-cyan-400 font-bold">{elaResult.min_error ?? "—"}</span>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <span className="text-slate-500 block">DISPARITY RATIO</span>
                  <span className="text-cyan-400 font-bold">
                    {elaResult.high_disparity_ratio != null
                      ? `${(elaResult.high_disparity_ratio * 100).toFixed(1)}%`
                      : "—"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* 6. Structured Forensic Observations & Findings */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              Forensic Observations & Structured Findings ({findings.length})
            </h3>
            <span className="text-xs font-mono text-slate-400">PostgreSQL Authoritative</span>
          </div>

          {findings.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-xs font-mono">
              No findings recorded. Execute image analysis to generate structured observations.
            </div>
          ) : (
            <div className="space-y-3">
              {findings.map((f, idx) => {
                const isDisparity = f.finding_type === "ELA_DISPARITY";
                const isTamper = f.finding_type === "HASH_TAMPER";
                return (
                  <div
                    key={f.id || idx}
                    className={`p-4 rounded-xl border bg-slate-950/60 transition-all ${
                      isTamper
                        ? "border-rose-600/50 bg-rose-950/20"
                        : isDisparity
                        ? "border-indigo-600/40"
                        : "border-slate-800"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                            f.severity === "CRITICAL"
                              ? "bg-rose-950 border border-rose-600/40 text-rose-400"
                              : f.severity === "MEDIUM"
                              ? "bg-amber-950 border border-amber-600/40 text-amber-400"
                              : f.severity === "LOW"
                              ? "bg-cyan-950 border border-cyan-600/40 text-cyan-400"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {f.severity}
                        </span>
                        <span className="text-xs font-bold text-white">{f.title}</span>
                      </div>
                      <div className="text-[11px] font-mono text-slate-500">
                        Confidence: {(f.confidence_score * 100).toFixed(0)}%
                      </div>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">{f.description}</p>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 7. Evidentiary Limitations & Legal Safeguards */}
        <section className="bg-slate-900/60 border border-indigo-900/40 rounded-2xl p-6 shadow-xl backdrop-blur space-y-3">
          <div className="flex items-center gap-2 text-indigo-400">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-indigo-200">
              Evidentiary Limitations & Forensic Guidelines
            </h3>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Forensic analysis heuristics require strict interpretative rigor. ELA cannot be used in isolation as courtroom proof of forgery.
          </p>

          {limitations.length > 0 && (
            <div className="p-3.5 bg-amber-950/30 rounded-xl border border-amber-800/40 space-y-1.5">
              <span className="font-semibold text-amber-300 block text-xs flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5" />
                Automated System Limitations & Disclaimers:
              </span>
              <ul className="list-disc pl-5 space-y-1 text-slate-300 text-xs">
                {limitations.map((lim, idx) => (
                  <li key={idx} className="leading-relaxed">{lim}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 text-xs text-slate-300">
            <div className="p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1">
              <span className="font-semibold text-indigo-300 block">
                Do Not Label Manipulated Solely on Brightness:
              </span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                High-contrast boundaries, structural edges, fine textures, and text inherently compress with elevated DCT quantization error and will naturally display as bright regions in 100% genuine images.
              </p>
            </div>
            <div className="p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1">
              <span className="font-semibold text-indigo-300 block">
                Absence of Error in Flat Regions:
              </span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Low-frequency zones (e.g. flat sky or monochrome backdrops) undergo minimal quantization error and naturally appear dark regardless of authenticity.
              </p>
            </div>
            <div className="p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1">
              <span className="font-semibold text-indigo-300 block">
                Multi-Generation Resave Flattening:
              </span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Multiple successive saves equalize error levels across the frame, progressively attenuating distinct error level boundaries.
              </p>
            </div>
            <div className="p-3.5 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1">
              <span className="font-semibold text-indigo-300 block">
                Corroborating Metadata Required:
              </span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Observations must be correlated with camera quantization matrices, EXIF MakerNotes, clone-detection algorithms, and physical chain of custody.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
