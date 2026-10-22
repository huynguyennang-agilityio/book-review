"use client";

import { useState } from "react";
import { parseModeChoice, type ImageMode } from "../_lib/images";
import { errorText, type Pending, type UploadedImage } from "../_lib/run";

export function ImageModeChoice({
  pending,
  busy,
  onChoose,
  onUpload,
  onCancel,
}: {
  pending: Pending;
  busy: boolean;
  onChoose: (mode: ImageMode) => void;
  onUpload: (file: File) => Promise<UploadedImage>;
  onCancel: () => void;
}) {
  const choice = parseModeChoice(pending.raw);
  const [mode, setMode] = useState<ImageMode>(pending.raw.default === "manual" ? "manual" : "auto");
  const [trial, setTrial] = useState<{ text: string; ok: boolean } | null>(null);
  const [uploading, setUploading] = useState(false);

  const tryUpload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setTrial(null);
    try {
      const r = await onUpload(file);
      const warn = r.warnings.map((w) => w.message_vi).join(" ");
      setTrial({
        ok: true,
        text: `Đã tải lên ${r.width}×${r.height}, ${Math.round(r.size / 1024)} KB.${warn ? ` ${warn}` : ""}`,
      });
    } catch (err) {
      setTrial({ ok: false, text: errorText(err, "Không tải được ảnh.") });
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="card" data-testid="choose-image-mode">
      <h3>Chọn cách làm ảnh</h3>
      <p className="muted">Áp dụng cho toàn bộ ảnh nhân vật và ảnh cảnh của video.</p>
      <div className="mode-options" role="radiogroup" aria-label="Cách làm ảnh">
        <label className={`mode-option${mode === "auto" ? " picked" : ""}`}>
          <input
            type="radio"
            name="image-mode"
            checked={mode === "auto"}
            disabled={busy}
            onChange={() => setMode("auto")}
            data-testid="mode-auto"
          />
          <strong>Tự tạo ảnh (auto)</strong>
          <span className="muted">
            AI tạo khoảng {choice.autoImages} ảnh, chi phí ~${choice.autoUsd.toFixed(2)}. Bạn chỉ
            chọn ảnh nhân vật.
          </span>
        </label>
        <label className={`mode-option${mode === "manual" ? " picked" : ""}`}>
          <input
            type="radio"
            name="image-mode"
            checked={mode === "manual"}
            disabled={busy}
            onChange={() => setMode("manual")}
            data-testid="mode-manual"
          />
          <strong>Tự tải ảnh lên (manual)</strong>
          <span className="muted">
            Bạn chuẩn bị khoảng {choice.manualImages} ảnh theo prompt gợi ý, không tốn tiền ảnh
            (tiết kiệm ~${choice.savingUsd.toFixed(2)}). Độ liền mạch và bản quyền ảnh do bạn chịu.
          </span>
        </label>
      </div>
      {mode === "manual" && (
        <div className="trial">
          <label>
            Thử tải một ảnh (JPEG, PNG, WebP, tối đa 10 MB)
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={busy || uploading}
              onChange={(e) => {
                void tryUpload(e.target.files?.[0]);
                e.target.value = "";
              }}
              data-testid="trial-upload"
            />
          </label>
          {uploading && <p className="muted">Đang tải lên…</p>}
          {trial && (
            <p className={trial.ok ? "muted" : "msg error"} data-testid="trial-result">
              {trial.text}
            </p>
          )}
        </div>
      )}
      <div className="actions">
        <button
          type="button"
          disabled={busy}
          onClick={() => onChoose(mode)}
          data-testid="choose-image-mode-continue"
        >
          Tiếp tục
        </button>
        <button type="button" className="danger" disabled={busy} onClick={onCancel}>
          Huỷ
        </button>
      </div>
    </section>
  );
}
