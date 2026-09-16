import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "KROMA",
  description: "Система спутникового мониторинга лесных пожаров",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
