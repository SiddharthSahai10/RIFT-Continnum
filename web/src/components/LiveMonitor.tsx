import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { Activity, FileCode, Bug, Gauge, RefreshCw } from "lucide-react";

export function LiveMonitor() {
  const {
    status,
    currentStep,
    currentBugType,
    currentFile,
    confidence,
    iteration,
    maxRetries,
    logs,
  } = useAgentStore();

  if (status === "idle") return null;

  const recentLogs = logs.slice(-8);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="card"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={15} className="text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-300">Live Monitor</h3>
        </div>
        {status === "running" && (
          <span className="flex items-center gap-1.5 text-[10px] font-medium text-emerald-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            LIVE
          </span>
        )}
      </div>

      {/* Current state */}
      <div className="mb-4 space-y-2.5">
        {/* Iteration badge */}
        <div className="flex items-center gap-2">
          <RefreshCw size={13} className="text-purple-400" />
          <span className="text-xs text-zinc-400">Iteration</span>
          <span className="ml-auto badge-info font-mono">
            {iteration}/{maxRetries}
          </span>
        </div>

        {/* Current bug type */}
        {currentBugType && (
          <div className="flex items-center gap-2">
            <Bug size={13} className="text-amber-400" />
            <span className="text-xs text-zinc-400">Bug Type</span>
            <span className="ml-auto badge-warning font-mono text-[10px]">
              {currentBugType}
            </span>
          </div>
        )}

        {/* Current file */}
        {currentFile && (
          <div className="flex items-center gap-2">
            <FileCode size={13} className="text-indigo-400" />
            <span className="text-xs text-zinc-400">File</span>
            <span className="ml-auto truncate max-w-[140px] font-mono text-[10px] text-zinc-300">
              {currentFile}
            </span>
          </div>
        )}

        {/* AI Confidence */}
        {confidence > 0 && (
          <div>
            <div className="mb-1 flex items-center gap-2">
              <Gauge size={13} className="text-purple-400" />
              <span className="text-xs text-zinc-400">AI Confidence</span>
              <span className="ml-auto text-xs font-semibold text-purple-300">
                {Math.round(confidence * 100)}%
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-zinc-800">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-purple-600 to-indigo-500"
                initial={{ width: 0 }}
                animate={{ width: `${confidence * 100}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Terminal Log feed */}
      <div className="relative overflow-hidden rounded-xl border border-white/[0.05] bg-black/40 p-4 shadow-inner backdrop-blur-xl">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent" />
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
          Terminal Output
        </p>
        <div className="relative z-10 max-h-40 space-y-1.5 overflow-y-auto font-mono text-[11px] leading-relaxed">
          {recentLogs.length === 0 ? (
            <p className="text-zinc-600 italic">Waiting for events…</p>
          ) : (
            recentLogs.map((log, i) => {
              const isError = log.includes("❌");
              const isSuccess = log.includes("✅") || log.includes("✓");
              const isUpdate = log.startsWith("▸") || log.startsWith("🔄");

              const textColor = isError
                ? "text-red-400 font-medium drop-shadow-[0_0_8px_rgba(248,113,113,0.5)]"
                : isSuccess
                  ? "text-emerald-400 font-medium drop-shadow-[0_0_8px_rgba(52,211,153,0.4)]"
                  : isUpdate
                    ? "text-cyan-300 drop-shadow-[0_0_5px_rgba(103,232,249,0.3)]"
                    : "text-zinc-400";

              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`flex gap-2 ${textColor}`}
                >
                  <span className="select-none border-r border-white/10 pr-2 opacity-50">
                    &gt;
                  </span>
                  <span className="flex-1 break-words">{log}</span>
                </motion.div>
              );
            })
          )}
        </div>
      </div>
    </motion.div>
  );
}
