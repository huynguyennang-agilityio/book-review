import "@copilotkit/react-core/v2/styles.css";
import type { ReactNode } from "react";

export const metadata = { title: "Spike stack ngày 2" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif" }}>{children}</body>
    </html>
  );
}
