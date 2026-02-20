import { useState } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { motion, AnimatePresence } from "framer-motion";
import { Table, CheckCircle2, XCircle, Clock, ChevronDown } from "lucide-react";
import type { Fix, BugType } from "../types";

const BUG_COLORS: Record<BugType, string> = {
  LINTING: "badge-info",
  SYNTAX: "badge-danger",
  LOGIC: "badge-warning",
  TYPE_ERROR: "badge-danger",
  IMPORT: "badge-info",
  INDENTATION: "badge-neutral",
};

export function FixesTable() {
  const fixes = useAgentStore((s) => s.fixes);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (fixes.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="card"
    >
      <div className="mb-4 flex items-center gap-2">
        <Table size={15} className="text-indigo-400" />
        <h3 className="text-sm font-semibold text-zinc-300">Fixes Applied</h3>
        <span className="ml-auto badge-info">{fixes.length}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-[10px] font-medium uppercase text-zinc-500">
              <th className="pb-2 pr-3">File</th>
              <th className="pb-2 pr-3">Bug Type</th>
              <th className="pb-2 pr-3">Line</th>
              <th className="pb-2 pr-3">Commit Message</th>
              <th className="pb-2 pr-3 text-center">Status</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            <AnimatePresence>
              {fixes.map((fix) => (
                <FixRow
                  key={fix.id}
                  fix={fix}
                  isExpanded={expanded === fix.id}
                  onToggle={() =>
                    setExpanded(expanded === fix.id ? null : fix.id)
                  }
                />
              ))}
            </AnimatePresence>
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}

function FixRow({
  fix,
  isExpanded,
  onToggle,
}: {
  fix: Fix;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const StatusIcon = {
    pending: <Clock size={14} className="text-zinc-500" />,
    applied: <CheckCircle2 size={14} className="text-amber-400" />,
    verified: <CheckCircle2 size={14} className="text-emerald-400" />,
    failed: <XCircle size={14} className="text-red-400" />,
  }[fix.status];

  return (
    <>
      <motion.tr
        layout
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        className="cursor-pointer border-b border-zinc-800/50 transition hover:bg-zinc-800/30"
        onClick={onToggle}
      >
        <td className="py-2.5 pr-3 font-mono text-zinc-300 truncate max-w-[180px]">
          {fix.file}
        </td>
        <td className="py-2.5 pr-3">
          <span className={BUG_COLORS[fix.bugType]}>{fix.bugType}</span>
        </td>
        <td className="py-2.5 pr-3 font-mono text-zinc-400">{fix.line}</td>
        <td className="py-2.5 pr-3 text-zinc-400 truncate max-w-[200px]">
          {fix.commitMessage}
        </td>
        <td className="py-2.5 pr-3 text-center">{StatusIcon}</td>
        <td className="py-2.5">
          <ChevronDown
            size={14}
            className={`text-zinc-500 transition-transform ${
              isExpanded ? "rotate-180" : ""
            }`}
          />
        </td>
      </motion.tr>

      <AnimatePresence>
        {isExpanded && (
          <motion.tr
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
          >
            <td colSpan={6} className="border-b border-zinc-800/50 p-0">
              <div className="space-y-2 bg-zinc-900/50 p-4">
                <div>
                  <span className="text-[10px] font-medium uppercase text-zinc-500">
                    Summary
                  </span>
                  <p className="mt-0.5 text-xs text-zinc-300">{fix.summary}</p>
                </div>
                {fix.rootCause && (
                  <div>
                    <span className="text-[10px] font-medium uppercase text-zinc-500">
                      Root Cause
                    </span>
                    <p className="mt-0.5 text-xs text-zinc-400">
                      {fix.rootCause}
                    </p>
                  </div>
                )}
                {fix.diff && (
                  <div>
                    <span className="text-[10px] font-medium uppercase text-zinc-500">
                      Diff
                    </span>
                    <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-zinc-950 p-3 font-mono text-[11px] text-zinc-400">
                      {fix.diff}
                    </pre>
                  </div>
                )}
                <div className="flex gap-4 text-[10px] text-zinc-500">
                  <span>
                    Confidence:{" "}
                    <strong className="text-purple-400">
                      {Math.round(fix.confidence * 100)}%
                    </strong>
                  </span>
                  <span>
                    Iteration: <strong className="text-zinc-300">{fix.iteration}</strong>
                  </span>
                </div>
              </div>
            </td>
          </motion.tr>
        )}
      </AnimatePresence>
    </>
  );
}
