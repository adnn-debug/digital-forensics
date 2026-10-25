"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  Microscope,
  RotateCcw,
  Play,
  CheckCircle2,
  AlertCircle,
  Clock,
  Cpu,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import {
  listCases,
  listCaseEvidence,
  createAnalysisJob,
  getAnalysisJob,
  getAnalysisHistory,
  retryAnalysisJob,
  CaseItem,
  EvidenceItem,
  ForensicAnalysisJob,
} from "@/lib/api";

export default function AnalysisPage(): React.JSX.Element {
  // State for cases & evidence selector
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string>("");

  // Job Submission Form State
  const [analysisType, setAnalysisType] = useState<string>("TEST_ANALYSIS");
  const [idempotencyKey, setIdempotencyKey] = useState<string>("");
  const [simulateDelay, setSimulateDelay] = useState<number>(0);
  const [simulateFailure, setSimulateFailure] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Active Job Polling
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ForensicAnalysisJob | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // History State
  const [historyJobs, setHistoryJobs] = useState<ForensicAnalysisJob[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Load initial cases and history
  useEffect(() => {
    loadCases();
    loadHistory();
  }, [statusFilter]);

  // Load evidence when case changes
  useEffect(() => {
    if (selectedCaseId) {
      loadEvidence(selectedCaseId);
    } else {
      setEvidenceList([]);
      setSelectedEvidenceId("");
    }
  }, [selectedCaseId]);

  // Handle active job polling
  useEffect(() => {
    if (!activeJobId) return;

    let isSubscribed = true;
    setIsPolling(true);

    const pollJob = async () => {
      try {
        const jobData = await getAnalysisJob(activeJobId);
        if (!isSubscribed) return;
        setActiveJob(jobData);

        // Stop polling if completed, failed, or skipped
        if (
          jobData.status === "COMPLETED" ||
          jobData.status === "FAILED" ||
          jobData.status === "SKIPPED"
        ) {
          setIsPolling(false);
          loadHistory(); // refresh history once complete
          return;
        }

        // Schedule next poll
        pollTimerRef.current = setTimeout(pollJob, 2000);
      } catch (err) {
        if (!isSubscribed) return;
        console.warn("Polling error for job:", err);
        setIsPolling(false);
      }
    };

    pollJob();

    return () => {
      isSubscribed = false;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [activeJobId]);

  const loadCases = async () => {
    try {
      const res = await listCases(1, 50);
      setCases(res.items || []);
      const firstCase = res.items && res.items.length > 0 ? res.items[0] : null;
      if (firstCase && !selectedCaseId) {
        setSelectedCaseId(firstCase.id);
      }
    } catch (err) {
      console.warn("Failed to load cases:", err);
    }
  };

  const loadEvidence = async (caseId: string) => {
    try {
      const list = await listCaseEvidence(caseId);
      setEvidenceList(list || []);
      const firstEvidence = list && list.length > 0 ? list[0] : null;
      if (firstEvidence) {
        setSelectedEvidenceId(firstEvidence.id);
      } else {
        setSelectedEvidenceId("");
      }
    } catch (err) {
      console.warn("Failed to load evidence:", err);
      setEvidenceList([]);
    }
  };

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await getAnalysisHistory({
        status: statusFilter || undefined,
        page_size: 20,
      });
      setHistoryJobs(res.items || []);
    } catch (err) {
      console.warn("Failed to load analysis history:", err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleLaunchJob = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEvidenceId) {
      setActionError("Please select a valid evidence item to analyze.");
      return;
    }

    setSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      const params: Record<string, any> = {};
      if (simulateDelay > 0) params["simulate_delay"] = simulateDelay;
      if (simulateFailure) params["simulate_failure"] = simulateFailure;

      const res = await createAnalysisJob({
        evidence_id: selectedEvidenceId,
        analysis_type: analysisType,
        parameters: Object.keys(params).length > 0 ? params : undefined,
        idempotency_key: idempotencyKey.trim() || undefined,
      });


      setActionSuccess(`Job dispatched! Transport ID: ${res.job_id}`);
      setActiveJobId(res.analysis_id);
      loadHistory();
    } catch (err: any) {
      setActionError(err.message || "Failed to schedule analysis job.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = async (analysisId: string) => {
    try {
      setActionError(null);
      const res = await retryAnalysisJob(analysisId);
      setActionSuccess(`Job re-enqueued: ${res.job_id}`);
      setActiveJobId(res.analysis_id);
      loadHistory();
    } catch (err: any) {
      setActionError(err.message || "Retry failed");
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "QUEUED":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3 animate-pulse" />
            <span>QUEUED</span>
          </span>
        );
      case "PROCESSING":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            <RefreshCw className="w-3 h-3 animate-spin text-cyan-400" />
            <span>PROCESSING</span>
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" />
            <span>COMPLETED</span>
          </span>
        );
      case "FAILED":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <AlertCircle className="w-3 h-3" />
            <span>FAILED</span>
          </span>
        );
      case "SKIPPED":
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-500/10 text-slate-300 border border-slate-500/30">
            <span>SKIPPED</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-forensic-800 text-forensic-300">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-forensic-900 via-forensic-850 to-forensic-900 border border-forensic-700/80 p-6 sm:p-8 shadow-2xl">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-integrity-teal/10 border border-integrity-teal/30 text-integrity-teal text-xs font-mono mb-3">
              <Cpu className="w-3.5 h-3.5" />
              <span>Durable Worker Fleet & Redis Task Queue</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Forensic Analysis Orchestration
            </h1>
            <p className="mt-1 text-sm text-forensic-300 max-w-3xl">
              Decoupled background task execution with Redis queue buffering, PostgreSQL authoritative state persistence, bounded transient retries, crash recovery, and idempotent findings deduplication.
            </p>
          </div>
          <button
            onClick={loadHistory}
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-xs font-mono text-forensic-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingHistory ? "animate-spin" : ""}`} />
            <span>Refresh History</span>
          </button>
        </div>
      </div>

      {actionError && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-3">
          <ShieldAlert className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center space-x-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Grid: Dispatcher + Active Job Monitor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Job Dispatcher */}
        <div className="lg:col-span-5 space-y-6">
          <div className="rounded-xl bg-forensic-900 border border-forensic-800 p-6 shadow-lg space-y-5">
            <div className="flex items-center space-x-3 pb-3 border-b border-forensic-800">
              <div className="p-2 rounded-lg bg-integrity-teal/10 border border-integrity-teal/30 text-integrity-teal">
                <Play className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white tracking-tight">
                  Enqueue Forensic Analysis
                </h2>
                <p className="text-xs text-forensic-400">
                  Non-blocking job submission with idempotency protection.
                </p>
              </div>
            </div>

            <form onSubmit={handleLaunchJob} className="space-y-4">
              {/* Select Case */}
              <div className="space-y-1.5">
                <label className="text-xs font-mono text-forensic-300">Target Case</label>
                <select
                  value={selectedCaseId}
                  onChange={(e) => setSelectedCaseId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-forensic-850 border border-forensic-700 text-xs text-forensic-100 font-mono focus:outline-none focus:border-integrity-teal"
                >
                  {cases.length === 0 && <option value="">No cases registered</option>}
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.case_number} — {c.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Select Evidence Item */}
              <div className="space-y-1.5">
                <label className="text-xs font-mono text-forensic-300">Evidence Bitstream</label>
                <select
                  value={selectedEvidenceId}
                  onChange={(e) => setSelectedEvidenceId(e.target.value)}
                  disabled={evidenceList.length === 0}
                  className="w-full px-3 py-2 rounded-lg bg-forensic-850 border border-forensic-700 text-xs text-forensic-100 font-mono focus:outline-none focus:border-integrity-teal disabled:opacity-50"
                >
                  {evidenceList.length === 0 && (
                    <option value="">No evidence items found for this case</option>
                  )}
                  {evidenceList.map((item) => (
                    <option key={item.id} value={item.id}>
                      [{item.media_type}] {item.evidence_number} — {item.original_filename}
                    </option>
                  ))}
                </select>
              </div>

              {/* Analysis Heuristic */}
              <div className="space-y-1.5">
                <label className="text-xs font-mono text-forensic-300">Analysis Heuristic</label>
                <select
                  value={analysisType}
                  onChange={(e) => setAnalysisType(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-forensic-850 border border-forensic-700 text-xs text-forensic-100 font-mono focus:outline-none focus:border-integrity-teal"
                >
                  <option value="TEST_ANALYSIS">TEST_ANALYSIS (Verified Test Pass Heuristic)</option>
                  <option value="METADATA_EXTRACTION">METADATA_EXTRACTION (ExifTool / FFprobe)</option>
                  <option value="JPEG_ELA">JPEG_ELA (Compression Disparity)</option>
                  <option value="VIDEO_FRAMES">VIDEO_FRAMES (Temporal Analysis)</option>
                  <option value="AUDIO_SPECTROGRAM">AUDIO_SPECTROGRAM (STFT Spectral Verification)</option>
                </select>
              </div>

              {/* Idempotency Key */}
              <div className="space-y-1.5">
                <label className="text-xs font-mono text-forensic-300 flex items-center justify-between">
                  <span>Idempotency Key (Optional)</span>
                  <span className="text-[10px] text-forensic-500">Duplicate Guard</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. IDEMP-2026-CASE01-ITEM01"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-forensic-850 border border-forensic-700 text-xs text-forensic-100 font-mono focus:outline-none focus:border-integrity-teal"
                />
              </div>

              {/* Fault Injection / Simulation Testing */}
              <div className="pt-2 border-t border-forensic-800 space-y-3">
                <span className="text-[11px] font-mono text-forensic-400 block font-semibold">
                  Queue Resilience Test Parameters
                </span>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] font-mono text-forensic-400 block mb-1">
                      Simulate Delay (sec)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={15}
                      step={0.5}
                      value={simulateDelay}
                      onChange={(e) => setSimulateDelay(parseFloat(e.target.value) || 0)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-forensic-850 border border-forensic-700 text-xs font-mono text-white"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-forensic-400 block mb-1">
                      Simulated Fault
                    </label>
                    <select
                      value={simulateFailure}
                      onChange={(e) => setSimulateFailure(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-forensic-850 border border-forensic-700 text-xs font-mono text-white"
                    >
                      <option value="">None (Pass)</option>
                      <option value="transient">Transient Error (Retries)</option>
                      <option value="permanent">Fatal Error (Immediate Fail)</option>
                    </select>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting || !selectedEvidenceId}
                className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-integrity-teal to-integrity-emerald hover:opacity-95 text-xs font-mono font-bold text-forensic-950 transition-opacity flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Enqueuing Job...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    <span>Dispatch Asynchronous Task</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Column: Live Job Polling Monitor */}
        <div className="lg:col-span-7 space-y-6">
          <div className="rounded-xl bg-forensic-900 border border-forensic-800 p-6 shadow-lg space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-forensic-800">
              <div className="flex items-center space-x-3">
                <div className="p-2 rounded-lg bg-integrity-cyan/10 border border-integrity-cyan/30 text-integrity-cyan">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white tracking-tight">
                    Authoritative PostgreSQL State Monitor
                  </h2>
                  <p className="text-xs text-forensic-400">
                    Live polling & diagnostic verification from database.
                  </p>
                </div>
              </div>
              {isPolling && (
                <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/30">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  <span>Polling Active Job</span>
                </div>
              )}
            </div>

            {activeJob ? (
              <div className="space-y-4 pt-1">
                {/* Status Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-forensic-850/70 border border-forensic-750">
                  <div className="flex items-center space-x-3">
                    <span className="text-xs text-forensic-400 font-mono">Current Status:</span>
                    {getStatusBadge(activeJob.status)}
                  </div>
                  <div className="flex items-center space-x-2 text-xs font-mono text-forensic-300">
                    <span>Attempts:</span>
                    <span className="px-2 py-0.5 rounded bg-forensic-800 border border-forensic-700 text-white font-bold">
                      {activeJob.attempt_count} / {activeJob.max_retries}
                    </span>
                  </div>
                </div>

                {/* Job Metadata Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs font-mono">
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Analysis UUID</span>
                    <span className="text-forensic-200 truncate block mt-0.5">{activeJob.id}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Transport Job ID</span>
                    <span className="text-forensic-200 truncate block mt-0.5">{activeJob.job_id || "N/A"}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Worker Fleet Node</span>
                    <span className="text-forensic-200 truncate block mt-0.5">{activeJob.worker_id || "Unassigned"}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Queued At</span>
                    <span className="text-forensic-200 block mt-0.5">{new Date(activeJob.created_at).toLocaleTimeString()}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Started At</span>
                    <span className="text-forensic-200 block mt-0.5">
                      {activeJob.started_at ? new Date(activeJob.started_at).toLocaleTimeString() : "Pending"}
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-forensic-850/50 border border-forensic-800">
                    <span className="text-forensic-400 block text-[10px] uppercase">Completed At</span>
                    <span className="text-forensic-200 block mt-0.5">
                      {activeJob.completed_at ? new Date(activeJob.completed_at).toLocaleTimeString() : "In Flight"}
                    </span>
                  </div>
                </div>

                {/* Error diagnostics banner if failed */}
                {activeJob.error_code && (
                  <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono space-y-1">
                    <div className="font-bold flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 text-rose-400" />
                      <span>Error Code: {activeJob.error_code}</span>
                    </div>
                    <p className="text-forensic-300 text-[11px] pl-6">{activeJob.error_message}</p>
                    {activeJob.status === "FAILED" && (
                      <div className="pt-2 pl-6">
                        <button
                          onClick={() => handleRetry(activeJob.id)}
                          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded bg-rose-600/30 hover:bg-rose-600/50 border border-rose-500 text-xs text-white"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Retry Interrupted Task</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Summary Results */}
                {activeJob.summary_results && (
                  <div className="space-y-2">
                    <span className="text-xs font-mono text-forensic-300 font-semibold block">
                      Execution Results (PostgreSQL Persisted)
                    </span>
                    <pre className="p-3 rounded-lg bg-forensic-950 border border-forensic-800 text-[11px] font-mono text-emerald-400 overflow-x-auto max-h-40">
                      {JSON.stringify(activeJob.summary_results, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Deduplicated Findings */}
                {activeJob.findings && activeJob.findings.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-xs font-mono text-forensic-300 font-semibold block">
                      Forensic Findings ({activeJob.findings.length} record - Cleanly Deduplicated)
                    </span>
                    <div className="space-y-2">
                      {activeJob.findings.map((f) => (
                        <div
                          key={f.id}
                          className="p-3 rounded-lg bg-forensic-850/60 border border-forensic-750 text-xs font-mono space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-white">{f.title}</span>
                            <span className="px-1.5 py-0.5 rounded bg-integrity-teal/10 text-integrity-teal text-[10px]">
                              {f.severity}
                            </span>
                          </div>
                          <p className="text-forensic-400 text-[11px]">{f.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-12 text-center text-forensic-500 text-xs font-mono space-y-2">
                <Microscope className="w-8 h-8 mx-auto text-forensic-600" />
                <p>No active job selected. Dispatch a task above or select from history.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Analysis History Section */}
      <div className="rounded-xl bg-forensic-900 border border-forensic-800 p-6 shadow-lg space-y-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-3 border-b border-forensic-800">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">
              Analysis Execution History
            </h2>
            <p className="text-xs text-forensic-400">
              Complete audit ledger of background forensic tasks.
            </p>
          </div>

          {/* Status Filter */}
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono text-forensic-400">Filter:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-forensic-850 border border-forensic-700 text-xs text-white font-mono focus:outline-none"
            >
              <option value="">All States</option>
              <option value="QUEUED">QUEUED</option>
              <option value="PROCESSING">PROCESSING</option>
              <option value="COMPLETED">COMPLETED</option>
              <option value="FAILED">FAILED</option>
              <option value="SKIPPED">SKIPPED</option>
            </select>
          </div>
        </div>

        {/* History Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-forensic-850/80 text-forensic-400 uppercase text-[10px] tracking-wider border-b border-forensic-800">
              <tr>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Heuristic Type</th>
                <th className="py-3 px-4">Attempts</th>
                <th className="py-3 px-4">Error Code</th>
                <th className="py-3 px-4">Created At</th>
                <th className="py-3 px-4">Completed</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-forensic-800 text-forensic-200">
              {historyJobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-forensic-500">
                    No historical analysis jobs matching criteria.
                  </td>
                </tr>
              ) : (
                historyJobs.map((job) => (
                  <tr key={job.id} className="hover:bg-forensic-850/50 transition-colors">
                    <td className="py-3 px-4">{getStatusBadge(job.status)}</td>
                    <td className="py-3 px-4 font-bold text-white">{job.analysis_type}</td>
                    <td className="py-3 px-4">
                      {job.attempt_count} / {job.max_retries}
                    </td>
                    <td className="py-3 px-4">
                      {job.error_code ? (
                        <span className="text-rose-400 font-bold">{job.error_code}</span>
                      ) : (
                        <span className="text-forensic-500">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4">{new Date(job.created_at).toLocaleString()}</td>
                    <td className="py-3 px-4">
                      {job.completed_at ? (
                        new Date(job.completed_at).toLocaleTimeString()
                      ) : (
                        <span className="text-amber-400">In Flight</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        onClick={() => {
                          setActiveJobId(job.id);
                          setActiveJob(job);
                        }}
                        className="px-2.5 py-1 rounded bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-forensic-200 text-xs transition-colors"
                      >
                        Inspect
                      </button>
                      {job.status === "FAILED" && (
                        <button
                          onClick={() => handleRetry(job.id)}
                          className="px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/50 text-rose-300 text-xs transition-colors"
                        >
                          Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
