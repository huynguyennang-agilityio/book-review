"use client";

import { useState } from "react";
import type { Options } from "../_lib/run";

const VOICES = [
  { id: "vi-VN-HoaiMyNeural", label: "Hoài My (nữ)" },
  { id: "vi-VN-NamMinhNeural", label: "Nam Minh (nam)" },
];

export function BookForm({
  disabled,
  onSubmit,
  defaults,
}: {
  disabled: boolean;
  onSubmit: (title: string, options: Options, author: string | null) => void;
  // Sở thích đã lưu trong bộ nhớ; chỉ dùng làm giá trị ban đầu.
  defaults?: { minutes?: number; voice?: string; noSpoiler?: boolean };
}) {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [edited, setEdited] = useState({ minutes: false, voice: false, noSpoiler: false });
  const [picked, setPicked] = useState({ minutes: 3, voice: VOICES[0].id, noSpoiler: true });
  // Giá trị đã chọn tay thắng sở thích đã lưu, sở thích thắng mặc định.
  const minutes = edited.minutes ? picked.minutes : (defaults?.minutes ?? picked.minutes);
  const voice = edited.voice ? picked.voice : (defaults?.voice ?? picked.voice);
  const noSpoiler = edited.noSpoiler ? picked.noSpoiler : (defaults?.noSpoiler ?? picked.noSpoiler);
  const setMinutes = (v: number) => {
    setEdited((e) => ({ ...e, minutes: true }));
    setPicked((p) => ({ ...p, minutes: v }));
  };
  const setVoice = (v: string) => {
    setEdited((e) => ({ ...e, voice: true }));
    setPicked((p) => ({ ...p, voice: v }));
  };
  const setNoSpoiler = (v: boolean) => {
    setEdited((e) => ({ ...e, noSpoiler: true }));
    setPicked((p) => ({ ...p, noSpoiler: v }));
  };
  const [budget, setBudget] = useState(1);

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) {
          onSubmit(
            title.trim(),
            { minutes, no_spoiler: noSpoiler, voice, budget_usd: budget },
            author.trim() || null,
          );
        }
      }}
    >
      <label>
        Tên sách
        <input
          name="book-title"
          placeholder="Ví dụ: Đắc nhân tâm"
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        Tác giả (không bắt buộc)
        <input
          name="book-author"
          placeholder="Ví dụ: Dale Carnegie"
          value={author}
          maxLength={100}
          onChange={(e) => setAuthor(e.target.value)}
        />
      </label>
      <div className="row">
        <label>
          Độ dài (phút)
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
            {[1, 2, 3, 5].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label>
          Giọng đọc
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
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
      <label className="check">
        <input
          type="checkbox"
          checked={noSpoiler}
          onChange={(e) => setNoSpoiler(e.target.checked)}
        />
        Không tiết lộ kết truyện (no spoiler)
      </label>
      <button type="submit" disabled={disabled || !title.trim()}>
        Bắt đầu review
      </button>
    </form>
  );
}
