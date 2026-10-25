"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, Mail, AlertCircle, ArrowRight, KeyRound } from "lucide-react";
import { login } from "@/lib/api";

export default function LoginPage(): React.JSX.Element {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      router.push("/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  const setPreset = (presetEmail: string) => {
    setEmail(presetEmail);
    setPassword("SecureEvidence1234!");
    setError(null);
  };

  return (
    <div className="max-w-md mx-auto py-12 px-4 sm:px-6">
      <div className="rounded-2xl bg-forensic-900 border border-forensic-750 p-8 shadow-2xl relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-integrity-cyan/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex items-center space-x-3 mb-6">
          <div className="p-2.5 rounded-xl bg-integrity-cyan/10 border border-integrity-cyan/30 text-integrity-cyan">
            <KeyRound className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Investigator Login</h2>
            <p className="text-xs text-forensic-400">Authenticated access to digital evidence vaults</p>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-3 rounded-lg bg-red-950/50 border border-red-800 text-xs text-red-200 flex items-start space-x-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-forensic-300 mb-1.5 uppercase tracking-wider">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-forensic-500 absolute left-3 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="investigator@agency.gov"
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan focus:ring-1 focus:ring-integrity-cyan transition-colors"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono text-forensic-300 mb-1.5 uppercase tracking-wider">
              Secret Passphrase
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-forensic-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-forensic-850 border border-forensic-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-forensic-500 focus:outline-none focus:border-integrity-cyan focus:ring-1 focus:ring-integrity-cyan transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 inline-flex items-center justify-center space-x-2 py-2.5 px-4 rounded-lg bg-integrity-cyan text-forensic-950 font-semibold text-sm hover:bg-integrity-cyan/90 focus:outline-none focus:ring-2 focus:ring-integrity-cyan focus:ring-offset-2 focus:ring-offset-forensic-900 transition-all disabled:opacity-50"
          >
            <span>{loading ? "Authenticating..." : "Sign In to Vault"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* Test credential helpers */}
        <div className="mt-8 pt-6 border-t border-forensic-800 text-xs">
          <span className="text-forensic-400 block mb-2 font-mono">Quick Test Credentials:</span>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setPreset("examiner@test.com")}
              className="px-2.5 py-1.5 rounded bg-forensic-850 hover:bg-forensic-800 border border-forensic-700 text-forensic-300 text-left text-[11px] font-mono transition-colors"
            >
              Examiner Profile
            </button>
            <button
              type="button"
              onClick={() => setPreset("admin@test.com")}
              className="px-2.5 py-1.5 rounded bg-forensic-850 hover:bg-forensic-800 border border-forensic-700 text-forensic-300 text-left text-[11px] font-mono transition-colors"
            >
              Admin Profile
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
