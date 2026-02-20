import { useCallback, useEffect, useRef, useState } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { API_BASE } from "../config";
import {
  GitBranch,
  Play,
  RotateCcw,
  User,
  Users,
  ShieldCheck,
  Shield,
  ShieldX,
  ExternalLink,
  Loader2,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

/* ── Repo auth check response type ── */
interface RepoAuthStatus {
  repo: string;
  owner: string;
  repo_name: string;
  app_configured: boolean;
  pat_available: boolean;
  app_installed: boolean;
  installation_id: number | null;
  auth_method: "github_app" | "pat" | "none";
  auth_ready: boolean;
  install_url?: string;
}

export function InputSection() {
  const repositoryUrl = useAgentStore((s) => s.repositoryUrl);
  const teamName = useAgentStore((s) => s.teamName);
  const leaderName = useAgentStore((s) => s.leaderName);
  const status = useAgentStore((s) => s.status);
  const setField = useAgentStore((s) => s.setField);
  const startRun = useAgentStore((s) => s.startRun);
  const reset = useAgentStore((s) => s.reset);

  /* ── Repo auth state ── */
  const [repoAuth, setRepoAuth] = useState<RepoAuthStatus | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [justInstalled, setJustInstalled] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isRunning = status === "running";
  const canStart =
    !!repositoryUrl &&
    !!teamName &&
    !!leaderName &&
    !isRunning &&
    (repoAuth?.auth_ready ?? false);

  /* ── Check if user returned from GitHub App install ── */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("github_app") === "installed") {
      setJustInstalled(true);
      const repo = params.get("repo");
      if (repo) {
        const url = `https://github.com/${repo}`;
        setField("repositoryUrl", url);
      }
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [setField]);

  /* ── Check repo auth when URL changes (debounced) ── */
  const checkRepoAuth = useCallback(async (url: string, fresh = false) => {
    if (
      !url.trim() ||
      !url.includes("github.com/") ||
      url.split("/").length < 5
    ) {
      setRepoAuth(null);
      setAuthError(null);
      return;
    }

    setCheckingAuth(true);
    setAuthError(null);

    try {
      const freshParam = fresh ? "&fresh=true" : "";
      const res = await fetch(
        `${API_BASE}/api/v1/github-app/check-repo?repo=${encodeURIComponent(url.trim())}${freshParam}`
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: RepoAuthStatus = await res.json();
      setRepoAuth(data);
      setJustInstalled(false);
    } catch (err) {
      setAuthError(
        err instanceof Error ? err.message : "Failed to check repo"
      );
      setRepoAuth(null);
    } finally {
      setCheckingAuth(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      checkRepoAuth(repositoryUrl);
    }, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [repositoryUrl, checkRepoAuth]);

  /* ── Re-check after install (fresh=true to clear cache) ── */
  useEffect(() => {
    if (justInstalled && repositoryUrl) {
      checkRepoAuth(repositoryUrl, true);
    }
  }, [justInstalled, repositoryUrl, checkRepoAuth]);

  /* ── Install App handler ── */
  const handleInstallApp = () => {
    if (repoAuth?.install_url) {
      window.location.href = repoAuth.install_url;
    }
  };

  /* ── Auth status badge ── */
  const renderAuthBadge = () => {
    if (checkingAuth) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
          <Loader2 size={12} className="animate-spin" /> Checking…
        </span>
      );
    }
    if (authError) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs text-red-400 ring-1 ring-red-500/20">
          <ShieldX size={12} /> Error
        </span>
      );
    }
    if (!repoAuth) return null;

    if (repoAuth.app_installed) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2.5 py-0.5 text-xs font-medium text-green-400 ring-1 ring-green-500/20">
          <ShieldCheck size={12} /> GitHub App ✓
        </span>
      );
    }
    if (repoAuth.auth_method === "pat") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-yellow-500/10 px-2.5 py-0.5 text-xs font-medium text-yellow-400 ring-1 ring-yellow-500/20">
          <Shield size={12} /> PAT Fallback
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-medium text-red-400 ring-1 ring-red-500/20">
        <ShieldX size={12} /> No Auth
      </span>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="card neon-glow"
    >
      <div className="mb-5 flex items-center gap-2">
        <GitBranch size={18} className="text-purple-400" />
        <h2 className="text-base font-semibold text-white">
          Run Healing Agent
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Repo URL + Auth Badge */}
        <div className="sm:col-span-3">
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-xs font-medium text-zinc-400">
              GitHub Repository URL
            </label>
            {renderAuthBadge()}
          </div>
          <input
            className="input-field font-mono text-xs"
            type="url"
            placeholder="https://github.com/RohanTewariIIITS/simple_notes_app"
            value={repositoryUrl}
            onChange={(e) => setField("repositoryUrl", e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* ── App NOT installed — show install prompt ── */}
        <AnimatePresence>
          {repoAuth && !repoAuth.app_installed && repoAuth.app_configured && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="sm:col-span-3 overflow-hidden"
            >
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    size={16}
                    className="mt-0.5 shrink-0 text-amber-400"
                  />
                  <div className="flex-1 space-y-2">
                    <p className="text-xs text-amber-300">
                      <strong>GitHub App not installed</strong> on{" "}
                      <span className="font-mono text-amber-200">
                        {repoAuth.repo}
                      </span>
                    </p>
                    <p className="text-[11px] text-amber-400/70">
                      Install the App for full permissions (branch create, push,
                      PR). Otherwise the system will use your Personal Access
                      Token as fallback.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleInstallApp}
                        className="flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500"
                      >
                        <ExternalLink size={12} /> Install GitHub App
                      </button>
                      {repoAuth.auth_method === "pat" && (
                        <span className="text-[11px] text-zinc-500">
                          or continue with PAT ↓
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Just-installed success ── */}
        <AnimatePresence>
          {justInstalled && repoAuth?.app_installed && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="sm:col-span-3 overflow-hidden"
            >
              <div className="flex items-center gap-2 rounded-lg border border-green-500/20 bg-green-500/5 p-3 text-xs text-green-400">
                <CheckCircle2 size={14} />
                GitHub App installed successfully on{" "}
                <span className="font-mono font-semibold">
                  {repoAuth.repo}
                </span>
                ! Ready to run.
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── No auth at all ── */}
        <AnimatePresence>
          {repoAuth && repoAuth.auth_method === "none" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="sm:col-span-3 overflow-hidden"
            >
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <div className="flex items-start gap-2">
                  <ShieldX size={14} className="mt-0.5 text-red-400" />
                  <div className="space-y-1">
                    <p className="text-xs text-red-400">
                      <strong>No authentication available.</strong>
                    </p>
                    <p className="text-[11px] text-red-400/70">
                      Set{" "}
                      <code className="rounded bg-red-500/10 px-1">
                        GITHUB_TOKEN
                      </code>{" "}
                      in .env or install the GitHub App.
                    </p>
                    {repoAuth.app_configured && repoAuth.install_url && (
                      <button
                        onClick={handleInstallApp}
                        className="mt-1 flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-red-500"
                      >
                        <ExternalLink size={12} /> Install GitHub App
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Team Name */}
        <div>
          <label className="mb-1.5 flex items-center gap-1 text-xs font-medium text-zinc-400">
            <Users size={12} /> Team Name
          </label>
          <input
            className="input-field"
            placeholder="Team Alpha"
            value={teamName}
            onChange={(e) => setField("teamName", e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* Leader Name */}
        <div>
          <label className="mb-1.5 flex items-center gap-1 text-xs font-medium text-zinc-400">
            <User size={12} /> Leader Name
          </label>
          <input
            className="input-field"
            placeholder="John Doe"
            value={leaderName}
            onChange={(e) => setField("leaderName", e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* Buttons */}
        <div className="flex items-end gap-2">
          <button
            className="btn-primary flex-1"
            onClick={startRun}
            disabled={!canStart}
          >
            {isRunning ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Running…
              </>
            ) : (
              <>
                <Play size={15} /> Run Agent
              </>
            )}
          </button>

          {(status === "passed" || status === "failed") && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 transition hover:bg-zinc-800"
            >
              <RotateCcw size={14} /> Reset
            </button>
          )}
        </div>
      </div>

      {/* Preview branch name */}
      {teamName && leaderName && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-3 font-mono text-xs text-zinc-500"
        >
          Branch:{" "}
          <span className="text-purple-400">
            {teamName.toUpperCase().replace(/\s+/g, "_")}_
            {leaderName.toUpperCase().replace(/\s+/g, "_")}_AI_Fix
          </span>
        </motion.p>
      )}

      {/* Auth method indicator */}
      {repoAuth?.auth_ready && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-600"
        >
          {repoAuth.app_installed ? (
            <>
              <ShieldCheck size={10} className="text-green-500" />
              Will use GitHub App (Installation #{repoAuth.installation_id})
            </>
          ) : (
            <>
              <Shield size={10} className="text-yellow-500" />
              Will use Personal Access Token (PAT fallback)
            </>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
