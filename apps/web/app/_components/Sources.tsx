import type { Source, SourceStage } from "../_lib/run";

const LABEL: Record<SourceStage, string> = {
  found: "Tìm thấy",
  read: "Đã đọc",
  ingested: "Dùng cho kịch bản",
};

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function Sources({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  const used = sources.filter((s) => s.stage === "ingested").length;
  const read = sources.filter((s) => s.stage !== "found").length;
  return (
    <section className="card">
      <h3>
        Nguồn ({sources.length} tìm thấy · {read} đã đọc · {used} dùng cho kịch bản)
      </h3>
      <ul className="sources">
        {sources.map((s) => (
          <li key={s.url} data-stage={s.stage}>
            <span className={`badge ${s.stage}`}>{LABEL[s.stage]}</span>
            <a href={s.url} target="_blank" rel="noreferrer noopener">
              {s.title || host(s.url)}
            </a>
            <span className="muted"> {host(s.url)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
