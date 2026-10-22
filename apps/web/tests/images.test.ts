import assert from "node:assert/strict";
import { test } from "node:test";
import {
  applyServerErrors,
  assignFiles,
  buildUploads,
  canSubmit,
  missingKeys,
  parseModeChoice,
  parseUploadPage,
  promptsText,
  shortText,
  setSlot,
} from "../app/_lib/images.ts";

const page = {
  characters: [{ key: "character:nam", slug: "nam", name: "Nam", prompt: "p0" }],
  scenes: [
    { key: "1:0", scene_id: 1, ref: 0, prompt: "p1" },
    { key: "1:1", scene_id: 1, ref: 1, prompt: "p2" },
  ],
  reused_characters: { lan: { name: "Lan", sheet_path: "x.jpg" } },
  errors: [{ key: "1:1", code: "MISSING" }],
};

test("parseModeChoice tính số ảnh auto và manual", () => {
  const c = parseModeChoice({
    characters: 8,
    character_count: 2,
    scene_images: 24,
    auto_images_usd: 1.5,
    manual_saving_usd: 1.5,
  });
  assert.deepEqual(c, { autoImages: 32, autoUsd: 1.5, manualImages: 26, savingUsd: 1.5 });
  assert.equal(parseModeChoice({}).autoImages, 0);
});

test("parseUploadPage dựng ô theo thứ tự nhân vật rồi cảnh", () => {
  const p = parseUploadPage(page);
  assert.deepEqual(
    p.slots.map((s) => s.key),
    ["character:nam", "1:0", "1:1"],
  );
  assert.equal(p.slots[2].label, "Cảnh 1 · ảnh 2");
  assert.deepEqual(p.reused, ["lan"]);
  assert.deepEqual(p.errors, { "1:1": "MISSING" });
});

test("chỉ gửi được khi đủ ảnh", () => {
  let slots = parseUploadPage(page).slots;
  assert.equal(canSubmit(slots), false);
  assert.deepEqual(missingKeys(slots), ["character:nam", "1:0", "1:1"]);
  for (const k of ["character:nam", "1:0"]) {
    slots = setSlot(slots, k, { status: "done", path: `uploads/p/${k.replace(":", "_")}.jpg` });
  }
  assert.equal(canSubmit(slots), false);
  slots = setSlot(slots, "1:1", { status: "uploading" });
  assert.equal(canSubmit(slots), false);
  slots = setSlot(slots, "1:1", { status: "done", path: "uploads/p/c.jpg" });
  assert.equal(canSubmit(slots), true);
  assert.deepEqual(Object.keys(buildUploads(slots)), ["character:nam", "1:0", "1:1"]);
});

test("assignFiles gán theo thứ tự vào ô còn thiếu và bỏ file thừa", () => {
  let slots = parseUploadPage(page).slots;
  slots = setSlot(slots, "character:nam", { status: "done", path: "a" });
  slots = setSlot(slots, "1:0", { status: "error", error: "x" });
  assert.deepEqual(assignFiles(slots, ["f1", "f2", "f3"]), [
    ["1:0", "f1"],
    ["1:1", "f2"],
  ]);
  assert.deepEqual(assignFiles(slots, []), []);
});

test("promptsText đánh số theo thứ tự ô và shortText cắt lời đọc dài", () => {
  const slots = parseUploadPage(page).slots;
  assert.equal(promptsText(slots), "#1 Nhân vật: Nam\np0\n\n#2 Cảnh 1 · ảnh 1\np1\n\n#3 Cảnh 1 · ảnh 2\np2");
  assert.equal(shortText("abc", 5), "abc");
  assert.equal(shortText("abcdefgh", 5), "abcde…");
});

test("applyServerErrors chuyển ô bị báo lỗi về error và giữ ô khác", () => {
  let slots = parseUploadPage(page).slots;
  slots = setSlot(slots, "1:0", { status: "done", path: "a" });
  slots = setSlot(slots, "1:1", { status: "done", path: "b" });
  const out = applyServerErrors(slots, { "1:1": "VALIDATION_ERROR" });
  assert.equal(out[1].status, "done");
  assert.equal(out[2].status, "error");
  assert.equal(out[2].path, undefined);
  assert.equal(canSubmit(out), false);
});
