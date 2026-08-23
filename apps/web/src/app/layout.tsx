import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReconMate",
  description: "Closed-loop AI revenue recovery for B2B receivables.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
