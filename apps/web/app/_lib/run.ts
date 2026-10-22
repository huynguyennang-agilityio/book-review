"use client";

import { HttpAgent, type Interrupt, type RunAgentParameters } from "@ag-ui/client";
import { useCallback, useRef, useState } from "react";
import type { RewriteResult, SceneEdit } from "./script";

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
  { id: "tts_align", label: "Tạo giọng đọc" },
  { id: "build_timeline", label: "Dựng timeline" },
  { id: "subtitles", label: "Phụ đề" },
  { id: "review_characters", label: "Chọn ảnh nhân vật" },
  { id: "scene_images", label: "Ảnh cảnh" },
  { id: "motion", label: "Chuyển động" },
  { id: "compose_render", label: "Ghép video" },
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

export interface OutputFile {
  key: string;
  name: string;
  label: string;
  size: number;
}

export type RunStatus = "idle" | "running" | "awaiting" | "done" | "failed" | "cancelled";

// Câu hiển thị theo mã lỗi của API (`errors.ErrorCode`); ưu tiên `message_vi` server trả về.
export const ERROR_TEXT: Record<string, string> = {
  BOOK_NOT_FOUND: "Không tìm thấy thông tin về cuốn sách này.",
  GENRE_EXCLUDED: "Thể loại sách này chưa được hỗ trợ.",
  BUDGET_EXCEEDED: "Đã vượt hạn mức chi phí cho phép.",
  PROVIDER_UNAVAILABLE: "Dịch vụ AI tạm thời không phản hồi, vui lòng thử lại sau.",
  LOW_FAITHFULNESS: "Kịch bản chưa bám sát nguồn, cần tạo lại.",
  RENDER_FAILED: "Dựng video thất bại.",
  CANCELLED: "Yêu cầu đã bị huỷ.",
  INVALID_STATE: "Project không ở trạng thái cho phép thao tác này.",
  UNAUTHORIZED: "Bạn cần đăng nhập để tiếp tục.",
  TOKEN_EXPIRED: "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
  FORBIDDEN: "Bạn không có quyền thực hiện thao tác này.",
  NOT_FOUND: "Không tìm thấy tài nguyên.",
  VALIDATION_ERROR: "Dữ liệu gửi lên không hợp lệ.",
  RATE_LIMITED: "Bạn thao tác quá nhanh, vui lòng thử lại sau ít phút.",
  INTERNAL_ERROR: "Đã có lỗi xảy ra, vui lòng thử lại.",
};

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export function errorText(err: unknown, fallback = "Có lỗi khi chạy."): string {
  if (err instanceof ApiError) return `${err.message} (${err.code})`;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function codeText(code: string): string {
  return `${ERROR_TEXT[code] ?? "Có lỗi xảy ra."} (${code})`;
}

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
    const e = data as { code?: string; message_vi?: string };
    const code = e.code ?? `HTTP_${resp.status}`;
    throw new ApiError(code, e.message_vi ?? ERROR_TEXT[code] ?? `Lỗi ${resp.status}`);
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
  const projectRef = useRef<Project | null>(null);
  const finalRef = useRef<{ status?: string; errorCode?: string; video?: string }>({});
  const [budget, setBudget] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const cancelledRef = useRef(false);
  const costRef = useRef<number | null>(null);
  // Node đã bắt đầu/kết thúc, giữ qua các lần resume của cùng một project.
  const progressRef = useRef({ started: new Set<string>(), finished: new Set<string>() });
  const [cost, setCost] = useState<number | null>(null);
  const [outputs, setOutputs] = useState<OutputFile[]>([]);

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
            const snap = event.snapshot as
              | {
                  cost?: { usd?: number };
                  status?: string;
                  error_code?: string;
                  asset_refs?: Record<string, string>;
                }
              | undefined;
            const usd = snap?.cost?.usd;
            if (typeof usd === "number") {
              costRef.current = usd;
              setCost(usd);
            }
            finalRef.current = {
              status: snap?.status ?? finalRef.current.status,
              errorCode: snap?.error_code ?? finalRef.current.errorCode,
              video: snap?.asset_refs?.["video:raw"] ?? finalRef.current.video,
            };
          },
          onRunFinishedEvent: (e) => {
            if (e.outcome === "interrupt") {
              const p = pendingFrom(e.interrupts[0]);
              setPending(p);
              setStatus("awaiting");
              if (p.type === "identify_confirm") say("assistant", p.message);
              else if (p.type === "review_script") {
                say("assistant", "Kịch bản đã sẵn sàng, xem lại và duyệt trước khi dựng video.");
              } else if (p.type === "review_characters") {
                say("assistant", "Ảnh nhân vật đã sẵn sàng, chọn ảnh cho từng nhân vật.");
              } else say("assistant", p.message || "Đã tới bước duyệt.");
              return;
            }
            const { status: final, errorCode, video } = finalRef.current;
            if (final === "cancelled") {
              setStatus("cancelled");
              say("assistant", codeText(errorCode ?? "CANCELLED"));
            } else if (final === "failed" || final === "rejected") {
              setStatus("failed");
              say("error", codeText(errorCode ?? "INTERNAL_ERROR"));
            } else {
              setStatus("done");
              setSteps(Object.fromEntries(NODES.map((n) => [n.id, "done" as StepState])));
              say("assistant", video ? "Xong. Xem và tải video ở mục Kết quả." : "Xong.");
              const project = projectRef.current;
              if (project) {
                getToken()
                  .then((token) => api<OutputFile[]>(`/projects/${project.id}/outputs`, token))
                  .then(setOutputs)
                  .catch((err) => say("error", errorText(err, "Không tải được danh sách file.")));
              }
            }
          },
          onRunErrorEvent: ({ event }) => {
            // Ngắt stream do người dùng bấm Huỷ không phải lỗi.
            if (cancelledRef.current) return;
            setStatus((cur) => (cur === "cancelled" ? cur : "failed"));
            say("error", event.message || "Có lỗi khi chạy.");
          },
        });
      } catch (err) {
        // Người dùng đã huỷ (ngắt kết nối chủ động) thì không báo lỗi.
        setStatus((cur) => (cur === "cancelled" ? cur : "failed"));
        if (!cancelledRef.current) say("error", errorText(err));
      }
    },
    [getToken, say],
  );

  const lastStartRef = useRef<{ title: string; options: Options } | null>(null);

  const start = useCallback(
    async (title: string, options: Options) => {
      lastStartRef.current = { title, options };
      setMessages([{ role: "user", text: title }]);
      setSources([]);
      setSteps({});
      progressRef.current = { started: new Set(), finished: new Set() };
      setCost(null);
      costRef.current = null;
      finalRef.current = {};
      setOutputs([]);
      cancelledRef.current = false;
      setBudget(options.budget_usd);
      setStatus("running");
      try {
        const token = await getToken();
        const project = await api<Project>("/projects", token, {
          method: "POST",
          body: JSON.stringify({ book_title: title }),
        });
        projectRef.current = project;
        const agent = new HttpAgent({
          url: "/api/backend/agent",
          threadId: project.thread_id,
          initialState: { book: { title }, options },
        });
        agentRef.current = agent;
        await execute(agent, {});
      } catch (err) {
        setStatus("failed");
        say("error", errorText(err, "Không bắt đầu được."));
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

  // Chạy lại sách vừa lỗi (lỗi tạm thời của nhà cung cấp) mà không phải nhập lại.
  const retry = useCallback(async () => {
    const last = lastStartRef.current;
    if (last) await start(last.title, last.options);
  }, [start]);

  // Huỷ: API đặt cờ để node và worker dừng, chi phí đã tiêu vẫn giữ trong state.
  const cancel = useCallback(async () => {
    const project = projectRef.current;
    if (!project || cancelling) return;
    setCancelling(true);
    try {
      cancelledRef.current = true;
      const result = await api<{ cost: { usd?: number } }>(
        `/projects/${project.id}/cancel`,
        await getToken(),
        { method: "POST" },
      );
      agentRef.current?.abortRun();
      setPending(null);
      setStatus("cancelled");
      const usd = result.cost?.usd;
      if (typeof usd === "number") setCost(usd);
      say(
        "assistant",
        `Đã huỷ.${typeof usd === "number" ? ` Chi phí đã tiêu: $${usd.toFixed(3)}.` : ""}`,
      );
    } catch (err) {
      cancelledRef.current = false;
      say("error", errorText(err, "Không huỷ được."));
    } finally {
      setCancelling(false);
    }
  }, [cancelling, getToken, say]);

  const approveScript = useCallback(
    (edits: SceneEdit[]) => resume({ approved: true, ...(edits.length ? { edits } : {}) }),
    [resume],
  );

  const rewriteScene = useCallback(
    async (sceneId: number, instruction: string, narration: string) => {
      const project = projectRef.current;
      if (!project) throw new ApiError("NOT_FOUND", ERROR_TEXT.NOT_FOUND);
      return api<RewriteResult>(
        `/projects/${project.id}/scenes/${sceneId}/rewrite`,
        await getToken(),
        { method: "POST", body: JSON.stringify({ instruction, narration_vi: narration }) },
      );
    },
    [getToken],
  );

  const approveCharacters = useCallback(
    (selections: Record<string, number>, regenerate: Record<string, string>) =>
      resume(Object.keys(regenerate).length ? { selections, regenerate } : { selections }),
    [resume],
  );

  // Ảnh nhân vật nằm sau JWT nên không dùng thẳng được trong <img src>: tải về rồi tạo object URL.
  const loadImage = useCallback(
    async (path: string) => {
      const project = projectRef.current;
      if (!project) throw new ApiError("NOT_FOUND", ERROR_TEXT.NOT_FOUND);
      const resp = await fetch(
        `/api/backend/projects/${project.id}/media?path=${encodeURIComponent(path)}`,
        { headers: { authorization: `Bearer ${await getToken()}` } },
      );
      if (!resp.ok) throw new ApiError(`HTTP_${resp.status}`, "Không tải được ảnh.");
      return URL.createObjectURL(await resp.blob());
    },
    [getToken],
  );

  // File đầu ra nằm sau JWT: tải về thành Blob để phát/tải bằng object URL.
  const loadOutput = useCallback(
    async (key: string) => {
      const project = projectRef.current;
      if (!project) throw new ApiError("NOT_FOUND", ERROR_TEXT.NOT_FOUND);
      const resp = await fetch(
        `/api/backend/projects/${project.id}/outputs/${encodeURIComponent(key)}`,
        { headers: { authorization: `Bearer ${await getToken()}` } },
      );
      if (!resp.ok) throw new ApiError(`HTTP_${resp.status}`, "Không tải được file.");
      return resp.blob();
    },
    [getToken],
  );

  return {
    status,
    messages,
    outputs,
    loadOutput,
    steps,
    sources,
    pending,
    cost,
    budget,
    cancelling,
    start,
    retry,
    resume,
    cancel,
    approveScript,
    rewriteScene,
    approveCharacters,
    loadImage,
  };
}
