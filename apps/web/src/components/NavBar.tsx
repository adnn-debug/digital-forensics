"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ShieldCheck,
  FolderOpen,
  UploadCloud,
  Microscope,
  FileText,
  Activity,
  LogOut,
  LogIn,
  User as UserIcon,
} from "lucide-react";
import { getStoredUserProfile, logout, UserProfile } from "@/lib/api";

export function NavBar(): React.JSX.Element {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    setUser(getStoredUserProfile());
  }, [pathname]);

  const handleLogout = async () => {
    await logout();
    setUser(null);
    router.push("/login");
  };

  const navLinks = [
    { href: "/", label: "Dashboard", icon: Activity },
    { href: "/cases", label: "Cases", icon: FolderOpen },
    { href: "/upload", label: "Upload Evidence", icon: UploadCloud },
    { href: "/analysis", label: "Analysis Results", icon: Microscope },
    { href: "/reports", label: "Reports", icon: FileText },
  ];

  return (
    <header className="border-b border-forensic-800 bg-forensic-900/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-6">
          <Link href="/" className="flex items-center space-x-3 group">
            <div className="p-2 rounded-lg bg-integrity-emerald/10 border border-integrity-emerald/30 text-integrity-emerald group-hover:border-integrity-emerald/60 transition-colors">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <span className="font-mono text-[10px] text-integrity-cyan tracking-wider uppercase font-semibold block leading-tight">
                PS-05 FORENSIC SUITE
              </span>
              <span className="text-sm font-bold text-white tracking-tight leading-none block">
                Evidence Platform
              </span>
            </div>
          </Link>

          {/* Nav Items */}
          <nav className="hidden md:flex items-center space-x-1">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive =
                link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`inline-flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? "bg-forensic-800 text-white border border-forensic-700/80 shadow-sm"
                      : "text-forensic-400 hover:text-forensic-100 hover:bg-forensic-850"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? "text-integrity-cyan" : ""}`} />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User Session Bar */}
        <div className="flex items-center space-x-3 text-xs">
          {user ? (
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2 bg-forensic-850 px-2.5 py-1.5 rounded-md border border-forensic-700/60">
                <UserIcon className="w-3.5 h-3.5 text-integrity-teal" />
                <span className="text-forensic-200 font-mono">{user.email}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-integrity-emerald/10 text-integrity-emerald border border-integrity-emerald/30 font-mono">
                  {user.role}
                </span>
              </div>
              <button
                onClick={handleLogout}
                className="inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md bg-forensic-850 hover:bg-red-950/40 text-forensic-400 hover:text-red-400 border border-forensic-700/60 transition-colors"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Logout</span>
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-md bg-integrity-cyan/10 hover:bg-integrity-cyan/20 text-integrity-cyan border border-integrity-cyan/30 transition-colors font-medium font-mono"
            >
              <LogIn className="w-3.5 h-3.5" />
              <span>Login</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
