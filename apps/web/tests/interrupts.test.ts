import assert from "node:assert/strict";
import { test } from "node:test";
import { keepPending } from "../app/_lib/interrupts.ts";

test("keepPending bỏ interrupt cũ, giữ interrupt đang trả lời", () => {
  const list = [{ id: "old-review-script" }, { id: "choose-image-mode" }];
  assert.deepEqual(keepPending(list, "choose-image-mode"), [{ id: "choose-image-mode" }]);
  assert.deepEqual(keepPending([{ id: "old" }], "new"), []);
  assert.deepEqual(keepPending([], "x"), []);
});
