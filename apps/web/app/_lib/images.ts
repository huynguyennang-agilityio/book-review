// Dữ liệu và hàm thuần cho chọn chế độ ảnh (interrupt `choose_image_mode`) và tải ảnh manual
// (interrupt `upload_images`). Không phụ thuộc React để test được bằng `node --test`.

export type ImageMode = "auto" | "manual";

export interface ModeChoice {
  autoImages: number;
  autoUsd: number;
  manualImages: number;
  savingUsd: number;
}

const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

// Auto: Fal tạo ảnh (ứng viên nhân vật + ảnh cảnh), tính tiền. Manual: mỗi nhân vật 1 ảnh và
// mỗi ảnh cảnh 1 ảnh, người dùng tự chuẩn bị, không tốn tiền ảnh.
export function parseModeChoice(raw: Record<string, unknown>): ModeChoice {
  const sceneImages = num(raw.scene_images);
  return {
    autoImages: Math.round(num(raw.characters) + sceneImages),
    autoUsd: num(raw.auto_images_usd),
    manualImages: Math.round(num(raw.character_count) + sceneImages),
    savingUsd: num(raw.manual_saving_usd),
  };
}

export type SlotStatus = "empty" | "uploading" | "done" | "error";

export interface Slot {
  // Khoá resume: `character:<slug>` hoặc `<scene_id>:<ref>`.
  key: string;
  kind: "character" | "scene";
  label: string;
  prompt: string;
  status: SlotStatus;
  path?: string;
  error?: string;
}

export interface UploadPage {
  slots: Slot[];
  reused: string[];
  // Lỗi server trả khi hỏi lại: khoá -> mã (`MISSING`, `VALIDATION_ERROR`).
  errors: Record<string, string>;
}

interface RawItem {
  key?: string;
  name?: string;
  scene_id?: number;
  ref?: number;
  prompt?: string;
}

export function parseUploadPage(raw: Record<string, unknown>): UploadPage {
  const chars = Array.isArray(raw.characters) ? (raw.characters as RawItem[]) : [];
  const scenes = Array.isArray(raw.scenes) ? (raw.scenes as RawItem[]) : [];
  const slots: Slot[] = [
    ...chars.map((c): Slot => ({
      key: String(c.key),
      kind: "character",
      label: `Nhân vật: ${c.name ?? c.key}`,
      prompt: c.prompt ?? "",
      status: "empty",
    })),
    ...scenes.map((s): Slot => ({
      key: String(s.key),
      kind: "scene",
      label: `Cảnh ${s.scene_id} · ảnh ${num(s.ref) + 1}`,
      prompt: s.prompt ?? "",
      status: "empty",
    })),
  ];
  const errors: Record<string, string> = {};
  if (Array.isArray(raw.errors)) {
    for (const e of raw.errors as { key?: string; code?: string }[]) {
      if (e.key) errors[e.key] = e.code ?? "VALIDATION_ERROR";
    }
  }
  const reused = raw.reused_characters ? Object.keys(raw.reused_characters as object) : [];
  return { slots, reused, errors };
}

export function missingKeys(slots: Slot[]): string[] {
  return slots.filter((s) => s.status !== "done").map((s) => s.key);
}

// Chỉ đi tiếp khi mọi ô đã có ảnh (đủ mọi prompt).
export function canSubmit(slots: Slot[]): boolean {
  return slots.every((s) => s.status === "done" && Boolean(s.path));
}

export function buildUploads(slots: Slot[]): Record<string, string> {
  return Object.fromEntries(
    slots.filter((s) => s.status === "done" && s.path).map((s) => [s.key, s.path as string]),
  );
}

// Gán nhiều file cho các ô còn thiếu theo thứ tự (ô trống hoặc lỗi), trả về [khoá ô, file].
// File thừa bị bỏ qua.
export function assignFiles<F>(slots: Slot[], files: F[]): [string, F][] {
  const open = slots.filter((s) => s.status === "empty" || s.status === "error");
  return open.slice(0, files.length).map((s, i) => [s.key, files[i]]);
}

export function setSlot(slots: Slot[], key: string, patch: Partial<Slot>): Slot[] {
  return slots.map((s) => (s.key === key ? { ...s, ...patch } : s));
}

export function progressText(slots: Slot[]): string {
  const done = slots.filter((s) => s.status === "done").length;
  return `${done}/${slots.length} ảnh`;
}
