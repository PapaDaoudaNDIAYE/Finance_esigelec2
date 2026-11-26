// Les requêtes /api/py/... du navigateur vont vers l'API Python (serveur.py) :
//   - sur Vercel : vers la fonction Python api/index.py, dans le même projet ;
//   - en local   : vers uvicorn (http://127.0.0.1:8000 par défaut, modifiable avec API_URL).
// Le navigateur ne parle donc qu'à une seule adresse : pas de problème de CORS.
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: process.env.VERCEL ? "/api/" : `${API_URL}/api/py/:path*`,
      },
    ];
  },
};

export default nextConfig;
