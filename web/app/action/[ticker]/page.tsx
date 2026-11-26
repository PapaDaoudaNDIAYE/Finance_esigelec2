// UC2 / UC3 — Page détail d'une action.
//
// Le site est exporté en fichiers statiques (voir next.config.mjs) : Next.js doit connaître
// à l'avance les pages à générer. Ce sont les 5 actions suivies (même liste que config.py).
// Le contenu de la page est dans Detail.tsx : il charge les données depuis l'API au navigateur.

import Detail from "./Detail";

const TICKERS = ["RMS.PA", "TTE.PA", "AI.PA", "DSY.PA", "CAP.PA"];

export const dynamicParams = false;

export function generateStaticParams() {
  return TICKERS.map((ticker) => ({ ticker }));
}

export default async function PageAction({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return <Detail ticker={decodeURIComponent(ticker)} />;
}
