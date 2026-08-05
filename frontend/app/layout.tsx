import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "投研评分助手",
  description: "基于已提供指标的研究辅助评分页面",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
