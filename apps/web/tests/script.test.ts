import assert from "node:assert/strict";
import { test } from "node:test";
import {
  countSyllables,
  estimateSeconds,
  formatDuration,
  isShortScript,
  parseReview,
} from "../app/_lib/script.ts";

test("đếm âm tiết khớp storyboard/duration.py", () => {
  assert.equal(countSyllables("Nhà giả kim, xuất bản 1988."), 6);
  assert.equal(countSyllables(""), 0);
});

test("ước lượng thời lượng: 38 âm tiết một cảnh ≈ 10,45 giây", () => {
  const one = "một ".repeat(38);
  assert.ok(Math.abs(estimateSeconds([one]) - 10.45) < 1e-9);
  assert.ok(Math.abs(estimateSeconds([one, one]) - 20.9) < 1e-9);
});

test("formatDuration", () => {
  assert.equal(formatDuration(180), "3:00");
  assert.equal(formatDuration(129.6), "2:10");
  assert.equal(formatDuration(5), "0:05");
});

test("kịch bản ngắn khi dưới 90% mục tiêu", () => {
  assert.equal(isShortScript(130, 180), true);
  assert.equal(isShortScript(170, 180), false);
  assert.equal(isShortScript(30, null), false);
});

test("parseReview đọc target_seconds, storyboard cũ thì null", () => {
  assert.equal(parseReview({ storyboard: { scenes: [], target_seconds: 180 } }).targetSeconds, 180);
  assert.equal(parseReview({ storyboard: { scenes: [] } }).targetSeconds, null);
});
