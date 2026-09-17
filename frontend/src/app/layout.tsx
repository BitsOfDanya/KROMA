import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { themeInitScript } from "@/state/theme";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "KROMA — оперативный мониторинг лесных пожаров",
  description: "От спутникового сигнала до решения оператора",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0c0e0d" },
    { media: "(prefers-color-scheme: light)", color: "#efede7" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
