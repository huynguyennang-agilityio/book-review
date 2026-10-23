// Dữ liệu và hàm thuần cho tab "Từ bài review có sẵn": 3 ô, tải file, thời lượng ước tính.
// Không phụ thuộc React để test được bằng `node --test`. Ngưỡng khớp `graph/nodes/review_text.py`.

import { countSyllables, estimateSeconds } from "./script.ts";

export type RunSource = "book" | "user_review";

export interface ReviewFields {
  hook: string;
  main: string;
  comment: string;
}

export const EMPTY_FIELDS: ReviewFields = { hook: "", main: "", comment: "" };
export const MIN_MAIN_WORDS = 100;
export const HOOK_MAX_WORDS = 20;
export const MAX_SECONDS = 300;
export const MAX_FILE_BYTES = 200 * 1024;
export const FILE_SUFFIXES = [".txt", ".md"];

const HEADINGS: Record<string, keyof ReviewFields> = {
  hook: "hook",
  "y chinh": "main",
  "nhan xet": "comment",
};

// Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng (như `precheck.fold`).
export function fold(text: string): string {
  return (text.toLowerCase().normalize("NFD").replace(/đ/g, "d").replace(/\p{Mn}/gu, "").match(
    /[\p{L}\p{N}_]+/gu,
  ) ?? []).join(" ");
}

// File `.md` có tiêu đề `## Hook` / `## Ý chính` / `## Nhận xét` thì tách vào 3 ô; không có
// tiêu đề nào thì cả bài vào Ý chính.
export function splitReviewText(text: string): ReviewFields {
  const normalized = text.replace(/\r\n?/g, "\n");
  const marks: { field: keyof ReviewFields; start: number; end: number }[] = [];
  for (const m of normalized.matchAll(/^##\s+(.+?)\s*$/gm)) {
    const field = HEADINGS[fold(m[1])];
    if (field) marks.push({ field, start: m.index, end: m.index + m[0].length });
  }
  if (marks.length === 0) return { ...EMPTY_FIELDS, main: normalized.trim() };
  const out: ReviewFields = { ...EMPTY_FIELDS };
  marks.forEach((m, i) => {
    const stop = i + 1 < marks.length ? marks[i + 1].start : normalized.length;
    out[m.field] = normalized.slice(m.end, stop).trim();
  });
  return out;
}

export class ReviewFileError extends Error {}

// Kiểm tra và đọc file tải lên: `.txt`/`.md`, tối đa 200 KB, UTF-8 hợp lệ.
export async function readReviewFile(file: {
  name: string;
  size: number;
  arrayBuffer: () => Promise<ArrayBuffer>;
}): Promise<ReviewFields> {
  const name = file.name.toLowerCase();
  if (!FILE_SUFFIXES.some((s) => name.endsWith(s))) {
    throw new ReviewFileError("Chỉ nhận file .txt hoặc .md.");
  }
  if (file.size > MAX_FILE_BYTES) throw new ReviewFileError("File quá lớn, tối đa 200 KB.");
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
  } catch {
    throw new ReviewFileError("File không phải văn bản UTF-8.");
  }
  return splitReviewText(text.replace(/^﻿/, ""));
}

// Thời lượng đọc ước tính của cả bài, mỗi ô tính như một cảnh (khớp `review_seconds` của API).
export function reviewSeconds(fields: ReviewFields): number {
  return estimateSeconds([fields.hook, fields.main, fields.comment].filter((t) => t.trim()));
}

export interface ReviewCheck {
  mainWords: number;
  hookWords: number;
  seconds: number;
  tooShort: boolean;
  tooLong: boolean;
  hookLong: boolean;
}

export function checkReview(fields: ReviewFields): ReviewCheck {
  const mainWords = countSyllables(fields.main);
  const hookWords = countSyllables(fields.hook);
  const seconds = reviewSeconds(fields);
  return {
    mainWords,
    hookWords,
    seconds,
    tooShort: mainWords < MIN_MAIN_WORDS,
    tooLong: seconds > MAX_SECONDS,
    hookLong: hookWords > HOOK_MAX_WORDS,
  };
}

// Payload `user_review` gửi vào graph: ô trống thì bỏ (API coi là không có phần đó).
export function toUserReview(fields: ReviewFields): Record<string, string> {
  const out: Record<string, string> = { main: fields.main.trim() };
  if (fields.hook.trim()) out.hook = fields.hook.trim();
  if (fields.comment.trim()) out.comment = fields.comment.trim();
  return out;
}
