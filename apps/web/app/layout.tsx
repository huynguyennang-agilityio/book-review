import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Book Review AI",
  description: "Nhập tên sách, nhận video review 9:16 để đăng TikTok, Shorts, Reels.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
