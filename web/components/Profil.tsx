"use client";

// Niveau d'investisseur (débutant, moyen, professionnel), demandé à l'entrée de l'application.
// Il fixe les garde-fous du portefeuille simulé ; les règles elles-mêmes viennent de l'API
// (portefeuille.py / config.py), qui les applique aussi de son côté.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  appeler, enregistrerNiveau, type CodeNiveau, type Profil, type RegleNiveau,
} from "@/lib/api";
import { euros } from "@/lib/format";

interface ContexteProfil {
  profil: Profil | null;
  regles: RegleNiveau | null;
  ouvrirChoix: () => void;
}

const Contexte = createContext<ContexteProfil>({ profil: null, regles: null, ouvrirChoix: () => {} });
export const useProfil = () => useContext(Contexte);

const ORDRE: CodeNiveau[] = ["debutant", "moyen", "professionnel"];
const ACCROCHE: Record<CodeNiveau, string> = {
  debutant: "Je découvre la Bourse",
  moyen: "J'ai déjà investi",
  professionnel: "J'investis régulièrement",
};
const montantRond = (x: number) => euros(x).replace(",00", "");
const pct = (x: number) => `${Math.round(x * 100)} %`;

/** Les règles d'un niveau, en phrases courtes. */
export function phrasesRegles(r: RegleNiveau): { texte: string; type: "bloque" | "alerte" | "libre" }[] {
  return [
    r.montant_max != null
      ? { texte: `Achats limités à ${montantRond(r.montant_max)} par ordre`, type: "bloque" }
      : { texte: "Aucune limite de montant", type: "libre" },
    r.montant_alerte != null
      ? { texte: `Avertissement dès ${montantRond(r.montant_alerte)}`, type: "alerte" }
      : { texte: "Pas d'avertissement de montant", type: "libre" },
    r.part_max != null
      ? { texte: `Une action : ${pct(r.part_max)} du portefeuille au plus`, type: "bloque" }
      : { texte: `Concentration libre (avertissement au-delà de ${pct(r.part_alerte ?? 1)})`, type: "libre" },
    r.achat_contre_conseil === "interdit"
      ? { texte: "Achat interdit quand nous conseillons de vendre", type: "bloque" }
      : r.achat_contre_conseil === "alerte"
        ? { texte: "Avertissement si vous allez contre notre conseil", type: "alerte" }
        : { texte: "Nos conseils restent indicatifs", type: "libre" },
  ];
}

export function ProfilProvider({ children }: { children: React.ReactNode }) {
  const [profil, setProfil] = useState<Profil | null>(null);
  const [ouvert, setOuvert] = useState(false);

  const charger = useCallback(async () => {
    try {
      setProfil(await appeler<Profil>("/api/profil"));
    } catch {
      /* API indisponible : les pages affichent déjà leur propre message d'erreur */
    }
  }, []);
  useEffect(() => { charger(); }, [charger]);

  const premiereVisite = profil != null && profil.niveau == null;
  const visible = premiereVisite || ouvert;

  // Pas de défilement de la page derrière la fenêtre de choix.
  useEffect(() => {
    document.body.style.overflow = visible ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [visible]);

  const regles = profil?.niveau ? profil.niveaux[profil.niveau] : null;
  return (
    <Contexte.Provider value={{ profil, regles, ouvrirChoix: () => setOuvert(true) }}>
      {children}
      {visible && profil && (
        <ChoixNiveau
          profil={profil}
          premiereVisite={premiereVisite}
          fermer={() => setOuvert(false)}
          quandChoisi={(p) => { setProfil(p); setOuvert(false); }}
        />
      )}
    </Contexte.Provider>
  );
}

function ChoixNiveau({
  profil, premiereVisite, fermer, quandChoisi,
}: {
  profil: Profil;
  premiereVisite: boolean;
  fermer: () => void;
  quandChoisi: (p: Profil) => void;
}) {
  const [choix, setChoix] = useState<CodeNiveau | null>(profil.niveau);
  const [risques, setRisques] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const valider = async () => {
    if (!choix) return;
    setEnvoi(true); setErreur(null);
    try {
      quandChoisi(await enregistrerNiveau(choix, risques));
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Enregistrement impossible.");
    } finally {
      setEnvoi(false);
    }
  };

  const bloque = !choix || (choix === "professionnel" && !risques) || envoi;

  return (
    <div className="voile" role="dialog" aria-modal="true" aria-labelledby="titre-niveau">
      <div className="fenetre-niveau">
        {!premiereVisite && <button className="toast-fermer fermer-fenetre" onClick={fermer} aria-label="Fermer">×</button>}
        <p className="surtitre">{premiereVisite ? "Bienvenue" : "Votre profil"}</p>
        <h2 id="titre-niveau">Quel investisseur <em>êtes-vous ?</em></h2>
        <p className="muted">
          Votre niveau fixe les garde-fous de votre portefeuille : certains ordres seront bloqués, d'autres
          demanderont une confirmation. Vous pourrez le changer à tout moment.
        </p>

        <div className="niveaux">
          {ORDRE.map((code, i) => {
            const r = profil.niveaux[code];
            return (
              <button key={code} className={`niveau niveau-${code} ${choix === code ? "actif" : ""}`}
                onClick={() => setChoix(code)} aria-pressed={choix === code}>
                <span className="niveau-haut">
                  <span className="niveau-jauge" aria-hidden>
                    {[0, 1, 2].map((b) => <span key={b} className={b <= i ? "plein" : ""} />)}
                  </span>
                  {profil.niveau === code && <span className="niveau-actuel">actuel</span>}
                </span>
                <b>{r.nom}</b>
                <span className="muted petit">{ACCROCHE[code]}</span>
                <ul>
                  {phrasesRegles(r).map((p) => <li key={p.texte} className={`regle-${p.type}`}>{p.texte}</li>)}
                </ul>
              </button>
            );
          })}
        </div>

        {choix === "professionnel" && (
          <label className="case-risques">
            <input type="checkbox" checked={risques} onChange={(e) => setRisques(e.target.checked)} />
            <span>
              Je comprends que le niveau Professionnel lève la plupart des garde-fous et que je peux perdre
              une grande partie de mon capital.
            </span>
          </label>
        )}
        {erreur && <p className="txt-sell petit">{erreur}</p>}

        <div className="fenetre-actions">
          <p className="muted petit">Portefeuille simulé : aucun argent réel n'est engagé.</p>
          <button className="btn btn-primaire" onClick={valider} disabled={bloque}>
            {envoi ? "Enregistrement…" : choix ? `Continuer en ${profil.niveaux[choix].nom}` : "Choisissez un niveau"}
          </button>
        </div>
      </div>
    </div>
  );
}
