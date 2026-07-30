import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toast";

export const metadata: Metadata = {
  title: "Job Review Control Plane",
  description: "Operations control plane for automated job applications",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-accent selection:text-accent-foreground">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
