import { useState } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileJson2,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  GitBranch,
  Bug,
  Wrench,
  Clock,
  Trophy,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from "lucide-react";

/* ── Type for the results.json payload ── */
interface ResultsPayload {
  repository: string;
  team_name: string;
  leader_name: string;
  branch_name: string;
  total_failures: number;
  total_fixes: number;
  iterations_used: number;
  max_iterations: number;
  final_status: string;
  total_time: string | number;
  total_time_seconds?: number;
  total_time_formatted?: string;
  score: {
    base: number;
    speed_bonus: number;
    efficiency_penalty: number;
    total_commits: number;
    final: number;
  } | number;
  fixes: Array<{
    file: string;
    bug_type: string;
    line_number: number;
    commit_message: string;
    status: string;
  }>;
  timeline?: Array<{
    state: string;
    timestamp: string;
    details: Record<string, unknown>;
  }>;
  generated_at?: string;
}

/** Build the clean hackathon-spec JSON (no internal fields). */
function buildSpecJson(r: ResultsPayload) {
  const scoreObj = typeof r.score === "object" ? r.score : null;
  return {
    repository: r.repository,
    team_name: r.team_name,
    leader_name: r.leader_name,
    branch_name: r.branch_name,
    total_failures: r.total_failures,
    total_fixes: r.total_fixes,
    iterations_used: r.iterations_used,
    final_status: r.final_status,
    total_time: typeof r.total_time === "string" ? r.total_time : r.total_time_formatted ?? `${Math.round(r.total_time as number)}s`,
    score: scoreObj?.final ?? (typeof r.score === "number" ? r.score : 0),
    fixes: (r.fixes ?? []).map((f) => ({
      file: f.file,
      bug_type: f.bug_type,
      line_number: f.line_number,
      commit_message: f.commit_message.replace("[NeverDown-AI]", "[AI-AGENT]"),
      status: f.status === "applied" || f.status === "fixed" ? "Fixed" : f.status === "Fixed" ? "Fixed" : f.status === "Failed" ? "Failed" : f.status,
    })),
  };
}

export function ResultsJSON() {
  const resultsJson = useAgentStore((s) => s.resultsJson);
  const status = useAgentStore((s) => s.status);
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [showRaw, setShowRaw] = useState(false);

  // Only show when pipeline is done
  if (status !== "passed" && status !== "failed") return null;
  if (!resultsJson || Object.keys(resultsJson).length === 0) return null;

  const r = resultsJson as unknown as ResultsPayload;
  const scoreObj = typeof r.score === "object" ? r.score : { base: 100, speed_bonus: 0, efficiency_penalty: 0, total_commits: 0, final: r.score as unknown as number };
  const isPassed = r.final_status === "PASSED";
  const specJson = buildSpecJson(r);
  const appliedFixes = specJson.fixes.filter((f) => f.status === "Fixed");
  const failedFixes = specJson.fixes.filter((f) => f.status === "Failed");
  const displayTime = specJson.total_time;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(specJson, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(specJson, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "results.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="card overflow-hidden"
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-semibold text-zinc-300 hover:text-white transition-colors"
        >
          <FileJson2 size={16} className="text-cyan-400" />
          <span>results.json</span>
          <span
            className={`ml-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
              isPassed
                ? "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30"
                : "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30"
            }`}
          >
            {isPassed ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
            {r.final_status}
          </span>
          {expanded ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
        </button>

        <div className="flex items-center gap-2">
          {/* Toggle raw JSON / pretty */}
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="rounded-lg px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 ring-1 ring-zinc-700 hover:bg-zinc-800 hover:text-zinc-200 transition-all"
          >
            {showRaw ? "Pretty" : "JSON"}
          </button>

          {/* Copy */}
          <button
            onClick={handleCopy}
            className="rounded-lg p-1.5 text-zinc-400 ring-1 ring-zinc-700 hover:bg-zinc-800 hover:text-zinc-200 transition-all"
            title="Copy JSON"
          >
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          </button>

          {/* Download */}
          <button
            onClick={handleDownload}
            className="rounded-lg p-1.5 text-zinc-400 ring-1 ring-zinc-700 hover:bg-zinc-800 hover:text-zinc-200 transition-all"
            title="Download results.json"
          >
            <Download size={13} />
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {showRaw ? (
              /* ── Raw JSON view ── */
              <pre className="mt-4 max-h-[500px] overflow-auto rounded-xl border border-zinc-800 bg-zinc-950/80 p-4 text-[11px] leading-relaxed text-zinc-300 font-mono">
                {JSON.stringify(specJson, null, 2)}
              </pre>
            ) : (
              /* ── Pretty view ── */
              <div className="mt-4 space-y-4">
                {/* ── Top-level info ── */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <InfoCard
                    icon={<GitBranch size={13} className="text-cyan-400" />}
                    label="Repository"
                    value={r.repository?.split("/").slice(-2).join("/") || "—"}
                    mono
                  />
                  <InfoCard
                    icon={<GitBranch size={13} className="text-purple-400" />}
                    label="Branch"
                    value={r.branch_name || "—"}
                    mono
                  />
                  <InfoCard label="Team" value={r.team_name || "—"} />
                  <InfoCard label="Leader" value={r.leader_name || "—"} />
                </div>

                {/* ── Stats row ── */}
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                  <MiniStat
                    icon={<Bug size={13} />}
                    label="Failures"
                    value={r.total_failures}
                    color="text-red-400"
                  />
                  <MiniStat
                    icon={<Wrench size={13} />}
                    label="Fixes"
                    value={r.total_fixes}
                    color="text-emerald-400"
                  />
                  <MiniStat
                    icon={<RefreshCw size={13} />}
                    label="Iterations"
                    value={`${r.iterations_used}/${r.max_iterations}`}
                    color="text-cyan-400"
                  />
                  <MiniStat
                    icon={<Clock size={13} />}
                    label="Time"
                    value={displayTime}
                    color="text-amber-400"
                  />
                  <MiniStat
                    icon={<Trophy size={13} />}
                    label="Score"
                    value={scoreObj.final}
                    color="text-yellow-400"
                  />
                  <MiniStat
                    label="Status"
                    value={r.final_status}
                    color={isPassed ? "text-emerald-400" : "text-amber-400"}
                  />
                </div>

                {/* ── Score breakdown ── */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                    Score Breakdown
                  </p>
                  <div className="flex flex-wrap gap-4 text-xs text-zinc-400">
                    <span>Base: <strong className="text-zinc-200">{scoreObj.base}</strong></span>
                    <span>Speed Bonus: <strong className="text-emerald-400">+{scoreObj.speed_bonus}</strong></span>
                    <span>Penalty: <strong className="text-red-400">-{scoreObj.efficiency_penalty}</strong></span>
                    <span>Commits: <strong className="text-zinc-200">{scoreObj.total_commits}</strong></span>
                    <span className="ml-auto text-sm font-bold text-yellow-400">Final: {scoreObj.final}</span>
                  </div>
                </div>

                {/* ── Fixes table ── */}
                {r.fixes && r.fixes.length > 0 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
                    <div className="border-b border-zinc-800 px-3 py-2">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                        Fixes ({appliedFixes.length} fixed, {failedFixes.length} failed)
                      </p>
                    </div>
                    <div className="max-h-[300px] overflow-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-zinc-800 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                            <th className="px-3 py-2">File</th>
                            <th className="px-3 py-2">Bug Type</th>
                            <th className="px-3 py-2">Line</th>
                            <th className="px-3 py-2">Commit Message</th>
                            <th className="px-3 py-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {specJson.fixes.map((fix, i) => (
                            <tr
                              key={i}
                              className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
                            >
                              <td className="px-3 py-2 font-mono text-[11px] text-zinc-300">
                                {fix.file}
                              </td>
                              <td className="px-3 py-2">
                                <span className="rounded-md bg-zinc-800 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-400">
                                  {fix.bug_type}
                                </span>
                              </td>
                              <td className="px-3 py-2 font-mono text-zinc-400">
                                {fix.line_number}
                              </td>
                              <td className="px-3 py-2 text-[10px] text-zinc-400 max-w-[200px] truncate" title={fix.commit_message}>
                                {fix.commit_message}
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`inline-flex items-center gap-1 text-[10px] font-semibold ${
                                    fix.status === "Fixed"
                                      ? "text-emerald-400"
                                      : "text-red-400"
                                  }`}
                                >
                                  {fix.status === "Fixed" ? (
                                    <CheckCircle2 size={10} />
                                  ) : (
                                    <XCircle size={10} />
                                  )}
                                  {fix.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* ── Generated at ── */}
                {r.generated_at && (
                  <p className="text-right text-[10px] text-zinc-600">
                    Generated at {new Date(r.generated_at).toLocaleString()}
                  </p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ── Small helper components ── */

function InfoCard({
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
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-2.5">
      <p className="flex items-center gap-1 text-[10px] font-medium uppercase text-zinc-500">
        {icon} {label}
      </p>
      <p
        title={value}
        className={`mt-0.5 truncate text-sm text-zinc-200 ${mono ? "font-mono text-[11px]" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

function MiniStat({
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
    <div className="rounded-xl border border-white/[0.04] bg-white/[0.02] p-2 text-center">
      <div className="mb-1 flex items-center justify-center gap-1">
        {icon && <span className={color}>{icon}</span>}
        <span className="text-[9px] font-semibold tracking-wider uppercase text-zinc-500">
          {label}
        </span>
      </div>
      <p className={`text-base font-bold ${color}`}>{value}</p>
    </div>
  );
}
