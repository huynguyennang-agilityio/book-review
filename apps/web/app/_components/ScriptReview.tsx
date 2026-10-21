"use client";

import { useMemo, useState } from "react";
import { errorText, type Pending, type Source } from "../_lib/run";
import {
  CITED,
  isUrl,
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
        <span>
          Bám nguồn: <strong>{pct(score)}</strong>
        </span>
        <span className={lowScenes.length ? "bad" : "good"} data-testid="low-faithfulness">
          {lowScenes.length
            ? `LOW_FAITHFULNESS: ${lowScenes.length} cảnh (${lowScenes.map((s) => s.id).join(", ")})`
            : "Không có cảnh nào điểm thấp"}
        </span>
        <span data-testid="cost-estimate">
          Ước tính dựng video: <strong>${estimate.toFixed(2)}</strong>
          {review.costEstimate.images != null && ` (${review.costEstimate.images} ảnh)`}
        </span>
        <span className="muted">Đã tiêu: ${review.spentUsd.toFixed(3)}</span>
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
                    {CITED.has(s.section) && <span className="chip">{pct(d.score)}</span>}
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
                    <Narration scene={s} draft={d} />
                    {d.onScreen && <p className="muted">Chữ trên màn hình: {d.onScreen}</p>}
                    <button type="button" className="link" onClick={() => setEditing(s.id)}>
                      Sửa
                    </button>
                  </>
                )}
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
                {notes[s.id] && <p className="muted">{notes[s.id]}</p>}
              </li>
            );
          })}
        </ol>

        <aside className="citations" aria-label="Nguồn trích dẫn">
          {scene ? (
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
