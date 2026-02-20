import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { GitBranch, ExternalLink, Scan, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

/**
 * Prominent banner that shows WHICH repository the system is analyzing.
 * Displayed above PipelineProgress so there's no confusion.
 */
export function TargetRepoBanner() {
  const repositoryUrl = useAgentStore((s) => s.repositoryUrl);
  const branchName = useAgentStore((s) => s.branchName);
  const status = useAgentStore((s) => s.status);
  const testFramework = useAgentStore((s) => s.testFramework);

  if (!repositoryUrl) return null;

  const repoName = repositoryUrl
    .split("/")
    .slice(-2)
    .join("/")
    .replace(".git", "");

  const isRunning = status === "running";
  const isPassed = status === "passed";

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`mt-4 rounded-2xl border px-5 py-4 backdrop-blur-sm ${
        isRunning
          ? "border-cyan-500/30 bg-cyan-500/5"
          : isPassed
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <div className="flex items-center justify-between flex-wrap gap-3">
        {/* Left: Repo info */}
        <div className="flex items-center gap-3">
          <div
            className={`flex h-9 w-9 items-center justify-center rounded-xl ${
              isRunning
                ? "bg-cyan-500/15 text-cyan-400"
                : isPassed
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-amber-500/15 text-amber-400"
            }`}
          >
            {isRunning ? (
              <Loader2 size={18} className="animate-spin" />
            ) : isPassed ? (
              <CheckCircle2 size={18} />
            ) : (
              <AlertTriangle size={18} />
            )}
          </div>

          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              {isRunning
                ? "🔍 Analyzing Target Repository"
                : isPassed
                ? "✅ Analysis Complete"
                : "⚠️ Analysis Complete — Partial Fix"}
            </p>
            <a
              href={repositoryUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 font-mono text-sm font-bold text-white hover:text-cyan-300 transition-colors"
            >
              <Scan size={14} className="text-cyan-400" />
              {repoName}
              <ExternalLink size={11} className="opacity-40" />
            </a>
          </div>
        </div>

        {/* Right: Branch + Framework */}
        <div className="flex items-center gap-4">
          {branchName && (
            <div className="flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 ring-1 ring-white/10">
              <GitBranch size={12} className="text-purple-400" />
              <span className="font-mono text-[11px] text-zinc-300">
                {branchName}
              </span>
            </div>
          )}
          {testFramework && (
            <div className="rounded-lg bg-white/5 px-3 py-1.5 ring-1 ring-white/10">
              <span className="text-[11px] font-semibold text-zinc-300">
                {testFramework.toUpperCase()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Subtle note */}
      <p className="mt-2 text-[10px] text-zinc-500">
        All tests, fixes, and analysis are performed on the repository above — not on NeverDown's own codebase.
      </p>
    </motion.div>
  );
}
