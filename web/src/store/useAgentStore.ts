import { create } from "zustand";
import { API_BASE } from "../config";
import type {
  BugType,
  Fix,
  TimelineEvent,
  Failure,
  IterationResult,
  PipelineStep,
  RunStatus,
} from "../types";

/* ── Store Shape ── */
interface AgentState {
  /* Input */
  repositoryUrl: string;
  teamName: string;
  leaderName: string;

  /* Run meta */
  runId: string | null;
  wsUrl: string | null;
  status: RunStatus;
  currentStep: PipelineStep;

  /* Results */
  branchName: string;
  totalFailures: number;
  totalFixes: number;
  totalTime: number;
  score: number;
  speedBonus: number;
  efficiencyPenalty: number;

  /* Collections */
  fixes: Fix[];
  failures: Failure[];
  timeline: TimelineEvent[];
  iterationResults: IterationResult[];
  logs: string[];

  /* Live monitor */
  iteration: number;
  maxRetries: number;
  currentBugType: BugType | "";
  currentFile: string;
  confidence: number;
  testFramework: string;

  /* Actions */
  setField: <K extends keyof AgentState>(key: K, value: AgentState[K]) => void;
  startRun: () => Promise<void>;
  handleWSMessage: (msg: Record<string, unknown>) => void;
  reset: () => void;
}

const INITIAL: Pick<
  AgentState,
  | "runId"
  | "wsUrl"
  | "status"
  | "currentStep"
  | "branchName"
  | "totalFailures"
  | "totalFixes"
  | "totalTime"
  | "score"
  | "speedBonus"
  | "efficiencyPenalty"
  | "fixes"
  | "failures"
  | "timeline"
  | "iterationResults"
  | "logs"
  | "iteration"
  | "maxRetries"
  | "currentBugType"
  | "currentFile"
  | "confidence"
  | "testFramework"
> = {
  runId: null,
  wsUrl: null,
  status: "idle",
  currentStep: "idle",
  branchName: "",
  totalFailures: 0,
  totalFixes: 0,
  totalTime: 0,
  score: 0,
  speedBonus: 0,
  efficiencyPenalty: 0,
  fixes: [],
  failures: [],
  timeline: [],
  iterationResults: [],
  logs: [],
  iteration: 0,
  maxRetries: 5,
  currentBugType: "",
  currentFile: "",
  confidence: 0,
  testFramework: "",
};

export const useAgentStore = create<AgentState>((set, get) => ({
  /* ── Defaults ── */
  repositoryUrl: "",
  teamName: "",
  leaderName: "",
  ...INITIAL,

  /* ── Setters ── */
  setField: (key, value) => set({ [key]: value } as Partial<AgentState>),

  /* ── Start pipeline ── */
  startRun: async () => {
    const { repositoryUrl, teamName, leaderName } = get();
    if (!repositoryUrl || !teamName || !leaderName) return;

    set({ ...INITIAL, status: "running", currentStep: "cloning" });

    try {
      const res = await fetch(`${API_BASE}/api/v1/run-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_url: repositoryUrl,
          team_name: teamName,
          leader_name: leaderName,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      set({
        runId: data.run_id,
        wsUrl: data.ws_url,
        branchName: data.branch_name ?? "",
      });
    } catch (err) {
      set({
        status: "failed",
        currentStep: "failed",
        logs: [...get().logs, `❌ Failed to start: ${err}`],
      });
    }
  },

  /* ── Handle incoming WebSocket messages ── */
  handleWSMessage: (msg) => {
    const state = get();
    const ts = (msg.timestamp as string) ?? new Date().toISOString();
    const data = (msg.data ?? {}) as Record<string, unknown>;
    const type = msg.type as string;

    switch (type) {
      case "step_update": {
        const step = data.step as PipelineStep;
        const label = (data.label as string) ?? step;

        /* Update timeline */
        const timeline = [...state.timeline];
        const lastEvent = timeline[timeline.length - 1];

        if (lastEvent && lastEvent.step === step && lastEvent.status === "running") {
          timeline[timeline.length - 1] = { ...lastEvent, label, timestamp: ts };
        } else {
          /* Mark prev running → success */
          const prevIdx = timeline.findIndex((t) => t.status === "running");
          if (prevIdx >= 0) timeline[prevIdx] = { ...timeline[prevIdx], status: "success" };

          timeline.push({
            id: `${step}-${Date.now()}`,
            step,
            label,
            status: "running",
            timestamp: ts,
          });
        }

        const patch: Partial<AgentState> = {
          currentStep: step,
          timeline,
          logs: [...state.logs, `▸ ${label}`],
        };

        if (step === "completed") {
          patch.status = "passed";
          /* Mark last running → success */
          const lastRunning = timeline.findIndex((t) => t.status === "running");
          if (lastRunning >= 0) timeline[lastRunning] = { ...timeline[lastRunning], status: "success" };
        }
        if (step === "failed") {
          patch.status = "failed";
          const lastRunning = timeline.findIndex((t) => t.status === "running");
          if (lastRunning >= 0) timeline[lastRunning] = { ...timeline[lastRunning], status: "error" };
        }

        if (data.test_framework) patch.testFramework = data.test_framework as string;
        if (data.branch_name) patch.branchName = data.branch_name as string;

        set(patch);
        break;
      }

      case "log":
        set({ logs: [...state.logs, data.message as string] });
        break;

      case "failure": {
        const failure: Failure = {
          file: (data.file as string) ?? "",
          line: (data.line as number) ?? 0,
          bugType: (data.bug_type as BugType) ?? "LOGIC",
          message: (data.message as string) ?? "",
          testName: data.test_name as string | undefined,
        };
        set({
          failures: [...state.failures, failure],
          totalFailures: state.totalFailures + 1,
          currentBugType: failure.bugType,
          currentFile: failure.file,
        });
        break;
      }

      case "fix": {
        const fix: Fix = {
          id: `fix-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          file: (data.file as string) ?? "",
          bugType: (data.bug_type as BugType) ?? "LOGIC",
          line: (data.line as number) ?? 0,
          summary: (data.summary as string) ?? "",
          commitMessage: (data.commit_message as string) ?? "",
          diff: (data.diff as string) ?? "",
          confidence: (data.confidence as number) ?? 0,
          rootCause: (data.root_cause as string) ?? "",
          status: (data.status as Fix["status"]) ?? "applied",
          iteration: (data.iteration as number) ?? state.iteration,
        };
        set({
          fixes: [...state.fixes, fix],
          totalFixes: state.totalFixes + 1,
          confidence: fix.confidence,
          currentFile: fix.file,
          currentBugType: fix.bugType,
        });
        break;
      }

      case "iteration": {
        const iterResult: IterationResult = {
          iteration: (data.iteration as number) ?? state.iteration + 1,
          testsRun: (data.tests_run as number) ?? 0,
          testsPassed: (data.tests_passed as number) ?? 0,
          testsFailed: (data.tests_failed as number) ?? 0,
          fixesApplied: (data.fixes_applied as number) ?? 0,
          passed: (data.passed as boolean) ?? false,
          timestamp: ts,
        };
        set({
          iteration: iterResult.iteration,
          maxRetries: (data.max_retries as number) ?? state.maxRetries,
          iterationResults: [...state.iterationResults, iterResult],
          logs: [
            ...state.logs,
            `🔄 Iteration ${iterResult.iteration}: ${iterResult.testsFailed} failures, ${iterResult.fixesApplied} fixes`,
          ],
        });
        break;
      }

      case "result": {
        set({
          status: (data.status as RunStatus) ?? "passed",
          currentStep: "completed",
          totalFailures: (data.total_failures as number) ?? state.totalFailures,
          totalFixes: (data.total_fixes as number) ?? state.totalFixes,
          totalTime: (data.total_time as number) ?? 0,
          score: (data.score as number) ?? 0,
          speedBonus: (data.speed_bonus as number) ?? 0,
          efficiencyPenalty: (data.efficiency_penalty as number) ?? 0,
          branchName: (data.branch_name as string) ?? state.branchName,
          logs: [...state.logs, `✅ Pipeline complete — Score: ${data.score}`],
        });
        break;
      }

      case "error":
        set({
          status: "failed",
          currentStep: "failed",
          logs: [...state.logs, `❌ ${data.message ?? "Unknown error"}`],
        });
        break;

      default:
        break;
    }
  },

  /* ── Reset ── */
  reset: () =>
    set({
      ...INITIAL,
      repositoryUrl: get().repositoryUrl,
      teamName: get().teamName,
      leaderName: get().leaderName,
    }),
}));
