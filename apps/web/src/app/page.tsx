"use client";

import React, { useEffect, useState } from "react";
import { ShieldAlert, RefreshCw, Layers, CheckCircle, Database, Server, FolderLock } from "lucide-react";
import { fetchHealth, fetchReadiness, SystemHealth, SystemReadiness } from "@/lib/api";
import { StatusCard } from "@/components/StatusCard";

export default function OperationalConsole(): React.JSX.Element {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<string>("");

  const refreshDiagnostics = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthData, readyData] = await Promise.all([
        fetchHealth().catch((e) => {
          console.warn("Health check error:", e);
          return null;
        }),
        fetchReadiness().catch((e) => {
          console.warn("Readiness check error:", e);
          return null;
        }),
      ]);

      setHealth(healthData);
      setReadiness(readyData);
      setLastCheck(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect to backend API");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshDiagnostics();
  }, []);

  return (
    <div className="space-y-8">
      {/* Overview Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-forensic-900 via-forensic-850 to-forensic-900 border border-forensic-700/80 p-6 sm:p-8 shadow-xl">
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-integrity-emerald/10 border border-integrity-emerald/30 text-integrity-emerald text-xs font-mono mb-3">
              <CheckCircle className="w-3.5 h-3.5" />
              <span>Phase 1 Architectural Foundation Initialized</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Operational Subsystems Console
            </h2>
            <p className="mt-1 text-sm text-forensic-400 max-w-2xl">
              Real-time connectivity monitoring, immutable private storage isolation, and background
              worker readiness for evidentiary media processing.
            </p>
          </div>

          <button
            onClick={refreshDiagnostics}
            disabled={loading}
            className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-lg bg-forensic-800 hover:bg-forensic-700 border border-forensic-600 text-sm font-medium text-white transition-all shadow disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-integrity-cyan" : ""}`} />
            <span>{loading ? "Probing..." : "Refresh Status"}</span>
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 font-mono">
            <strong>Diagnostic Error:</strong> {error}
          </div>
        )}

        {lastCheck && (
          <div className="mt-4 pt-4 border-t border-forensic-800/80 text-xs text-forensic-500 font-mono">
            Last probe timestamp: <span className="text-forensic-300">{lastCheck}</span> &bull; API Target:{" "}
            <span className="text-integrity-cyan">
              {"/api/v1 (same-origin proxy)"}
            </span>
          </div>
        )}
      </div>

      {/* Subsystem Health Cards Grid */}
      <div>
        <h3 className="text-xs font-mono uppercase tracking-wider text-forensic-400 mb-4 flex items-center space-x-2">
          <Layers className="w-4 h-4 text-integrity-teal" />
          <span>Core Infrastructure Diagnostics</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatusCard
            title="FastAPI Monolith"
            type="api"
            status={health ? (health.status as any) : "UNKNOWN"}
            details={health ? `Version ${health.version} (${health.environment})` : "Disconnected"}
          />

          <StatusCard
            title="PostgreSQL 16"
            type="database"
            status={readiness?.subsystems.database.status || "UNKNOWN"}
            latencyMs={readiness?.subsystems.database.latency_ms}
            details={readiness?.subsystems.database.database || readiness?.subsystems.database.error}
          />

          <StatusCard
            title="Redis 7 Message Queue"
            type="redis"
            status={readiness?.subsystems.redis.status || "UNKNOWN"}
            latencyMs={readiness?.subsystems.redis.latency_ms}
            details={readiness?.subsystems.redis.error || "Ready for forensic tasks"}
          />

          <StatusCard
            title="Private Vault Storage"
            type="storage"
            status={readiness?.subsystems.storage.status || "UNKNOWN"}
            subItems={readiness?.subsystems.storage.directories}
          />
        </div>
      </div>

      {/* Architecture Verification Matrix */}
      <div className="bg-forensic-900 border border-forensic-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center space-x-2">
          <Server className="w-4 h-4 text-integrity-blue" />
          <span>Phase 1 Verification Matrix</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
          <div className="bg-forensic-850 p-4 rounded-lg border border-forensic-700/60">
            <div className="flex items-center space-x-2 text-integrity-emerald mb-2">
              <FolderLock className="w-4 h-4" />
              <span className="font-bold">Private Storage Vaults</span>
            </div>
            <p className="text-forensic-400">
              Isolated directory tree created: <code className="text-forensic-200">storage/originals</code> (0400 read-only target), <code className="text-forensic-200">storage/artifacts</code>, <code className="text-forensic-200">storage/reports</code>, and <code className="text-forensic-200">storage/tmp</code>.
            </p>
          </div>

          <div className="bg-forensic-850 p-4 rounded-lg border border-forensic-700/60">
            <div className="flex items-center space-x-2 text-integrity-teal mb-2">
              <Database className="w-4 h-4" />
              <span className="font-bold">Database & Queue Services</span>
            </div>
            <p className="text-forensic-400">
              Docker Compose orchestrates PostgreSQL 16 Alpine and Redis 7 with persistent volumes, connection pooling, and healthcheck probes.
            </p>
          </div>

          <div className="bg-forensic-850 p-4 rounded-lg border border-forensic-700/60">
            <div className="flex items-center space-x-2 text-integrity-cyan mb-2">
              <ShieldAlert className="w-4 h-4" />
              <span className="font-bold">Security & Error Handling</span>
            </div>
            <p className="text-forensic-400">
              Centralized exception handling with RFC-7807 structured JSON, path traversal containment checks, and security HTTP headers (CSP, HSTS).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
