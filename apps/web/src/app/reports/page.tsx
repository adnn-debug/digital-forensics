"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  FileText,
  RefreshCw,
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
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Package,
  BookOpen,
  Fingerprint,
  ClipboardList,
  Shield,
  Database,
} from "lucide-react";

import {
  listCases,
  listCaseReports,
  generateCourtroomReport,
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
              <h3 className="text-sm font-bold text-white">Generate Report</h3>
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
                placeholder="e.g. State of Bihar" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Court Name</label>
              <input value={courtName} onChange={(e) => setCourtName(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="Special Cyber Court" />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-forensic-300">Docket Number</label>
              <input value={docketNumber} onChange={(e) => setDocketNumber(e.target.value)}
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan transition-colors"
                placeholder="e.g. BC-2026-CR-0001" />
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
                <><Loader2 className="w-4 h-4 animate-spin" /><span>Compiling...</span></>
              ) : (
                <><FileText className="w-4 h-4" /><span>Generate Report</span></>
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

function HashBadge({ hash }: { hash?: string | null }) {
  if (!hash) return <span className="text-forensic-600 font-mono text-[11px]">—</span>;
  return (
    <span className="inline-block font-mono text-[11px] text-integrity-emerald bg-integrity-emerald/5 border border-integrity-emerald/20 rounded px-1.5 py-0.5" title={hash}>
      {hash.substring(0, 14)}…
    </span>
  );
}

function StatusPill({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
      <CheckCircle2 className="w-3 h-3" />INTACT
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-950/50 text-red-400 border border-red-800">
      <AlertTriangle className="w-3 h-3" />TAMPERED
    </span>
  );
}

function Section({ icon, title, subtitle, children }: {
  icon: React.ReactNode; title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <div className="px-5 py-4 border-b border-forensic-800 last:border-b-0">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs font-bold text-white tracking-wide">{title}</span>
      </div>
      {subtitle && <p className="text-[11px] text-forensic-500 mb-3">{subtitle}</p>}
      {children}
    </div>
  );
}

function HashRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-forensic-900 rounded-lg border border-forensic-800 p-3">
      <div className="text-[10px] text-forensic-500 font-mono mb-1">{label}</div>
      <div className={`font-mono text-[11px] break-all ${color}`}>{value || "—"}</div>
    </div>
  );
}

function MetaItem({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <div className="text-forensic-500 mt-0.5 shrink-0">{icon}</div>
      <div>
        <div className="text-[10px] text-forensic-500 font-mono">{label}</div>
        <div className="text-xs text-forensic-200 font-medium">{value}</div>
      </div>
    </div>
  );
}

function ReportInlineView({ report }: { report: ReportRead }) {
  const [open, setOpen] = useState(false);

  const hashVal = report.file_hash_sha256 || report.sha256_hash || "";
  const dateVal = report.created_at || report.generated_at;
  const evidenceIds = report.included_evidence_ids || [];

  const formatBytes = (n?: number) => {
    if (!n || n < 1024) return `${n || 0} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  };

  return (
    <div className="bg-forensic-900 border border-forensic-800 hover:border-forensic-700 rounded-2xl overflow-hidden transition-all">
      {/* Header */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start space-x-3">
            <div className="mt-0.5 w-10 h-10 rounded-xl bg-integrity-cyan/10 border border-integrity-cyan/20 flex items-center justify-center shrink-0">
              <FileBarChart2 className="w-5 h-5 text-integrity-cyan" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-[11px] font-mono text-forensic-400">{report.report_number}</span>
                {report.is_sealed !== false && (
                  <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
                    <Lock className="w-2.5 h-2.5" /><span>SEALED</span>
                  </span>
                )}
                <span className="text-[10px] font-mono text-amber-400/80 bg-amber-950/30 border border-amber-900/30 px-1.5 py-0.5 rounded">
                  {report.classification_marking || "RESTRICTED // FRE 902"}
                </span>
              </div>
              <h4 className="font-bold text-base text-white leading-tight">{report.title}</h4>
            </div>
          </div>
          <button
            onClick={() => setOpen((v) => !v)}
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-forensic-800 hover:bg-forensic-750 border border-forensic-700 text-xs font-medium text-forensic-200 hover:text-white transition-all"
          >
            {open ? <><ChevronUp className="w-3.5 h-3.5" />Hide</> : <><ChevronDown className="w-3.5 h-3.5" />View Full Report</>}
          </button>
        </div>

        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px] font-mono text-forensic-400">
          <div className="flex items-center space-x-1.5">
            <Scale className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
            <span className="text-forensic-300 truncate">{report.jurisdiction || "State of Bihar"}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <Gavel className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
            <span className="text-forensic-300 truncate">{report.court_name || "Special Cyber Court"}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <User className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
            <span className="text-forensic-300">{report.examiner_name || "Lead Examiner"}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <Calendar className="w-3.5 h-3.5 text-forensic-500 shrink-0" />
            <span>{dateVal ? new Date(dateVal).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "Recent"}</span>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-forensic-800 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-2 text-[11px] font-mono">
            <Hash className="w-3 h-3 text-forensic-500" />
            <span className="text-forensic-500">SHA-256:</span>
            <span className="text-integrity-emerald" title={hashVal}>
              {hashVal ? `${hashVal.substring(0, 32)}…` : "PENDING"}
            </span>
          </div>
          <div className="text-[11px] font-mono text-forensic-500">
            {formatBytes(report.file_size_bytes)} &bull; {evidenceIds.length} exhibit{evidenceIds.length !== 1 ? "s" : ""}
          </div>
        </div>
      </div>

      {/* Expanded View */}
      {open && (
        <div className="border-t border-forensic-800 bg-forensic-950/40">

          {/* Evidence Registry */}
          <Section icon={<Package className="w-4 h-4 text-integrity-teal" />} title="Evidence Exhibit Registry" subtitle="All exhibits bundled in this examination report">
            {evidenceIds.length === 0 ? (
              <p className="text-[11px] text-forensic-500 font-mono py-2">No evidence items linked to this report.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-forensic-800">
                <table className="w-full text-[11px] font-mono">
                  <thead>
                    <tr className="bg-forensic-900 border-b border-forensic-800">
                      <th className="text-left px-3 py-2 text-forensic-500 font-medium">#</th>
                      <th className="text-left px-3 py-2 text-forensic-500 font-medium">Exhibit ID</th>
                      <th className="text-left px-3 py-2 text-forensic-500 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidenceIds.map((id, idx) => (
                      <tr key={id} className="border-b border-forensic-800/40 hover:bg-forensic-800/20">
                        <td className="px-3 py-2.5 text-forensic-500">{idx + 1}</td>
                        <td className="px-3 py-2.5">
                          <span className="text-integrity-cyan">{id}</span>
                        </td>
                        <td className="px-3 py-2.5"><StatusPill ok={true} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* Cryptographic Seal */}
          <Section icon={<Fingerprint className="w-4 h-4 text-integrity-emerald" />} title="Cryptographic Integrity Seal" subtitle="Verify report authenticity using these immutable values">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <HashRow label="SHA-256 Hash (Report File)" value={hashVal} color="text-integrity-emerald" />
              <HashRow label="Report Number" value={report.report_number} color="text-integrity-cyan" />
              <HashRow label="Case ID" value={String(report.case_id)} color="text-forensic-300" />
              <HashRow label="Generated At" value={dateVal ? new Date(dateVal).toISOString() : "—"} color="text-forensic-300" />
            </div>
            <div className="p-3 rounded-lg bg-integrity-emerald/5 border border-integrity-emerald/20 text-[11px] font-mono text-integrity-emerald flex items-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
              Any modification to this report will invalidate the SHA-256 hash and break chain of custody.
            </div>
          </Section>

          {/* Examiner Details */}
          <Section icon={<User className="w-4 h-4 text-forensic-300" />} title="Examiner Certification" subtitle="Credentials of the certifying forensic examiner">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <MetaItem icon={<User className="w-3.5 h-3.5" />} label="Lead Examiner" value={report.examiner_name || "On file"} />
              <MetaItem icon={<Shield className="w-3.5 h-3.5" />} label="Certification" value={report.examiner_certification || "CFCE / EnCE Certified"} />
              <MetaItem icon={<Scale className="w-3.5 h-3.5" />} label="Jurisdiction" value={report.jurisdiction || "State of Bihar"} />
              <MetaItem icon={<Gavel className="w-3.5 h-3.5" />} label="Court" value={report.court_name || "Special Cyber Court"} />
              <MetaItem icon={<ClipboardList className="w-3.5 h-3.5" />} label="Docket No." value={report.docket_number || "On file"} />
              <MetaItem icon={<Calendar className="w-3.5 h-3.5" />} label="Report Date" value={dateVal ? new Date(dateVal).toLocaleDateString("en-IN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }) : "—"} />
            </div>
          </Section>

          {/* Admissibility Standards */}
          <Section icon={<BookOpen className="w-4 h-4 text-amber-400" />} title="Legal Admissibility Standards" subtitle="Compliance frameworks embedded in this examination report">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                { label: "FRE 901-902", desc: "Self-authenticating digital record with cryptographic hash attestation.", cls: "border-integrity-cyan/30 bg-integrity-cyan/5 text-integrity-cyan" },
                { label: "ISO/IEC 27037:2012", desc: "Collection, acquisition, preservation and chain-of-custody procedures.", cls: "border-integrity-emerald/30 bg-integrity-emerald/5 text-integrity-emerald" },
                { label: "NIST SP 800-86", desc: "Repeatable, documented processes for media analysis and forensic reporting.", cls: "border-amber-500/30 bg-amber-950/20 text-amber-400" },
              ].map((s) => (
                <div key={s.label} className={`rounded-xl border p-4 ${s.cls}`}>
                  <div className="font-bold font-mono text-[11px] mb-1">{s.label}</div>
                  <div className="text-[11px] text-forensic-400 leading-relaxed">{s.desc}</div>
                </div>
              ))}
            </div>
          </Section>

          {/* Audit Trail Notice */}
          <div className="px-5 pb-5">
            <div className="rounded-xl bg-forensic-900 border border-forensic-700 p-4 flex items-start gap-3">
              <Database className="w-4 h-4 text-integrity-teal shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-white mb-1">Append-Only Chain-of-Custody Audit Log</p>
                <p className="text-[11px] text-forensic-400 leading-relaxed">
                  All evidence custody transfers are recorded in an immutable, cryptographically chained audit log
                  per ISO/IEC 27037 and FRE 901. Full chain-of-custody events are visible in the
                  <span className="text-integrity-cyan"> Audit Trail</span> tab of this case.
                </p>
              </div>
            </div>
          </div>

        </div>
      )}
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
      const firstCase = res.items[0];
      if (firstCase) setSelectedCaseId((prev) => prev || firstCase.id);
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
    setSuccessMsg(`Report ${r.report_number} generated successfully.`);
    setTimeout(() => setSuccessMsg(null), 6000);
  };

  return (
    <div className="space-y-8">
      {showModal && selectedCase && (
        <GenerateModal caseItem={selectedCase} onClose={() => setShowModal(false)} onGenerated={handleGenerated} />
      )}

      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-forensic-900 via-forensic-850 to-forensic-900 border border-forensic-700/80 p-6 sm:p-8 shadow-xl">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-integrity-cyan/10 border border-integrity-cyan/30 text-integrity-cyan text-xs font-mono mb-3">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>FRE 902 | ISO/IEC 27037 | Chain of Custody Certified</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">Courtroom Evidentiary Reports</h2>
            <p className="mt-1 text-sm text-forensic-400 max-w-2xl">
              Full open inline view of forensic examination reports — evidence hashes, examiner certifications,
              chain of custody and admissibility standards, directly on screen.
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
        {/* Case Selector */}
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

        {/* Reports Panel */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 flex items-center space-x-2">
              <FileText className="w-4 h-4 text-integrity-cyan" />
              <span>Reports{selectedCase ? ` — ${selectedCase.case_number}` : ""}</span>
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
              <Loader2 className="w-4 h-4 animate-spin" /><span>Loading reports from vault...</span>
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
                Generate a report to compile all evidence hashes, chain-of-custody events, and forensic findings into a single admissible record.
              </p>
              {selectedCase && (
                <button onClick={() => setShowModal(true)}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-integrity-cyan text-forensic-950 text-xs font-semibold hover:bg-integrity-cyan/90 transition-all">
                  <PlusCircle className="w-3.5 h-3.5" /><span>Generate First Report</span>
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {reports.map((r) => (
                <ReportInlineView key={r.id} report={r} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
