import type { Metadata } from "next";
import "./globals.css";
import React from "react";

import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "PS-05 Digital Evidence Verification Platform",
  description: "Enterprise digital forensics, evidence authenticity, integrity hashing & courtroom reporting.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <html lang="en" className="dark">
      <body className="bg-forensic-950 text-forensic-100 antialiased min-h-screen flex flex-col font-sans">
        <NavBar />

        {/* Main Content Viewport */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        {/* Footer */}
        <footer className="border-t border-forensic-800/80 py-4 text-center text-xs text-forensic-500 font-mono">
          PS-05 Digital Evidence Platform &bull; High-Integrity Chain of Custody &bull; NIST SP 800-86
        </footer>
      </body>
    </html>
  );
}
