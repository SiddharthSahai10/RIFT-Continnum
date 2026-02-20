import { useAgentStore } from "./store/useAgentStore";
import { useWebSocket } from "./hooks/useWebSocket";
import { Layout } from "./components/Layout";
import { InputSection } from "./components/InputSection";
import { PipelineProgress } from "./components/PipelineProgress";
import { RunSummary } from "./components/RunSummary";
import { LiveMonitor } from "./components/LiveMonitor";
import { ScoreBreakdown } from "./components/ScoreBreakdown";
import { FixesTable } from "./components/FixesTable";
import { CICDTimeline } from "./components/CICDTimeline";
import { FailureHeatmap } from "./components/FailureHeatmap";
import { RootCauseCard } from "./components/RootCauseCard";
import { DiffViewer } from "./components/DiffViewer";
import { GitHubAppStatus } from "./components/GitHubAppStatus";

export default function App() {
  const runId = useAgentStore((s) => s.runId);
  const status = useAgentStore((s) => s.status);

  /* Establish WebSocket when a run starts */
  useWebSocket(runId);

  const isActive = status === "running" || status === "passed" || status === "failed";

  return (
    <Layout>
      {/* ── Input / Start Section ── */}
      <InputSection />

      {/* ── GitHub App Auth Status ── */}
      <GitHubAppStatus />

      {/* ── Pipeline Progress Bar ── */}
      {isActive && <PipelineProgress />}

      {/* ── Main Dashboard Grid ── */}
      {isActive && (
        <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Left Column */}
          <div className="space-y-5 lg:col-span-8">
            <RunSummary />
            <FixesTable />
            <DiffViewer />
            <CICDTimeline />
          </div>

          {/* Right Column */}
          <div className="space-y-5 lg:col-span-4">
            <LiveMonitor />
            <ScoreBreakdown />
            <FailureHeatmap />
            <RootCauseCard />
          </div>
        </div>
      )}
    </Layout>
  );
}
