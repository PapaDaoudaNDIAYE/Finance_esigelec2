// Deux modes :
//
// - « npm run dev » (développement) : Next.js sert les pages et relaie les requêtes /api/...
//   vers l'API Python lancée à part (uvicorn api:app --port 8000).
//
// - « npm run build » (production) : export STATIQUE dans web/out/ (HTML, CSS, JS).
//   C'est api.py (FastAPI) qui sert ces fichiers, en local comme sur Vercel : une seule
//   application, une seule adresse, et les appels /api/... restent relatifs.
//   Après toute modification du site : relancer « npm run build » et commiter web/out/.
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";
const developpement = process.env.NODE_ENV !== "production";

/** @type {import('next').NextConfig} */
const nextConfig = developpement
  ? {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
      },
    }
  : {
      output: "export",
      trailingSlash: true, // /action/AI.PA/ -> out/action/AI.PA/index.html
      images: { unoptimized: true },
    };

export default nextConfig;
