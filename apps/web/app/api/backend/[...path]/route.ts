// Chuyển tiếp REST (`/projects`) và AG-UI (`/agent`) tới FastAPI cùng origin, giữ nguyên JWT của
// người dùng (header Authorization). Nhờ vậy trình duyệt không cần CORS và stream SSE đi thẳng qua.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function forward(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = new URL(`${API_URL.replace(/\/$/, "")}/${path.join("/")}`);
  target.search = new URL(request.url).search;
  const headers = new Headers();
  for (const name of ["authorization", "content-type", "accept"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
