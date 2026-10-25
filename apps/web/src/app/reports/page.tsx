"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  FileText,
  RefreshCw,
  Download,
  ShieldCheck,
  Lock,
  FolderOpen,
  AlertCircle,
  PlusCircle,
  X,
  Loader2,
  Hash,
  Calendar,
  User,
  Scale,
  Gavel,
  FileBarChart2,
} from "lucide-react";

import {
  listCases,
  listCaseReports,
  generateCourtroomReport,
  getReportDownloadUrl,
  CaseItem,
  ReportRead,
} from "@/lib/api";

function GenerateModal({
  caseItem,
  onClose,
  onGenerated,
}: {
  caseItem: CaseItem;
  onClose: () => void;
  onGenerated: (r: ReportRead) => void;
}) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState(`Forensic Examination Report — ${caseItem.title}`);
  const [certId, setCertId] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [courtName, setCourtName] = useState("");
  const [docketNumber, setDocketNumber] = useState("");
  const [classification, setClassification] = useState("CONFIDENTIAL // FOR OFFICIAL USE ONLY");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerating(true);
    setError(null);
    try {
      const report = await generateCourtroomReport(caseItem.id, {
        title: title.trim() || undefined,
        examiner_certification: certId.trim() || undefined,
        jurisdiction: jurisdiction.trim() || undefined,
        court_name: courtName.trim() || undefined,
        docket_number: docketNumber.trim() || undefined,
        classification_marking: classification.trim() || undefined,
      });
      onGenerated(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report generation failed.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-xl bg-forensic-900 border border-forensic-700 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-forensic-800 bg-forensic-850">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-integrity-cyan/10 border border-integrity-cyan/30 flex items-center justify-center">
              <Gavel className="w-4 h-4 text-integrity-cyan" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">Generate Sealed Report</h3>
              <p className="text-[11px] text-forensic-400 font-mono">{caseItem.case_number}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-forensic-800 text-forensic-400 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="flex items-start space-x-2 p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
          <div className="space-y-1">
            <label className="block text-xs font-medium text-forensic-300">Report Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
              placeholder="Forensic Examination Report" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Examiner Cert. ID</label>
              <input value={certId} onChange={(e) => setCertId(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="e.g. CFCE-12345" />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Jurisdiction</label>
              <input value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="e.g. Federal — E.D. Va." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Court Name</label>
              <input value={courtName} onChange={(e) => setCourtName(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="U.S. District Court" />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Docket Number</label>
              <input value={docketNumber} onChange={(e) => setDocketNumber(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="e.g. 1:24-cr-00123" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="block text-xs font-medium text-forensic-300">Classification Marking</label>
            <input value={classification} onChange={(e) => setClassification(e.target.value)}
              className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors font-mono"
              placeholder="CONFIDENTIAL // FOR OFFICIAL USE ONLY" />
          </div>
          <div className="pt-2 flex items-center space-x-3">
            <button type="submit" disabled={generating}
              className="flex-1 inline-flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg bg-integrity-cyan text-forensic-950 font-semibold text-sm hover:bg-integrity-cyan/90 transition-all disabled:opacity-50">
              {generating ? (
                <><Loader2 className="w-4 h-4 animate-spin" /><span>Compiling and Sealing PDF</span></>
              ) : (
                <><FileText className="w-4 h-4" /><span>Generate Sealed Report</span></>
              )}
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2.5 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-sm text-forensic-200 transition-colors">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ReportCard({ report, caseId }: { report: ReportRead; caseId: string }) {
  const formatBytes = (n: number) => {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  };
  return (
    <div className="group bg-forensic-900 border border-forensic-800 hover:border-forensic-700 rounded-xl p-5 transition-all">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-start space-x-3">
          <div className="mt-0.5 w-9 h-9 rounded-lg bg-integrity-cyan/10 border border-integrity-cyan/20 flex items-center justify-center shrink-0">
            <FileBarChart2 className="w-5 h-5 text-integrity-cyan" />
          </div>
          <div>
            <h4 className="font-semibold text-sm text-white leading-tight">{report.title}</h4>
            <div className="flex flex-wrap items-center gap-2 mt-0.5">
              <span className="text-[11px] font-mono text-forensic-400">{report.report_number}</span>
              {report.is_sealed && (
                <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
                  <Lock className="w-2.5 h-2.5" /><span>SEALED</span>
                </span>
              )}
              <span className="text-[10px] font-mono text-amber-400/80 bg-amber-950/30 border border-amber-900/30 px-1.5 py-0.5 rounded">
                {report.classification_marking}
              </span>
            </div>
          </div>
        </div>
        <a href={getReportDownloadUrl(caseId, report.id)} download
          className="shrink-0 inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-integrity-teal text-forensic-950 font-semibold text-xs hover:bg-integrity-teal/90 transition-all shadow">
          <Download className="w-3.5 h-3.5" /><span>Download PDF</span>
        </a>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px] font-mono text-forensic-400">
        <div className="flex items-center space-x-1.5">
          <Scale className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
          <span className="text-forensic-300 truncate">{report.jurisdiction || "N/A"}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <Gavel className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
          <span className="text-forensic-300 truncate">{report.court_name || "N/A"}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <User className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
          <span className="text-forensic-300">{report.examiner_name}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <Calendar className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
          <span>{new Date(report.generated_at).toLocaleDateString()}</span>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-forensic-800 flex items-center justify-between">
        <div className="flex items-center space-x-2 text-[11px] font-mono">
          <Hash className="w-3 h-3 text-forensic-500" />
          <span className="text-forensic-500">SHA-256:</span>
          <span className="text-integrity-emerald truncate max-w-[200px] sm:max-w-xs">{report.sha256_hash.substring(0, 32)}...</span>
        </div>
        <div className="text-[11px] font-mono text-forensic-500">
          {formatBytes(report.file_size_bytes)} &bull; {report.evidence_count} exhibits
        </div>
      </div>
    </div>
  );
}

export default function CourtroomReportsPage(): React.JSX.Element {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [reports, setReports] = useState<ReportRead[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loadingReports, setLoadingReports] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadCases = useCallback(async () => {
    setLoadingCases(true);
    try {
      const res = await listCases();
      setCases(res.items);
      const firstCase = res.items[0]; if (firstCase) setSelectedCaseId((prev) => prev || firstCase.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cases.");
    } finally {
      setLoadingCases(false);
    }
  }, []);

  const loadReports = useCallback(async () => {
    if (!selectedCaseId) return;
    setLoadingReports(true);
    setError(null);
    try {
      const res = await listCaseReports(selectedCaseId);
      setReports(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reports.");
      setReports([]);
    } finally {
      setLoadingReports(false);
    }
  }, [selectedCaseId]);

  useEffect(() => { loadCases(); }, [loadCases]);
  useEffect(() => { if (selectedCaseId) loadReports(); }, [selectedCaseId, loadReports]);

  const selectedCase = cases.find((c) => c.id === selectedCaseId) ?? null;

  const handleGenerated = (r: ReportRead) => {
    setShowModal(false);
    setReports((prev) => [r, ...prev]);
    setSuccessMsg(`Report ${r.report_number} generated and sealed successfully.`);
    setTimeout(() => setSuccessMsg(null), 6000);
  };

  return (
    <div className="space-y-8">
      {showModal && selectedCase && (
        <GenerateModal caseItem={selectedCase} onClose={() => setShowModal(false)} onGenerated={handleGenerated} />
      )}

      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-forensic-900 via-forensic-850 to-forensic-900 border border-forensic-700/80 p-6 sm:p-8 shadow-xl">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-integrity-cyan/10 border border-integrity-cyan/30 text-integrity-cyan text-xs font-mono mb-3">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>FRE 902 | ISO/IEC 27037 | Chain of Custody Certified</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">Courtroom Evidentiary Reports</h2>
            <p className="mt-1 text-sm text-forensic-400 max-w-2xl">
              Generate, manage and download cryptographically sealed PDF examination reports
              admissible under Federal Rules of Evidence with embedded SHA-256 QR verification seals.
            </p>
          </div>
          <button onClick={() => setShowModal(true)} disabled={!selectedCase}
            className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-lg bg-integrity-cyan text-forensic-950 font-semibold text-sm hover:bg-integrity-cyan/90 transition-all shadow disabled:opacity-40">
            <PlusCircle className="w-4 h-4" /><span>Generate Report</span>
          </button>
        </div>
      </div>

      {successMsg && (
        <div className="flex items-center space-x-2 p-3.5 rounded-xl bg-integrity-emerald/10 border border-integrity-emerald/30 text-sm text-integrity-emerald">
          <ShieldCheck className="w-4 h-4 shrink-0" /><span>{successMsg}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1 space-y-2">
          <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-3 flex items-center space-x-2">
            <FolderOpen className="w-4 h-4 text-integrity-teal" /><span>Select Case</span>
          </h3>
          {loadingCases ? (
            <div className="text-xs text-forensic-500 font-mono animate-pulse">Loading cases...</div>
          ) : cases.length === 0 ? (
            <div className="text-xs text-forensic-500 font-mono">No cases found.</div>
          ) : (
            <div className="space-y-1">
              {cases.map((c) => (
                <button key={c.id} onClick={() => setSelectedCaseId(c.id)}
                  className={`w-full text-left px-3.5 py-2.5 rounded-lg border text-xs font-mono transition-all ${c.id === selectedCaseId
                    ? "bg-integrity-teal/10 border-integrity-teal/50 text-integrity-teal"
                    : "bg-forensic-900 border-forensic-800 hover:border-forensic-700 text-forensic-300 hover:text-white"}`}>
                  <div className="font-bold truncate">{c.case_number}</div>
                  <div className="text-[11px] text-forensic-400 truncate mt-0.5">{c.title}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 flex items-center space-x-2">
              <FileText className="w-4 h-4 text-integrity-cyan" />
              <span>Sealed Reports{selectedCase ? ` - ${selectedCase.case_number}` : ""}</span>
            </h3>
            <button onClick={loadReports} disabled={loadingReports || !selectedCaseId}
              className="p-1.5 rounded-lg hover:bg-forensic-800 border border-forensic-800 text-forensic-400 hover:text-white transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${loadingReports ? "animate-spin text-integrity-cyan" : ""}`} />
            </button>
          </div>

          {error && (
            <div className="flex items-center space-x-2 p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200">
              <AlertCircle className="w-4 h-4 shrink-0" /><span>{error}</span>
            </div>
          )}

          {loadingReports ? (
            <div className="flex items-center space-x-2 text-xs text-forensic-500 font-mono animate-pulse p-4">
              <Loader2 className="w-4 h-4 animate-spin" /><span>Loading sealed reports from vault...</span>
            </div>
          ) : !selectedCaseId ? (
            <div className="py-12 text-center rounded-xl border border-dashed border-forensic-800">
              <FolderOpen className="w-10 h-10 text-forensic-600 mx-auto mb-3" />
              <p className="text-sm text-forensic-400">Select a case to view its reports.</p>
            </div>
          ) : reports.length === 0 ? (
            <div className="py-12 text-center rounded-xl border border-dashed border-forensic-800">
              <FileText className="w-10 h-10 text-forensic-600 mx-auto mb-3" />
              <h4 className="text-sm font-semibold text-white mb-1">No reports yet</h4>
              <p className="text-xs text-forensic-400 max-w-sm mx-auto mb-4">
                Generate a sealed courtroom-admissible PDF report bundling all evidence hashes, chain-of-custody events, and forensic findings.
              </p>
              {selectedCase && (
                <button onClick={() => setShowModal(true)}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-integrity-cyan text-forensic-950 text-xs font-semibold hover:bg-integrity-cyan/90 transition-all">
                  <PlusCircle className="w-3.5 h-3.5" /><span>Generate First Report</span>
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {reports.map((r) => <ReportCard key={r.id} report={r} caseId={selectedCase!.id} />)}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl bg-forensic-900 border border-forensic-800 p-5">
        <h4 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-4 flex items-center space-x-2">
          <ShieldCheck className="w-4 h-4 text-integrity-emerald" /><span>Admissibility Standards Compliance</span>
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
          {[
            { label: "Federal Rules of Evidence", code: "FRE 901-902", desc: "Self-authenticating digital records with cryptographic hash attestation." },
            { label: "ISO/IEC 27037:2012", code: "Digital Evidence Guidelines", desc: "Collection, acquisition, preservation, and chain-of-custody procedures." },
            { label: "NIST SP 800-86", code: "Guide to Integrating Forensic", desc: "Repeatable, documented processes for media analysis and reporting." },
          ].map((s) => (
            <div key={s.code} className="bg-forensic-850 rounded-lg border border-forensic-700/60 p-4">
              <div className="text-integrity-emerald font-bold mb-0.5">{s.label}</div>
              <div className="text-forensic-400 text-[10px] mb-1.5">{s.code}</div>
              <div className="text-forensic-400">{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
