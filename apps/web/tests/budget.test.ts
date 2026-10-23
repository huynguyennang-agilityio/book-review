import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_BUDGET_USD, suggestBudget } from "../app/_lib/budget.ts";

const estimate = { total_usd: 1.41, images: 47, images_usd: 1.41 };

test("gợi ý = tiền model đã tiêu + ước tính media, cộng 0,05 rồi làm tròn lên 0,1", () => {
  // Project 23/10: đã tiêu 0,99 USD gồm 30 ảnh × 0,03; còn 0,09 tiền model.
  assert.equal(suggestBudget(0.9913915, 30, estimate), 1.6);
});

test("không có ước tính thì lớn hơn số đã tiêu", () => {
  assert.equal(suggestBudget(0.99, 30, null), 1.1);
});

test("không vượt trần", () => {
  assert.equal(suggestBudget(19.95, 0, estimate), MAX_BUDGET_USD);
});
