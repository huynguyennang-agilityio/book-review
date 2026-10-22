"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  applyServerErrors,
  assignFiles,
  buildUploads,
  canSubmit,
  parseUploadPage,
  progressText,
  promptsText,
  setSlot,
  shortText,
  type Slot,
} from "../_lib/images";
import { errorText, type Pending, type UploadedImage } from "../_lib/run";

const ACCEPT = "image/jpeg,image/png,image/webp";

export function ManualImages({
  pending,
  busy,
  onUpload,
  onSubmit,
  onCancel,
}: {
  pending: Pending;
  busy: boolean;
  onUpload: (file: File) => Promise<UploadedImage>;
  onSubmit: (uploads: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const page = useMemo(() => parseUploadPage(pending.raw), [pending.raw]);
  const [slots, setSlots] = useState<Slot[]>(page.slots);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState<string | null>(null);
  // Nhiều file kéo thả/chọn một lượt: chờ người dùng xác nhận thứ tự gán.
  const [batch, setBatch] = useState<File[] | null>(null);
  const slotsRef = useRef(slots);
  slotsRef.current = slots;
  const previewsRef = useRef(previews);
  previewsRef.current = previews;

  // Server hỏi lại (thiếu/hỏng ảnh): đánh dấu lỗi đúng ô, giữ nguyên các ô đã tải.
  useEffect(() => {
    if (Object.keys(page.errors).length) setSlots((s) => applyServerErrors(s, page.errors));
  }, [page.errors]);
  useEffect(
    () => () => {
      for (const u of Object.values(previewsRef.current)) URL.revokeObjectURL(u);
    },
    [],
  );

  const uploadTo = async (key: string, file: File) => {
    setSlots((s) => setSlot(s, key, { status: "uploading", error: undefined }));
    try {
      const r = await onUpload(file);
      const url = URL.createObjectURL(file);
      setPreviews((p) => {
        if (p[key]) URL.revokeObjectURL(p[key]);
        return { ...p, [key]: url };
      });
      setSlots((s) => setSlot(s, key, { status: "done", path: r.path, error: undefined }));
    } catch (err) {
      setSlots((s) =>
        setSlot(s, key, { status: "error", path: undefined, error: errorText(err, "Không tải được ảnh.") }),
      );
    }
  };

  const confirmBatch = () => {
    if (!batch) return;
    for (const [key, file] of assignFiles(slotsRef.current, batch)) void uploadTo(key, file);
    setBatch(null);
  };

  const copy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied((c) => (c === id ? null : c)), 1500);
    } catch {
      setCopied(null);
    }
  };

  const downloadPrompts = () => {
    const url = URL.createObjectURL(new Blob([promptsText(slots)], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "prompts.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const uploading = slots.some((s) => s.status === "uploading");
  const ready = canSubmit(slots);
  const open = slots.filter((s) => s.status === "empty" || s.status === "error");
  const characters = slots.filter((s) => s.kind === "character");
  const scenes = slots.filter((s) => s.kind === "scene");

  const row = (s: Slot) => (
    <div className={`upload-slot ${s.status}`} key={s.key} data-testid={`slot-${s.key}`}>
      <div className="upload-info">
        <strong>{s.label}</strong>
        {s.narration && <p className="muted">“{shortText(s.narration)}”</p>}
        <p className="prompt-text">{s.prompt}</p>
        <div className="actions">
          <button type="button" className="link" onClick={() => void copy(s.key, s.prompt)}>
            {copied === s.key ? "Đã sao chép" : "Sao chép prompt"}
          </button>
          <label className="file-btn">
            {s.status === "done" ? "Thay ảnh" : "Chọn ảnh"}
            <input
              type="file"
              accept={ACCEPT}
              hidden
              disabled={busy || s.status === "uploading"}
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) void uploadTo(s.key, f);
              }}
              data-testid={`file-${s.key}`}
            />
          </label>
        </div>
        {s.status === "uploading" && <p className="muted">Đang tải lên…</p>}
        {s.error && (
          <p className="msg error" data-testid={`error-${s.key}`}>
            {s.error}
          </p>
        )}
      </div>
      <div className="upload-preview">
        {previews[s.key] && s.status === "done" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previews[s.key]} alt={s.label} />
        ) : (
          <span className="muted">9:16</span>
        )}
      </div>
    </div>
  );

  return (
    <section className="card" data-testid="manual-images">
      <h3>Tải ảnh cho video</h3>
      <p className="muted">
        Mỗi prompt cần đúng một ảnh. Bạn chịu trách nhiệm về độ liền mạch giữa các ảnh và bản quyền
        ảnh. Ảnh được cắt 9:16 khi dựng video.
      </p>
      {page.reused.length > 0 && (
        <p className="muted">Nhân vật dùng lại từ series, không cần ảnh mới: {page.reused.join(", ")}.</p>
      )}
      <div className="upload-progress" data-testid="upload-progress">
        <progress value={slots.filter((s) => s.status === "done").length} max={slots.length} />
        <span>Đã tải {progressText(slots)}</span>
      </div>
      <div className="actions">
        <button type="button" className="link" onClick={() => void copy("all", promptsText(slots))}>
          {copied === "all" ? "Đã sao chép" : "Sao chép tất cả prompt"}
        </button>
        <button type="button" className="link" onClick={downloadPrompts}>
          Tải file prompt
        </button>
        <label
          className="file-btn drop"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const files = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/"));
            if (files.length) setBatch(files);
          }}
        >
          Chọn/kéo nhiều ảnh (gán theo thứ tự)
          <input
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            disabled={busy || open.length === 0}
            onChange={(e) => {
              const files = [...(e.target.files ?? [])];
              e.target.value = "";
              if (files.length) setBatch(files);
            }}
            data-testid="file-multi"
          />
        </label>
      </div>
      {batch && (
        <div className="batch-confirm" data-testid="batch-confirm">
          <p>
            Gán {Math.min(batch.length, open.length)} ảnh theo thứ tự vào các ô còn thiếu, bắt đầu từ
            “{open[0]?.label}”?
            {batch.length > open.length && ` ${batch.length - open.length} ảnh thừa sẽ bị bỏ qua.`}
          </p>
          <ol className="muted">
            {assignFiles(slots, batch)
              .slice(0, 5)
              .map(([key, f]) => (
                <li key={key}>
                  {f.name} → {slots.find((s) => s.key === key)?.label}
                </li>
              ))}
          </ol>
          <div className="actions">
            <button type="button" onClick={confirmBatch} data-testid="batch-ok">
              Xác nhận
            </button>
            <button type="button" className="link" onClick={() => setBatch(null)}>
              Bỏ
            </button>
          </div>
        </div>
      )}
      {characters.length > 0 && <h4>Nhân vật</h4>}
      {characters.map(row)}
      <h4>Ảnh cảnh</h4>
      {scenes.map(row)}
      <div className="actions">
        <button
          type="button"
          disabled={busy || uploading || !ready}
          onClick={() => onSubmit(buildUploads(slots))}
          data-testid="manual-continue"
        >
          Tiếp tục dựng video
        </button>
        <button type="button" className="danger" disabled={busy} onClick={onCancel}>
          Huỷ
        </button>
        {!ready && (
          <span className="muted">Cần đủ {slots.length} ảnh mới tiếp tục được.</span>
        )}
      </div>
    </section>
  );
}
