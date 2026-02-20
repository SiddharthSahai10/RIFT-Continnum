import { useEffect, useState } from "react";
import { Shield, ShieldCheck, ShieldX, ExternalLink, RefreshCw, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface AppStatus {
  auth_method: string;
  github_app_configured: boolean;
  pat_available: boolean;
  app_id: string | null;
  app_slug: string | null;
  total_installations?: number;
  installations?: Array<{
    id: number;
    account: string;
    repository_selection: string;
    created_at: string;
  }>;
  installations_error?: string;
}

export function GitHubAppStatus() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installRepo, setInstallRepo] = useState("");

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/github-app/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  // Check if user came back from GitHub App install callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("github_app") === "installed") {
      fetchStatus(); // Refresh status after install
      // Clean up URL
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const handleInstall = () => {
    const repo = installRepo.trim();
    const url = repo
      ? `/api/v1/github-app/install?repo=${encodeURIComponent(repo)}`
      : `/api/v1/github-app/install`;
    window.open(url, "_blank");
  };

  const getAuthBadge = () => {
    if (!status) return null;
    switch (status.auth_method) {
      case "github_app":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2.5 py-0.5 text-xs font-medium text-green-400 ring-1 ring-green-500/20">
            <ShieldCheck size={12} /> GitHub App ✓
          </span>
        );
      case "pat":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-yellow-500/10 px-2.5 py-0.5 text-xs font-medium text-yellow-400 ring-1 ring-yellow-500/20">
            <Shield size={12} /> PAT Fallback
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-medium text-red-400 ring-1 ring-red-500/20">
            <ShieldX size={12} /> No Auth
          </span>
        );
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="card"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-purple-400" />
          <h3 className="text-sm font-semibold text-white">GitHub App Auth</h3>
          {getAuthBadge()}
        </div>
        <button
          onClick={fetchStatus}
          disabled={loading}
          className="rounded-md p-1.5 text-zinc-400 transition hover:bg-zinc-700 hover:text-white"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      <AnimatePresence>
        {status && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-3"
          >
            {/* Status Details */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md bg-zinc-800/50 px-3 py-2">
                <span className="text-zinc-500">App ID</span>
                <p className="font-mono text-zinc-300">{status.app_id ?? "Not set"}</p>
              </div>
              <div className="rounded-md bg-zinc-800/50 px-3 py-2">
                <span className="text-zinc-500">Installations</span>
                <p className="font-mono text-zinc-300">{status.total_installations ?? 0}</p>
              </div>
            </div>

            {/* Installations List */}
            {status.installations && status.installations.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-zinc-400">Active Installations</p>
                {status.installations.map((inst) => (
                  <div
                    key={inst.id}
                    className="flex items-center justify-between rounded-md bg-zinc-800/50 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle2 size={12} className="text-green-400" />
                      <span className="text-zinc-300">@{inst.account}</span>
                    </div>
                    <span className="text-zinc-500">{inst.repository_selection}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Install on new repo */}
            {status.github_app_configured && (
              <div className="space-y-2 border-t border-zinc-800 pt-3">
                <p className="text-xs font-medium text-zinc-400">
                  Install on a Repository
                </p>
                <div className="flex gap-2">
                  <input
                    className="input-field flex-1 text-xs"
                    placeholder="owner/repo (optional)"
                    value={installRepo}
                    onChange={(e) => setInstallRepo(e.target.value)}
                  />
                  <button
                    onClick={handleInstall}
                    className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-purple-500"
                  >
                    <ExternalLink size={12} /> Install
                  </button>
                </div>
                <p className="text-[10px] text-zinc-600">
                  Leave blank to install on all repos. After install, GitHub will redirect back here.
                </p>
              </div>
            )}

            {/* Warning if no auth */}
            {status.auth_method === "none" && (
              <div className="rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-400">
                ⚠️ No authentication configured. Set GITHUB_APP_* or GITHUB_TOKEN in .env
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
