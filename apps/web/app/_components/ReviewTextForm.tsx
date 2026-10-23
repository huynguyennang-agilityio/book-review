"use client";

import { useEffect, useRef, useState } from "react";
import type { Options } from "../_lib/run";
import {
  checkReview,
  EMPTY_FIELDS,
  FILE_SUFFIXES,
  HOOK_MAX_WORDS,
  MIN_MAIN_WORDS,
  readReviewFile,
  ReviewFileError,
  type ReviewFields,
  toUserReview,
} from "../_lib/reviewText";
import { formatDuration } from "../_lib/script";
import { VOICES } from "./BookForm";

const DRAFT_KEY = "review-text-draft";

function loadDraft(): ReviewFields & { title: string; author: string } {
  const empty = { ...EMPTY_FIELDS, title: "", author: "" };
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    return raw ? { ...empty, ...(JSON.parse(raw) as Partial<typeof empty>) } : empty;
  } catch {
    return empty;
  }
}

export function ReviewTextForm({
  disabled,
  onSubmit,
  defaults,
}: {
  disabled: boolean;
  onSubmit: (
    title: string,
    options: Options,
    author: string | null,
    userReview: Record<string, string>,
  ) => void;
  defaults?: { voice?: string };
}) {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [fields, setFields] = useState<ReviewFields>(EMPTY_FIELDS);
  const [pickedVoice, setPickedVoice] = useState<string | null>(null);
  const voice = pickedVoice ?? defaults?.voice ?? VOICES[0].id;
  const [budget, setBudget] = useState(1);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const loaded = useRef(false);

  // Nháp 3 ô sống qua lần tải lại trang; đọc sau khi mount để HTML server và client khớp.
  useEffect(() => {
    const draft = loadDraft();
    /* eslint-disable react-hooks/set-state-in-effect -- đọc localStorage một lần sau mount */
    setTitle(draft.title);
    setAuthor(draft.author);
    setFields({ hook: draft.hook, main: draft.main, comment: draft.comment });
    /* eslint-enable react-hooks/set-state-in-effect */
    loaded.current = true;
  }, []);
  useEffect(() => {
    if (!loaded.current) return;
    try {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...fields, title, author }));
    } catch {
      // Trình duyệt chặn lưu trữ: nháp chỉ mất khi tải lại trang.
    }
  }, [fields, title, author]);

  const check = checkReview(fields);
  const set = (key: keyof ReviewFields) => (e: { target: { value: string } }) =>
    setFields((f) => ({ ...f, [key]: e.target.value }));
  const canSubmit = !disabled && title.trim() && !check.tooShort && !check.tooLong;

  async function pickFile(file: File | undefined) {
    if (!file) return;
    try {
      const read = await readReviewFile(file);
      const split = Boolean(read.hook || read.comment);
      setFields(split ? read : (f) => ({ ...f, main: read.main }));
      setFileNote(split ? `Đã tách ${file.name} vào 3 ô.` : `Đã đưa ${file.name} vào ô Ý chính.`);
    } catch (err) {
      setFileNote(err instanceof ReviewFileError ? err.message : "Không đọc được file.");
    }
  }

  return (
    <form
      className="card"
      data-testid="review-text-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit) return;
        onSubmit(
          title.trim(),
          // Độ dài theo bài: `minutes` chỉ để giữ dạng Options, graph không dùng ở tab này.
          {
            minutes: Math.max(1, Math.round(check.seconds / 60)),
            no_spoiler: false,
            voice,
            budget_usd: budget,
          },
          author.trim() || null,
          toUserReview(fields),
        );
      }}
    >
      <label>
        Tên sách
        <input
          name="review-book-title"
          placeholder="Ví dụ: Nhà giả kim"
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        Tác giả (không bắt buộc)
        <input
          name="review-book-author"
          value={author}
          maxLength={100}
          onChange={(e) => setAuthor(e.target.value)}
        />
      </label>
      <label>
        Hook (không bắt buộc, {check.hookWords} từ)
        <textarea
          name="review-hook"
          rows={2}
          placeholder="Câu mở đầu gây tò mò, đọc thành 1 cảnh"
          value={fields.hook}
          onChange={set("hook")}
        />
      </label>
      {check.hookLong && (
        <p className="bad">Hook dài hơn {HOOK_MAX_WORDS} từ, nên rút gọn để mở đầu thật nhanh.</p>
      )}
      <label>
        Ý chính ({check.mainWords} từ, tối thiểu {MIN_MAIN_WORDS})
        <textarea
          name="review-main"
          rows={10}
          placeholder="Nội dung chính của bài review, lời đọc giữ nguyên văn"
          value={fields.main}
          onChange={set("main")}
        />
      </label>
      <label>
        Nhận xét (không bắt buộc)
        <textarea
          name="review-comment"
          rows={3}
          placeholder="Cảm nhận, đánh giá, lời kêu gọi"
          value={fields.comment}
          onChange={set("comment")}
        />
      </label>
      <label>
        Tải file .txt hoặc .md (tối đa 200 KB)
        <input
          type="file"
          accept={FILE_SUFFIXES.join(",")}
          data-testid="review-file"
          onChange={(e) => {
            void pickFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      {fileNote && <p className="muted">{fileNote}</p>}
      <p className={check.tooLong ? "bad" : "muted"} data-testid="review-duration">
        ≈ {formatDuration(check.seconds)} video
        {check.tooLong && ", dài hơn 5 phút, hãy cắt bớt"}
        {fields.main.trim() && check.tooShort && `, ý chính cần ít nhất ${MIN_MAIN_WORDS} từ`}
      </p>
      <div className="row">
        <label>
          Giọng đọc
          <select value={voice} onChange={(e) => setPickedVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ngân sách (USD)
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </label>
      </div>
      <p className="muted">Bạn chịu trách nhiệm về nội dung và bản quyền của bài review.</p>
      <button type="submit" disabled={!canSubmit}>
        Tạo video từ bài review
      </button>
    </form>
  );
}
