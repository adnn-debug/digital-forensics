"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { FolderOpen, Plus, ArrowUpRight, UploadCloud, RefreshCw, AlertCircle } from "lucide-react";
import { listCases, createCase, CaseItem } from "@/lib/api";

export default function CasesPage(): React.JSX.Element {
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Form State
  const [caseNumber, setCaseNumber] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const loadCases = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listCases();
      setCases(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cases.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCases();
  }, []);

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const payload: { case_number: string; title: string; description?: string } = {
        case_number: caseNumber.trim(),
        title: title.trim(),
      };
      if (description.trim()) {
        payload.description = description.trim();
      }
      await createCase(payload);
      setShowCreateModal(false);
      setCaseNumber("");
      setTitle("");
      setDescription("");
      await loadCases();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create case.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-forensic-800">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-3">
            <FolderOpen className="w-6 h-6 text-integrity-teal" />
            <span>Authorized Investigation Cases</span>
          </h2>
          <p className="text-sm text-forensic-400 mt-1">
            Access-controlled case vaults scoped to authorized forensic investigators.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={loadCases}
            disabled={loading}
            className="p-2 rounded-lg bg-forensic-850 hover:bg-forensic-800 border border-forensic-700 text-forensic-300 transition-colors"
            title="Refresh cases"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-integrity-cyan" : ""}`} />
          </button>

          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-integrity-teal text-forensic-950 font-medium text-xs hover:bg-integrity-teal/90 transition-all shadow"
          >
            <Plus className="w-4 h-4" />
            <span>New Investigation Case</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Case Creation Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-forensic-900 border border-forensic-700 rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Create New Case Vault</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-forensic-400 hover:text-white"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateCase} className="space-y-4">
              <div>
                <label className="block text-xs font-mono text-forensic-300 mb-1 uppercase tracking-wider">
                  Case Number (e.g. CAS-2026-0042)
                </label>
                <input
                  type="text"
                  required
                  value={caseNumber}
                  onChange={(e) => setCaseNumber(e.target.value)}
                  placeholder="CAS-2026-0001"
                  className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-teal font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-forensic-300 mb-1 uppercase tracking-wider">
                  Investigation Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Cyber Incident Financial Forensics"
                  className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-teal"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-forensic-300 mb-1 uppercase tracking-wider">
                  Description / Warrant Reference (Optional)
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Federal search warrant docket #4492-X"
                  className="w-full bg-forensic-850 border border-forensic-700 rounded-lg px-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-teal"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-forensic-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-forensic-800 hover:bg-forensic-750 text-xs text-forensic-300 font-mono"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 rounded-lg bg-integrity-teal text-forensic-950 font-semibold text-xs hover:bg-integrity-teal/90 disabled:opacity-50 font-mono"
                >
                  {creating ? "Creating..." : "Initialize Vault"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Case Grid */}
      {loading ? (
        <div className="p-12 text-center text-forensic-400 font-mono text-xs animate-pulse">
          Querying authorized cases from database...
        </div>
      ) : cases.length === 0 ? (
        <div className="p-12 text-center rounded-xl bg-forensic-900 border border-forensic-800 space-y-3">
          <FolderOpen className="w-10 h-10 text-forensic-500 mx-auto" />
          <h3 className="text-sm font-semibold text-white">No active cases found</h3>
          <p className="text-xs text-forensic-400 max-w-sm mx-auto">
            You currently do not lead any cases. Create a new case or log in with an examiner/admin account.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-integrity-teal text-forensic-950 text-xs font-medium"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create First Case</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map((c) => (
            <div
              key={c.id}
              className="rounded-xl bg-forensic-900 border border-forensic-800 hover:border-forensic-700 p-5 space-y-4 transition-all shadow-md group"
            >
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-mono text-xs text-integrity-cyan font-bold tracking-wider">
                    {c.case_number}
                  </span>
                  <h3 className="text-base font-semibold text-white mt-1 group-hover:text-integrity-teal transition-colors">
                    {c.title}
                  </h3>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30">
                  {c.status}
                </span>
              </div>

              {c.description && (
                <p className="text-xs text-forensic-400 line-clamp-2">{c.description}</p>
              )}

              <div className="pt-3 border-t border-forensic-800 flex items-center justify-between text-xs font-mono text-forensic-500">
                <Link
                  href={`/cases/${c.id}`}
                  className="inline-flex items-center space-x-1 text-integrity-teal hover:underline transition-colors"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span>View Vault Evidence</span>
                </Link>

                <Link
                  href={`/upload?case_id=${c.id}`}
                  className="inline-flex items-center space-x-1 text-integrity-cyan hover:text-white transition-colors"
                >
                  <UploadCloud className="w-3.5 h-3.5" />
                  <span>Intake</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
