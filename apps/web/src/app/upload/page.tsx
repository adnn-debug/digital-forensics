"use client";

import React, { Suspense, useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  UploadCloud,
  FileCheck2,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  RefreshCw,
  FolderLock,
  FileAudio,
  FileVideo,
  FileImage,
  Info,
  Scale,
  ShieldAlert,
  Camera,
} from "lucide-react";
import {
  listCases,
  uploadEvidenceWithProgress,
  verifyEvidenceHash,
  CaseItem,
  EvidenceItem,
  HashVerificationResult,
} from "@/lib/api";

function EvidenceUploadContent(): React.JSX.Element {
  const searchParams = useSearchParams();
  const preselectedCaseId = searchParams.get("case_id");

  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(preselectedCaseId || "");
  const [loadingCases, setLoadingCases] = useState(true);

  // File & Form State
  const [file, setFile] = useState<File | null>(null);
  const [evidenceNumber, setEvidenceNumber] = useState<string>("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload State
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [validationWarning, setValidationWarning] = useState<string | null>(null);

  // Completed Intake Result
  const [intakeResult, setIntakeResult] = useState<EvidenceItem | null>(null);
  const [copiedHash, setCopiedHash] = useState(false);

  // Independent Verification State
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<HashVerificationResult | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchCases() {
      setLoadingCases(true);
      try {
        const res = await listCases();
        setCases(res.items);
        if (preselectedCaseId) {
          setSelectedCaseId(preselectedCaseId);
        } else if (res.items.length > 0 && res.items[0]) {
          setSelectedCaseId(res.items[0].id);
        }
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : "Failed to load cases");
      } finally {
        setLoadingCases(false);
      }
    }
    fetchCases();
  }, [preselectedCaseId]);

  // Pre-validate file on selection
  const handleFileSelection = (selectedFile: File) => {
    setUploadError(null);
    setValidationWarning(null);
    setIntakeResult(null);
    setVerificationResult(null);

    if (selectedFile.size === 0) {
      setUploadError("Selected file is empty (0 bytes). Forensic vaults reject zero-byte files.");
      setFile(null);
      return;
    }

    // Supported extensions heuristic check (server performs authoritative magic-byte signature check)
    const name = selectedFile.name.toLowerCase();
    const isImage = /\.(jpe?g|png|gif|webp|tiff?|bmp)$/i.test(name);
    const isAudio = /\.(mp3|wav|flac|ogg|aac|m4a)$/i.test(name);
    const isVideo = /\.(mp4|mov|webm|mkv|avi|mpg|mpeg)$/i.test(name);

    if (!isImage && !isAudio && !isVideo) {
      setValidationWarning(
        "Notice: File extension is not standard image/audio/video. The server will inspect deep magic-byte file signatures to verify media type."
      );
    }

    setFile(selectedFile);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCaseId) {
      setUploadError("Please select an authorized case vault first.");
      return;
    }
    if (!file) {
      setUploadError("Please select an evidence file to upload.");
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setUploadError(null);
    setIntakeResult(null);
    setVerificationResult(null);

    try {
      const result = await uploadEvidenceWithProgress(
        selectedCaseId,
        file,
        evidenceNumber || undefined,
        (percent) => setUploadProgress(percent)
      );
      setIntakeResult(result);
      setFile(null);
      setEvidenceNumber("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Evidence upload stream failed.");
    } finally {
      setUploading(false);
    }
  };

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const handleIndependentVerify = async () => {
    if (!intakeResult) return;
    setVerifying(true);
    setVerificationError(null);
    try {
      const res = await verifyEvidenceHash(intakeResult.case_id, intakeResult.id, "MANUAL");
      setVerificationResult(res);
    } catch (err) {
      setVerificationError(err instanceof Error ? err.message : "Hash verification failed.");
    } finally {
      setVerifying(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      {/* Title & Introduction */}
      <div>
        <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-integrity-teal/10 border border-integrity-teal/30 text-integrity-teal text-xs font-mono mb-2">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Cryptographic Chain-of-Custody Intake</span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
          Secure Evidence Intake Vault
        </h2>
        <p className="mt-1 text-sm text-forensic-400">
          Upload media bitstreams (images, audio, video) directly into isolated case vaults with
          server-side signature validation, bounded memory streaming, and baseline SHA-256 calculation.
        </p>
      </div>

      {/* Main Upload Card */}
      <div className="rounded-2xl bg-forensic-900 border border-forensic-800 p-6 sm:p-8 shadow-xl space-y-6">
        <form onSubmit={handleUploadSubmit} className="space-y-6">
          {/* Step 1: Scoped Case Selection */}
          <div>
            <label className="block text-xs font-mono text-forensic-300 uppercase tracking-wider mb-2 flex items-center space-x-2">
              <FolderLock className="w-4 h-4 text-integrity-cyan" />
              <span>Target Investigation Case Vault (Access Controlled)</span>
            </label>

            {loadingCases ? (
              <div className="h-10 bg-forensic-850 rounded-lg animate-pulse" />
            ) : cases.length === 0 ? (
              <div className="p-3 bg-alert-warning/10 border border-alert-warning/30 rounded-lg text-xs text-alert-warning font-mono">
                No authorized cases found. Please create or join an investigation case first.
              </div>
            ) : (
              <select
                value={selectedCaseId}
                onChange={(e) => setSelectedCaseId(e.target.value)}
                disabled={uploading}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-integrity-cyan font-mono"
              >
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.case_number} — {c.title}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Step 2: Custom Evidence Number (Optional) */}
          <div>
            <label className="block text-xs font-mono text-forensic-300 uppercase tracking-wider mb-2">
              Evidence Identifier / Property Tag (Optional)
            </label>
            <input
              type="text"
              value={evidenceNumber}
              onChange={(e) => setEvidenceNumber(e.target.value)}
              placeholder="Auto-generated (e.g. EVD-CAS-2026-0001-A4F9)"
              disabled={uploading}
              className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3.5 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan font-mono text-xs"
            />
          </div>

          {/* Step 3: Drag & Drop Intake Zone */}
          <div>
            <label className="block text-xs font-mono text-forensic-300 uppercase tracking-wider mb-2 flex items-center space-x-2">
              <FileCheck2 className="w-4 h-4 text-integrity-emerald" />
              <span>Evidence Media Bitstream (Image, Audio, Video)</span>
            </label>

            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                dragActive
                  ? "border-integrity-cyan bg-integrity-cyan/5"
                  : file
                  ? "border-integrity-emerald/60 bg-integrity-emerald/5"
                  : "border-forensic-700 hover:border-forensic-600 bg-forensic-850/50"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,audio/*,video/*"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileSelection(e.target.files[0]);
                  }
                }}
                className="hidden"
              />

              {file ? (
                <div className="space-y-2">
                  <div className="w-12 h-12 rounded-full bg-integrity-emerald/10 text-integrity-emerald flex items-center justify-center mx-auto">
                    {file.type.startsWith("image/") ? (
                      <FileImage className="w-6 h-6" />
                    ) : file.type.startsWith("audio/") ? (
                      <FileAudio className="w-6 h-6" />
                    ) : (
                      <FileVideo className="w-6 h-6" />
                    )}
                  </div>
                  <div className="text-sm font-semibold text-white">{file.name}</div>
                  <div className="text-xs font-mono text-forensic-400">
                    {formatBytes(file.size)} &bull; {file.type || "binary stream"}
                  </div>
                  <div className="text-xs text-integrity-cyan pt-1">Click to replace file</div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="w-12 h-12 rounded-full bg-forensic-800 text-forensic-400 flex items-center justify-center mx-auto">
                    <UploadCloud className="w-6 h-6" />
                  </div>
                  <div>
                    <span className="text-sm font-medium text-white">
                      Drop evidence bitstream here or{" "}
                      <span className="text-integrity-cyan underline">browse</span>
                    </span>
                    <p className="text-xs text-forensic-400 mt-1">
                      Accepts JPEG, PNG, GIF, WebP, WAV, MP3, FLAC, MP4, MOV, WebM, MKV
                    </p>
                  </div>
                  <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded bg-forensic-800 text-[11px] text-forensic-400 font-mono">
                    <Scale className="w-3 h-3 text-forensic-400" />
                    <span>Exact bytes preserved untouched &bull; Max 5 GB stream limit</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Validation Feedback Warnings */}
          {validationWarning && (
            <div className="p-3.5 rounded-lg bg-alert-warning/10 border border-alert-warning/30 text-xs text-alert-warning flex items-start space-x-2">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{validationWarning}</span>
            </div>
          )}

          {uploadError && (
            <div className="p-3.5 rounded-lg bg-red-950/60 border border-red-800 text-xs text-red-200 flex items-start space-x-2 font-mono">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <strong>Intake Rejected:</strong> {uploadError}
              </div>
            </div>
          )}

          {/* Progress Bar */}
          {uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-mono text-forensic-300">
                <span className="flex items-center space-x-1.5">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-integrity-cyan" />
                  <span>Streaming chunks to isolated staging vault...</span>
                </span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-forensic-800 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-integrity-teal to-integrity-cyan h-2 rounded-full transition-all duration-200"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Submit Action */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={uploading || !file || !selectedCaseId}
              className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-integrity-teal to-integrity-cyan text-forensic-950 font-bold text-sm hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-integrity-cyan disabled:opacity-40 transition-all shadow-lg flex items-center justify-center space-x-2"
            >
              <UploadCloud className="w-4 h-4" />
              <span>{uploading ? "Ingesting Evidence..." : "Ingest & Cryptographically Baseline"}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Intake Success Card */}
      {intakeResult && (
        <div className="rounded-2xl bg-gradient-to-br from-forensic-900 to-forensic-850 border border-integrity-emerald/40 p-6 sm:p-8 shadow-2xl space-y-6 relative overflow-hidden animate-in fade-in duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-forensic-800">
            <div className="flex items-center space-x-3">
              <div className="p-3 rounded-xl bg-integrity-emerald/20 text-integrity-emerald border border-integrity-emerald/40">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[10px] font-mono text-integrity-emerald uppercase tracking-wider font-semibold">
                  Intake Success &bull; Chain of Custody Initialized
                </span>
                <h3 className="text-xl font-bold text-white">
                  Evidence Vault Record #{intakeResult.evidence_number}
                </h3>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
                STATUS: {intakeResult.intake_status || "INTACT"}
              </span>
            </div>
          </div>

          {/* Metadata Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
            <div className="bg-forensic-800/60 p-3.5 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[11px] mb-1">Server Evidence ID</span>
              <span className="text-white font-bold select-all break-all">{intakeResult.id}</span>
            </div>

            <div className="bg-forensic-800/60 p-3.5 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[11px] mb-1">Detected Media Type</span>
              <span className="text-integrity-cyan font-bold block">{intakeResult.media_type}</span>
              <span className="text-forensic-400 text-[10px]">{intakeResult.mime_type}</span>
            </div>

            <div className="bg-forensic-800/60 p-3.5 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[11px] mb-1">Stored Byte Size</span>
              <span className="text-white font-bold block">{formatBytes(intakeResult.file_size_bytes)}</span>
              <span className="text-forensic-400 text-[10px]">({intakeResult.file_size_bytes.toLocaleString()} bytes)</span>
            </div>

            <div className="bg-forensic-800/60 p-3.5 rounded-lg border border-forensic-750">
              <span className="text-forensic-400 block text-[11px] mb-1">Receipt Timestamp</span>
              <span className="text-white block font-bold">
                {new Date(intakeResult.ingested_at).toLocaleTimeString()}
              </span>
              <span className="text-forensic-400 text-[10px]">
                {new Date(intakeResult.ingested_at).toLocaleDateString()}
              </span>
            </div>
          </div>

          {/* SHA-256 Hash Display */}
          <div className="bg-forensic-950 p-4 rounded-xl border border-forensic-750 space-y-1.5">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-integrity-teal font-semibold flex items-center space-x-1.5">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Primary SHA-256 Cryptographic Baseline</span>
              </span>
              <button
                onClick={() => handleCopyHash(intakeResult.primary_hash_sha256)}
                className="inline-flex items-center space-x-1 text-forensic-400 hover:text-white transition-colors text-[11px]"
              >
                {copiedHash ? <Check className="w-3.5 h-3.5 text-integrity-emerald" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedHash ? "Copied" : "Copy Hash"}</span>
              </button>
            </div>
            <div className="font-mono text-sm text-forensic-100 break-all select-all bg-forensic-900 p-2 rounded border border-forensic-800">
              {intakeResult.primary_hash_sha256}
            </div>
            <div className="flex flex-wrap gap-4 pt-1 text-[11px] font-mono text-forensic-400">
              <span>MD5: <code className="text-forensic-300">{intakeResult.hash_md5}</code></span>
              <span>SHA-1: <code className="text-forensic-300">{intakeResult.hash_sha1}</code></span>
            </div>
          </div>

          {/* Legal / Forensic Admissibility Notice */}
          <div className="p-4 rounded-xl bg-integrity-cyan/5 border border-integrity-cyan/20 text-xs text-forensic-300 space-y-1">
            <div className="font-semibold text-integrity-cyan flex items-center space-x-1.5">
              <Scale className="w-4 h-4" />
              <span>Courtroom Admissibility Notice (Integrity vs. Authenticity)</span>
            </div>
            <p className="text-forensic-400 leading-relaxed">
              {intakeResult.integrity_notice}
            </p>
          </div>

          {/* Actions & Verification */}
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-forensic-800">
            <span className="text-xs text-forensic-400 font-mono">
              Perform deep forensic inspection or bitstream verification
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleIndependentVerify}
                disabled={verifying}
                className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-xs text-white font-mono transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${verifying ? "animate-spin text-integrity-cyan" : ""}`} />
                <span>{verifying ? "Recalculating..." : "Verify Vault Integrity"}</span>
              </button>

              <Link
                href={`/cases/${intakeResult.case_id}/evidence/${intakeResult.id}`}
                className="inline-flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-integrity-teal text-forensic-950 font-semibold text-xs font-mono hover:bg-integrity-teal/90 transition-all shadow"
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Inspect Forensic Metadata</span>
              </Link>
            </div>
          </div>

          {/* Verification Result Display */}
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
                      ? "VAULT RE-VERIFICATION PASSED: BITSTREAM 100% INTACT"
                      : "CRITICAL ALERT: CRYPTOGRAPHIC HASH MISMATCH (TAMPER DETECTED)"}
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

          {verificationError && (
            <div className="p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 font-mono">
              Verification check failed: {verificationError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function EvidenceUploadPage(): React.JSX.Element {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-forensic-400 font-mono text-xs animate-pulse">
          Loading evidence intake console...
        </div>
      }
    >
      <EvidenceUploadContent />
    </Suspense>
  );
}
