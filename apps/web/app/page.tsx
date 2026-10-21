"use client";

import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useRef, useState } from "react";
import { BookForm } from "./_components/BookForm";
import { IdentifyConfirm } from "./_components/IdentifyConfirm";
import { LoginForm } from "./_components/LoginForm";
import { Progress } from "./_components/Progress";
import { Sources } from "./_components/Sources";
import { useReviewRun } from "./_lib/run";
import { supabase } from "./_lib/supabase";

function ReviewApp({ session }: { session: Session }) {
  // Luôn lấy token mới nhất từ Supabase (tự làm mới khi sắp hết hạn).
  const getToken = useCallback(async () => {
    const { data } = await supabase().auth.getSession();
    return data.session?.access_token ?? session.access_token;
  }, [session.access_token]);
  const run = useReviewRun(getToken);
  const busy = run.status === "running";
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
            <div ref={endRef} />
          </div>
          {run.pending?.type === "identify_confirm" && (
            <IdentifyConfirm
              pending={run.pending}
              onPick={(index) => run.resume({ index })}
              onCancel={() => run.resume({ cancel: true })}
            />
          )}
        </div>
        <div className="col">
          <section className="card">
            <h3>Tiến độ</h3>
            <Progress steps={run.steps} />
            {run.cost != null && <p className="muted">Chi phí: ${run.cost.toFixed(3)}</p>}
          </section>
          <Sources sources={run.sources} />
        </div>
      </div>
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
