import { useState } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { Code2, ChevronDown } from "lucide-react";

export function DiffViewer() {
  const fixes = useAgentStore((s) => s.fixes);
  const [selectedIdx, setSelectedIdx] = useState(0);

  const withDiff = fixes.filter((f) => f.diff);
  if (withDiff.length === 0) return null;

  const fix = withDiff[selectedIdx % withDiff.length];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25 }}
      className="card"
    >
      <div className="mb-4 flex items-center gap-2">
        <Code2 size={15} className="text-emerald-400" />
        <h3 className="text-sm font-semibold text-zinc-300">Diff Viewer</h3>
      </div>

      {/* Fix selector */}
      {withDiff.length > 1 && (
        <div className="relative mb-3">
          <select
            value={selectedIdx}
            onChange={(e) => setSelectedIdx(Number(e.target.value))}
            className="w-full appearance-none rounded-lg border border-zinc-700/60 bg-zinc-800/50 py-2 pl-3 pr-8 font-mono text-xs text-zinc-300 outline-none focus:border-purple-500/50"
          >
            {withDiff.map((f, i) => (
              <option key={f.id} value={i}>
                {f.file} — {f.bugType} (line {f.line})
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
        </div>
      )}

      {/* Diff display */}
      <div className="overflow-x-auto rounded-lg border border-zinc-800/60 bg-zinc-950">
        <pre className="p-4 font-mono text-[11px] leading-5">
          {fix.diff.split("\n").map((line, i) => {
            let cls = "text-zinc-500";
            if (line.startsWith("+") && !line.startsWith("+++")) {
              cls = "text-emerald-400 bg-emerald-500/5";
            } else if (line.startsWith("-") && !line.startsWith("---")) {
              cls = "text-red-400 bg-red-500/5";
            } else if (line.startsWith("@@")) {
              cls = "text-cyan-400";
            } else if (line.startsWith("diff") || line.startsWith("index")) {
              cls = "text-zinc-600 font-bold";
            }

            return (
              <div key={i} className={`px-2 ${cls}`}>
                {line}
              </div>
            );
          })}
        </pre>
      </div>

      {/* Meta */}
      <div className="mt-2 flex gap-3 text-[10px] text-zinc-500">
        <span>{fix.commitMessage}</span>
      </div>
    </motion.div>
  );
}
