import assert from "node:assert/strict";
import { test } from "node:test";
import { visibleNodes } from "../app/_lib/nodes.ts";
import {
  checkReview,
  EMPTY_FIELDS,
  MAX_FILE_BYTES,
  readReviewFile,
  ReviewFileError,
  reviewSeconds,
  splitReviewText,
  toUserReview,
} from "../app/_lib/reviewText.ts";
import { findQuote, markChanges, parseReview } from "../app/_lib/script.ts";

function file(name: string, text: string | Uint8Array, size?: number) {
  const bytes = typeof text === "string" ? new TextEncoder().encode(text) : text;
  return {
    name,
    size: size ?? bytes.byteLength,
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer,
  };
}

test("file .md có đủ tiêu đề thì tách vào 3 ô", () => {
  const md = "## Hook\nMở đầu.\n\n## Ý chính\nĐoạn một.\n\nĐoạn hai.\n\n## Nhận xét\nNên đọc.";
  assert.deepEqual(splitReviewText(md), {
    hook: "Mở đầu.",
    main: "Đoạn một.\n\nĐoạn hai.",
    comment: "Nên đọc.",
  });
});

test("tiêu đề viết không dấu, thiếu ô vẫn tách đúng", () => {
  assert.deepEqual(splitReviewText("## y chinh\r\nNội dung.\r\n## NHAN XET\r\nHay."), {
    hook: "",
    main: "Nội dung.",
    comment: "Hay.",
  });
});

test("không có tiêu đề thì cả bài vào Ý chính", () => {
  const text = "# Tiêu đề khác\nNội dung bài.";
  assert.deepEqual(splitReviewText(text), { ...EMPTY_FIELDS, main: text });
});

test("đọc file: .txt, có BOM", async () => {
  const fields = await readReviewFile(file("bai.TXT", "﻿Nội dung."));
  assert.equal(fields.main, "Nội dung.");
});

test("file quá 200 KB, sai đuôi, không phải UTF-8 thì báo lỗi", async () => {
  await assert.rejects(readReviewFile(file("a.md", "x", MAX_FILE_BYTES + 1)), /200 KB/);
  await assert.rejects(readReviewFile(file("a.docx", "x")), ReviewFileError);
  await assert.rejects(readReviewFile(file("a.txt", new Uint8Array([0xff, 0xfe, 0xc3]))), /UTF-8/);
});

test("thời lượng: ~25 âm tiết một cảnh, Hook luôn 1 cảnh", () => {
  const main = "một ".repeat(76);
  // 76 âm tiết / 3,8 + 4 cảnh × 0,45 = 21,8 giây.
  assert.ok(Math.abs(reviewSeconds({ ...EMPTY_FIELDS, main }) - 21.8) < 1e-9);
  const two = reviewSeconds({ hook: "hai ".repeat(38), main, comment: "" });
  assert.ok(Math.abs(two - 21.8 - 10.45) < 1e-9);
  const check = checkReview({ hook: "a ".repeat(21), main, comment: "" });
  assert.equal(check.tooShort, true);
  assert.equal(check.hookLong, true);
  assert.equal(checkReview({ ...EMPTY_FIELDS, main: "một ".repeat(1200) }).tooLong, true);
  assert.equal(checkReview({ ...EMPTY_FIELDS, main: "một ".repeat(100) }).tooShort, false);
});

test("payload user_review bỏ ô trống", () => {
  assert.deepEqual(toUserReview({ hook: "  ", main: " Ý ", comment: "Hay" }), {
    main: "Ý",
    comment: "Hay",
  });
});

test("tiến độ: tab review ẩn research, thêm Đọc bài review", () => {
  const ids = (s?: "book" | "user_review") => visibleNodes(null, s).map((n) => n.id);
  const review = ids("user_review");
  for (const id of ["research_agent", "identify_confirm", "storyboard", "faithfulness_eval"]) {
    assert.ok(!review.includes(id as never));
  }
  assert.ok(review.includes("ingest_review"));
  assert.equal(visibleNodes(null, "user_review")[0].label, "Kiểm tra bài review");
  const book = ids();
  assert.ok(book.includes("research_agent") && !book.includes("ingest_review"));
  assert.equal(visibleNodes(null)[0].label, "Kiểm tra tên sách");
  assert.ok(!ids("user_review").includes("manual_images"));
});

test("đánh dấu chỗ đổi số thành chữ", () => {
  const segs = markChanges("Năm một nghìn chín trăm, có một người.", [
    { from: "1900", to: "một nghìn chín trăm" },
    { from: "1", to: "một" },
  ]);
  assert.deepEqual(
    segs.filter((s) => s.from).map((s) => [s.text, s.from]),
    [
      ["một nghìn chín trăm", "1900"],
      ["một", "1"],
    ],
  );
  assert.equal(segs.map((s) => s.text).join(""), "Năm một nghìn chín trăm, có một người.");
  assert.deepEqual(markChanges("Không đổi.", []), [{ text: "Không đổi." }]);
});

test("tìm câu trích trong bài gốc, bỏ qua khác khoảng trắng", () => {
  assert.deepEqual(findQuote("Câu một.\nCâu  hai (thật).", "Câu hai (thật)."), [
    "Câu một.\n",
    "Câu  hai (thật).",
    "",
  ]);
  assert.equal(findQuote("abc", "xyz"), null);
});

test("parseReview đọc nguồn user_review", () => {
  const r = parseReview({
    storyboard: { source: "user_review", scenes: [{ id: 1, tts_changes: [{ from: "3", to: "ba" }] }] },
    user_review: { main: "Bài." },
  });
  assert.equal(r.source, "user_review");
  assert.equal(r.userReview?.main, "Bài.");
  assert.deepEqual(r.scenes[0].tts_changes, [{ from: "3", to: "ba" }]);
  assert.equal(parseReview({ storyboard: {} }).source, "book");
});
