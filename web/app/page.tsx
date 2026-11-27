"use client";

// Page d'accueil : « Bonjour Monsieur Dupont », choix du niveau d'investisseur, puis accès aux
// 5 actions (/actions/) et au portefeuille simulé (/portefeuille/).

import Link from "next/link";
import Entete from "@/components/Entete";
import Pied from "@/components/Pied";
import { SelecteurNiveau, useProfil } from "@/components/Profil";
import { Avatar, SignalBadge } from "@/components/ui";
import { useApi, type ActionResume, type Etat, type Portefeuille } from "@/lib/api";
import { dateDuJour, euros, pourcent } from "@/lib/format";

const majuscule = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

export default function Accueil() {
  const etat = useApi<Etat>("/api/etat");
  const actions = useApi<ActionResume[]>("/api/actions");
  const pf = useApi<Portefeuille>("/api/portefeuille");
  const { profil, regles } = useProfil();
  const toutRecharger = () => { etat.recharger(); actions.recharger(); pf.recharger(); };

  const client = etat.data?.client ?? "Monsieur Dupont";
  const niveauChoisi = !!profil?.niveau;
  const liste = actions.data ?? [];
  const compte = (s: string) => liste.filter((a) => a.signal === s).length;

  return (
    <>
      <Entete etat={etat.data} quandActualise={toutRecharger} />

      <section className="hero accueil-hero">
        <p className="hero-date">{majuscule(dateDuJour())}</p>
        <h1>
          Bonjour, <em>{client}</em>
        </h1>
        <p className="hero-sous-titre">
          Chaque jour, votre conseiller analyse cinq grandes actions de la Bourse de Paris et vous dit s'il faut
          les acheter, les vendre ou ne rien faire, raisons à l'appui.
        </p>
      </section>

      <section className="card etape">
        <div className="etape-titre">
          <span className={`etape-numero ${niveauChoisi ? "fait" : ""}`}>{niveauChoisi ? "✓" : "1"}</span>
          <div>
            <h2>Votre niveau d'investisseur</h2>
            <p className="muted">
              {regles
                ? <>Vous êtes en niveau <b>{regles.nom}</b>. Ses garde-fous s'appliquent à vos ordres ; vous pouvez en changer ici.</>
                : "Il fixe les garde-fous de votre portefeuille : certains ordres seront bloqués, d'autres demanderont une confirmation."}
            </p>
          </div>
        </div>
        {profil ? <SelecteurNiveau libelle="Continuer" quandChoisi={() => setTimeout(() => document.getElementById("decouvrir")?.scrollIntoView({ behavior: "smooth", block: "start" }), 150)} /> : <div className="squelette" style={{ height: 260 }} />}
      </section>

      <section id="decouvrir" className={`card etape etape-decouvrir ${niveauChoisi ? "" : "verrouillee"}`}>
        <div className="etape-titre">
          <span className="etape-numero">2</span>
          <div>
            <h2>Découvrir les actions</h2>
            <p className="muted">
              {actions.data
                ? `Aujourd'hui : ${compte("ACHETER")} à acheter, ${compte("VENDRE")} à vendre, ${compte("NE RIEN FAIRE")} à conserver.`
                : "Le conseil du jour pour chacune de vos cinq actions."}
            </p>
          </div>
        </div>

        <div className="apercu-actions">
          {liste.map((a) => (
            <div key={a.ticker} className="apercu-action">
              <Avatar nom={a.nom} signal={a.signal} taille={34} />
              <span className="apercu-nom"><b>{a.nom}</b><span className="muted petit">{euros(a.dernier)}</span></span>
              <SignalBadge signal={a.signal} />
            </div>
          ))}
        </div>

        <div className="etape-actions">
          {niveauChoisi ? (
            <>
              <Link href="/actions/" className="btn btn-primaire btn-grand">Découvrir les actions →</Link>
              <Link href="/portefeuille/" className="btn btn-ghost btn-grand">
                Mon portefeuille{pf.data && <span className="muted"> · {euros(pf.data.valeur_totale)} ({pourcent(pf.data.performance)})</span>}
              </Link>
            </>
          ) : (
            <>
              <span className="btn btn-primaire btn-grand desactive" aria-disabled="true">Découvrir les actions →</span>
              <span className="muted petit">Choisissez d'abord votre niveau ci-dessus.</span>
            </>
          )}
        </div>
      </section>

      <Pied />
    </>
  );
}
