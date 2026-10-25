"use client";

import React, { use, useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  RefreshCw,
  Play,
  AlertCircle,
  CheckCircle2,
  Cpu,
  Activity,
  Volume2,
  Clock,
  Loader2,
  BarChart2,
  ShieldAlert,
  AlertTriangle,
  Info,
} from "lucide-react";
import {
  fetchEvidenceDetail,
  getArtifactContentUrl,
  createAnalysisJob,
  getAnalysisJob,
  getAnalysisHistory,
  EvidenceDetailItem,
  ForensicAnalysisJob,
  AudioSpectrogramResult,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ caseId: string; evidenceId: string }>;
}

export default function AudioAnalysisPage({ params }: PageProps): React.JSX.Element {
  const resolvedParams = use(params);
  const { caseId, evidenceId } = resolvedParams;

  const [evidence, setEvidence] = useState<EvidenceDetailItem | null>(null);
  const [activeJob, setActiveJob] = useState<ForensicAnalysisJob | null>(null);
  const [loadingJob, setLoadingJob] = useState(true);
  const [isPolling, setIsPolling] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [spectrogramUrl, setSpectrogramUrl] = useState<string | null>(null);
  const [waveformUrl, setWaveformUrl] = useState<string | null>(null);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const loadEvidence = useCallback(async () => {
    try {
      const data = await fetchEvidenceDetail(caseId, evidenceId);
      setEvidence(data);
    } catch {
      // ignore
    }
  }, [caseId, evidenceId]);

  const findLatestAudioJob = useCallback(async () => {
    setLoadingJob(true);
    try {
      const history = await getAnalysisHistory({ evidence_id: evidenceId, analysis_type: "AUDIO_SPECTROGRAM" });
      if (history.items.length > 0) {
        setActiveJob(history.items[0] ?? null);
      } else {
        setActiveJob(null);
      }
    } catch {
      setActiveJob(null);
    } finally {
      setLoadingJob(false);
    }
  }, [evidenceId]);

  useEffect(() => {
    loadEvidence();
    findLatestAudioJob();
  }, [loadEvidence, findLatestAudioJob]);

  useEffect(() => {
    if (!activeJob) return;
    if (activeJob.status !== "QUEUED" && activeJob.status !== "PROCESSING") return;
    let isSubscribed = true;
    setIsPolling(true);
    const poll = async () => {
      try {
        const updated = await getAnalysisJob(activeJob.id);
        if (!isSubscribed) return;
        setActiveJob(updated);
        if (updated.status === "QUEUED" || updated.status === "PROCESSING") {
          pollTimerRef.current = setTimeout(poll, 2500);
        } else {
          setIsPolling(false);
        }
      } catch {
        if (isSubscribed) setIsPolling(false);
      }
    };
    pollTimerRef.current = setTimeout(poll, 2500);
    return () => {
      isSubscribed = false;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [activeJob?.id, activeJob?.status]);

  useEffect(() => {
    if (activeJob?.status !== "COMPLETED") return;
    const results = activeJob.summary_results as AudioSpectrogramResult | null;
    if (!results) return;
    setLoadingArtifacts(true);
    const token = typeof window !== "undefined" ? localStorage.getItem("ps05_auth_token") || "" : "";
    const authHeader = { Authorization: `Bearer ${token}` };
    const tasks: Promise<void>[] = [];
    if (results.spectrogram_artifact_id) {
      tasks.push(
        fetch(getArtifactContentUrl(results.spectrogram_artifact_id), { headers: authHeader })
          .then((r) => r.blob())
          .then((b) => setSpectrogramUrl(URL.createObjectURL(b)))
          .catch(() => {})
      );
    }
    if (results.waveform_artifact_id) {
      tasks.push(
        fetch(getArtifactContentUrl(results.waveform_artifact_id), { headers: authHeader })
          .then((r) => r.blob())
          .then((b) => setWaveformUrl(URL.createObjectURL(b)))
          .catch(() => {})
      );
    }
    Promise.all(tasks).finally(() => setLoadingArtifacts(false));
  }, [activeJob?.status]);

  const handleSubmitJob = async () => {
    setSubmitting(true);
    setActionError(null);
    try {
      const res = await createAnalysisJob({ evidence_id: evidenceId, analysis_type: "AUDIO_SPECTROGRAM" });
      setActionSuccess("Audio analysis queued successfully.");
      const job = await getAnalysisJob(res.analysis_id);
      setActiveJob(job);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to queue analysis.");
    } finally {
      setSubmitting(false);
    }
  };

  const results = activeJob?.summary_results as AudioSpectrogramResult | null;

  const statusColor = (s: string) => {
    if (s === "COMPLETED") return "text-integrity-emerald";
    if (s === "PROCESSING" || s === "QUEUED") return "text-integrity-cyan";
    if (s === "FAILED") return "text-red-400";
    return "text-forensic-400";
  };

  const statusBg = (s: string) => {
    if (s === "COMPLETED") return "bg-integrity-emerald/10 border-integrity-emerald/30";
    if (s === "PROCESSING" || s === "QUEUED") return "bg-integrity-cyan/10 border-integrity-cyan/30";
    if (s === "FAILED") return "bg-red-950/50 border-red-800";
    return "bg-forensic-850 border-forensic-700";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-forensic-800">
        <div>
          <Link
            href={`/cases/${caseId}/evidence/${evidenceId}`}
            className="inline-flex items-center space-x-1.5 text-xs text-forensic-400 hover:text-white transition-colors font-mono mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Evidence Detail</span>
          </Link>
          <h2 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-3">
            <Activity className="w-6 h-6 text-integrity-cyan" />
            <span>Audio STFT Spectrogram Analysis</span>
          </h2>
          {evidence && (
            <p className="text-xs text-forensic-400 font-mono mt-0.5">
              {evidence.evidence_number} &bull; {evidence.original_filename}
            </p>
          )}
        </div>
        <button
          onClick={handleSubmitJob}
          disabled={submitting || isPolling}
          className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-lg bg-integrity-cyan text-forensic-950 font-semibold text-sm hover:bg-integrity-cyan/90 transition-all shadow disabled:opacity-50"
        >
          {submitting || isPolling ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          <span>
            {isPolling ? "Analyzing..." : submitting ? "Queuing..." : activeJob ? "Re-run Analysis" : "Run Analysis"}
          </span>
        </button>
      </div>

      {actionError && (
        <div className="flex items-start space-x-2 p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>{actionError}</span>
        </div>
      )}
      {actionSuccess && (
        <div className="flex items-center space-x-2 p-3 rounded-lg bg-integrity-emerald/10 border border-integrity-emerald/30 text-xs text-integrity-emerald">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {loadingJob ? (
        <div className="flex items-center space-x-2 text-sm text-forensic-400 font-mono animate-pulse p-6">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading analysis records...</span>
        </div>
      ) : !activeJob ? (
        <div className="py-16 text-center rounded-xl border border-dashed border-forensic-800">
          <Volume2 className="w-12 h-12 text-forensic-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">No Audio Analysis Yet</h3>
          <p className="text-sm text-forensic-400 max-w-md mx-auto mb-6">
            Run the STFT spectrogram engine to detect lossy compression artifacts, high-frequency
            cutoff signatures, amplitude clipping, and waveform anomalies.
          </p>
          <button
            onClick={handleSubmitJob}
            disabled={submitting}
            className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-lg bg-integrity-cyan text-forensic-950 font-semibold text-sm hover:bg-integrity-cyan/90 transition-all"
          >
            <Play className="w-4 h-4" />
            <span>Run Spectrogram Analysis</span>
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Status card */}
          <div className={`flex items-center justify-between p-4 rounded-xl border ${statusBg(activeJob.status)}`}>
            <div className="flex items-center space-x-3">
              {(activeJob.status === "QUEUED" || activeJob.status === "PROCESSING") && (
                <Loader2 className="w-5 h-5 text-integrity-cyan animate-spin" />
              )}
              {activeJob.status === "COMPLETED" && <CheckCircle2 className="w-5 h-5 text-integrity-emerald" />}
              {activeJob.status === "FAILED" && <AlertCircle className="w-5 h-5 text-red-400" />}
              <div>
                <div className={`text-sm font-bold ${statusColor(activeJob.status)}`}>
                  {activeJob.status}
                </div>
                <div className="text-[11px] text-forensic-400 font-mono">
                  AUDIO_SPECTROGRAM &bull; Attempt {activeJob.attempt_count}/{activeJob.max_retries + 1}
                </div>
              </div>
            </div>
            <button
              onClick={findLatestAudioJob}
              className="p-1.5 rounded-lg hover:bg-forensic-800 text-forensic-400 hover:text-white transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {activeJob.status === "FAILED" && activeJob.error_message && (
            <div className="p-4 rounded-lg bg-red-950/30 border border-red-800 text-xs text-red-200 font-mono">
              <strong>Error [{activeJob.error_code}]:</strong> {activeJob.error_message}
            </div>
          )}

          {activeJob.status === "COMPLETED" && results && (
            <>
              {!results.is_applicable && (
                <div className="flex items-start space-x-2 p-3.5 rounded-lg bg-amber-950/30 border border-amber-800 text-sm text-amber-200">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <span>{results.inapplicability_reason || "Audio analysis not applicable for this file."}</span>
                </div>
              )}

              {results.is_applicable && (
                <>
                  {/* Signal metrics */}
                  <div>
                    <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-2">
                      <BarChart2 className="w-4 h-4 text-integrity-cyan" />
                      <span>Signal Metrics</span>
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[
                        { label: "Sample Rate", value: results.sample_rate ? `${(results.sample_rate / 1000).toFixed(1)} kHz` : "N/A", icon: <Activity className="w-4 h-4 text-integrity-teal" /> },
                        { label: "Duration", value: results.duration_seconds ? `${results.duration_seconds.toFixed(2)}s` : "N/A", icon: <Clock className="w-4 h-4 text-integrity-blue" /> },
                        { label: "Channels", value: results.channel_count?.toString() ?? "N/A", icon: <Volume2 className="w-4 h-4 text-integrity-cyan" /> },
                        { label: "Bit Depth", value: results.bit_depth ? `${results.bit_depth}-bit` : "N/A", icon: <Cpu className="w-4 h-4 text-forensic-400" /> },
                        { label: "RMS Level", value: results.rms_db != null ? `${results.rms_db.toFixed(1)} dBFS` : "N/A", icon: <BarChart2 className="w-4 h-4 text-integrity-teal" /> },
                        { label: "Peak Level", value: results.peak_db != null ? `${results.peak_db.toFixed(1)} dBFS` : "N/A", icon: <BarChart2 className="w-4 h-4 text-integrity-blue" /> },
                        { label: "Dynamic Range", value: results.dynamic_range_db != null ? `${results.dynamic_range_db.toFixed(1)} dB` : "N/A", icon: <Activity className="w-4 h-4 text-integrity-cyan" /> },
                        { label: "HF Cutoff", value: results.high_freq_cutoff_hz ? `${(results.high_freq_cutoff_hz / 1000).toFixed(1)} kHz` : "N/A", icon: <BarChart2 className="w-4 h-4 text-forensic-400" /> },
                      ].map((m) => (
                        <div key={m.label} className="bg-forensic-900 border border-forensic-800 rounded-xl p-4 text-center">
                          <div className="flex justify-center mb-2">{m.icon}</div>
                          <div className="text-lg font-bold text-white font-mono">{m.value}</div>
                          <div className="text-[11px] text-forensic-400 mt-0.5">{m.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Forensic flags */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className={`p-4 rounded-xl border ${results.lossy_compression_detected ? "bg-amber-950/30 border-amber-800" : "bg-integrity-emerald/10 border-integrity-emerald/30"}`}>
                      <div className="flex items-center space-x-2 mb-2">
                        {results.lossy_compression_detected ? (
                          <AlertTriangle className="w-4 h-4 text-amber-400" />
                        ) : (
                          <CheckCircle2 className="w-4 h-4 text-integrity-emerald" />
                        )}
                        <span className={`text-sm font-semibold ${results.lossy_compression_detected ? "text-amber-300" : "text-integrity-emerald"}`}>
                          Lossy Compression: {results.lossy_compression_detected ? "DETECTED" : "Not Detected"}
                        </span>
                      </div>
                      {results.high_freq_cutoff_hz && (
                        <p className="text-xs text-forensic-400 font-mono">
                          HF rolloff at {(results.high_freq_cutoff_hz / 1000).toFixed(1)} kHz — consistent with{" "}
                          {results.high_freq_cutoff_hz < 16000
                            ? "MP3/AAC 128 kbps"
                            : results.high_freq_cutoff_hz < 20000
                            ? "MP3 320 kbps"
                            : "lossless"}{" "}
                          encoding.
                        </p>
                      )}
                    </div>
                    <div className={`p-4 rounded-xl border ${results.clipping_detected ? "bg-red-950/30 border-red-800" : "bg-integrity-emerald/10 border-integrity-emerald/30"}`}>
                      <div className="flex items-center space-x-2 mb-2">
                        {results.clipping_detected ? (
                          <ShieldAlert className="w-4 h-4 text-red-400" />
                        ) : (
                          <CheckCircle2 className="w-4 h-4 text-integrity-emerald" />
                        )}
                        <span className={`text-sm font-semibold ${results.clipping_detected ? "text-red-300" : "text-integrity-emerald"}`}>
                          Amplitude Clipping: {results.clipping_detected ? "DETECTED" : "Not Detected"}
                        </span>
                      </div>
                      {results.clipping_ratio != null && (
                        <p className="text-xs text-forensic-400 font-mono">
                          Clipping ratio: {(results.clipping_ratio * 100).toFixed(3)}% of samples saturated.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Artifacts */}
                  {loadingArtifacts ? (
                    <div className="flex items-center space-x-2 text-xs text-forensic-500 font-mono animate-pulse p-4">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Loading spectrogram artifacts...</span>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {spectrogramUrl && (
                        <div className="rounded-xl overflow-hidden border border-forensic-800 bg-forensic-950">
                          <div className="px-4 py-2.5 border-b border-forensic-800 bg-forensic-900 text-xs font-mono text-forensic-400 flex items-center space-x-2">
                            <BarChart2 className="w-3.5 h-3.5 text-integrity-cyan" />
                            <span>STFT Power Spectrogram (dB scale)</span>
                          </div>
                          <img src={spectrogramUrl} alt="STFT Spectrogram" className="w-full object-contain" />
                        </div>
                      )}
                      {waveformUrl && (
                        <div className="rounded-xl overflow-hidden border border-forensic-800 bg-forensic-950">
                          <div className="px-4 py-2.5 border-b border-forensic-800 bg-forensic-900 text-xs font-mono text-forensic-400 flex items-center space-x-2">
                            <Activity className="w-3.5 h-3.5 text-integrity-teal" />
                            <span>Amplitude Waveform (clipping highlighted)</span>
                          </div>
                          <img src={waveformUrl} alt="Audio Waveform" className="w-full object-contain" />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Findings */}
                  {activeJob.findings.length > 0 && (
                    <div>
                      <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-2">
                        <Info className="w-4 h-4 text-integrity-blue" />
                        <span>Analysis Findings ({activeJob.findings.length})</span>
                      </h3>
                      <div className="space-y-2">
                        {activeJob.findings.map((f) => {
                          const sc: Record<string, string> = {
                            CRITICAL: "text-red-400 bg-red-950/50 border-red-800",
                            HIGH: "text-orange-400 bg-orange-950/30 border-orange-800",
                            MEDIUM: "text-amber-400 bg-amber-950/30 border-amber-800",
                            LOW: "text-yellow-400 bg-yellow-950/30 border-yellow-800",
                            INFO: "text-integrity-cyan bg-integrity-cyan/5 border-integrity-cyan/30",
                          };
                          return (
                            <div key={f.id} className={`p-3.5 rounded-lg border text-xs font-mono ${sc[f.severity] ?? ""}`}>
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-bold">[{f.severity}] {f.title}</span>
                                <span className="text-[10px] opacity-70">confidence: {(f.confidence_score * 100).toFixed(0)}%</span>
                              </div>
                              <p className="opacity-80 leading-relaxed">{f.description}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
