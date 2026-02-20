import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { GitBranch, CheckCircle2, XCircle, Clock } from "lucide-react";

export function CICDTimeline() {
  const { iterationResults, timeline, status } = useAgentStore();

  if (timeline.length === 0 && iterationResults.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="card"
    >
      <div className="mb-4 flex items-center gap-2">
        <GitBranch size={15} className="text-cyan-400" />
        <h3 className="text-sm font-semibold text-zinc-300">
          CI/CD Iteration Timeline
        </h3>
      </div>

      {/* Iteration bars */}
      {iterationResults.length > 0 && (
        <div className="mb-5">
          <p className="mb-2 text-[10px] font-medium uppercase text-zinc-500">
            Iterations ({iterationResults.length})
          </p>
          <div className="space-y-2">
            {iterationResults.map((ir, idx) => {
              const total = ir.testsRun || 1;
              const passedPct = (ir.testsPassed / total) * 100;
              const failedPct = (ir.testsFailed / total) * 100;

              return (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="flex items-center gap-3"
                >
                  <span className="w-6 text-right font-mono text-[10px] text-zinc-500">
                    #{ir.iteration}
                  </span>

                  <div className="flex-1">
                    <div className="flex h-4 overflow-hidden rounded-full bg-zinc-800">
                      <motion.div
                        className="bg-emerald-500/80"
                        initial={{ width: 0 }}
                        animate={{ width: `${passedPct}%` }}
                        transition={{ duration: 0.6 }}
                      />
                      <motion.div
                        className="bg-red-500/80"
                        initial={{ width: 0 }}
                        animate={{ width: `${failedPct}%` }}
                        transition={{ duration: 0.6 }}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-emerald-400">{ir.testsPassed}✓</span>
                    <span className="text-red-400">{ir.testsFailed}✗</span>
                    <span className="text-zinc-500">
                      {ir.fixesApplied} fix{ir.fixesApplied !== 1 ? "es" : ""}
                    </span>
                    {ir.passed ? (
                      <CheckCircle2 size={12} className="text-emerald-400" />
                    ) : (
                      <XCircle size={12} className="text-red-400" />
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* Pipeline step timeline */}
      <div>
        <p className="mb-2 text-[10px] font-medium uppercase text-zinc-500">
          Step Timeline
        </p>
        <div className="relative ml-3 border-l border-zinc-700/50 pl-5 space-y-3">
          {timeline.map((event, idx) => {
            const StatusIcon =
              event.status === "success" ? (
                <CheckCircle2 size={14} className="text-emerald-400" />
              ) : event.status === "error" ? (
                <XCircle size={14} className="text-red-400" />
              ) : event.status === "running" ? (
                <Clock size={14} className="animate-pulse text-amber-400" />
              ) : (
                <Clock size={14} className="text-zinc-600" />
              );

            const dotColor =
              event.status === "success"
                ? "bg-emerald-400"
                : event.status === "error"
                  ? "bg-red-400"
                  : event.status === "running"
                    ? "bg-amber-400 animate-pulse"
                    : "bg-zinc-600";

            return (
              <motion.div
                key={event.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.03 }}
                className="relative flex items-start gap-2"
              >
                {/* Dot on the timeline line */}
                <div
                  className={`absolute -left-[25px] top-1.5 h-2 w-2 rounded-full ${dotColor}`}
                />

                {StatusIcon}
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-300">{event.label}</p>
                  {event.details && (
                    <p className="text-[10px] text-zinc-500">{event.details}</p>
                  )}
                </div>
                <span className="whitespace-nowrap font-mono text-[9px] text-zinc-600">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </motion.div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}
