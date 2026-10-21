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
}: {
  disabled: boolean;
  onSubmit: (title: string, options: Options) => void;
}) {
  const [title, setTitle] = useState("");
  const [minutes, setMinutes] = useState(3);
  const [noSpoiler, setNoSpoiler] = useState(true);
  const [voice, setVoice] = useState(VOICES[0].id);
  const [budget, setBudget] = useState(1);

  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) {
          onSubmit(title.trim(), {
            minutes,
            no_spoiler: noSpoiler,
            voice,
            budget_usd: budget,
          });
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
