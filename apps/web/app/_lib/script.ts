// Dữ liệu và hàm thuần cho màn duyệt kịch bản (interrupt `review_script`).

export interface Citation {
  source_id: string;
  chunk_id: string;
  quote: string;
}

export interface UnsupportedClaim {
  claim: string;
  reason: string;
}

export interface Scene {
  id: number;
  section: "hook" | "context" | "body" | "review_cta";
  narration_vi: string;
  on_screen_text_vi?: string | null;
  citations: Citation[];
  faithfulness?: number | null;
  flags: string[];
  unsupported: UnsupportedClaim[];
}

export interface CostEstimate {
  images?: number;
  images_usd?: number;
  tts_chars?: number;
  total_usd?: number;
}

export interface SourceInfo {
  url?: string | null;
  title?: string | null;
}

export interface ReviewPayload {
  scenes: Scene[];
  // `source_id` của citation -> url và tiêu đề của nguồn.
  sourceInfo: Record<string, SourceInfo>;
  evalScores: Record<string, number>;
  costEstimate: CostEstimate;
  spentUsd: number;
  // Thời lượng mục tiêu (số phút đã chọn), null với storyboard cũ.
  targetSeconds: number | null;
}

export interface SceneEdit {
  scene_id: number;
  narration_vi: string;
  on_screen_text_vi: string | null;
}

export interface RewriteResult {
  scene_id: number;
  narration_vi: string;
  on_screen_text_vi: string | null;
  faithfulness: number | null;
  unsupported: UnsupportedClaim[];
  cost_usd: number;
}

export const SECTION_LABEL: Record<Scene["section"], string> = {
  hook: "Mở đầu",
  context: "Bối cảnh",
  body: "Nội dung",
  review_cta: "Kêu gọi",
};

// Phần cần trích dẫn: thiếu nguồn ở đây là lỗi, còn mở đầu/kêu gọi là lời dẫn không đưa dữ kiện.
export const CITED = new Set<Scene["section"]>(["context", "body"]);

export function parseReview(raw: Record<string, unknown>): ReviewPayload {
  const storyboard = (raw.storyboard ?? {}) as {
    scenes?: Partial<Scene>[];
    target_seconds?: number | null;
  };
  const scenes = (storyboard.scenes ?? []).map(
    (s): Scene => ({
      id: Number(s.id),
      section: (s.section ?? "body") as Scene["section"],
      narration_vi: s.narration_vi ?? "",
      on_screen_text_vi: s.on_screen_text_vi ?? null,
      citations: s.citations ?? [],
      faithfulness: s.faithfulness ?? null,
      flags: s.flags ?? [],
      unsupported: s.unsupported ?? [],
    }),
  );
  const cost = (raw.cost ?? {}) as { usd?: number };
  const sourceInfo: Record<string, SourceInfo> = {};
  for (const s of (raw.sources ?? []) as (SourceInfo & { source_id: string })[]) {
    sourceInfo[s.source_id] = { url: s.url, title: s.title };
  }
  return {
    scenes,
    sourceInfo,
    evalScores: (raw.eval_scores ?? {}) as Record<string, number>,
    costEstimate: (raw.cost_estimate ?? {}) as CostEstimate,
    spentUsd: typeof cost.usd === "number" ? cost.usd : 0,
    targetSeconds: typeof storyboard.target_seconds === "number" ? storyboard.target_seconds : null,
  };
}

// Ước lượng thời lượng đọc, khớp `storyboard/duration.py`: ~3,8 âm tiết/giây (edge-tts, spike
// ngày 1) cộng ~0,45 s mỗi cảnh cho lặng đầu, hơi thở cuối và khoảng nghỉ giữa cảnh.
export const SYLLABLES_PER_S = 3.8;
export const SCENE_OVERHEAD_S = 0.45;
// Ngắn hơn tỉ lệ này của mục tiêu thì cảnh báo (cờ `SHORT_SCRIPT` của API).
export const SHORT_SCRIPT_RATIO = 0.9;

export function countSyllables(text: string): number {
  return text.match(/[\p{L}\p{N}_]+/gu)?.length ?? 0;
}

export function estimateSeconds(narrations: string[]): number {
  return narrations.reduce((t, n) => t + countSyllables(n) / SYLLABLES_PER_S + SCENE_OVERHEAD_S, 0);
}

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function isShortScript(estimated: number, target: number | null): boolean {
  return target != null && estimated < target * SHORT_SCRIPT_RATIO;
}

export function splitSentences(text: string): string[] {
  const parts = text.match(/[^.!?…\n]+(?:[.!?…]+["”')\]]*|$)\s*/gu) ?? [];
  return parts.map((p) => p.trim()).filter(Boolean);
}

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .normalize("NFC")
      .split(/[^\p{L}\p{N}]+/u)
      .filter((t) => t.length > 1),
  );
}

// Với mỗi khẳng định chưa có căn cứ, câu trùng nhiều từ nhất trong lời đọc bị tô màu.
export function unsupportedSentences(narration: string, claims: UnsupportedClaim[]): Set<number> {
  const sentences = splitSentences(narration).map(tokens);
  const marked = new Set<number>();
  for (const { claim } of claims) {
    const want = tokens(claim);
    if (want.size === 0) continue;
    let best = -1;
    let bestScore = 0;
    sentences.forEach((have, i) => {
      let shared = 0;
      for (const t of want) if (have.has(t)) shared += 1;
      const score = shared / want.size;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    });
    if (best >= 0 && bestScore >= 0.4) marked.add(best);
  }
  return marked;
}

export function sourceLabel(sourceId: string): string {
  try {
    return new URL(sourceId).hostname.replace(/^www\./, "");
  } catch {
    return sourceId;
  }
}

export function isUrl(sourceId: string): boolean {
  return /^https?:\/\//i.test(sourceId);
}
