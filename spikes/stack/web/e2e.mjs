// Kiểm tra end-to-end bằng trình duyệt: chat -> interrupt hiện form -> gửi tên sách -> graph chạy tiếp.
// Cần API (cổng 8000) và web (cổng 3000) đang chạy. Lần đầu: npx playwright install chromium
//   node e2e.mjs                 chạy 1 vòng
//   node e2e.mjs --restart "cmd" chạy lệnh restart API giữa lúc đang chờ interrupt
import { execSync } from "node:child_process";
import { chromium } from "playwright";

const restartIdx = process.argv.indexOf("--restart");
const restartCmd = restartIdx > 0 ? process.argv[restartIdx + 1] : null;
const executablePath = process.env.CHROMIUM_PATH || undefined;

const browser = await chromium.launch({ executablePath });
const page = await browser.newPage();
await page.goto(process.env.WEB_URL ?? "http://localhost:3000", { waitUntil: "networkidle" });

const input = page.locator("textarea").first();
await input.fill("chào bạn");
await input.press("Enter");

const field = page.getByTestId("book-title");
await field.waitFor({ timeout: 30000 });
console.log("Interrupt đã hiện:", await page.getByText("Bạn muốn review cuốn sách nào?").count() > 0);

if (restartCmd) {
  execSync(restartCmd, { stdio: "inherit" });
}

await field.fill("Nhà giả kim");
await page.getByRole("button", { name: "Gửi" }).click();
await page.getByText("Đã nhận: «Nhà giả kim»").waitFor({ timeout: 30000 });
console.log("Graph chạy tiếp sau interrupt: OK");
await browser.close();
