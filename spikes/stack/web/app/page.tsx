"use client";

import { CopilotChat, CopilotKit, useInterrupt } from "@copilotkit/react-core/v2";
import { useState } from "react";

function BookTitleInterrupt() {
  useInterrupt({
    agentId: "hello",
    // API bật emit_interrupt_outcome nên đây là interrupt chuẩn AG-UI; message lấy từ
    // interrupt({"message": ...}) bên graph.
    render: ({ interrupt, resolve }) => (
      <AskForm question={interrupt?.message ?? ""} onSubmit={(title) => resolve(title)} />
    ),
  });
  return null;
}

function AskForm({ question, onSubmit }: { question: string; onSubmit: (v: string) => unknown }) {
  const [title, setTitle] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) onSubmit(title.trim());
      }}
      style={{ display: "flex", gap: 8, padding: 12, border: "1px solid #ccc", borderRadius: 8 }}
    >
      <label style={{ flex: 1 }}>
        {question}
        <input
          data-testid="book-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ display: "block", width: "100%", marginTop: 4 }}
        />
      </label>
      <button type="submit">Gửi</button>
    </form>
  );
}

export default function Page() {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit">
      <BookTitleInterrupt />
      <main style={{ height: "100vh" }}>
        <CopilotChat agentId="hello" />
      </main>
    </CopilotKit>
  );
}
