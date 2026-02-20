import { useState } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { Brain, ChevronLeft, ChevronRight, Lightbulb } from "lucide-react";

export function RootCauseCard() {
  const fixes = useAgentStore((s) => s.fixes);
  const [idx, setIdx] = useState(0);

  /* Only show fixes that have a root cause */
  const withRC = fixes.filter((f) => f.rootCause);
  if (withRC.length === 0) return null;

  const fix = withRC[idx % withRC.length];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.35 }}
      className="card"
    >
      <div className="mb-3 flex items-center gap-2">
        <Brain size={15} className="text-violet-400" />
        <h3 className="text-sm font-semibold text-zinc-300">
          Root Cause Analysis
        </h3>
        {withRC.length > 1 && (
          <span className="ml-auto text-[10px] text-zinc-500">
            {(idx % withRC.length) + 1}/{withRC.length}
          </span>
        )}
      </div>

      {/* Current root cause */}
      <div className="rounded-lg border border-violet-500/10 bg-violet-500/[0.03] p-4">
        <div className="mb-2 flex items-center gap-2">
          <Lightbulb size={13} className="text-amber-400" />
          <span className="font-mono text-xs text-zinc-300">{fix.file}</span>
          <span className="ml-auto badge-warning text-[9px]">{fix.bugType}</span>
        </div>

        <p className="mb-3 text-xs leading-relaxed text-zinc-400">
          {fix.rootCause}
        </p>

        <div className="flex items-center gap-3 text-[10px] text-zinc-500">
          <span>
            Line <strong className="text-zinc-300">{fix.line}</strong>
          </span>
          <span>
            Confidence{" "}
            <strong className="text-purple-400">
              {Math.round(fix.confidence * 100)}%
            </strong>
          </span>
        </div>
      </div>

      {/* Navigation */}
      {withRC.length > 1 && (
        <div className="mt-3 flex justify-center gap-2">
          <button
            onClick={() => setIdx((p) => (p - 1 + withRC.length) % withRC.length)}
            className="rounded-md border border-zinc-700 p-1.5 text-zinc-400 transition hover:bg-zinc-800"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            onClick={() => setIdx((p) => (p + 1) % withRC.length)}
            className="rounded-md border border-zinc-700 p-1.5 text-zinc-400 transition hover:bg-zinc-800"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </motion.div>
  );
}
