"use client";

import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useRef, useState } from "react";
import { BookForm } from "./_components/BookForm";
import { BudgetRetry } from "./_components/BudgetRetry";
import { CharacterReview } from "./_components/CharacterReview";
import { IdentifyConfirm } from "./_components/IdentifyConfirm";
import { MemorySettings } from "./_components/MemorySettings";
import { LoginForm } from "./_components/LoginForm";
import { ImageModeChoice } from "./_components/ImageModeChoice";
import { ManualImages } from "./_components/ManualImages";
import { Progress } from "./_components/Progress";
import { ResultScreen } from "./_components/ResultScreen";
import { ReviewTextForm } from "./_components/ReviewTextForm";
import { ScriptReview } from "./_components/ScriptReview";
import { Sources } from "./_components/Sources";
import { suggestBudget } from "./_lib/budget";
import { getMemory, type Memory } from "./_lib/memory";
import type { RunSource } from "./_lib/reviewText";
import { useReviewRun } from "./_lib/run";
import { supabase } from "./_lib/supabase";

const TAB_KEY = "review-tab";
const TABS: { id: RunSource; label: string }[] = [
  { id: "book", label: "Từ tên sách" },
  { id: "user_review", label: "Từ bài review có sẵn" },
];

// Giá ước tính một ảnh Seedream (khớp `price_image_usd` của API), chỉ để hiện trên nút.
const PRICE_IMAGE_USD = 0.03;

function ReviewApp({ session }: { session: Session }) {
  // Luôn lấy token mới nhất từ Supabase (tự làm mới khi sắp hết hạn).
  const getToken = useCallback(async () => {
    const { data } = await supabase().auth.getSession();
    return data.session?.access_token ?? session.access_token;
  }, [session.access_token]);
  const run = useReviewRun(getToken);
  const [showSettings, setShowSettings] = useState(false);
  const [memory, setMemory] = useState<Memory | null>(null);
  const defaults = memory
    ? {
        minutes: memory.preferences.length_minutes,
        voice: memory.preferences.voice === "default" ? undefined : memory.preferences.voice,
        noSpoiler: memory.preferences.no_spoiler,
      }
    : undefined;
  // Tải sở thích đã lưu một lần khi vào trang để điền sẵn form.
  useEffect(() => {
    getToken()
      .then(getMemory)
      .then(setMemory)
      .catch(() => setMemory(null));
  }, [getToken]);
  const busy = run.status === "running";
  const locked = busy || run.status === "awaiting";
  // Tab lần trước, đọc sau khi mount để HTML server và client khớp.
  const [tab, setTab] = useState<RunSource>("book");
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(TAB_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- đọc localStorage một lần
      if (saved === "user_review") setTab(saved);
    } catch {
      // Không đọc được lưu trữ: giữ tab mặc định.
    }
  }, []);
  const pickTab = (next: RunSource) => {
    setTab(next);
    try {
      window.localStorage.setItem(TAB_KEY, next);
    } catch {
      // Trình duyệt chặn lưu trữ: lần sau mở lại tab mặc định.
    }
  };
  const canCancel = run.status === "running" || run.status === "awaiting";
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [run.messages]);

  return (
    <main className="layout">
      <header>
        <h1>Book Review AI</h1>
        <span className="muted">{session.user.email}</span>
        <button type="button" className="link" onClick={() => setShowSettings((s) => !s)}>
          Bộ nhớ
        </button>
        <button type="button" className="link" onClick={() => supabase().auth.signOut()}>
          Đăng xuất
        </button>
      </header>
      {run.pending?.type === "review_script" && (
        <ScriptReview
          key={run.pending.interruptId}
          pending={run.pending}
          sources={run.sources}
          budget={run.budget}
          busy={busy || run.cancelling}
          onApprove={run.approveScript}
          onCancel={run.cancel}
          onRewrite={run.rewriteScene}
        />
      )}
      <div className="grid">
        <div className="col">
          {showSettings && (
            <MemorySettings
              getToken={getToken}
              onChange={setMemory}
              onClose={() => setShowSettings(false)}
            />
          )}
          <div className="tabs" role="tablist" aria-label="Cách tạo kịch bản">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                disabled={locked && tab !== t.id}
                title={locked && tab !== t.id ? "Đang có project chạy hoặc chờ duyệt" : undefined}
                onClick={() => pickTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          {tab === "book" ? (
            <BookForm disabled={locked} onSubmit={run.start} defaults={defaults} />
          ) : (
            <ReviewTextForm disabled={locked} onSubmit={run.start} defaults={defaults} />
          )}
          <div className="card chat" aria-live="polite">
            {run.messages.length === 0 && (
              <p className="muted">
                {tab === "book" ? "Nhập tên sách để bắt đầu." : "Dán bài review để bắt đầu."}
              </p>
            )}
            {run.messages.map((m, i) => (
              <p key={i} className={`msg ${m.role}`}>
                {m.text}
              </p>
            ))}
            {busy && <p className="muted">Đang chạy…</p>}
            {run.status === "failed" &&
              (run.errorCode === "BUDGET_EXCEEDED" ? (
                <BudgetRetry
                  spent={run.cost ?? 0}
                  budget={run.budget}
                  suggested={suggestBudget(run.cost ?? 0, run.imagesBought, run.costEstimate)}
                  onRetry={(usd) => void run.retry(usd)}
                />
              ) : (
                <button type="button" onClick={() => void run.retry()}>
                  Thử lại
                </button>
              ))}
            {run.status === "cancelled" && <p className="muted">Project đã huỷ.</p>}
            <div ref={endRef} />
          </div>
          {run.pending?.type === "identify_confirm" && (
            <IdentifyConfirm
              pending={run.pending}
              onPick={(index) => run.resume({ index })}
              onCancel={run.cancel}
            />
          )}
          {run.pending?.type === "choose_image_mode" && (
            <ImageModeChoice
              key={run.pending.interruptId}
              pending={run.pending}
              busy={busy || run.cancelling}
              onChoose={(mode) => void run.chooseImageMode(mode)}
              onUpload={run.uploadImage}
              onCancel={run.cancel}
            />
          )}
          {run.pending?.type === "upload_images" && (
            <ManualImages
              pending={run.pending}
              draft={run.uploadDraft}
              busy={busy || run.cancelling}
              onUpload={run.uploadImage}
              onSubmit={(uploads) => void run.resume({ uploads })}
              onCancel={run.cancel}
            />
          )}
          {run.pending?.type === "review_characters" && (
            <CharacterReview
              key={run.pending.interruptId}
              pending={run.pending}
              busy={busy || run.cancelling}
              priceImage={PRICE_IMAGE_USD}
              loadImage={run.loadImage}
              onSubmit={run.approveCharacters}
              onCancel={run.cancel}
            />
          )}
        </div>
        <div className="col">
          <section className="card">
            <h3>Tiến độ</h3>
            <Progress steps={run.steps} imageMode={run.imageMode} source={run.source} />
            {run.cost != null && <p className="muted">Chi phí: ${run.cost.toFixed(3)}</p>}
            {canCancel && (
              <button
                type="button"
                className="danger"
                disabled={run.cancelling}
                onClick={run.cancel}
                data-testid="cancel"
              >
                {run.cancelling ? "Đang huỷ…" : "Huỷ"}
              </button>
            )}
          </section>
          <Sources sources={run.sources} />
        </div>
      </div>
      {run.status === "done" && run.outputs.length > 0 && (
        <ResultScreen outputs={run.outputs} loadOutput={run.loadOutput} />
      )}
    </main>
  );
}

export default function Page() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  useEffect(() => {
    const auth = supabase().auth;
    auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  if (session === undefined) return <main className="layout muted">Đang tải…</main>;
  if (session === null) {
    return (
      <main className="layout">
        <h1>Book Review AI</h1>
        <LoginForm />
      </main>
    );
  }
  return <ReviewApp session={session} />;
}
