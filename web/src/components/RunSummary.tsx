import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import {
  GitBranch,
  Bug,
  Wrench,
  Clock,
  RefreshCw,
  ExternalLink,
} from "lucide-react";

export function RunSummary() {
  const {
    repositoryUrl,
    teamName,
    leaderName,
    branchName,
    totalFailures,
    totalFixes,
    iteration,
    maxRetries,
    totalTime,
    status,
    testFramework,
  } = useAgentStore();

  const statusConfig = {
    idle: { label: "Idle", cls: "badge-neutral" },
    running: { label: "Running", cls: "badge-warning" },
    passed: { label: "All Tests Passed", cls: "badge-success" },
    failed: { label: "Failed", cls: "badge-danger" },
  }[status];

  const repoName = repositoryUrl.split("/").slice(-2).join("/").replace(".git", "");

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="card"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-300">Run Summary</h3>
        <span className={statusConfig.cls}>{statusConfig.label}</span>
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetaItem
          icon={<ExternalLink size={13} />}
          label="Repository"
          value={repoName || "—"}
          mono
        />
        <MetaItem
          icon={<GitBranch size={13} />}
          label="Branch"
          value={branchName || "—"}
          mono
        />
        <MetaItem label="Team" value={teamName || "—"} />
        <MetaItem label="Leader" value={leaderName || "—"} />
      </div>

      <div className="my-3 border-t border-zinc-800" />

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatBox
          icon={<Bug size={14} className="text-red-400" />}
          label="Failures"
          value={totalFailures}
          color="text-red-400"
        />
        <StatBox
          icon={<Wrench size={14} className="text-emerald-400" />}
          label="Fixes"
          value={totalFixes}
          color="text-emerald-400"
        />
        <StatBox
          icon={<RefreshCw size={14} className="text-cyan-400" />}
          label="Iterations"
          value={`${iteration}/${maxRetries}`}
          color="text-cyan-400"
        />
        <StatBox
          icon={<Clock size={14} className="text-amber-400" />}
          label="Time"
          value={totalTime > 0 ? `${totalTime.toFixed(1)}s` : "—"}
          color="text-amber-400"
        />
        <StatBox
          label="Framework"
          value={testFramework || "—"}
          color="text-purple-400"
        />
      </div>
    </motion.div>
  );
}

function MetaItem({
  icon,
  label,
  value,
  mono,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[10px] font-medium uppercase text-zinc-500">
        {icon} {label}
      </p>
      <p
        title={value}
        className={`mt-0.5 truncate text-sm text-zinc-200 ${mono ? "font-mono text-[11px]" : ""
          }`}
      >
        {value}
      </p>
    </div>
  );
}

function StatBox({
  icon,
  label,
  value,
  color,
}: {
  icon?: React.ReactNode;
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.04] bg-white/[0.02] p-3 text-center shadow-sm backdrop-blur-md transition-all hover:bg-white/[0.04]">
      <div className="mb-1.5 flex items-center justify-center gap-1.5">
        {icon}
        <span className="text-[10px] font-semibold tracking-wider uppercase text-zinc-400">
          {label}
        </span>
      </div>
      <p className={`text-xl font-bold tracking-tight ${color}`}>{value}</p>
    </div>
  );
}
