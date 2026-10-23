"use client";

import { HttpAgent, type Interrupt, type RunAgentParameters } from "@ag-ui/client";
import { useCallback, useRef, useState } from "react";
import type { CostEstimate } from "./budget";
import { emptyDraft, resetDraft, type ImageMode, type UploadDraft } from "./images";
import { keepPending } from "./interrupts";
import { NODES } from "./nodes";
import type { RunSource } from "./reviewText";
import type { RewriteResult, SceneEdit } from "./script";

export { NODES, visibleNodes, type NodeId } from "./nodes";

export interface UploadedImage {
  path: string;
  width: number;
  height: number;
  size: number;
  warnings: { code: string; message_vi: string }[];
}
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
  PROVIDER_QUOTA:
    "Tài khoản tạo ảnh (Fal) hết tiền hoặc đang bị giới hạn. Nạp thêm hoặc đợi vài phút rồi bấm Thử lại.",
  LOW_FAITHFULNESS: "Kịch bản có trích dẫn không khớp nguồn. Bấm Thử lại để viết lại.",
  RENDER_FAILED: "Dựng video thất bại.",
  CANCELLED: "Yêu cầu đã bị huỷ.",
  INVALID_STATE: "Project không ở trạng thái cho phép thao tác này.",
  UNSUPPORTED_IMAGE: "Chỉ nhận ảnh JPEG, PNG hoặc WebP.",
  IMAGE_TOO_LARGE: "Ảnh quá nặng, tối đa 10 MB.",
  INVALID_IMAGE: "Không mở được ảnh, file có thể bị hỏng.",
  UPLOAD_LIMIT: "Project đã có đủ số ảnh tải lên tối đa.",
  REVIEW_TOO_SHORT: "Phần ý chính của bài review quá ngắn, cần ít nhất 100 từ.",
  REVIEW_TOO_LONG: "Bài review đọc dài hơn 5 phút, hãy cắt bớt.",
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
  // Số ảnh đã trả tiền và ước tính chi phí media: để gợi ý ngân sách mới khi BUDGET_EXCEEDED.
  const [imagesBought, setImagesBought] = useState(0);
  const [costEstimate, setCostEstimate] = useState<CostEstimate | null>(null);
  // Mã lỗi của lần chạy vừa thất bại (null khi đang chạy hoặc xong).
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [imageMode, setImageMode] = useState<ImageMode | null>(null);
  // Tab của run hiện tại: "book" (từ tên sách) hoặc "user_review" (bài review có sẵn).
  const [source, setSource] = useState<RunSource>("book");
  // Ô ảnh manual đã tải, sống qua các lần server hỏi lại (xem `UploadDraft`).
  const [uploadDraft] = useState<UploadDraft>(emptyDraft);

  const say = useCallback((role: ChatMessage["role"], text: string) => {
    setMessages((m) => [...m, { role, text }]);
  }, []);

  const execute = useCallback(
    async (agent: HttpAgent, params: RunAgentParameters) => {
      setStatus("running");
      setPending(null);
      setErrorCode(null);
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
                  cost?: { usd?: number; images?: number };
                  cost_estimate?: CostEstimate | null;
                  status?: string;
                  error_code?: string;
                  options?: { image_mode?: string };
                  asset_refs?: Record<string, string>;
                }
              | undefined;
            const usd = snap?.cost?.usd;
            if (typeof usd === "number") {
              costRef.current = usd;
              setCost(usd);
            }
            const images = snap?.cost?.images;
            if (typeof images === "number") setImagesBought(images);
            if (snap?.cost_estimate) setCostEstimate(snap.cost_estimate);
            const mode = snap?.options?.image_mode;
            if (mode === "auto" || mode === "manual") setImageMode(mode);
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
              } else if (p.type === "upload_images") {
                say("assistant", "Tải một ảnh cho mỗi prompt, đủ ảnh mới dựng tiếp được.");
              } else say("assistant", p.message || "Đã tới bước duyệt.");
              return;
            }
            const { status: final, errorCode, video } = finalRef.current;
            if (final === "cancelled") {
              setStatus("cancelled");
              say("assistant", codeText(errorCode ?? "CANCELLED"));
            } else if (final === "failed" || final === "rejected") {
              setStatus("failed");
              setErrorCode(errorCode ?? "INTERNAL_ERROR");
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

  const lastStartRef = useRef<{
    title: string;
    options: Options;
    author: string | null;
    userReview: Record<string, string> | null;
  } | null>(null);

  // `userReview` có thì chạy tab "Từ bài review có sẵn": graph bỏ research, đọc nguyên văn bài.
  const start = useCallback(
    async (
      title: string,
      options: Options,
      author: string | null = null,
      userReview: Record<string, string> | null = null,
    ) => {
      lastStartRef.current = { title, options, author, userReview };
      const runSource: RunSource = userReview ? "user_review" : "book";
      setSource(runSource);
      setMessages([{ role: "user", text: title }]);
      setSources([]);
      setSteps({});
      progressRef.current = { started: new Set(), finished: new Set() };
      setCost(null);
      costRef.current = null;
      setImagesBought(0);
      setCostEstimate(null);
      finalRef.current = {};
      setOutputs([]);
      setImageMode(null);
      resetDraft(uploadDraft);
      cancelledRef.current = false;
      setBudget(options.budget_usd);
      setStatus("running");
      try {
        const token = await getToken();
        const project = await api<Project>("/projects", token, {
          method: "POST",
          body: JSON.stringify({ book_title: title, book_author: author, source: runSource }),
        });
        projectRef.current = project;
        const agent = new HttpAgent({
          url: "/api/backend/agent",
          threadId: project.thread_id,
          // Không gửi `image_mode`: sau khi duyệt kịch bản graph dừng ở `choose_image_mode` để hỏi.
          initialState: {
            book: author ? { title, author } : { title },
            ...(userReview
              ? { options: { ...options, source: runSource }, user_review: userReview }
              : { options }),
          },
        });
        agentRef.current = agent;
        await execute(agent, {});
      } catch (err) {
        setStatus("failed");
        say("error", errorText(err, "Không bắt đầu được."));
      }
    },
    [execute, getToken, say, uploadDraft],
  );

  // Chặn bấm hai lần: hai lần resume cùng interrupt chạy song song trên một thread làm client
  // AG-UI giữ lại interrupt đã trả lời và từ chối các lần resume sau.
  const resumingRef = useRef(false);
  const resume = useCallback(
    async (payload: Record<string, unknown>) => {
      const agent = agentRef.current;
      if (!agent || !pending || resumingRef.current) return;
      resumingRef.current = true;
      // Graph chỉ chờ một interrupt mỗi lúc (cái đang hiện trên màn hình). Interrupt cũ còn trong
      // sổ của client là thừa, bỏ đi để client không chặn lần resume này.
      agent.pendingInterrupts = keepPending(agent.pendingInterrupts, pending.interruptId);
      try {
        await execute(agent, {
          resume: [{ interruptId: pending.interruptId, status: "resolved", payload }],
        });
      } finally {
        resumingRef.current = false;
      }
    },
    [execute, pending],
  );

  // Chạy lại sách vừa lỗi (lỗi tạm thời của nhà cung cấp) mà không phải nhập lại.
  // Có project rồi thì chạy tiếp từ bước vừa lỗi (API tua checkpoint); chưa có thì bắt đầu lại.
  // `budgetUsd`: ngân sách mới khi lỗi là BUDGET_EXCEEDED, API ghi vào state trước khi chạy tiếp.
  const retry = useCallback(async (budgetUsd?: number) => {
    const agent = agentRef.current;
    if (agent && projectRef.current) {
      cancelledRef.current = false;
      finalRef.current = {};
      setStatus("running");
      if (budgetUsd != null) {
        await execute(agent, { forwardedProps: { budget_usd: budgetUsd } });
        if (finalRef.current.status) setBudget(budgetUsd); // API đã nhận ngân sách mới
        return;
      }
      await execute(agent, {});
      return;
    }
    const last = lastStartRef.current;
    if (last) await start(last.title, last.options, last.author, last.userReview);
  }, [execute, start]);

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
      resetDraft(uploadDraft);
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
  }, [cancelling, getToken, say, uploadDraft]);

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

  const chooseImageMode = useCallback(
    async (mode: ImageMode) => {
      setImageMode(mode);
      await resume({ mode });
    },
    [resume],
  );

  // Tải một ảnh của project lên, trả về đường dẫn dùng khi resume `upload_images`.
  const uploadImage = useCallback(
    async (file: File): Promise<UploadedImage> => {
      const project = projectRef.current;
      if (!project) throw new ApiError("NOT_FOUND", ERROR_TEXT.NOT_FOUND);
      const body = new FormData();
      body.append("file", file);
      // Không đặt content-type: trình duyệt tự thêm boundary của multipart.
      const resp = await fetch(`/api/backend/projects/${project.id}/uploads`, {
        method: "POST",
        headers: { authorization: `Bearer ${await getToken()}` },
        body,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const e = data as { code?: string; message_vi?: string };
        const code = e.code ?? `HTTP_${resp.status}`;
        throw new ApiError(code, e.message_vi ?? ERROR_TEXT[code] ?? `Lỗi ${resp.status}`);
      }
      return data as UploadedImage;
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
    imagesBought,
    costEstimate,
    errorCode,
    cancelling,
    start,
    retry,
    resume,
    cancel,
    approveScript,
    rewriteScene,
    approveCharacters,
    chooseImageMode,
    uploadImage,
    imageMode,
    source,
    uploadDraft,
    loadImage,
  };
}
