"use client";

import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useRef, useState } from "react";
import { BookForm } from "./_components/BookForm";
import { CharacterReview } from "./_components/CharacterReview";
import { IdentifyConfirm } from "./_components/IdentifyConfirm";
import { LoginForm } from "./_components/LoginForm";
import { Progress } from "./_components/Progress";
import { ResultScreen } from "./_components/ResultScreen";
import { ScriptReview } from "./_components/ScriptReview";
import { Sources } from "./_components/Sources";
import { useReviewRun } from "./_lib/run";
import { supabase } from "./_lib/supabase";

// Giá ước tính một ảnh Seedream (khớp `price_image_usd` của API), chỉ để hiện trên nút.
const PRICE_IMAGE_USD = 0.03;

function ReviewApp({ session }: { session: Session }) {
  // Luôn lấy token mới nhất từ Supabase (tự làm mới khi sắp hết hạn).
  const getToken = useCallback(async () => {
    const { data } = await supabase().auth.getSession();
    return data.session?.access_token ?? session.access_token;
  }, [session.access_token]);
  const run = useReviewRun(getToken);
  const busy = run.status === "running";
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
          <BookForm disabled={busy || run.status === "awaiting"} onSubmit={run.start} />
          <div className="card chat" aria-live="polite">
            {run.messages.length === 0 && <p className="muted">Nhập tên sách để bắt đầu.</p>}
            {run.messages.map((m, i) => (
              <p key={i} className={`msg ${m.role}`}>
                {m.text}
              </p>
            ))}
            {busy && <p className="muted">Đang chạy…</p>}
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
            <Progress steps={run.steps} />
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
