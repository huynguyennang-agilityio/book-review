"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteMemory, getMemory, type Memory, savePreferences } from "../_lib/memory";
import { errorText } from "../_lib/run";

const VOICES = [
  { id: "default", label: "Mặc định" },
  { id: "vi-VN-HoaiMyNeural", label: "Hoài My (nữ)" },
  { id: "vi-VN-NamMinhNeural", label: "Nam Minh (nam)" },
];

function titles(items: { key: string; [field: string]: unknown }[], field: string) {
  return items.map((i) => String(i[field] ?? i.key)).join(", ") || "Chưa có";
}

export function MemorySettings({
  getToken,
  onChange,
  onClose,
}: {
  getToken: () => Promise<string>;
  onChange: (memory: Memory | null) => void;
  onClose: () => void;
}) {
  const [memory, setMemory] = useState<Memory | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const apply = useCallback(
    (next: Memory | null) => {
      setMemory(next);
      onChange(next);
    },
    [onChange],
  );

  useEffect(() => {
    getToken()
      .then(getMemory)
      .then(apply)
      .catch((e) => setError(errorText(e, "Không tải được bộ nhớ.")));
  }, [getToken, apply]);

  async function run(job: (token: string) => Promise<Memory | null>) {
    setBusy(true);
    setError("");
    try {
      apply(await job(await getToken()));
    } catch (e) {
      setError(errorText(e, "Không lưu được."));
    } finally {
      setBusy(false);
    }
  }

  const prefs = memory?.preferences;
  return (
    <section className="card" aria-label="Bộ nhớ">
      <h3>Bộ nhớ của tôi</h3>
      <p className="muted">
        Lần chạy sau tự áp dụng sở thích đã lưu (giọng đọc, độ dài, tránh spoil) khi bạn chưa chọn.
      </p>
      {error && <p role="alert">{error}</p>}
      {prefs && (
        <>
          <div className="row">
            <label>
              Giọng đọc
              <select
                value={prefs.voice}
                disabled={busy}
                onChange={(e) => run((t) => savePreferences(t, { voice: e.target.value }))}
              >
                {VOICES.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Độ dài (phút)
              <select
                value={prefs.length_minutes}
                disabled={busy}
                onChange={(e) =>
                  run((t) => savePreferences(t, { length_minutes: Number(e.target.value) }))
                }
              >
                {[1, 2, 3, 5].map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={prefs.no_spoiler}
                disabled={busy}
                onChange={(e) => run((t) => savePreferences(t, { no_spoiler: e.target.checked }))}
              />{" "}
              Không spoil
            </label>
          </div>
          <p>Sách đã làm: {titles(memory.books, "title")}</p>
          <p>Nhân vật đã duyệt: {titles(memory.characters, "name")}</p>
          <p>Phản hồi đã lưu: {memory.feedback.length}</p>
        </>
      )}
      <div className="row">
        <button
          type="button"
          className="danger"
          disabled={busy}
          data-testid="delete-memory"
          onClick={() => {
            if (window.confirm("Xoá toàn bộ bộ nhớ của bạn?")) {
              run(async (t) => {
                await deleteMemory(t);
                return getMemory(t);
              });
            }
          }}
        >
          Xoá bộ nhớ
        </button>
        <button type="button" className="link" onClick={onClose}>
          Đóng
        </button>
      </div>
    </section>
  );
}
