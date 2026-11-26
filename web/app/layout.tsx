import type { Metadata } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import { ProfilProvider } from "@/components/Profil";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-serif" });

export const metadata: Metadata = {
  title: "Conseiller Bourse",
  description: "Acheter, vendre ou ne rien faire : l'analyse quotidienne de vos 5 actions.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${inter.variable} ${serif.variable}`}>
      <body>
        <div className="fond" aria-hidden />
        <ProfilProvider>
          <div className="page">{children}</div>
        </ProfilProvider>
      </body>
    </html>
  );
}
