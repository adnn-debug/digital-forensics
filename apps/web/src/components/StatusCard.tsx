"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, Database, HardDrive, Cpu, ShieldCheck } from "lucide-react";

interface StatusCardProps {
  title: string;
  type: "database" | "redis" | "storage" | "api";
  status: "HEALTHY" | "UNHEALTHY" | "OPERATIONAL" | "NOT_READY" | "UNKNOWN";
  latencyMs?: number | undefined;
  details?: string | undefined;
  subItems?: Record<string, { status: string; path: string; error?: string | undefined }> | undefined;
}

export function StatusCard({
  title,
  type,
  status,
  latencyMs,
  details,
  subItems,
}: StatusCardProps): React.JSX.Element {
  const isHealthy = status === "HEALTHY" || status === "OPERATIONAL";

  const getIcon = () => {
    switch (type) {
      case "database":
        return <Database className="w-5 h-5 text-integrity-teal" />;
      case "redis":
        return <Cpu className="w-5 h-5 text-integrity-cyan" />;
      case "storage":
        return <HardDrive className="w-5 h-5 text-integrity-emerald" />;
      case "api":
        return <ShieldCheck className="w-5 h-5 text-integrity-blue" />;
    }
  };

  return (
    <div className="bg-forensic-900 border border-forensic-700/60 rounded-xl p-5 shadow-lg shadow-black/40 hover:border-forensic-600 transition-all">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-forensic-850 border border-forensic-700/50">
            {getIcon()}
          </div>
          <h3 className="font-semibold text-forensic-100 text-sm">{title}</h3>
        </div>

        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border border-opacity-30 bg-opacity-10"
             style={{
               backgroundColor: isHealthy ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
               borderColor: isHealthy ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)",
               color: isHealthy ? "#34d399" : "#f87171",
             }}>
          {isHealthy ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{status}</span>
            </>
          ) : (
            <>
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{status}</span>
            </>
          )}
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-forensic-800 text-xs text-forensic-400 font-mono space-y-1.5">
        {latencyMs !== undefined && (
          <div className="flex justify-between">
            <span className="text-forensic-500">Latency:</span>
            <span className="text-forensic-300 font-medium">{latencyMs} ms</span>
          </div>
        )}
        {details && (
          <div className="flex justify-between">
            <span className="text-forensic-500">Info:</span>
            <span className="text-forensic-300 truncate max-w-[200px]" title={details}>
              {details}
            </span>
          </div>
        )}
        {subItems && (
          <div className="mt-2 space-y-1">
            <span className="text-forensic-500 text-[11px] block">Vault Directories:</span>
            <div className="grid grid-cols-2 gap-1.5 mt-1">
              {Object.entries(subItems).map(([key, item]) => (
                <div
                  key={key}
                  className="bg-forensic-950/80 px-2 py-1 rounded border border-forensic-800 text-[10px] flex items-center justify-between"
                >
                  <span className="capitalize text-forensic-300">{key}</span>
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      item.status === "HEALTHY" ? "bg-emerald-500" : "bg-red-500"
                    }`}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
