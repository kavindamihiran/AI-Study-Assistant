"use client";

import { Check, Copy, Loader2, Plug, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  MCPConnection,
  MCP_SERVER_URL,
  listMcpConnections,
  revokeMcpConnection,
} from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "unknown" : parsed.toLocaleString();
}

/**
 * Lets a student add StudyOS to Claude or ChatGPT and manage the chats that
 * are already connected to their account.
 */
export function MCPConnections() {
  const [connections, setConnections] = useState<MCPConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setConnections(await listMcpConnections());
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not load connections",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(MCP_SERVER_URL);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copying failed. Select the address and copy it manually.");
    }
  };

  const revoke = async (grantId: string) => {
    setRevoking(grantId);
    try {
      await revokeMcpConnection(grantId);
      setConnections((current) =>
        current.filter((connection) => connection.grant_id !== grantId),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not disconnect the app",
      );
    } finally {
      setRevoking("");
    }
  };

  return (
    <section className="rounded-3xl border border-[#dfe5e1] bg-white p-6">
      <div className="flex items-center gap-3">
        <Plug size={18} className="text-[#66806f]" />
        <h2 className="text-base font-semibold">Connected chat apps</h2>
      </div>
      <p className="mt-2 text-sm text-[#6f7c75]">
        Add StudyOS as a connector in Claude or ChatGPT and work with your notes
        without leaving the chat. Paste this address when the app asks for an
        MCP server URL, then sign in to StudyOS to approve it.
      </p>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-xl border border-[#dce3de] bg-[#f6f8f6] px-4 py-3 text-xs text-[#3f4b45]">
          {MCP_SERVER_URL}
        </code>
        <button
          type="button"
          onClick={copyUrl}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#dce3de] px-4 py-3 text-sm font-medium hover:border-[#6e947a]"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {error ? (
        <p className="mt-3 rounded-xl bg-[#fdf1f1] px-4 py-3 text-xs text-[#9a3b3b]">
          {error}
        </p>
      ) : null}

      <div className="mt-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c8982]">
          Apps with access
        </p>
        {loading ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-[#849089]">
            <Loader2 size={14} className="animate-spin" /> Loading connections
          </p>
        ) : connections.length === 0 ? (
          <p className="mt-3 text-sm text-[#849089]">
            No chat app is connected yet.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {connections.map((connection) => (
              <li
                key={connection.grant_id}
                className="flex flex-col gap-3 rounded-2xl border border-[#dfe5e1] p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    {connection.client_name}
                  </p>
                  <p className="mt-1 text-xs text-[#849089]">
                    Connected {formatDate(connection.created_at)} · last used{" "}
                    {formatDate(connection.last_used_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => revoke(connection.grant_id)}
                  disabled={revoking === connection.grant_id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#e4d3d3] px-4 py-2 text-sm font-medium text-[#9a3b3b] hover:border-[#c98b8b] disabled:opacity-60"
                >
                  {revoking === connection.grant_id ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                  Disconnect
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
