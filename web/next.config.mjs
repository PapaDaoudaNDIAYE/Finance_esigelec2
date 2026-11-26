// Toutes les requêtes /api/... du navigateur sont relayées vers l'API Python (api.py).
// Ainsi le navigateur ne parle qu'à Next.js : pas de problème de CORS, une seule adresse.
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
