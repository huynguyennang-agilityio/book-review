// CopilotRuntime chuyển tiếp tới agent Python qua AG-UI (HTTP + SSE). Cách làm theo spike ngày 2.
import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";

const runtime = new CopilotRuntime({
  agents: {
    review: new HttpAgent({ url: process.env.AGENT_URL ?? "http://localhost:8000/agent" }),
  },
});

const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

export const GET = handler;
export const POST = handler;
