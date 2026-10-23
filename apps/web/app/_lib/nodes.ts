// Các bước của graph cho thanh tiến độ. Không phụ thuộc React để test được bằng `node --test`.

import type { ImageMode } from "./images";
import type { RunSource } from "./reviewText";

// Node của graph theo thứ tự chạy (apps/api/.../graph/build.py). Tiến độ lấy từ event tuỳ biến
// `node` do graph tự phát, không dùng `STEP_*` của adapter (lẫn tên bước nội bộ của research agent).
// `source`: bước chỉ có ở một tab; `mode`: bước chỉ có ở một chế độ ảnh.
export const NODES = [
  { id: "precheck", label: "Kiểm tra tên sách", reviewLabel: "Kiểm tra bài review" },
  { id: "research_agent", label: "Tìm hiểu sách", source: "book" },
  { id: "identify_confirm", label: "Xác nhận đúng sách", source: "book" },
  { id: "ingest_review", label: "Đọc bài review", source: "user_review" },
  { id: "storyboard", label: "Viết kịch bản", source: "book" },
  { id: "faithfulness_eval", label: "Kiểm tra bám nguồn", source: "book" },
  { id: "estimate_cost", label: "Ước tính chi phí" },
  { id: "review_script", label: "Duyệt kịch bản" },
  { id: "tts_align", label: "Tạo giọng đọc" },
  { id: "build_timeline", label: "Dựng timeline" },
  { id: "subtitles", label: "Phụ đề" },
  { id: "choose_image_mode", label: "Chọn cách làm ảnh" },
  { id: "review_characters", label: "Chọn ảnh nhân vật", mode: "auto" },
  { id: "scene_images", label: "Ảnh cảnh", mode: "auto" },
  { id: "manual_images", label: "Tải ảnh lên", mode: "manual" },
  { id: "motion", label: "Chuyển động" },
  { id: "compose_render", label: "Ghép video" },
] as const;

export type NodeId = (typeof NODES)[number]["id"];

// Bước của tab hoặc chế độ ảnh khác bị ẩn (chưa chọn chế độ thì coi là auto, thiếu tab là "book").
export function visibleNodes(mode: ImageMode | null, source: RunSource = "book") {
  return NODES.filter(
    (n) =>
      (!("mode" in n) || n.mode === (mode ?? "auto")) && (!("source" in n) || n.source === source),
  ).map((n) => ({
    id: n.id,
    label: source === "user_review" && "reviewLabel" in n ? n.reviewLabel : n.label,
  }));
}
