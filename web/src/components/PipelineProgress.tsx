import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import {
  GitBranch,
  Search,
  Package,
  TestTube,
  Bug,
  Wrench,
  CheckCircle2,
  Upload,
  FileJson,
  AlertCircle,
} from "lucide-react";
import type { PipelineStep } from "../types";

const STEPS: { key: PipelineStep; label: string; icon: React.ReactNode }[] = [
  { key: "cloning", label: "Clone", icon: <GitBranch size={14} /> },
  { key: "detecting_framework", label: "Detect", icon: <Search size={14} /> },
  { key: "installing_deps", label: "Install", icon: <Package size={14} /> },
  { key: "running_tests", label: "Test", icon: <TestTube size={14} /> },
  { key: "analyzing_failures", label: "Analyze", icon: <Bug size={14} /> },
  { key: "generating_fix", label: "Fix", icon: <Wrench size={14} /> },
  { key: "applying_fix", label: "Apply", icon: <Wrench size={14} /> },
  { key: "verifying", label: "Verify", icon: <CheckCircle2 size={14} /> },
  { key: "publishing", label: "Publish", icon: <Upload size={14} /> },
  { key: "generating_results", label: "Results", icon: <FileJson size={14} /> },
];

function stepIndex(step: PipelineStep): number {
  if (step === "completed") return STEPS.length;
  if (step === "failed") return STEPS.length; // mark all steps as done even on failure
  const idx = STEPS.findIndex((s) => s.key === step);
  return idx >= 0 ? idx : 0; // graceful fallback for unknown steps
}

export function PipelineProgress() {
  const currentStep = useAgentStore((s) => s.currentStep);
  const status = useAgentStore((s) => s.status);
  const activeIdx = stepIndex(currentStep);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card mt-5"
    >
      <div className="flex items-center gap-2 mb-4">
        {status === "failed" && <AlertCircle size={16} className="text-red-400" />}
        <h3 className="text-sm font-semibold text-zinc-300">Pipeline Progress</h3>
        {status === "running" && (
          <span className="badge-warning ml-auto">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-yellow-400" />
            In Progress
          </span>
        )}
        {status === "passed" && <span className="badge-success ml-auto">✓ All Passed</span>}
        {status === "failed" && <span className="badge-danger ml-auto">⚠ Partial Fix</span>}
      </div>

      {/* Progress bar */}
      <div className="relative mb-8 h-2 rounded-full bg-zinc-800/80 shadow-[inset_0_1px_3px_rgba(0,0,0,0.5)]">
        <motion.div
          className={`absolute inset-y-0 left-0 rounded-full ${status === "failed"
              ? "bg-gradient-to-r from-amber-600 to-orange-500 shadow-[0_0_15px_rgba(245,158,11,0.4)]"
              : "bg-gradient-to-r from-purple-500 via-indigo-500 to-cyan-400 shadow-[0_0_15px_rgba(99,102,241,0.5)]"
            }`}
          initial={{ width: "0%" }}
          animate={{
            width:
              status === "passed"
                ? "100%"
                : activeIdx < 0
                  ? "100%"
                  : `${((activeIdx + 0.5) / STEPS.length) * 100}%`,
          }}
          transition={{ duration: 0.6, ease: "easeInOut" }}
        />
      </div>

      {/* Step indicators */}
      <div className="grid grid-cols-10 gap-1">
        {STEPS.map((step, i) => {
          const isCompleted = status === "passed" || status === "failed";
          const isDone = activeIdx > i || isCompleted;
          const isActive = activeIdx === i && status === "running";
          const isFailed = false; // individual steps don't fail, the pipeline outcome does;

          return (
            <div key={step.key} className="flex flex-col items-center gap-2">
              <div
                className={`flex h-[34px] w-[34px] items-center justify-center rounded-full border transition-all duration-300 ${isDone
                    ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                    : isActive
                      ? "animate-pulse border-purple-500 bg-purple-500/20 text-purple-300 shadow-[0_0_15px_rgba(168,85,247,0.3)]"
                      : isFailed
                        ? "border-red-500/50 bg-red-500/10 text-red-400 shadow-[0_0_10px_rgba(239,68,68,0.2)]"
                        : "border-zinc-700/40 bg-zinc-800/40 text-zinc-600"
                  }`}
              >
                {step.icon}
              </div>
              <span
                className={`text-[10px] uppercase font-bold tracking-wider ${isDone
                    ? "text-emerald-400 drop-shadow-[0_0_5px_rgba(52,211,153,0.3)]"
                    : isActive
                      ? "text-purple-300 drop-shadow-[0_0_8px_rgba(216,180,254,0.4)]"
                      : isFailed
                        ? "text-red-400 drop-shadow-[0_0_5px_rgba(248,113,113,0.3)]"
                        : "text-zinc-600"
                  }`}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
