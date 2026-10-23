import { useState } from "react";
import { MAX_BUDGET_USD } from "../_lib/budget";

// Project dừng vì vượt ngân sách: nhập ngân sách mới rồi chạy tiếp từ bước vừa dừng.
export function BudgetRetry({
  spent,
  budget,
  suggested,
  onRetry,
}: {
  spent: number;
  budget: number | null;
  suggested: number;
  onRetry: (budgetUsd: number) => void;
}) {
  const [value, setValue] = useState(suggested);
  const valid = Number.isFinite(value) && value > spent && value <= MAX_BUDGET_USD;
  return (
    <form
      className="budget-retry"
      data-testid="budget-retry"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onRetry(value);
      }}
    >
      <p className="muted">
        Đã tiêu ${spent.toFixed(2)}
        {budget != null ? ` / ngân sách $${budget.toFixed(2)}` : ""}. Ảnh đã tạo không bị tính tiền
        lại.
      </p>
      <label>
        Ngân sách mới (USD)
        <input
          id="budget-retry-usd"
          type="number"
          min={Number((spent + 0.01).toFixed(2))}
          max={MAX_BUDGET_USD}
          step={0.1}
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
        />
      </label>
      {!valid && (
        <p className="bad">
          Nhập số lớn hơn ${spent.toFixed(2)} và không quá ${MAX_BUDGET_USD}.
        </p>
      )}
      <button type="submit" disabled={!valid}>
        Tăng ngân sách và chạy tiếp
      </button>
    </form>
  );
}
