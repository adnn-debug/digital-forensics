"use client";

import React, { useEffect, useState, useCallback, use } from "react";
import Link from "next/link";
import {
  FolderOpen,
  ArrowLeft,
  UploadCloud,
  FileText,
  FileImage,
  FileAudio,
  FileVideo,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  Database,
} from "lucide-react";
import { listCases, listEvidence, CaseItem, EvidenceItem } from "@/lib/api";

interface CaseDetailPageProps {
  params: Promise<{ caseId: string }>;
}

export default function CaseDetailPage({ params }: CaseDetailPageProps): React.JSX.Element {
  const resolvedParams = use(params);
  const caseId = resolvedParams.caseId;

  const [currentCase, setCurrentCase] = useState<CaseItem | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [casesRes, evidenceRes] = await Promise.all([
        listCases(),
        listEvidence(caseId).catch((err) => {
          console.warn("Evidence fetch warning:", err);
          return [] as EvidenceItem[];
        }),
      ]);

      const found = casesRes.items.find((c) => c.id === caseId);
      if (found) {
        setCurrentCase(found);
      }
      setEvidenceList(evidenceRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load case evidence.");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const getMediaIcon = (mediaType: string) => {
    switch (mediaType) {
      case "IMAGE":
        return <FileImage className="w-4 h-4 text-integrity-teal" />;
      case "AUDIO":
        return <FileAudio className="w-4 h-4 text-integrity-cyan" />;
      case "VIDEO":
        return <FileVideo className="w-4 h-4 text-integrity-blue" />;
      default:
        return <FileText className="w-4 h-4 text-forensic-400" />;
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
    <div className="space-y-6">
      {/* Navigation & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-forensic-800">
        <div className="space-y-1">
          <Link
            href="/cases"
            className="inline-flex items-center space-x-1.5 text-xs text-forensic-400 hover:text-white transition-colors font-mono mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to All Cases</span>
          </Link>

          <div className="flex items-center space-x-3">
            <h2 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-3">
              <FolderOpen className="w-6 h-6 text-integrity-teal" />
              <span>{currentCase ? currentCase.title : "Investigation Case Vault"}</span>
            </h2>
            {currentCase && (
              <span className="px-2 py-0.5 rounded text-xs font-mono bg-integrity-teal/10 text-integrity-teal border border-integrity-teal/30">
                {currentCase.case_number}
              </span>
            )}
          </div>
          {currentCase?.description && (
            <p className="text-xs text-forensic-400 max-w-2xl">{currentCase.description}</p>
          )}
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg bg-forensic-850 hover:bg-forensic-800 border border-forensic-700 text-forensic-300 transition-colors"
            title="Refresh evidence vault"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-integrity-cyan" : ""}`} />
          </button>

          <Link
            href={`/upload?case_id=${caseId}`}
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-integrity-teal text-forensic-950 font-semibold text-xs hover:bg-integrity-teal/90 transition-all shadow"
          >
            <UploadCloud className="w-4 h-4" />
            <span>Intake New Evidence</span>
          </Link>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Evidence Table */}
      <div className="rounded-xl bg-forensic-900 border border-forensic-800 overflow-hidden shadow-xl">
        <div className="p-4 border-b border-forensic-800 bg-forensic-850/50 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs font-mono text-forensic-300">
            <Database className="w-4 h-4 text-integrity-teal" />
            <span>Vault Evidentiary Bitstreams ({evidenceList.length})</span>
          </div>
          <span className="text-[11px] text-forensic-400 font-mono">
            Immutable physical storage &bull; Read-only permissions enforced
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-forensic-400 font-mono text-xs animate-pulse">
            Querying evidentiary files from vault...
          </div>
        ) : evidenceList.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <FolderOpen className="w-10 h-10 text-forensic-600 mx-auto" />
            <h3 className="text-sm font-semibold text-white">No evidence files in vault</h3>
            <p className="text-xs text-forensic-400 max-w-sm mx-auto">
              Intake evidentiary image, audio, or video files into this case to begin automated metadata extraction and forensic analysis.
            </p>
            <Link
              href={`/upload?case_id=${caseId}`}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-integrity-teal text-forensic-950 text-xs font-medium"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              <span>Intake First Evidence</span>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-forensic-850/80 text-forensic-400 uppercase tracking-wider text-[11px] border-b border-forensic-800">
                <tr>
                  <th className="py-3 px-4">Evidence #</th>
                  <th className="py-3 px-4">Original Filename</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Size</th>
                  <th className="py-3 px-4">SHA-256 Baseline</th>
                  <th className="py-3 px-4">Ingested At</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-forensic-800 text-forensic-200">
                {evidenceList.map((item) => (
                  <tr key={item.id} className="hover:bg-forensic-850/40 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-integrity-teal">
                      <Link
                        href={`/cases/${caseId}/evidence/${item.id}`}
                        className="hover:underline flex items-center space-x-1"
                      >
                        <span>{item.evidence_number}</span>
                      </Link>
                    </td>
                    <td className="py-3.5 px-4 text-white font-medium max-w-[200px] truncate" title={item.original_filename}>
                      {item.original_filename}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center space-x-1.5 px-2 py-0.5 rounded bg-forensic-800 border border-forensic-700 text-[10px]">
                        {getMediaIcon(item.media_type)}
                        <span>{item.media_type}</span>
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-forensic-300">
                      {formatBytes(item.file_size_bytes)}
                    </td>
                    <td className="py-3.5 px-4 text-forensic-400 font-mono text-[11px]">
                      <span title={item.primary_hash_sha256}>
                        {item.primary_hash_sha256.substring(0, 16)}...
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-forensic-400 text-[11px]">
                      {new Date(item.ingested_at).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <Link
                        href={`/cases/${caseId}/evidence/${item.id}`}
                        className="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-integrity-cyan hover:text-white transition-colors text-[11px]"
                      >
                        <span>Inspect Metadata</span>
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
