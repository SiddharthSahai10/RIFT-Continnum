/* ── Shared Type Definitions ── */

export type BugType =
  | "LINTING"
  | "SYNTAX"
  | "LOGIC"
  | "TYPE_ERROR"
  | "IMPORT"
  | "INDENTATION";

export type PipelineStep =
  | "idle"
  | "cloning"
  | "detecting_framework"
  | "installing_deps"
  | "running_tests"
  | "analyzing_failures"
  | "generating_fix"
  | "applying_fix"
  | "verifying"
  | "publishing"
  | "generating_results"
  | "completed"
  | "failed";

export type RunStatus = "idle" | "running" | "passed" | "failed";

export interface Fix {
  id: string;
  file: string;
  bugType: BugType;
  line: number;
  summary: string;
  commitMessage: string;
  diff: string;
  confidence: number;
  rootCause: string;
  status: "pending" | "applied" | "verified" | "failed";
  iteration: number;
}

export interface TimelineEvent {
  id: string;
  step: PipelineStep;
  label: string;
  status: "pending" | "running" | "success" | "error";
  timestamp: string;
  duration?: number;
  details?: string;
}

export interface Failure {
  file: string;
  line: number;
  bugType: BugType;
  message: string;
  testName?: string;
}

export interface IterationResult {
  iteration: number;
  testsRun: number;
  testsPassed: number;
  testsFailed: number;
  fixesApplied: number;
  passed: boolean;
  timestamp: string;
}

export interface RunResult {
  runId: string;
  repositoryUrl: string;
  teamName: string;
  leaderName: string;
  branchName: string;
  status: RunStatus;
  totalFailures: number;
  totalFixes: number;
  iterations: number;
  maxRetries: number;
  score: number;
  speedBonus: number;
  efficiencyPenalty: number;
  totalTime: number;
  fixes: Fix[];
  failures: Failure[];
  timeline: TimelineEvent[];
  iterationResults: IterationResult[];
}

export interface WSMessage {
  type:
    | "step_update"
    | "log"
    | "failure"
    | "fix"
    | "iteration"
    | "result"
    | "error";
  run_id: string;
  data: Record<string, unknown>;
  timestamp: string;
}
