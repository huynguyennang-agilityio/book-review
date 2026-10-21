import { NODES, type StepState } from "../_lib/run";

export function Progress({ steps }: { steps: Record<string, StepState> }) {
  return (
    <ol className="progress" aria-label="Tiến độ">
      {NODES.map((n) => {
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
