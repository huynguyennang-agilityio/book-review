// Ngân sách gợi ý khi chạy lại project dừng vì BUDGET_EXCEEDED.

// Khớp `max_budget_usd` của API.
export const MAX_BUDGET_USD = 20;

export type CostEstimate = { total_usd?: number; images?: number; images_usd?: number };

/**
 * Tiền gọi model đã tiêu (phần không phải ảnh) cộng ước tính media của cả video, thêm 0,05 USD
 * dự phòng rồi làm tròn lên 0,1 USD. Ảnh đã tạo có cache nên không bị tính hai lần.
 */
export function suggestBudget(
  spent: number,
  imagesBought: number,
  estimate: CostEstimate | null,
): number {
  const perImage =
    estimate?.images && estimate.images_usd ? estimate.images_usd / estimate.images : 0;
  const nonMedia = Math.max(spent - imagesBought * perImage, 0);
  const need = Math.max(nonMedia + (estimate?.total_usd ?? 0), spent);
  const rounded = Math.ceil(Number(((need + 0.05) * 10).toFixed(6))) / 10;
  return Math.min(Number(rounded.toFixed(2)), MAX_BUDGET_USD);
}
