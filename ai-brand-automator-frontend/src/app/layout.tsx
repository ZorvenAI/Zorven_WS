import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ToastContainer } from "@/components/common/ToastContainer";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { Navigation } from "@/components/common/Navigation";
import { TenantProvider } from "@/contexts/TenantContext";

// Default Geist fonts
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Digital Twilight Design System Fonts
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "AI Brand Automator - Build Your Brand with AI",
  description: "AI-powered brand building platform for modern businesses",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} antialiased bg-brand-midnight text-brand-silver`}
      >
        <ErrorBoundary>
          <TenantProvider>
            <Navigation>{children}</Navigation>
            <ToastContainer />
          </TenantProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
