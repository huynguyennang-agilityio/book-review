"use client";

import { HttpAgent, type Interrupt, type RunAgentParameters } from "@ag-ui/client";
import { useCallback, useRef, useState } from "react";

// Node của graph theo thứ tự chạy (apps/api/.../graph/build.py). Tiến độ lấy từ event tuỳ biến
// `node` do graph tự phát, không dùng `STEP_*` của adapter (lẫn tên bước nội bộ của research agent).
export const NODES = [
  { id: "precheck", label: "Kiểm tra tên sách" },
  { id: "research_agent", label: "Tìm hiểu sách" },
  { id: "identify_confirm", label: "Xác nhận đúng sách" },
  { id: "storyboard", label: "Viết kịch bản" },
  { id: "faithfulness_eval", label: "Kiểm tra bám nguồn" },
  { id: "estimate_cost", label: "Ước tính chi phí" },
  { id: "review_script", label: "Duyệt kịch bản" },
] as const;

export type NodeId = (typeof NODES)[number]["id"];
export type StepState = "pending" | "active" | "done";
export type SourceStage = "found" | "read" | "ingested";

export interface Source {
  url: string;
  title: string;
  stage: SourceStage;
}

export interface Candidate {
  title: string;
  author?: string | null;
  year?: number | null;
  [key: string]: unknown;
}

export interface Pending {
  interruptId: string;
  type: string;
  message: string;
  raw: Record<string, unknown>;
}

export interface Options {
  minutes: number;
  no_spoiler: boolean;
  voice: string;
  budget_usd: number;
}

export interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
}

export type RunStatus = "idle" | "running" | "awaiting" | "done" | "failed";

const STAGE_RANK: Record<SourceStage, number> = { found: 0, read: 1, ingested: 2 };

export function parseCustomValue(value: unknown): Record<string, unknown> | null {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

export function pendingFrom(interrupt: Interrupt): Pending {
  const meta = interrupt.metadata as { langgraph?: { raw?: Record<string, unknown> } } | undefined;
  const raw = meta?.langgraph?.raw ?? {};
  return {
    interruptId: interrupt.id,
    type: typeof raw.type === "string" ? raw.type : "",
    message: interrupt.message ?? (typeof raw.message === "string" ? raw.message : ""),
    raw,
  };
}

export async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api/backend${path}`, {
    ...init,
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error((data as { message_vi?: string }).message_vi ?? `Lỗi ${resp.status}`);
  }
  return data as T;
}

interface Project {
  id: string;
  thread_id: string;
}

export function useReviewRun(getToken: () => Promise<string>) {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<Record<string, StepState>>({});
  const [sources, setSources] = useState<Source[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const agentRef = useRef<HttpAgent | null>(null);
  const costRef = useRef<number | null>(null);
  // Node đã bắt đầu/kết thúc, giữ qua các lần resume của cùng một project.
  const progressRef = useRef({ started: new Set<string>(), finished: new Set<string>() });
  const [cost, setCost] = useState<number | null>(null);

  const say = useCallback((role: ChatMessage["role"], text: string) => {
    setMessages((m) => [...m, { role, text }]);
  }, []);

  const execute = useCallback(
    async (agent: HttpAgent, params: RunAgentParameters) => {
      setStatus("running");
      setPending(null);
      // Token Supabase hết hạn sau ~1 giờ: lấy lại mỗi lần chạy.
      agent.headers = { authorization: `Bearer ${await getToken()}` };
      const { started, finished } = progressRef.current;
      const recompute = () => {
        const next: Record<string, StepState> = {};
        for (const { id } of NODES) {
          next[id] = finished.has(id) ? "done" : started.has(id) ? "active" : "pending";
        }
        setSteps(next);
      };
      recompute();
      try {
        await agent.runAgent(params, {
          onCustomEvent: ({ event }) => {
            const v = parseCustomValue(event.value);
            if (event.name === "node") {
              const id = String(v?.node);
              if (!NODES.some((n) => n.id === id)) return;
              if (v?.phase === "start") {
                started.add(id);
                finished.delete(id);
              } else finished.add(id);
              recompute();
              return;
            }
            if (event.name !== "source") return;
            const url = typeof v?.url === "string" ? v.url : null;
            const stage = { source_found: "found", source_read: "read", source_ingested: "ingested" }[
              String(v?.type)
            ] as SourceStage | undefined;
            if (!url || !stage) return;
            setSources((list) => {
              const i = list.findIndex((s) => s.url === url);
              const title = typeof v?.title === "string" ? v.title : "";
              if (i < 0) return [...list, { url, title, stage }];
              const cur = list[i];
              const merged = {
                url,
                title: title || cur.title,
                stage: STAGE_RANK[stage] > STAGE_RANK[cur.stage] ? stage : cur.stage,
              };
              return list.map((s, j) => (j === i ? merged : s));
            });
          },
          onStateSnapshotEvent: ({ event }) => {
            const usd = (event.snapshot as { cost?: { usd?: number } } | undefined)?.cost?.usd;
            if (typeof usd === "number") {
              costRef.current = usd;
              setCost(usd);
            }
          },
          onRunFinishedEvent: (e) => {
            if (e.outcome === "interrupt") {
              const p = pendingFrom(e.interrupts[0]);
              setPending(p);
              setStatus("awaiting");
              if (p.type === "identify_confirm") say("assistant", p.message);
              else {
                const usd = costRef.current;
                say(
                  "assistant",
                  `${p.message || "Đã tới bước duyệt."} Màn duyệt kịch bản làm ở ngày 15.` +
                    (usd != null ? ` Chi phí research: $${usd.toFixed(3)}.` : ""),
                );
              }
            } else {
              setStatus("done");
              setSteps(Object.fromEntries(NODES.map((n) => [n.id, "done" as StepState])));
              say("assistant", "Xong.");
            }
          },
          onRunErrorEvent: ({ event }) => {
            setStatus("failed");
            say("error", event.message || "Có lỗi khi chạy.");
          },
        });
      } catch (err) {
        setStatus("failed");
        say("error", err instanceof Error ? err.message : "Có lỗi khi chạy.");
      }
    },
    [getToken, say],
  );

  const start = useCallback(
    async (title: string, options: Options) => {
      setMessages([{ role: "user", text: title }]);
      setSources([]);
      setSteps({});
      progressRef.current = { started: new Set(), finished: new Set() };
      setCost(null);
      costRef.current = null;
      setStatus("running");
      try {
        const token = await getToken();
        const project = await api<Project>("/projects", token, {
          method: "POST",
          body: JSON.stringify({ book_title: title }),
        });
        const agent = new HttpAgent({
          url: "/api/backend/agent",
          threadId: project.thread_id,
          initialState: { book: { title }, options },
        });
        agentRef.current = agent;
        await execute(agent, {});
      } catch (err) {
        setStatus("failed");
        say("error", err instanceof Error ? err.message : "Không bắt đầu được.");
      }
    },
    [execute, getToken, say],
  );

  const resume = useCallback(
    async (payload: Record<string, unknown>) => {
      const agent = agentRef.current;
      if (!agent || !pending) return;
      await execute(agent, {
        resume: [{ interruptId: pending.interruptId, status: "resolved", payload }],
      });
    },
    [execute, pending],
  );

  return { status, messages, steps, sources, pending, cost, start, resume };
}
