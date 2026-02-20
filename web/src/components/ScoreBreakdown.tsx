import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { Trophy, Zap, GitCommitHorizontal, Clock } from "lucide-react";

export function ScoreBreakdown() {
  const { score, speedBonus, efficiencyPenalty, totalTime, totalFixes, status } =
    useAgentStore();

  if (status !== "passed" && status !== "failed") return null;

  const baseScore = 100;
  const final = score || baseScore + speedBonus - efficiencyPenalty;
  const maxScore = 110;
  const pct = Math.min((final / maxScore) * 100, 100);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: 0.3 }}
      className="card"
    >
      <div className="mb-4 flex items-center gap-2">
        <Trophy size={15} className="text-amber-400" />
        <h3 className="text-sm font-semibold text-zinc-300">Score Breakdown</h3>
      </div>

      {/* Main score */}
      <div className="mb-5 text-center">
        <motion.p
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 200, delay: 0.5 }}
          className="text-5xl font-black text-gradient"
        >
          {final}
        </motion.p>
        <p className="mt-1 text-xs text-zinc-500">out of {maxScore}</p>
      </div>

      {/* Score bar */}
      <div className="mb-5 h-2.5 rounded-full bg-zinc-800">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-amber-500 via-purple-500 to-indigo-500"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 1, delay: 0.4 }}
        />
      </div>

      {/* Breakdown */}
      <div className="space-y-3">
        <BreakdownRow
          icon={<Trophy size={14} className="text-zinc-500" />}
          label="Base Score"
          value={`${baseScore}`}
          color="text-zinc-300"
        />
        <BreakdownRow
          icon={<Zap size={14} className={speedBonus > 0 ? "text-amber-400" : "text-zinc-500"} />}
          label="Speed Bonus"
          value={speedBonus > 0 ? `+${speedBonus}` : "0"}
          detail={
            totalTime > 0
              ? `${(totalTime / 60).toFixed(1)} min ${totalTime < 300 ? "(<5 min ✓)" : "(≥5 min)"}`
              : undefined
          }
          color={speedBonus > 0 ? "text-emerald-400 text-shadow-sm font-bold" : "text-zinc-500"}
        />
        <BreakdownRow
          icon={<GitCommitHorizontal size={14} className={efficiencyPenalty > 0 ? "text-red-400" : "text-zinc-500"} />}
          label="Efficiency Penalty"
          value={efficiencyPenalty > 0 ? `-${efficiencyPenalty}` : "0"}
          detail={
            totalFixes > 20
              ? `${totalFixes} fixes (${totalFixes - 20} over limit)`
              : `${totalFixes} fixes (≤20 ✓)`
          }
          color={efficiencyPenalty > 0 ? "text-red-400 font-bold" : "text-zinc-500"}
        />
        <div className="border-t border-white/5 pt-3">
          <BreakdownRow
            icon={<Clock size={14} className="text-purple-400" />}
            label="Final Score"
            value={`${final}`}
            color="text-purple-400 font-bold drop-shadow-[0_0_8px_rgba(192,132,252,0.4)] text-sm"
          />
        </div>
      </div>
    </motion.div>
  );
}

function BreakdownRow({
  icon,
  label,
  value,
  detail,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail?: string;
  color: string;
}) {
  return (
    <div className="flex items-center justify-between text-xs rounded-lg bg-zinc-800/20 px-3 py-2 border border-white/[0.02] shadow-sm backdrop-blur-md hover:bg-zinc-800/40 transition-colors">
      <span className="flex items-center gap-2 font-medium text-zinc-300">
        {icon} {label}
      </span>
      <div className="text-right">
        <span className={`font-mono ${color}`}>{value}</span>
        {detail && (
          <p className="mt-0.5 text-[9px] uppercase tracking-wider text-zinc-500">{detail}</p>
        )}
      </div>
    </div>
  );
}
