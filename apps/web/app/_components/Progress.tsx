import type { ImageMode } from "../_lib/images";
import { visibleNodes, type StepState } from "../_lib/run";

export function Progress({
  steps,
  imageMode = null,
}: {
  steps: Record<string, StepState>;
  imageMode?: ImageMode | null;
}) {
  return (
    <ol className="progress" aria-label="Tiến độ">
      {visibleNodes(imageMode).map((n) => {
        const state = steps[n.id] ?? "pending";
        return (
          <li key={n.id} data-state={state} data-node={n.id}>
            <span className="dot" />
            {n.label}
          </li>
        );
      })}
    </ol>
  );
}
