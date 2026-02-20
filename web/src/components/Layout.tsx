import { Shield } from "lucide-react";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="mesh-gradient grid-bg relative min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-zinc-800/60 bg-zinc-950/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600 shadow-lg shadow-purple-500/20">
              <Shield size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                NeverDown
              </h1>
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">
                Autonomous CI/CD Healing Agent
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="badge-info">v1.0</span>
            <a
              href="https://github.com"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-zinc-500 transition hover:text-zinc-300"
            >
              Docs
            </a>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>

      {/* Footer */}
      <footer className="border-t border-zinc-800/40 py-4 text-center text-xs text-zinc-600">
        Built for PW RIFT Hackathon — Powered by LangGraph &amp; Claude
      </footer>
    </div>
  );
}
