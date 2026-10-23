"use client";

import { useMemo, useState } from "react";
import { errorText, type Pending, type Source } from "../_lib/run";
import {
  CITED,
  estimateSeconds,
  findQuote,
  formatDuration,
  isShortScript,
  isUrl,
  markChanges,
  parseReview,
  type RewriteResult,
  SECTION_LABEL,
  type Scene,
  type SceneEdit,
  type SourceInfo,
  sourceLabel,
  splitSentences,
  unsupportedSentences,
  type UnsupportedClaim,
  type UserReviewText,
} from "../_lib/script";

interface Draft {
  narration: string;
  onScreen: string;
  score: number | null;
  unsupported: UnsupportedClaim[];
  // Lời đọc mà `unsupported` và `score` được chấm trên đó.
  scoredNarration: string;
  edited: boolean;
}

function initialDraft(scene: Scene): Draft {
  return {
    narration: scene.narration_vi,
    onScreen: scene.on_screen_text_vi ?? "",
    score: scene.faithfulness ?? null,
    unsupported: scene.unsupported,
    scoredNarration: scene.narration_vi,
    edited: false,
  };
}

function pct(score: number | null | undefined) {
  return score == null ? "—" : `${Math.round(score * 100)}%`;
}

function SourceLink({
  sourceId,
  info,
  titles,
}: {
  sourceId: string;
  info?: SourceInfo;
  titles: Map<string, string>;
}) {
  const url = info?.url || (isUrl(sourceId) ? sourceId : null);
  const label = info?.title || (url && titles.get(url)) || (url ? sourceLabel(url) : sourceId);
  if (!url) return <span className="muted">{label}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer noopener">
      {label} <span className="muted">{sourceLabel(url)}</span>
    </a>
  );
}

// Tab review có sẵn: lời đọc nguyên văn, chỉ gạch chân chỗ số/ký hiệu đã đọc thành chữ.
function VerbatimNarration({ scene, draft }: { scene: Scene; draft: Draft }) {
  // Sửa tay rồi thì vị trí chỗ đổi không còn đúng.
  const changes = draft.narration === scene.narration_vi ? scene.tts_changes : [];
  return (
    <p className="narration">
      {markChanges(draft.narration, changes).map((seg, i) =>
        seg.from ? (
          <span
            key={i}
            className="tts-change"
            data-testid="tts-change"
            title={`Bài viết "${seg.from}", đọc thành chữ`}
          >
            {seg.text}
          </span>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </p>
  );
}

const REVIEW_BLOCKS: { key: keyof UserReviewText; label: string }[] = [
  { key: "hook", label: "Hook" },
  { key: "main", label: "Ý chính" },
  { key: "comment", label: "Nhận xét" },
];

// Nguồn của tab review có sẵn là chính bài của người dùng: 3 khối, tô câu của cảnh đang chọn.
function ReviewBlocks({ review, quote }: { review: UserReviewText; quote: string | null }) {
  // Chỉ tô ở khối đầu tiên chứa câu trích.
  const hits = REVIEW_BLOCKS.map(({ key }) => {
    const text = review[key];
    return text && quote ? findQuote(text, quote) : null;
  });
  const first = hits.findIndex(Boolean);
  return (
    <>
      <h4>Bài review của bạn</h4>
      {REVIEW_BLOCKS.map(({ key, label }, i) => {
        const text = review[key];
        if (!text) return null;
        const hit = i === first ? hits[i] : null;
        return (
          <div key={key}>
            <p className="muted">{label}</p>
            <p className="verbatim-block" data-testid={`review-block-${key}`}>
              {hit ? (
                <>
                  {hit[0]}
                  <mark className="cited">{hit[1]}</mark>
                  {hit[2]}
                </>
              ) : (
                text
              )}
            </p>
          </div>
        );
      })}
    </>
  );
}

function Narration({ scene, draft }: { scene: Scene; draft: Draft }) {
  const sentences = splitSentences(draft.narration);
  // Chỉ tô khi lời đọc vẫn là bản đã được chấm; sửa tay rồi thì điểm cũ không còn đúng.
  const scored = draft.narration === draft.scoredNarration;
  const marked = useMemo(
    () => (scored ? unsupportedSentences(draft.narration, draft.unsupported) : new Set<number>()),
    [scored, draft.narration, draft.unsupported],
  );
  const needsSource = CITED.has(scene.section) && scene.citations.length === 0;
  return (
    <p className="narration">
      {sentences.map((s, i) => (
        <span
          key={i}
          className={needsSource || marked.has(i) ? "no-source" : undefined}
          data-testid={needsSource || marked.has(i) ? "no-source" : undefined}
          title={needsSource ? "Cảnh này chưa có nguồn trích dẫn" : marked.has(i) ? "Chưa thấy căn cứ trong nguồn" : undefined}
        >
          {s}{" "}
        </span>
      ))}
    </p>
  );
}

export function ScriptReview({
  pending,
  sources,
  budget,
  busy,
  onApprove,
  onCancel,
  onRewrite,
}: {
  pending: Pending;
  sources: Source[];
  budget: number | null;
  busy: boolean;
  onApprove: (edits: SceneEdit[]) => void;
  onCancel: () => void;
  onRewrite: (sceneId: number, instruction: string, narration: string) => Promise<RewriteResult>;
}) {
  const review = useMemo(() => parseReview(pending.raw), [pending.raw]);
  // Tab review có sẵn: lời đọc nguyên văn, không chấm bám nguồn, không viết lại bằng AI.
  const verbatim = review.source === "user_review";
  const [drafts, setDrafts] = useState<Record<number, Draft>>(() =>
    Object.fromEntries(review.scenes.map((s) => [s.id, initialDraft(s)])),
  );
  const [selected, setSelected] = useState<number | null>(review.scenes[0]?.id ?? null);
  const [editing, setEditing] = useState<number | null>(null);
  const [asks, setAsks] = useState<Record<number, string>>({});
  const [working, setWorking] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const titles = useMemo(() => new Map(sources.map((s) => [s.url, s.title])), [sources]);

  const patch = (id: number, next: Partial<Draft>) =>
    setDrafts((d) => ({ ...d, [id]: { ...d[id], ...next } }));
  const note = (id: number, text: string) => setNotes((n) => ({ ...n, [id]: text }));

  const scene = review.scenes.find((s) => s.id === selected) ?? null;
  const edits: SceneEdit[] = review.scenes.flatMap((s) => {
    const d = drafts[s.id];
    if (!d) return [];
    const onScreen = d.onScreen.trim() || null;
    const changed =
      d.narration.trim() !== s.narration_vi || onScreen !== (s.on_screen_text_vi ?? null);
    return changed
      ? [{ scene_id: s.id, narration_vi: d.narration.trim(), on_screen_text_vi: onScreen }]
      : [];
  });
  const emptyNarration = review.scenes.some((s) => !drafts[s.id]?.narration.trim());

  const lowScenes = review.scenes.filter(
    (s) => s.flags.includes("LOW_FAITHFULNESS") && !drafts[s.id]?.edited,
  );
  const score = review.evalScores.faithfulness;
  const estimate = review.costEstimate.total_usd ?? 0;
  const total = estimate + review.spentUsd;
  const overBudget = budget != null && total > budget;
  // Tính lại theo lời đọc đang sửa để biết video dài bao nhiêu trước khi duyệt.
  const seconds = estimateSeconds(review.scenes.map((s) => drafts[s.id]?.narration ?? ""));
  const short = isShortScript(seconds, review.targetSeconds);

  async function rewrite(s: Scene) {
    const instruction = (asks[s.id] ?? "").trim();
    if (!instruction) return;
    setWorking(s.id);
    note(s.id, "");
    try {
      const r = await onRewrite(s.id, instruction, drafts[s.id].narration);
      patch(s.id, {
        narration: r.narration_vi,
        onScreen: r.on_screen_text_vi ?? "",
        score: r.faithfulness,
        unsupported: r.unsupported,
        scoredNarration: r.narration_vi,
        edited: true,
      });
      setAsks((a) => ({ ...a, [s.id]: "" }));
      note(s.id, "Đã viết lại. Bấm Duyệt để lưu thay đổi.");
    } catch (err) {
      note(s.id, errorText(err, "Không viết lại được."));
    } finally {
      setWorking(null);
    }
  }

  return (
    <section className="card review" data-testid="script-review">
      <h3>{pending.message || "Duyệt kịch bản trước khi dựng video."}</h3>
      <div className="stats">
        {verbatim ? (
          <span data-testid="verbatim">
            Lời đọc: <strong>Nguyên văn</strong>
          </span>
        ) : (
          <>
            <span>
              Bám nguồn: <strong>{pct(score)}</strong>
            </span>
            <span className={lowScenes.length ? "bad" : "good"} data-testid="low-faithfulness">
              {lowScenes.length
                ? `LOW_FAITHFULNESS: ${lowScenes.length} cảnh (${lowScenes.map((s) => s.id).join(", ")})`
                : "Không có cảnh nào điểm thấp"}
            </span>
          </>
        )}
        <span data-testid="cost-estimate">
          Ước tính dựng video: <strong>${estimate.toFixed(2)}</strong>
          {review.costEstimate.images != null && ` (${review.costEstimate.images} ảnh)`}
        </span>
        <span className="muted">Đã tiêu: ${review.spentUsd.toFixed(3)}</span>
        <span className={short ? "bad" : undefined} data-testid="duration-estimate">
          Thời lượng ≈ <strong>{formatDuration(seconds)}</strong>
          {review.targetSeconds != null && ` (mục tiêu ${formatDuration(review.targetSeconds)})`}
          {short && ", kịch bản ngắn hơn mục tiêu"}
        </span>
        {overBudget && (
          <span className="bad">Tổng ${total.toFixed(2)} vượt ngân sách ${budget?.toFixed(2)}</span>
        )}
      </div>

      <div className="review-grid">
        <ol className="scenes">
          {review.scenes.map((s) => {
            const d = drafts[s.id];
            const isOpen = editing === s.id;
            return (
              <li
                key={s.id}
                className={s.id === selected ? "scene selected" : "scene"}
                data-testid={`scene-${s.id}`}
              >
                <button
                  type="button"
                  className="scene-head"
                  onClick={() => setSelected(s.id)}
                  aria-pressed={s.id === selected}
                >
                  <span>
                    Cảnh {s.id} · {SECTION_LABEL[s.section]}
                  </span>
                  <span className="chips">
                    {s.flags.includes("LOW_FAITHFULNESS") && !d.edited && (
                      <span className="chip bad">LOW_FAITHFULNESS</span>
                    )}
                    {d.edited && <span className="chip">Đã sửa</span>}
                    {!verbatim && CITED.has(s.section) && (
                      <span className="chip">{pct(d.score)}</span>
                    )}
                  </span>
                </button>
                {isOpen ? (
                  <div className="edit">
                    <textarea
                      aria-label={`Lời đọc cảnh ${s.id}`}
                      value={d.narration}
                      rows={4}
                      onChange={(e) => patch(s.id, { narration: e.target.value, edited: true })}
                    />
                    <input
                      aria-label={`Chữ trên màn hình cảnh ${s.id}`}
                      placeholder="Chữ trên màn hình (có thể để trống)"
                      value={d.onScreen}
                      onChange={(e) => patch(s.id, { onScreen: e.target.value, edited: true })}
                    />
                    <button type="button" className="link" onClick={() => setEditing(null)}>
                      Xong
                    </button>
                  </div>
                ) : (
                  <>
                    {verbatim ? (
                      <VerbatimNarration scene={s} draft={d} />
                    ) : (
                      <Narration scene={s} draft={d} />
                    )}
                    {d.onScreen && <p className="muted">Chữ trên màn hình: {d.onScreen}</p>}
                    <button type="button" className="link" onClick={() => setEditing(s.id)}>
                      Sửa
                    </button>
                  </>
                )}
                {!verbatim && (
                  <div className="ask">
                    <input
                      aria-label={`Yêu cầu viết lại cảnh ${s.id}`}
                      placeholder="Viết lại bằng lời, ví dụ: ngắn hơn, bớt khô khan"
                      value={asks[s.id] ?? ""}
                      onChange={(e) => setAsks((a) => ({ ...a, [s.id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void rewrite(s);
                        }
                      }}
                    />
                    <button
                      type="button"
                      disabled={working !== null || busy || !(asks[s.id] ?? "").trim()}
                      onClick={() => void rewrite(s)}
                    >
                      {working === s.id ? "Đang viết lại…" : "Viết lại"}
                    </button>
                  </div>
                )}
                {notes[s.id] && <p className="muted">{notes[s.id]}</p>}
              </li>
            );
          })}
        </ol>

        <aside className="citations" aria-label="Nguồn trích dẫn">
          {scene && verbatim && review.userReview ? (
            <ReviewBlocks review={review.userReview} quote={scene.citations[0]?.quote ?? null} />
          ) : scene ? (
            <>
              <h4>Nguồn của cảnh {scene.id}</h4>
              {scene.citations.length === 0 ? (
                <p className={CITED.has(scene.section) ? "bad" : "muted"}>
                  {CITED.has(scene.section)
                    ? "Cảnh này chưa có nguồn trích dẫn."
                    : "Lời dẫn, không đưa dữ kiện nên không cần nguồn."}
                </p>
              ) : (
                <ul>
                  {scene.citations.map((c, i) => (
                    <li key={`${c.chunk_id}-${i}`}>
                      <blockquote>{c.quote}</blockquote>
                      <SourceLink sourceId={c.source_id} info={review.sourceInfo[c.source_id]} titles={titles} />
                    </li>
                  ))}
                </ul>
              )}
              {drafts[scene.id]?.unsupported.length > 0 &&
                drafts[scene.id].narration === drafts[scene.id].scoredNarration && (
                  <>
                    <h4>Ý chưa có căn cứ</h4>
                    <ul>
                      {drafts[scene.id].unsupported.map((u, i) => (
                        <li key={i} className="no-source-note">
                          {u.claim}
                          {u.reason && <span className="muted"> — {u.reason}</span>}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
            </>
          ) : (
            <p className="muted">Chọn một cảnh để xem nguồn.</p>
          )}
        </aside>
      </div>

      <div className="row actions">
        <button
          type="button"
          disabled={busy || emptyNarration}
          onClick={() => onApprove(edits)}
          data-testid="approve"
        >
          Duyệt{edits.length ? ` (${edits.length} cảnh đã sửa)` : ""}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          Huỷ project
        </button>
        {emptyNarration && <span className="bad">Lời đọc không được để trống.</span>}
      </div>
    </section>
  );
}
