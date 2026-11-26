"use client";

// Types des réponses de l'API Python (api.py) et petits outils pour les appeler.

import { useCallback, useEffect, useRef, useState } from "react";

export type Signal = "ACHETER" | "VENDRE" | "NE RIEN FAIRE";
export type Module = "information" | "technique" | "financier" | "risque";

export interface Tache {
  en_cours: boolean;
  etape: string | null;
  debut: string | null;
  fin: string | null;
  erreur: string | null;
}

export interface Etat {
  client: string;
  marche_ouvert: boolean;
  derniere_mise_a_jour: string | null;
  maintenant: string;
  seuils: { achat: number; vente: number };
  mise_a_jour: Tache;
  mode_actualisation: "local" | "github";
}

export interface ActionResume {
  ticker: string;
  nom: string;
  secteur: string | null;
  dernier: number | null;
  veille: number | null;
  date: string | null;
  variation: number | null;
  sparkline: number[];
  signal: Signal | null;
  score_final: number | null;
}

export interface Note {
  action: string;
  score: number | null;
  raisons: string[];
  disponible: boolean;
}

export interface Conseil {
  action: string;
  score_final: number | null;
  signal: Signal;
  raisons: string[];
  phrase: string;
  poids: Partial<Record<Module, number>>;
  date: string | null;
}

export interface Point {
  date: string;
  ouverture: number | null;
  haut: number | null;
  bas: number | null;
  cloture: number;
  volume: number | null;
  mm20: number | null;
  mm50: number | null;
  mm200: number | null;
  boll_haut: number | null;
  boll_bas: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histo: number | null;
}

export interface Actualite {
  ticker: string;
  lien: string;
  date: string;
  titre: string;
  source: string | null;
  score_sentiment: number | null;
}

export interface Fondamentaux {
  date: string;
  per: number | null;
  croissance: number | null;
  marge: number | null;
  dette: number | null;
  dividende: number | null;
}

export interface SourceEtat {
  date: string;
  source: string;
  statut: "ok" | "erreur";
  message: string;
}

export interface ActionDetail extends Omit<ActionResume, "sparkline" | "signal" | "score_final"> {
  etat_marche: string;
  marche_ouvert: boolean;
  historique: Point[];
  indicateurs: {
    support?: number | null;
    resistance?: number | null;
    rsi?: number | null;
    macd?: number | null;
    macd_signal?: number | null;
  };
  familles_techniques: Record<string, { note: number; raison: string }>;
  fondamentaux: Fondamentaux | null;
  actualites: Actualite[];
  scores: Partial<Record<Module, Note>>;
  conseil: Conseil | null;
  sources: SourceEtat[];
}

export class ErreurApi extends Error {}

export async function appeler<T>(chemin: string, options?: RequestInit): Promise<T> {
  let reponse: Response;
  try {
    reponse = await fetch(chemin, { cache: "no-store", ...options });
  } catch {
    throw new ErreurApi("Le serveur d'analyse ne répond pas.");
  }
  if (!reponse.ok) {
    if (reponse.status === 404) throw new ErreurApi("Cette action n'est pas suivie par le conseiller.");
    throw new ErreurApi(
      reponse.status >= 500
        ? "Le serveur d'analyse est injoignable. Vérifiez qu'il est lancé (uvicorn serveur:app --port 8000)."
        : `Erreur ${reponse.status}`,
    );
  }
  return reponse.json() as Promise<T>;
}

/** Charge une route de l'API à l'ouverture de la page (UC4) et permet de la recharger. */
export function useApi<T>(chemin: string) {
  const [data, setData] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [chargement, setChargement] = useState(true);

  const recharger = useCallback(async () => {
    setChargement(true);
    try {
      setData(await appeler<T>(chemin));
      setErreur(null);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setChargement(false);
    }
  }, [chemin]);

  useEffect(() => {
    recharger();
  }, [recharger]);

  return { data, erreur, chargement, recharger };
}

/** Bouton « Actualiser » : lance la mise à jour puis suit son avancement toutes les 2 s. */
export function useActualisation(quandFini: () => void, tacheInitiale?: Tache | null) {
  const [tache, setTache] = useState<Tache | null>(null);
  const minuteur = useRef<ReturnType<typeof setInterval> | null>(null);
  const rappel = useRef(quandFini);
  rappel.current = quandFini;

  const arreter = () => {
    if (minuteur.current) clearInterval(minuteur.current);
    minuteur.current = null;
  };

  // « depuis » = heure du clic : sur Vercel, l'API retrouve ainsi l'exécution GitHub Actions
  // lancée par ce clic (en local, ce paramètre est ignoré).
  const suivre = useCallback((depuis?: string | null) => {
    arreter();
    const chemin = `/api/py/actualiser${depuis ? `?depuis=${encodeURIComponent(depuis)}` : ""}`;
    minuteur.current = setInterval(async () => {
      try {
        const t = await appeler<Tache>(chemin);
        setTache(t);
        if (!t.en_cours) {
          arreter();
          rappel.current();
        }
      } catch {
        arreter();
        setTache((t) => (t ? { ...t, en_cours: false, erreur: "Suivi de la mise à jour interrompu." } : t));
      }
    }, 3000);
  }, []);

  // Une mise à jour lancée depuis un autre onglet est déjà en cours : on la suit.
  useEffect(() => {
    if (tacheInitiale?.en_cours && !minuteur.current) {
      setTache(tacheInitiale);
      suivre();
    }
  }, [tacheInitiale, suivre]);

  useEffect(() => arreter, []);

  const lancer = useCallback(async () => {
    try {
      const t = await appeler<Tache>("/api/py/actualiser", { method: "POST" });
      setTache(t);
      if (t.en_cours) suivre(t.debut);   // refusée (déjà en cours, non configurée) : rien à suivre
    } catch (e) {
      setTache({
        en_cours: false, etape: null, debut: null, fin: null,
        erreur: e instanceof Error ? e.message : "Impossible de lancer la mise à jour.",
      });
    }
  }, [suivre]);

  return { tache, lancer, fermer: () => setTache(null) };
}
