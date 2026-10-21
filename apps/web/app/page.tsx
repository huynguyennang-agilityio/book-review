"use client";

import { CopilotChat, CopilotKit } from "@copilotkit/react-core/v2";

// Khung trang. Agent `review` (graph LangGraph thật) được gắn ở API từ ngày 4.
export default function Page() {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit">
      <main style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
        <header style={{ padding: "12px 16px", borderBottom: "1px solid #ddd" }}>
          <h1 style={{ margin: 0, fontSize: 18 }}>Book Review AI</h1>
        </header>
        <div style={{ flex: 1, minHeight: 0 }}>
          <CopilotChat agentId="review" />
        </div>
      </main>
    </CopilotKit>
  );
}
