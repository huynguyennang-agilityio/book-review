import type { Candidate, Pending } from "../_lib/run";

export function IdentifyConfirm({
  pending,
  onPick,
  onCancel,
}: {
  pending: Pending;
  onPick: (index: number) => void;
  onCancel: () => void;
}) {
  const candidates = (pending.raw.candidates as Candidate[] | undefined) ?? [];
  return (
    <section className="card" data-testid="identify-confirm">
      <h3>{pending.message || "Chọn đúng cuốn sách"}</h3>
      <ul className="candidates">
        {candidates.map((c, i) => (
          <li key={`${c.title}-${i}`}>
            <button type="button" onClick={() => onPick(i)}>
              <strong>{c.title}</strong>
              <span className="muted">
                {[c.author, c.year].filter(Boolean).join(" · ") || "Chưa rõ tác giả"}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="link" onClick={onCancel}>
        Huỷ
      </button>
    </section>
  );
}
