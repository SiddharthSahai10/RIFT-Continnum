import { useAgentStore } from "../store/useAgentStore";
import { motion } from "framer-motion";
import { Flame } from "lucide-react";
import type { BugType } from "../types";

const BUG_TYPE_COLORS: Record<BugType, string> = {
  LINTING: "#22d3ee",
  SYNTAX: "#ef4444",
  LOGIC: "#eab308",
  TYPE_ERROR: "#f97316",
  IMPORT: "#8b5cf6",
  INDENTATION: "#6b7280",
};

export function FailureHeatmap() {
  const failures = useAgentStore((s) => s.failures);

  if (failures.length === 0) return null;

  /* Group by file */
  const byFile = failures.reduce<Record<string, Record<BugType, number>>>(
    (acc, f) => {
      if (!acc[f.file]) acc[f.file] = {} as Record<BugType, number>;
      acc[f.file][f.bugType] = (acc[f.file][f.bugType] || 0) + 1;
      return acc;
    },
    {},
  );

  const files = Object.keys(byFile);
  const bugTypes: BugType[] = [
    "LINTING",
    "SYNTAX",
    "LOGIC",
    "TYPE_ERROR",
    "IMPORT",
    "INDENTATION",
  ];

  /* Find max for opacity scaling */
  let maxCount = 1;
  for (const file of files) {
    for (const bt of bugTypes) {
      const c = byFile[file]?.[bt] ?? 0;
      if (c > maxCount) maxCount = c;
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="card"
    >
      <div className="mb-4 flex items-center gap-2">
        <Flame size={15} className="text-orange-400" />
        <h3 className="text-sm font-semibold text-zinc-300">Failure Heatmap</h3>
      </div>

      <div className="overflow-x-auto">
        {/* Header */}
        <div className="flex gap-1 mb-1">
          <div className="w-28 shrink-0" />
          {bugTypes.map((bt) => (
            <div
              key={bt}
              className="flex-1 min-w-[40px] text-center text-[8px] font-medium uppercase"
              style={{ color: BUG_TYPE_COLORS[bt] }}
            >
              {bt.slice(0, 4)}
            </div>
          ))}
        </div>

        {/* Rows */}
        {files.map((file, fi) => (
          <motion.div
            key={file}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: fi * 0.04 }}
            className="flex items-center gap-1 mb-1"
          >
            <div className="w-28 shrink-0 truncate font-mono text-[10px] text-zinc-500">
              {file.split("/").pop()}
            </div>
            {bugTypes.map((bt) => {
              const count = byFile[file]?.[bt] ?? 0;
              const opacity = count > 0 ? 0.2 + (count / maxCount) * 0.8 : 0.05;

              return (
                <div
                  key={bt}
                  className="flex-1 min-w-[40px] h-6 rounded-sm flex items-center justify-center text-[10px] font-mono"
                  style={{
                    backgroundColor:
                      count > 0
                        ? `${BUG_TYPE_COLORS[bt]}${Math.round(opacity * 255)
                            .toString(16)
                            .padStart(2, "0")}`
                        : "rgba(255,255,255,0.02)",
                    color:
                      count > 0 ? BUG_TYPE_COLORS[bt] : "rgba(255,255,255,0.1)",
                  }}
                  title={`${file}: ${bt} × ${count}`}
                >
                  {count > 0 ? count : ""}
                </div>
              );
            })}
          </motion.div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-2">
        {bugTypes.map((bt) => (
          <span
            key={bt}
            className="flex items-center gap-1 text-[9px] text-zinc-500"
          >
            <span
              className="h-2 w-2 rounded-sm"
              style={{ backgroundColor: BUG_TYPE_COLORS[bt] }}
            />
            {bt}
          </span>
        ))}
      </div>
    </motion.div>
  );
}
