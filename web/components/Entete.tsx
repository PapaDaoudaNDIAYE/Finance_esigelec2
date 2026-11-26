"use client";

// Barre du haut : logo, état du marché, dernière mise à jour et bouton « Actualiser » (UC4, UC7).

import Link from "next/link";
import { useActualisation, type Etat } from "@/lib/api";
import { dateHeure } from "@/lib/format";

export default function Entete({ etat, quandActualise }: { etat: Etat | null; quandActualise: () => void }) {
  const { tache, lancer, fermer } = useActualisation(quandActualise, etat?.mise_a_jour);
  const enCours = !!tache?.en_cours;

  return (
    <>
      <header className="entete">
        <Link href="/" className="logo">
          <span className="logo-marque">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
              <path d="M4 17l5-5 4 3 7-8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="logo-texte">Conseiller<b>Bourse</b></span>
        </Link>

        <div className="entete-droite">
          {etat && (
            <span className={`marche ${etat.marche_ouvert ? "ouvert" : "ferme"}`}>
              <span className="marche-point" />
              {etat.marche_ouvert ? "Marché ouvert" : "Marché fermé"}
              <span className="marche-sep">Euronext Paris</span>
            </span>
          )}
          {etat && (
            <span className="maj muted">
              Données du {dateHeure(etat.derniere_mise_a_jour)}
            </span>
          )}
          <button className="btn btn-primaire" onClick={lancer} disabled={enCours}>
            <svg className={enCours ? "tourne" : ""} viewBox="0 0 24 24" width="16" height="16" aria-hidden>
              <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {enCours ? "Actualisation…" : "Actualiser"}
          </button>
        </div>
      </header>

      {tache && (
        <div className={`toast ${tache.erreur ? "toast-erreur" : tache.en_cours ? "" : "toast-ok"}`} role="status">
          {tache.en_cours && <span className="toast-barre" />}
          <div>
            <strong>
              {tache.erreur ? "Mise à jour impossible" : tache.en_cours ? "Mise à jour en cours" : "Données à jour"}
            </strong>
            <span>{tache.erreur ?? (tache.en_cours ? tache.etape : "Les conseils ont été recalculés.")}</span>
          </div>
          {!tache.en_cours && <button className="toast-fermer" onClick={fermer} aria-label="Fermer">×</button>}
        </div>
      )}
    </>
  );
}
