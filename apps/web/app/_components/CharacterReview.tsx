"use client";

import { useEffect, useState } from "react";
import { canApprove, parseCharacters, type CharacterCandidate } from "../_lib/characters";
import type { Pending } from "../_lib/run";

function Candidate({
  path,
  loadImage,
  alt,
}: {
  path: string;
  loadImage: (path: string) => Promise<string>;
  alt: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let alive = true;
    loadImage(path)
      .then((u) => {
        url = u;
        if (alive) setSrc(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path, loadImage]);
  if (failed) return <span className="muted">Không tải được ảnh</span>;
  // eslint-disable-next-line @next/next/no-img-element
  return src ? <img src={src} alt={alt} /> : <span className="muted">Đang tải…</span>;
}

function Character({
  character,
  picked,
  note,
  busy,
  loadImage,
  onPick,
  onNote,
}: {
  character: CharacterCandidate;
  picked: number | undefined;
  note: string | undefined;
  busy: boolean;
  loadImage: (path: string) => Promise<string>;
  onPick: (index: number) => void;
  onNote: (note: string | undefined) => void;
}) {
  const regen = note !== undefined;
  return (
    <section className="character" data-testid={`character-${character.slug}`}>
      <h4>
        {character.name}
        {character.reused && <span className="muted"> · dùng lại bản đã duyệt của series</span>}
      </h4>
      <div className="candidate-grid">
        {character.images.map((path, i) => (
          <button
            key={path}
            type="button"
            className={`candidate${picked === i || character.reused ? " picked" : ""}`}
            aria-pressed={picked === i || character.reused}
            disabled={busy || character.reused || regen}
            onClick={() => onPick(i)}
            data-testid={`pick-${character.slug}-${i}`}
          >
            <Candidate path={path} loadImage={loadImage} alt={`${character.name} ${i + 1}`} />
            <span>Ảnh {i + 1}</span>
          </button>
        ))}
      </div>
      {!character.reused && (
        <div className="regen">
          {regen ? (
            <>
              <label>
                Ghi chú cho lần tạo lại
                <input
                  value={note}
                  maxLength={200}
                  placeholder="vd: tóc ngắn hơn, đội mũ"
                  onChange={(e) => onNote(e.target.value)}
                  data-testid={`note-${character.slug}`}
                />
              </label>
              <button type="button" className="link" onClick={() => onNote(undefined)}>
                Bỏ yêu cầu tạo lại
              </button>
            </>
          ) : (
            <button
              type="button"
              className="link"
              disabled={busy || character.regenLeft === 0}
              onClick={() => onNote("")}
              data-testid={`regen-${character.slug}`}
            >
              {character.regenLeft === 0
                ? "Đã hết lượt tạo lại"
                : `Tạo lại 4 ảnh (còn ${character.regenLeft} lượt)`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function CharacterReview({
  pending,
  busy,
  priceImage,
  loadImage,
  onSubmit,
  onCancel,
}: {
  pending: Pending;
  busy: boolean;
  priceImage: number;
  loadImage: (path: string) => Promise<string>;
  onSubmit: (selections: Record<string, number>, regenerate: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const review = parseCharacters(pending.raw);
  const [picks, setPicks] = useState<Record<string, number>>(review.picks);
  const [regen, setRegen] = useState<Record<string, string>>({});
  const regenCount = Object.keys(regen).length;
  const ok = canApprove(review.characters, picks, regen);

  const setNote = (slug: string, note: string | undefined) =>
    setRegen((r) => {
      const next = { ...r };
      if (note === undefined) delete next[slug];
      else next[slug] = note;
      return next;
    });

  return (
    <section className="card" data-testid="review-characters">
      <h3>Chọn ảnh nhân vật</h3>
      <p className="muted">
        Chọn 1 trong 4 ảnh cho mỗi nhân vật, hoặc yêu cầu tạo lại kèm ghi chú.
      </p>
      {review.characters.length === 0 && (
        <p className="muted">Sách này không có nhân vật chính, bạn có thể tiếp tục.</p>
      )}
      {review.characters.map((c) => (
        <Character
          key={c.slug}
          character={c}
          picked={picks[c.slug]}
          note={regen[c.slug]}
          busy={busy}
          loadImage={loadImage}
          onPick={(i) => setPicks((p) => ({ ...p, [c.slug]: i }))}
          onNote={(n) => setNote(c.slug, n)}
        />
      ))}
      <div className="actions">
        {regenCount > 0 ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => onSubmit(picks, regen)}
            data-testid="regenerate"
          >
            Tạo lại {regenCount} nhân vật (~${(regenCount * 4 * priceImage).toFixed(2)})
          </button>
        ) : (
          <button
            type="button"
            disabled={busy || !ok}
            onClick={() => onSubmit(picks, {})}
            data-testid="approve-characters"
          >
            Duyệt nhân vật và tiếp tục
          </button>
        )}
        <button type="button" className="danger" disabled={busy} onClick={onCancel}>
          Huỷ
        </button>
      </div>
      {regenCount === 0 && !ok && review.characters.length > 0 && (
        <p className="muted">Chọn ảnh cho mọi nhân vật để tiếp tục.</p>
      )}
    </section>
  );
}
