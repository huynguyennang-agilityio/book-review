"use client";

import { useEffect, useState } from "react";
import type { OutputFile } from "../_lib/run";

function formatSize(bytes: number): string {
  return bytes >= 1_000_000
    ? `${(bytes / 1_000_000).toFixed(1)} MB`
    : `${Math.ceil(bytes / 1000)} KB`;
}

// Tải file (kèm JWT) rồi trả object URL; thu hồi khi component bỏ đi.
function useBlobUrl(
  key: string | undefined,
  loadOutput: (key: string) => Promise<Blob>,
): { url: string | null; failed: boolean } {
  const [state, setState] = useState<{ url: string | null; failed: boolean }>({
    url: null,
    failed: false,
  });
  useEffect(() => {
    if (!key) return;
    let alive = true;
    let url: string | null = null;
    loadOutput(key)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        if (alive) setState({ url, failed: false });
        else URL.revokeObjectURL(url);
      })
      .catch(() => alive && setState({ url: null, failed: true }));
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [key, loadOutput]);
  return state;
}

function Caption({ loadOutput }: { loadOutput: (key: string) => Promise<Blob> }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadOutput("caption")
      .then((blob) => blob.text())
      .then((t) => alive && setText(t))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [loadOutput]);
  if (!text) return null;
  return (
    <div>
      <h4>Caption</h4>
      <pre className="caption">{text}</pre>
      <button type="button" onClick={() => navigator.clipboard?.writeText(text)}>
        Chép caption
      </button>
    </div>
  );
}

export function ResultScreen({
  outputs,
  loadOutput,
}: {
  outputs: OutputFile[];
  loadOutput: (key: string) => Promise<Blob>;
}) {
  const has = (key: string) => outputs.some((o) => o.key === key);
  const previewKey = has("video:final")
    ? "video:final"
    : has("video:voice_only")
      ? "video:voice_only"
      : undefined;
  const video = useBlobUrl(previewKey, loadOutput);
  const cover = useBlobUrl(has("cover") ? "cover" : undefined, loadOutput);
  const [error, setError] = useState<string | null>(null);

  async function download(file: OutputFile) {
    setError(null);
    try {
      const url = URL.createObjectURL(await loadOutput(file.key));
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      setError(`Không tải được ${file.name}.`);
    }
  }

  return (
    <section className="card result" data-testid="result" aria-label="Kết quả">
      <h3>Kết quả</h3>
      <div className="result-grid">
        <div>
          {video.url ? (
            <video
              className="result-video"
              src={video.url}
              poster={cover.url ?? undefined}
              controls
              playsInline
            />
          ) : (
            <p className="muted">{video.failed ? "Không tải được video." : "Đang tải video…"}</p>
          )}
        </div>
        <div className="result-side">
          <ul className="downloads">
            {outputs.map((o) => (
              <li key={o.key}>
                <button type="button" onClick={() => download(o)} data-testid={`download-${o.key}`}>
                  Tải {o.label}
                </button>
                <span className="muted">
                  {o.name} · {formatSize(o.size)}
                </span>
              </li>
            ))}
          </ul>
          {error && <p className="error">{error}</p>}
          {has("caption") && <Caption loadOutput={loadOutput} />}
          <p className="muted">Khi đăng, bật nhãn &quot;AI-generated content&quot;.</p>
        </div>
      </div>
    </section>
  );
}
