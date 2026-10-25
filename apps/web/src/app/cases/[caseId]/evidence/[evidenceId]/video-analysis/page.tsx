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
  Film,
  Loader2,
  BarChart2,
  AlertTriangle,
  Info,
  Maximize2,
  X,
  Hash,
} from "lucide-react";
import {
  fetchEvidenceDetail,
  getArtifactContentUrl,
  createAnalysisJob,
  getAnalysisJob,
  getAnalysisHistory,
  EvidenceDetailItem,
  ForensicAnalysisJob,
  VideoKeyframeResult,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ caseId: string; evidenceId: string }>;
}

interface KeyframeWithUrl {
  frame_index: number;
  timestamp_s: number;
  diff_score: number;
  artifact_id?: string | null;
  dhash?: string | null;
  blobUrl?: string;
  loading?: boolean;
}

export default function VideoAnalysisPage({ params }: PageProps): React.JSX.Element {
  const resolvedParams = use(params);
  const { caseId, evidenceId } = resolvedParams;

  const [evidence, setEvidence] = useState<EvidenceDetailItem | null>(null);
  const [activeJob, setActiveJob] = useState<ForensicAnalysisJob | null>(null);
  const [loadingJob, setLoadingJob] = useState(true);
  const [isPolling, setIsPolling] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [keyframes, setKeyframes] = useState<KeyframeWithUrl[]>([]);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [lightboxFrame, setLightboxFrame] = useState<KeyframeWithUrl | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const loadEvidence = useCallback(async () => {
    try {
      const data = await fetchEvidenceDetail(caseId, evidenceId);
      setEvidence(data);
    } catch {
      // ignore
    }
  }, [caseId, evidenceId]);

  const findLatestVideoJob = useCallback(async () => {
    setLoadingJob(true);
    try {
      const history = await getAnalysisHistory({ evidence_id: evidenceId, analysis_type: "VIDEO_FRAMES" });
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
    findLatestVideoJob();
  }, [loadEvidence, findLatestVideoJob]);

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

  // Load keyframe artifact blobs when job completes
  useEffect(() => {
    if (activeJob?.status !== "COMPLETED") return;
    const results = activeJob.summary_results as VideoKeyframeResult | null;
    if (!results?.scene_cuts) return;

    const token =
      typeof window !== "undefined" ? localStorage.getItem("ps05_auth_token") || "" : "";
    const authHeader = { Authorization: `Bearer ${token}` };

    const initialFrames: KeyframeWithUrl[] = results.scene_cuts.map((sc) => ({
      ...sc,
      loading: !!sc.artifact_id,
    }));
    setKeyframes(initialFrames);

    // Load each artifact image
    initialFrames.forEach((kf, idx) => {
      if (!kf.artifact_id) return;
      const url = getArtifactContentUrl(kf.artifact_id);
      fetch(url, { headers: authHeader })
        .then((r) => r.blob())
        .then((b) => {
          const blobUrl = URL.createObjectURL(b);
          setKeyframes((prev) =>
            prev.map((f, i) => (i === idx ? { ...f, blobUrl, loading: false } : f))
          );
        })
        .catch(() => {
          setKeyframes((prev) => prev.map((f, i) => (i === idx ? { ...f, loading: false } : f)));
        });
    });
  }, [activeJob?.status]);

  const handleSubmitJob = async () => {
    setSubmitting(true);
    setActionError(null);
    try {
      const res = await createAnalysisJob({ evidence_id: evidenceId, analysis_type: "VIDEO_FRAMES" });
      setActionSuccess("Video keyframe analysis queued successfully.");
      const job = await getAnalysisJob(res.analysis_id);
      setActiveJob(job);
      setKeyframes([]);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to queue analysis.");
    } finally {
      setSubmitting(false);
    }
  };

  const results = activeJob?.summary_results as VideoKeyframeResult | null;

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

  const formatTimestamp = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = (s % 60).toFixed(2);
    return `${m}:${sec.padStart(5, "0")}`;
  };

  return (
    <div className="space-y-6">
      {/* Lightbox */}
      {lightboxUrl && lightboxFrame && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4"
          onClick={() => { setLightboxUrl(null); setLightboxFrame(null); }}
        >
          <div
            className="relative max-w-4xl w-full rounded-2xl overflow-hidden border border-forensic-700 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 bg-forensic-900 border-b border-forensic-800 text-xs font-mono text-forensic-400">
              <span>
                Frame #{lightboxFrame.frame_index} &bull; T={formatTimestamp(lightboxFrame.timestamp_s)} &bull; diff={lightboxFrame.diff_score.toFixed(2)}
              </span>
              <button
                onClick={() => { setLightboxUrl(null); setLightboxFrame(null); }}
                className="p-1.5 hover:bg-forensic-800 rounded-lg text-forensic-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <img src={lightboxUrl} alt={`Keyframe ${lightboxFrame.frame_index}`} className="w-full object-contain bg-black" />
            {lightboxFrame.dhash && (
              <div className="px-4 py-2 bg-forensic-900 border-t border-forensic-800 text-[10px] font-mono text-forensic-500 flex items-center space-x-2">
                <Hash className="w-3 h-3" />
                <span>dHash: {lightboxFrame.dhash}</span>
              </div>
            )}
          </div>
        </div>
      )}

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
            <Film className="w-6 h-6 text-integrity-blue" />
            <span>Video Keyframe &amp; Scene Cut Analysis</span>
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
          className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-lg bg-integrity-blue text-forensic-950 font-semibold text-sm hover:bg-integrity-blue/90 transition-all shadow disabled:opacity-50"
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
          <Film className="w-12 h-12 text-forensic-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">No Video Analysis Yet</h3>
          <p className="text-sm text-forensic-400 max-w-md mx-auto mb-6">
            Run the temporal frame analysis engine to detect scene cuts, extract keyframes with
            dHash perceptual hashing, and identify anomalous frame transitions.
          </p>
          <button
            onClick={handleSubmitJob}
            disabled={submitting}
            className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-lg bg-integrity-blue text-forensic-950 font-semibold text-sm hover:bg-integrity-blue/90 transition-all"
          >
            <Play className="w-4 h-4" />
            <span>Run Frame Analysis</span>
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
                  VIDEO_FRAMES &bull; Attempt {activeJob.attempt_count}/{activeJob.max_retries + 1}
                </div>
              </div>
            </div>
            <button
              onClick={findLatestVideoJob}
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
                  <span>{results.inapplicability_reason || "Video analysis not applicable for this file."}</span>
                </div>
              )}

              {results.is_applicable && (
                <>
                  {/* Video properties */}
                  <div>
                    <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-2">
                      <Cpu className="w-4 h-4 text-integrity-blue" />
                      <span>Video Properties</span>
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[
                        { label: "Resolution", value: results.width && results.height ? `${results.width}x${results.height}` : "N/A" },
                        { label: "Frame Rate", value: results.fps ? `${results.fps.toFixed(2)} fps` : "N/A" },
                        { label: "Duration", value: results.duration_seconds ? `${results.duration_seconds.toFixed(2)}s` : "N/A" },
                        { label: "Total Frames", value: results.frame_count?.toLocaleString() ?? "N/A" },
                        { label: "Codec", value: results.codec ?? "N/A" },
                        { label: "Scene Cuts", value: results.scene_cut_count?.toString() ?? "0" },
                        { label: "Keyframes", value: results.keyframe_count?.toString() ?? "0" },
                        { label: "Engine", value: results.engine_version ?? "OpenCV" },
                      ].map((m) => (
                        <div key={m.label} className="bg-forensic-900 border border-forensic-800 rounded-xl p-4 text-center">
                          <div className="text-lg font-bold text-white font-mono">{m.value}</div>
                          <div className="text-[11px] text-forensic-400 mt-0.5">{m.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Scene cut summary */}
                  {results.scene_cut_count != null && results.scene_cut_count > 0 && (
                    <div className="p-4 rounded-xl bg-integrity-blue/5 border border-integrity-blue/20 flex items-start space-x-3">
                      <BarChart2 className="w-5 h-5 text-integrity-blue shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-semibold text-white">
                          {results.scene_cut_count} scene transition
                          {results.scene_cut_count !== 1 ? "s" : ""} detected
                        </p>
                        <p className="text-xs text-forensic-400 mt-0.5">
                          Temporal dHash frame differencing analysis identified{" "}
                          {results.scene_cut_count} cut{results.scene_cut_count !== 1 ? "s" : ""}{" "}
                          in {results.frame_count?.toLocaleString() ?? "?"} frames. Keyframes extracted for
                          forensic provenance verification.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Keyframe carousel */}
                  {keyframes.length > 0 && (
                    <div>
                      <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-2">
                        <Film className="w-4 h-4 text-integrity-blue" />
                        <span>Scene Cut Keyframes ({keyframes.length})</span>
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                        {keyframes.map((kf, idx) => (
                          <div
                            key={idx}
                            className="group relative bg-forensic-900 border border-forensic-800 hover:border-integrity-blue/50 rounded-xl overflow-hidden transition-all cursor-pointer"
                            onClick={() => {
                              if (kf.blobUrl) {
                                setLightboxUrl(kf.blobUrl);
                                setLightboxFrame(kf);
                              }
                            }}
                          >
                            {kf.loading ? (
                              <div className="aspect-video flex items-center justify-center bg-forensic-950">
                                <Loader2 className="w-6 h-6 text-forensic-600 animate-spin" />
                              </div>
                            ) : kf.blobUrl ? (
                              <div className="relative aspect-video">
                                <img
                                  src={kf.blobUrl}
                                  alt={`Frame ${kf.frame_index}`}
                                  className="w-full h-full object-cover"
                                />
                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                                  <Maximize2 className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                                </div>
                              </div>
                            ) : (
                              <div className="aspect-video flex items-center justify-center bg-forensic-950">
                                <Film className="w-6 h-6 text-forensic-600" />
                              </div>
                            )}
                            <div className="p-2 text-[10px] font-mono text-forensic-400">
                              <div className="flex justify-between">
                                <span>#{kf.frame_index}</span>
                                <span className="text-integrity-blue">{formatTimestamp(kf.timestamp_s)}</span>
                              </div>
                              <div className="text-forensic-600 truncate">
                                diff: {kf.diff_score.toFixed(1)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
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
                            INFO: "text-integrity-blue bg-integrity-blue/5 border-integrity-blue/30",
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
