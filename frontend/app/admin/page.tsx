"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Database,
  MessageSquare,
  RefreshCw,
  Trash2,
  Users,
} from "lucide-react";

const API_BASE_URL = "http://127.0.0.1:8000/api/v1/admin";

type KnowledgeEntry = {
  id: string;
  content: string;
  category: string;
};

type Analytics = {
  total_queries: number;
  active_users: number;
  kb_size: number;
  system_health: string;
};

type StatusMessage = {
  type: "success" | "error";
  text: string;
} | null;

export default function AdminPage() {
  const [knowledge, setKnowledge] = useState<KnowledgeEntry[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [textId, setTextId] = useState("");
  const [category, setCategory] = useState("logistics");
  const [content, setContent] = useState("");
  const [statusMsg, setStatusMsg] = useState<StatusMessage>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [analyticsResponse, knowledgeResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/analytics`),
        fetch(`${API_BASE_URL}/knowledge`),
      ]);

      if (!analyticsResponse.ok || !knowledgeResponse.ok) {
        throw new Error("Unable to load dashboard data.");
      }

      const analyticsData = await analyticsResponse.json();
      const knowledgeData = await knowledgeResponse.json();

      setAnalytics(analyticsData);
      setKnowledge(knowledgeData.data ?? []);
    } catch (error) {
      setStatusMsg({
        type: "error",
        text: error instanceof Error ? error.message : "Unable to load dashboard data.",
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    try {
      const response = await fetch(`${API_BASE_URL}/knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text_id: textId, category, content }),
      });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Knowledge ingestion failed.");
      }

      setStatusMsg({ type: "success", text: result.message || "Knowledge added successfully!" });
      setTextId("");
      setCategory("logistics");
      setContent("");
      await fetchData();
    } catch (error) {
      setStatusMsg({
        type: "error",
        text: error instanceof Error ? error.message : "Unable to add knowledge.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    setStatusMsg(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/knowledge/${encodeURIComponent(id)}`,
        { method: "DELETE" }
      );
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Knowledge deletion failed.");
      }

      setStatusMsg({ type: "success", text: `Deleted entry ${id}.` });
      await fetchData();
    } catch (error) {
      setStatusMsg({
        type: "error",
        text: error instanceof Error ? error.message : "Unable to delete knowledge.",
      });
    } finally {
      setDeletingId(null);
    }
  };

  const metricCards = [
    { label: "Total Queries", value: analytics?.total_queries || 0, icon: MessageSquare, color: "text-blue-400" },
    { label: "Active Users", value: analytics?.active_users || 0, icon: Users, color: "text-violet-400" },
    { label: "Stored Facts", value: analytics?.kb_size || 0, icon: Database, color: "text-amber-400" },
    { label: "System Health", value: analytics?.system_health || "Checking...", icon: Activity, color: "text-emerald-400" },
  ];

  const fieldClasses = "mt-2 w-full rounded-xl border border-gray-700 bg-gray-800 px-4 py-3 text-gray-100 outline-none transition placeholder:text-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";

  return (
    <main className="h-screen overflow-y-auto bg-gray-950 text-gray-200 p-8">
      <div className="mx-auto max-w-7xl">
        <a href="/" className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-blue-400 transition hover:text-blue-300 hover:underline">
          <ArrowLeft size={16} aria-hidden="true" />
          Back to Concierge Avatar
        </a>

        <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-blue-400">
              Organizer Control Center
            </p>
            <h1 className="text-3xl font-bold text-white sm:text-4xl">
              IOAI 2027 Admin Dashboard
            </h1>
            <p className="mt-3 max-w-2xl text-gray-400">
              Monitor concierge activity and manage the verified knowledge used to answer attendee questions.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void fetchData()}
            disabled={isLoading}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm font-semibold text-gray-200 transition hover:border-gray-600 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={16} className={isLoading ? "animate-spin" : ""} />
            Refresh
          </button>
        </header>

        {statusMsg && (
          <div role="status" className={`mt-6 rounded-xl border px-4 py-3 text-sm ${statusMsg.type === "success" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
            {statusMsg.text}
          </div>
        )}

        <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metricCards.map(({ label, value, icon: Icon, color }) => (
            <article key={label} className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-gray-400">{label}</p>
                  <p className="mt-2 text-2xl font-bold text-white">{value}</p>
                </div>
                <div className="rounded-xl bg-gray-800 p-3">
                  <Icon size={21} className={color} />
                </div>
              </div>
            </article>
          ))}
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-8 mt-8 pb-10">
          
          {/* THE FORM WITH THE FIX */}
          <form onSubmit={handleSubmit} className="h-fit rounded-2xl border border-gray-800 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-xl bg-blue-500/10 p-3 text-blue-400">
                <Database size={22} />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Add Knowledge</h2>
                <p className="text-sm text-gray-500">Create or update an entry</p>
              </div>
            </div>

            <div className="space-y-5">
              <div>
                <label htmlFor="text-id" className="text-sm font-medium">Text ID</label>
                <input id="text-id" required value={textId} onChange={(e) => setTextId(e.target.value)} placeholder="e.g. venue-registration" className={fieldClasses} />
              </div>

              <div>
                <label htmlFor="category" className="text-sm font-medium">Category</label>
                <select id="category" value={category} onChange={(e) => setCategory(e.target.value)} className={fieldClasses}>
                  <option value="logistics">Logistics</option>
                  <option value="culture">Culture</option>
                  <option value="event">Event</option>
                </select>
              </div>

              <div>
                <label htmlFor="content" className="text-sm font-medium">Content</label>
                <textarea id="content" rows={7} required value={content} onChange={(e) => setContent(e.target.value)} placeholder="Enter verified event information..." className={`${fieldClasses} resize-y`} />
              </div>

              {/* THE BUTTON IS PERFECTLY PLACED HERE */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-6 bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded-xl shadow-lg transition-all shadow-blue-500/30 disabled:opacity-50"
              >
                {isSubmitting ? "Adding..." : "+ Add to Knowledge Base"}
              </button>
            </div>
          </form>

          {/* THE DATABASE TABLE */}
          <section className="overflow-hidden rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl lg:col-span-2">
            <div className="flex items-center justify-between border-b border-gray-800 px-6 py-5">
              <div>
                <h2 className="text-lg font-semibold text-white">Knowledge Database</h2>
                <p className="mt-1 text-sm text-gray-500">{knowledge.length} stored {knowledge.length === 1 ? "entry" : "entries"}</p>
              </div>
              <Database size={22} className="text-gray-500" />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="bg-gray-900/80 text-xs uppercase tracking-wider text-gray-500">
                  <tr>
                    <th className="px-6 py-4 font-medium">ID</th>
                    <th className="px-6 py-4 font-medium">Category</th>
                    <th className="px-6 py-4 font-medium">Content</th>
                    <th className="px-6 py-4 text-right font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {knowledge.map((entry) => (
                    <tr key={entry.id} className="transition hover:bg-gray-800/40">
                      <td className="max-w-44 truncate px-6 py-4 font-mono text-xs text-blue-300">{entry.id}</td>
                      <td className="px-6 py-4">
                        <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2.5 py-1 text-xs font-medium capitalize text-violet-300">
                          {entry.category}
                        </span>
                      </td>
                      <td className="max-w-xs truncate px-6 py-4 text-gray-400" title={entry.content}>{entry.content}</td>
                      <td className="px-6 py-4 text-right">
                        <button
                          type="button"
                          onClick={() => void handleDelete(entry.id)}
                          disabled={deletingId === entry.id}
                          className="inline-flex rounded-lg p-2 text-red-400 transition hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Trash2 size={18} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!isLoading && knowledge.length === 0 && (
              <div className="px-6 py-16 text-center">
                <Database size={34} className="mx-auto text-gray-700" />
                <p className="mt-4 text-gray-400">No knowledge entries found.</p>
              </div>
            )}
            {isLoading && <div className="px-6 py-16 text-center text-gray-500">Loading knowledge entries...</div>}
          </section>

        </section>
      </div>
    </main>
  );
}
