"use client";

import React, { useEffect, useState, useCallback, use } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Copy,
  Check,
  FileImage,
  FileAudio,
  FileVideo,
  FileText,
  AlertTriangle,
  Scale,
  Camera,
  Layers,
  Clock,
  Sliders,
  Maximize2,
  Cpu,
  Terminal,
  CheckCircle2,
} from "lucide-react";
import {
  fetchEvidenceDetail,
  verifyEvidenceHash,
  triggerMetadataExtraction,
  EvidenceDetailItem,
  MetadataExtract,
  HashVerificationResult,
} from "@/lib/api";

interface ExifToolNormalizedMetadata {
  file_type?: string;
  mime_type?: string;
  image_width?: number | string;
  image_height?: number | string;
  dimensions?: string;
  aspect_ratio?: string;
  megapixels?: number | string;
  color_space?: string;
  bits_per_sample?: string;
  timestamps?: {
    date_time_original?: string;
    create_date?: string;
    modify_date?: string;
    file_modify_date?: string;
  };
  software_tags?: {
    make?: string;
    model?: string;
    software?: string;
    lens_model?: string;
    serial_number?: string;
    artist?: string;
  };
  camera_settings?: {
    iso?: string;
    f_number?: string;
    exposure_time?: string;
    focal_length?: string;
    flash?: string;
  };
  gps?: {
    latitude?: string;
    longitude?: string;
    altitude?: string;
  };
  total_tags_extracted?: number;
  forensic_authenticity_notice?: string;
}

interface FFprobeNormalizedMetadata {
  container?: {
    format_name?: string;
    format_long_name?: string;
    duration_seconds?: number | string;
    duration_formatted?: string;
    bitrate_bps?: number | string;
    size_bytes?: number | string;
    stream_count?: number;
    tags?: Record<string, string>;
  };
  video_streams?: Array<{
    stream_index: number;
    codec_name?: string;
    codec_long_name?: string;
    profile?: string;
    dimensions?: string;
    frame_rate?: string;
    pixel_format?: string;
    frame_count?: number | string;
  }>;
  audio_streams?: Array<{
    stream_index: number;
    codec_name?: string;
    codec_long_name?: string;
    sample_rate_hz?: number | string;
    channels?: number | string;
    channel_layout?: string;
    sample_format?: string;
    bitrate_bps?: number | string;
  }>;
  video_stream_count?: number;
  audio_stream_count?: number;
  forensic_authenticity_notice?: string;
}

interface EvidenceDetailPageProps {
  params: Promise<{ caseId: string; evidenceId: string }>;
}

export default function EvidenceDetailPage({ params }: EvidenceDetailPageProps): React.JSX.Element {
  const resolvedParams = use(params);
  const { caseId, evidenceId } = resolvedParams;

  const [evidence, setEvidence] = useState<EvidenceDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Verification state
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<HashVerificationResult | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);

  // Metadata Extraction state
  const [extracting, setExtracting] = useState(false);
  const [extractSuccessMsg, setExtractSuccessMsg] = useState<string | null>(null);

  // UI state
  const [activeTab, setActiveTab] = useState<"exiftool" | "ffprobe" | "raw">("exiftool");
  const [copiedHash, setCopiedHash] = useState(false);

  const loadEvidence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEvidenceDetail(caseId, evidenceId);
      setEvidence(data);
      // Auto select appropriate tab based on media type or extracts
      if (data.metadata_extracts?.length > 0) {
        const hasExif = data.metadata_extracts.some((e) => e.tool_name.toLowerCase().includes("exif"));
        const hasFF = data.metadata_extracts.some((e) => e.tool_name.toLowerCase().includes("ffprobe"));
        if (data.media_type === "IMAGE" && hasExif) {
          setActiveTab("exiftool");
        } else if ((data.media_type === "AUDIO" || data.media_type === "VIDEO") && hasFF) {
          setActiveTab("ffprobe");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evidence details.");
    } finally {
      setLoading(false);
    }
  }, [caseId, evidenceId]);

  useEffect(() => {
    loadEvidence();
  }, [loadEvidence]);

  const handleCopyHash = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const handleVerify = async () => {
    setVerifying(true);
    setVerificationError(null);
    setVerificationResult(null);
    try {
      const res = await verifyEvidenceHash(caseId, evidenceId, "MANUAL_INSPECTION");
      setVerificationResult(res);
      // Refresh evidence details to load new verification record
      await loadEvidence();
    } catch (err) {
      setVerificationError(err instanceof Error ? err.message : "Verification check failed.");
    } finally {
      setVerifying(false);
    }
  };

  const handleExtractMetadata = async () => {
    setExtracting(true);
    setError(null);
    setExtractSuccessMsg(null);
    try {
      await triggerMetadataExtraction(caseId, evidenceId);
      setExtractSuccessMsg("Metadata successfully extracted and persisted via ExifTool and FFprobe.");
      await loadEvidence();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Metadata extraction failed.");
    } finally {
      setExtracting(false);
    }
  };

  const getMediaIcon = (mediaType: string) => {
    switch (mediaType) {
      case "IMAGE":
        return <FileImage className="w-5 h-5 text-integrity-teal" />;
      case "AUDIO":
        return <FileAudio className="w-5 h-5 text-integrity-cyan" />;
      case "VIDEO":
        return <FileVideo className="w-5 h-5 text-integrity-blue" />;
      default:
        return <FileText className="w-5 h-5 text-forensic-400" />;
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  // Find extracts by tool
  const exifExtract = evidence?.metadata_extracts?.find(
    (e) => e.tool_name.toLowerCase().includes("exif")
  );
  const ffprobeExtract = evidence?.metadata_extracts?.find(
    (e) => e.tool_name.toLowerCase().includes("ffprobe")
  );

  return (
    <div className="space-y-6">
      {/* Header & Breadcrumb */}
      <div className="space-y-2 pb-5 border-b border-forensic-800">
        <Link
          href={`/cases/${caseId}`}
          className="inline-flex items-center space-x-1.5 text-xs text-forensic-400 hover:text-white transition-colors font-mono"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Case Vault</span>
        </Link>

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pt-1">
          <div>
            <div className="flex items-center space-x-3">
              <span className="p-2 rounded-lg bg-forensic-800 border border-forensic-700">
                {evidence ? getMediaIcon(evidence.media_type) : <FileText className="w-5 h-5" />}
              </span>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-xs text-integrity-teal font-bold tracking-wider">
                    {evidence?.evidence_number || "..."}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
                    VAULT SECURED
                  </span>
                </div>
                <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5 truncate max-w-xl">
                  {evidence?.original_filename || "Evidence Details"}
                </h2>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {evidence?.media_type === "IMAGE" && (
              <Link
                href={`/cases/${caseId}/evidence/${evidenceId}/image-analysis`}
                className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-integrity-teal/15 hover:bg-integrity-teal/25 border border-integrity-teal/40 text-xs font-mono text-integrity-teal hover:text-white transition-all shadow"
                id="btn-nav-image-analysis"
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Image Analysis & ELA</span>
              </Link>
            )}

            <button
              onClick={handleExtractMetadata}
              disabled={extracting || loading}
              className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-xs font-mono text-integrity-cyan hover:text-white transition-all shadow disabled:opacity-50"
              title="Execute sandboxed ExifTool & FFprobe extraction"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${extracting ? "animate-spin" : ""}`} />
              <span>{extracting ? "Running Tools..." : "Re-extract Metadata"}</span>
            </button>

            <button
              onClick={handleVerify}
              disabled={verifying || loading}
              className="inline-flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-integrity-teal text-forensic-950 font-semibold text-xs font-mono hover:bg-integrity-teal/90 transition-all shadow disabled:opacity-50"
            >
              <ShieldCheck className={`w-3.5 h-3.5 ${verifying ? "animate-spin" : ""}`} />
              <span>{verifying ? "Verifying SHA-256..." : "Verify Vault Integrity"}</span>
            </button>
          </div>
        </div>
      </div>

      {extractSuccessMsg && (
        <div className="p-3.5 rounded-lg bg-integrity-emerald/10 border border-integrity-emerald/30 text-xs text-integrity-emerald flex items-center space-x-2 font-mono">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{extractSuccessMsg}</span>
        </div>
      )}

      {error && (
        <div className="p-3.5 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 flex items-start space-x-2 font-mono">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {verificationError && (
        <div className="p-3.5 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 flex items-start space-x-2 font-mono">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>Verification failed: {verificationError}</span>
        </div>
      )}

      {/* Verification Result Banner */}
      {verificationResult && (
        <div
          className={`p-4 rounded-xl border text-xs font-mono space-y-2 animate-in fade-in duration-200 ${
            verificationResult.is_intact
              ? "bg-integrity-emerald/10 border-integrity-emerald/30 text-integrity-emerald"
              : "bg-alert-tamper/10 border-alert-tamper/40 text-alert-tamper"
          }`}
        >
          <div className="flex items-center justify-between font-bold">
            <span className="flex items-center space-x-2">
              {verificationResult.is_intact ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <ShieldAlert className="w-4 h-4" />
              )}
              <span>
                {verificationResult.is_intact
                  ? "VAULT BITSTREAM RE-VERIFICATION: 100% INTACT"
                  : "CRITICAL ALERT: CRYPTOGRAPHIC HASH MISMATCH (EVIDENCE TAMPER DETECTED)"}
              </span>
            </span>
            <span className="text-[10px] text-forensic-400 font-normal">
              {new Date(verificationResult.verified_at).toLocaleTimeString()}
            </span>
          </div>
          <div className="text-[11px] text-forensic-300">
            Calculated SHA-256: <code className="text-white break-all">{verificationResult.calculated_sha256}</code>
          </div>
          <div className="text-[10px] text-forensic-400 pt-1 border-t border-forensic-800/60 leading-normal">
            {verificationResult.integrity_notice}
          </div>
        </div>
      )}

      {/* Courtroom Admissibility & Forensic Notice Banner */}
      <div className="p-4 rounded-xl bg-integrity-cyan/5 border border-integrity-cyan/20 text-xs text-forensic-300 space-y-1.5 shadow-sm">
        <div className="font-semibold text-integrity-cyan flex items-center space-x-2">
          <Scale className="w-4 h-4" />
          <span>Forensic Metadata Courtroom Admissibility Notice (Integrity vs. Authenticity)</span>
        </div>
        <p className="text-forensic-400 leading-relaxed text-[11px]">
          <strong>Crucial Forensic Principle:</strong> Consistent, standard, or normal-looking EXIF, IPTC, and FFprobe
          container metadata can be effortlessly forged, stripped, or injected using standard open-source tools or hex editors.
          Technical metadata extracts document container attributes at the time of intake, but <strong>do not prove</strong> historical
          authenticity, camera sensor origin, or the absence of prior digital manipulation.
        </p>
      </div>

      {/* Overview & Hashes Card */}
      {evidence && (
        <div className="rounded-xl bg-forensic-900 border border-forensic-800 p-5 space-y-4 shadow-md">
          <div className="flex items-center justify-between border-b border-forensic-800 pb-3">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2 font-mono uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4 text-integrity-teal" />
              <span>Evidence Baseline & Storage Provenance</span>
            </h3>
            <span className="text-xs font-mono text-forensic-400">
              Ingested: {new Date(evidence.ingested_at).toLocaleString()}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="bg-forensic-850 p-3 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[10px] uppercase mb-1">Media Category</span>
              <span className="text-integrity-cyan font-bold text-sm">{evidence.media_type}</span>
              <span className="text-forensic-400 text-[10px] block truncate" title={evidence.mime_type}>
                {evidence.mime_type}
              </span>
            </div>

            <div className="bg-forensic-850 p-3 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[10px] uppercase mb-1">Byte Size</span>
              <span className="text-white font-bold text-sm">{formatBytes(evidence.file_size_bytes)}</span>
              <span className="text-forensic-400 text-[10px] block">
                {evidence.file_size_bytes.toLocaleString()} bytes
              </span>
            </div>

            <div className="bg-forensic-850 p-3 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[10px] uppercase mb-1">Server Stored Name</span>
              <span className="text-white font-mono text-xs block truncate" title={evidence.stored_filename}>
                {evidence.stored_filename}
              </span>
              <span className="text-integrity-emerald text-[10px] block">Read-Only Vault Locked</span>
            </div>

            <div className="bg-forensic-850 p-3 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[10px] uppercase mb-1">Vault Storage Path</span>
              <span className="text-forensic-300 font-mono text-[11px] block truncate" title={evidence.storage_path}>
                {evidence.storage_path}
              </span>
              <span className="text-forensic-400 text-[10px] block">Non-root sandboxed mount</span>
            </div>
          </div>

          {/* Cryptographic Baseline Hashes */}
          <div className="bg-forensic-950 p-3.5 rounded-lg border border-forensic-800 space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-integrity-teal font-semibold flex items-center space-x-1.5">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Primary SHA-256 Bitstream Baseline</span>
              </span>
              <button
                onClick={() => handleCopyHash(evidence.primary_hash_sha256)}
                className="inline-flex items-center space-x-1 text-forensic-400 hover:text-white transition-colors text-[11px]"
              >
                {copiedHash ? <Check className="w-3 h-3 text-integrity-emerald" /> : <Copy className="w-3 h-3" />}
                <span>{copiedHash ? "Copied" : "Copy SHA-256"}</span>
              </button>
            </div>
            <div className="font-mono text-xs text-forensic-100 break-all select-all bg-forensic-900 p-2 rounded border border-forensic-850">
              {evidence.primary_hash_sha256}
            </div>
            <div className="flex flex-wrap gap-4 text-[11px] font-mono text-forensic-400 pt-1">
              <span>MD5: <code className="text-forensic-300">{evidence.hash_md5}</code></span>
              <span>SHA-1: <code className="text-forensic-300">{evidence.hash_sha1}</code></span>
            </div>
          </div>
        </div>
      )}

      {/* Metadata Extracts Section */}
      <div className="rounded-xl bg-forensic-900 border border-forensic-800 overflow-hidden shadow-xl">
        {/* Tab Headers */}
        <div className="flex items-center justify-between border-b border-forensic-800 bg-forensic-850/60 px-4 pt-2">
          <div className="flex space-x-1">
            <button
              onClick={() => setActiveTab("exiftool")}
              className={`px-4 py-2.5 text-xs font-mono font-medium rounded-t-lg transition-all flex items-center space-x-2 border-b-2 ${
                activeTab === "exiftool"
                  ? "border-integrity-teal text-white bg-forensic-900"
                  : "border-transparent text-forensic-400 hover:text-white hover:bg-forensic-800/40"
              }`}
            >
              <Camera className="w-3.5 h-3.5 text-integrity-teal" />
              <span>ExifTool Container Metadata</span>
              {exifExtract && (
                <span className="px-1.5 py-0.2 rounded-full bg-integrity-teal/10 text-integrity-teal text-[10px]">
                  v{exifExtract.tool_version}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("ffprobe")}
              className={`px-4 py-2.5 text-xs font-mono font-medium rounded-t-lg transition-all flex items-center space-x-2 border-b-2 ${
                activeTab === "ffprobe"
                  ? "border-integrity-cyan text-white bg-forensic-900"
                  : "border-transparent text-forensic-400 hover:text-white hover:bg-forensic-800/40"
              }`}
            >
              <Layers className="w-3.5 h-3.5 text-integrity-cyan" />
              <span>FFprobe Stream Profiles</span>
              {ffprobeExtract && (
                <span className="px-1.5 py-0.2 rounded-full bg-integrity-cyan/10 text-integrity-cyan text-[10px]">
                  v{ffprobeExtract.tool_version}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("raw")}
              className={`px-4 py-2.5 text-xs font-mono font-medium rounded-t-lg transition-all flex items-center space-x-2 border-b-2 ${
                activeTab === "raw"
                  ? "border-integrity-blue text-white bg-forensic-900"
                  : "border-transparent text-forensic-400 hover:text-white hover:bg-forensic-800/40"
              }`}
            >
              <Terminal className="w-3.5 h-3.5 text-integrity-blue" />
              <span>Raw JSON Inspector</span>
            </button>
          </div>

          <div className="text-[11px] font-mono text-forensic-400 hidden sm:block">
            {evidence?.metadata_extracts?.length || 0} Forensic Tool Extracts Recorded
          </div>
        </div>

        {/* Tab Body */}
        <div className="p-6">
          {loading ? (
            <div className="p-12 text-center text-forensic-400 font-mono text-xs animate-pulse">
              Parsing technical metadata extracts...
            </div>
          ) : !evidence?.metadata_extracts || evidence.metadata_extracts.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <Camera className="w-10 h-10 text-forensic-600 mx-auto" />
              <h3 className="text-sm font-semibold text-white">No metadata extracts recorded</h3>
              <p className="text-xs text-forensic-400 max-w-sm mx-auto">
                Execute ExifTool and FFprobe sandboxed subprocesses to extract container and stream profiles.
              </p>
              <button
                onClick={handleExtractMetadata}
                disabled={extracting}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-integrity-teal text-forensic-950 text-xs font-medium"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${extracting ? "animate-spin" : ""}`} />
                <span>Extract Metadata Now</span>
              </button>
            </div>
          ) : activeTab === "exiftool" ? (
            <ExifToolView extract={exifExtract} />
          ) : activeTab === "ffprobe" ? (
            <FFprobeView extract={ffprobeExtract} />
          ) : (
            <RawJsonView extracts={evidence.metadata_extracts} />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExifTool View Component
// ---------------------------------------------------------------------------

function ExifToolView({ extract }: { extract?: MetadataExtract | undefined }): React.JSX.Element {
  if (!extract) {
    return (
      <div className="p-8 text-center text-forensic-400 font-mono text-xs">
        ExifTool extract is not available for this evidence item.
      </div>
    );
  }

  const meta = (extract.filtered_forensic_metadata || {}) as ExifToolNormalizedMetadata;
  const timestamps = meta.timestamps || {};
  const software = meta.software_tags || {};
  const camera = meta.camera_settings || {};
  const gps = meta.gps || {};

  return (
    <div className="space-y-6">
      {/* Tool Provenance Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-forensic-850 rounded-lg border border-forensic-800 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-integrity-teal animate-pulse" />
          <span className="text-white font-bold">Phil Harvey&apos;s ExifTool</span>
          <span className="text-forensic-400">v{extract.tool_version}</span>
        </div>
        <div className="flex items-center space-x-3 text-forensic-400 text-[11px]">
          <span>Extracted: {new Date(extract.extracted_at).toLocaleString()}</span>
          <span>Total Tags: {meta.total_tags_extracted || 0}</span>
        </div>
      </div>

      {/* Primary Specifications Grid */}
      <div>
        <h4 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-1.5">
          <Maximize2 className="w-3.5 h-3.5 text-integrity-teal" />
          <span>Image & Container Geometry</span>
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono">
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Dimensions</span>
            <span className="text-white font-bold">{meta.dimensions || "Unavailable"}</span>
          </div>
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Aspect Ratio</span>
            <span className="text-integrity-cyan font-bold">{meta.aspect_ratio || "Unavailable"}</span>
          </div>
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Megapixels</span>
            <span className="text-white font-bold">{meta.megapixels ? `${meta.megapixels} MP` : "Unavailable"}</span>
          </div>
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">File Format</span>
            <span className="text-white font-bold">{meta.file_type || "Unavailable"}</span>
          </div>
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Color Space</span>
            <span className="text-white font-bold">{meta.color_space || "Unavailable"}</span>
          </div>
          <div className="bg-forensic-850/70 p-3 rounded-lg border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Bits Per Sample</span>
            <span className="text-white font-bold">{meta.bits_per_sample || "Unavailable"}</span>
          </div>
        </div>
      </div>

      {/* Software, Hardware, and Camera Origin */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-forensic-850/50 p-4 rounded-xl border border-forensic-800 space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-integrity-teal font-semibold flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5" />
            <span>Hardware & Software Provenance</span>
          </h4>
          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">Camera Make:</span>
              <span className="text-white font-semibold">{software.make || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">Camera Model:</span>
              <span className="text-white font-semibold">{software.model || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">Lens Model:</span>
              <span className="text-white">{software.lens_model || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">Software Tag:</span>
              <span className="text-integrity-cyan font-bold">{software.software || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">Body Serial No:</span>
              <span className="text-white">{software.serial_number || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-forensic-400">Artist / Author:</span>
              <span className="text-white">{software.artist || "Unavailable"}</span>
            </div>
          </div>
        </div>

        {/* Timestamps & Capture Settings */}
        <div className="bg-forensic-850/50 p-4 rounded-xl border border-forensic-800 space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-integrity-cyan font-semibold flex items-center space-x-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>Recorded Metadata Timestamps</span>
          </h4>
          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">DateTimeOriginal:</span>
              <span className="text-white font-semibold">{timestamps.date_time_original || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">CreateDate:</span>
              <span className="text-white">{timestamps.create_date || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">ModifyDate:</span>
              <span className="text-white">{timestamps.modify_date || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">FileModifyDate:</span>
              <span className="text-forensic-300">{timestamps.file_modify_date || "Unavailable"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-forensic-800/60">
              <span className="text-forensic-400">GPS Coordinates:</span>
              <span className="text-white">
                {gps.latitude !== "Unavailable" && gps.longitude !== "Unavailable"
                  ? `${gps.latitude}, ${gps.longitude}`
                  : "Unavailable"}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-forensic-400">Exposure (ISO / F-Stop):</span>
              <span className="text-integrity-teal">
                {camera.iso || "Unavailable"} &bull; {camera.f_number || "Unavailable"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FFprobe View Component
// ---------------------------------------------------------------------------

function FFprobeView({ extract }: { extract?: MetadataExtract | undefined }): React.JSX.Element {
  if (!extract) {
    return (
      <div className="p-8 text-center text-forensic-400 font-mono text-xs">
        FFprobe extract is not available for this evidence item.
      </div>
    );
  }

  const meta = (extract.filtered_forensic_metadata || {}) as FFprobeNormalizedMetadata;
  const container = meta.container || {};
  const videoStreams = meta.video_streams || [];
  const audioStreams = meta.audio_streams || [];

  return (
    <div className="space-y-6">
      {/* Tool Provenance Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-forensic-850 rounded-lg border border-forensic-800 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-integrity-cyan animate-pulse" />
          <span className="text-white font-bold">FFprobe Multimedia Stream Inspector</span>
          <span className="text-forensic-400">v{extract.tool_version}</span>
        </div>
        <div className="flex items-center space-x-3 text-forensic-400 text-[11px]">
          <span>Extracted: {new Date(extract.extracted_at).toLocaleString()}</span>
          <span>Streams: {container.stream_count || 0}</span>
        </div>
      </div>

      {/* Container Information Card */}
      <div className="bg-forensic-850/50 p-4 rounded-xl border border-forensic-800 space-y-3">
        <h4 className="text-xs font-mono uppercase tracking-wider text-integrity-teal font-semibold flex items-center space-x-1.5">
          <Sliders className="w-3.5 h-3.5" />
          <span>Container Format & Encapsulation</span>
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div className="bg-forensic-900 p-2.5 rounded border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Format Name</span>
            <span className="text-white font-bold truncate block">{container.format_name || "Unavailable"}</span>
          </div>
          <div className="bg-forensic-900 p-2.5 rounded border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Duration</span>
            <span className="text-integrity-cyan font-bold">{container.duration_formatted || "Unavailable"}</span>
            {container.duration_seconds !== "Unavailable" && (
              <span className="text-[10px] text-forensic-400 block">({container.duration_seconds}s)</span>
            )}
          </div>
          <div className="bg-forensic-900 p-2.5 rounded border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Overall Bitrate</span>
            <span className="text-white font-bold">
              {container.bitrate_bps !== "Unavailable"
                ? `${(Number(container.bitrate_bps) / 1000).toFixed(0)} kbps`
                : "Unavailable"}
            </span>
          </div>
          <div className="bg-forensic-900 p-2.5 rounded border border-forensic-800">
            <span className="text-forensic-400 text-[10px] block mb-1">Streams Breakdown</span>
            <span className="text-white font-bold">
              {meta.video_stream_count || 0} Video &bull; {meta.audio_stream_count || 0} Audio
            </span>
          </div>
        </div>
      </div>

      {/* Video Streams */}
      {videoStreams.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-integrity-cyan font-semibold flex items-center space-x-1.5">
            <FileVideo className="w-3.5 h-3.5" />
            <span>Video Stream Profiles ({videoStreams.length})</span>
          </h4>
          <div className="space-y-3">
            {videoStreams.map((v: any, idx: number) => (
              <div key={idx} className="bg-forensic-850/60 p-4 rounded-xl border border-forensic-800 space-y-3 text-xs font-mono">
                <div className="flex items-center justify-between border-b border-forensic-800/80 pb-2">
                  <div className="flex items-center space-x-2">
                    <span className="px-2 py-0.5 rounded bg-forensic-900 border border-forensic-750 text-[11px] text-integrity-cyan font-bold">
                      Stream #{v.stream_index}
                    </span>
                    <span className="text-white font-bold">{v.codec_name}</span>
                    <span className="text-forensic-400 text-[11px]">({v.codec_long_name})</span>
                  </div>
                  <span className="text-forensic-300 text-[11px]">Profile: {v.profile || "Unavailable"}</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Dimensions:</span>
                    <span className="text-white font-bold">{v.dimensions || "Unavailable"}</span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Frame Rate:</span>
                    <span className="text-integrity-teal font-bold">{v.frame_rate || "Unavailable"}</span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Pixel Format:</span>
                    <span className="text-white">{v.pixel_format || "Unavailable"}</span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Frame Count:</span>
                    <span className="text-white">{v.frame_count || "Unavailable"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Audio Streams */}
      {audioStreams.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-integrity-teal font-semibold flex items-center space-x-1.5">
            <FileAudio className="w-3.5 h-3.5" />
            <span>Audio Stream Profiles ({audioStreams.length})</span>
          </h4>
          <div className="space-y-3">
            {audioStreams.map((a: any, idx: number) => (
              <div key={idx} className="bg-forensic-850/60 p-4 rounded-xl border border-forensic-800 space-y-3 text-xs font-mono">
                <div className="flex items-center justify-between border-b border-forensic-800/80 pb-2">
                  <div className="flex items-center space-x-2">
                    <span className="px-2 py-0.5 rounded bg-forensic-900 border border-forensic-750 text-[11px] text-integrity-teal font-bold">
                      Stream #{a.stream_index}
                    </span>
                    <span className="text-white font-bold">{a.codec_name}</span>
                    <span className="text-forensic-400 text-[11px]">({a.codec_long_name})</span>
                  </div>
                  <span className="text-forensic-300 text-[11px]">Layout: {a.channel_layout || "Unavailable"}</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Sample Rate:</span>
                    <span className="text-white font-bold">
                      {a.sample_rate_hz !== "Unavailable" ? `${a.sample_rate_hz} Hz` : "Unavailable"}
                    </span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Channels:</span>
                    <span className="text-integrity-teal font-bold">
                      {a.channels !== "Unavailable" ? `${a.channels} channel(s)` : "Unavailable"}
                    </span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Sample Format:</span>
                    <span className="text-white">{a.sample_format || "Unavailable"}</span>
                  </div>
                  <div>
                    <span className="text-forensic-400 text-[10px] block">Bitrate:</span>
                    <span className="text-white">
                      {a.bitrate_bps !== "Unavailable"
                        ? `${(Number(a.bitrate_bps) / 1000).toFixed(0)} kbps`
                        : "Unavailable"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Raw JSON Inspector Component
// ---------------------------------------------------------------------------

function RawJsonView({ extracts }: { extracts: MetadataExtract[] }): React.JSX.Element {
  const [selectedTool, setSelectedTool] = useState<string>(extracts[0]?.tool_name || "");
  const [copied, setCopied] = useState(false);

  const currentExtract = extracts.find((e) => e.tool_name === selectedTool) || extracts[0];

  const handleCopy = () => {
    if (currentExtract) {
      navigator.clipboard.writeText(JSON.stringify(currentExtract.raw_metadata, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          {extracts.map((e) => (
            <button
              key={e.tool_name}
              onClick={() => setSelectedTool(e.tool_name)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                currentExtract?.tool_name === e.tool_name
                  ? "bg-forensic-750 text-white border border-forensic-600"
                  : "bg-forensic-850 text-forensic-400 hover:text-white border border-forensic-800"
              }`}
            >
              {e.tool_name} (v{e.tool_version})
            </button>
          ))}
        </div>

        <button
          onClick={handleCopy}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-xs text-forensic-300 font-mono transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-integrity-emerald" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? "Copied JSON" : "Copy Raw JSON"}</span>
        </button>
      </div>

      <div className="relative rounded-xl bg-forensic-950 border border-forensic-800 p-4 overflow-x-auto max-h-[500px]">
        <pre className="text-xs font-mono text-forensic-300 leading-relaxed whitespace-pre-wrap">
          {currentExtract
            ? JSON.stringify(currentExtract.raw_metadata, null, 2)
            : "No raw metadata available."}
        </pre>
      </div>
    </div>
  );
}
