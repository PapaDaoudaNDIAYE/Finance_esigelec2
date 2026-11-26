"use client";

// UC1 — Page d'accueil : « Bonjour Monsieur Dupont » et la liste des 5 actions.

import Link from "next/link";
import Entete from "@/components/Entete";
import Pied from "@/components/Pied";
import { Avatar, EtatErreur, ScoreBar, SignalBadge, Sparkline, Squelette, Variation } from "@/components/ui";
import { useApi, type ActionResume, type Etat, type Portefeuille } from "@/lib/api";
import { classeSignal, dateCourte, dateDuJour, euros, note, pourcent } from "@/lib/format";

export default function Accueil() {
  const etat = useApi<Etat>("/api/etat");
  const actions = useApi<ActionResume[]>("/api/actions");
  const pf = useApi<Portefeuille>("/api/portefeuille");
  const toutRecharger = () => { etat.recharger(); actions.recharger(); pf.recharger(); };

  const liste = actions.data ?? [];
  const compte = (s: string) => liste.filter((a) => a.signal === s).length;
  const seuil = etat.data?.seuils.achat ?? 0.3;
  const client = etat.data?.client ?? "Monsieur Dupont";

  return (
    <>
      <Entete etat={etat.data} quandActualise={toutRecharger} />

      <section className="hero">
        <p className="hero-date">{dateDuJour()}</p>
        <h1>
          Bonjour, <em>{client}</em>
        </h1>
        <p className="hero-sous-titre">
          Voici l'analyse du jour de vos cinq actions : actualités, graphique, comptes de l'entreprise et risque,
          réunis en un conseil clair.
        </p>

        <div className="resume">
          <Link href="/portefeuille/" className="resume-carte lien-portefeuille">
            <span className="muted petit">Votre portefeuille →</span>
            <strong>{pf.data ? euros(pf.data.valeur_totale) : "–"}</strong>
            {pf.data && (
              <span className={`petit ${pf.data.gain > 0.005 ? "txt-buy" : pf.data.gain < -0.005 ? "txt-sell" : "muted"}`}>
                {pourcent(pf.data.performance)} depuis le départ
              </span>
            )}
          </Link>
          <div className="resume-carte buy">
            <span className="muted petit">À acheter</span>
            <strong>{actions.data ? compte("ACHETER") : "–"}</strong>
          </div>
          <div className="resume-carte sell">
            <span className="muted petit">À vendre</span>
            <strong>{actions.data ? compte("VENDRE") : "–"}</strong>
          </div>
          <div className="resume-carte hold">
            <span className="muted petit">À conserver</span>
            <strong>{actions.data ? compte("NE RIEN FAIRE") : "–"}</strong>
          </div>
        </div>
      </section>

      <section>
        <div className="titre-section">
          <h2>Vos actions</h2>
          <span className="muted petit">Euronext Paris · cliquez sur une action pour le détail</span>
        </div>

        {actions.erreur && !actions.data ? (
          <EtatErreur message={actions.erreur} onReessayer={toutRecharger} />
        ) : (
          <div className="grille-actions">
            {actions.chargement && !actions.data
              ? Array.from({ length: 5 }, (_, i) => <Squelette key={i} hauteur={248} />)
              : liste.map((a, i) => (
                  <Link key={a.ticker} href={`/action/${a.ticker}/`}
                    className={`card carte-action s-${classeSignal(a.signal)}`} style={{ animationDelay: `${i * 60}ms` }}>
                    <div className="carte-haut">
                      <Avatar nom={a.nom} signal={a.signal} />
                      <div className="carte-nom">
                        <h3>{a.nom}</h3>
                        <span className="muted petit">{a.ticker} · {a.secteur}</span>
                      </div>
                      <SignalBadge signal={a.signal} />
                    </div>

                    <div className="carte-prix">
                      <span className="prix">{euros(a.dernier)}</span>
                      <Variation valeur={a.variation} />
                    </div>

                    <Sparkline valeurs={a.sparkline} />

                    <div className="carte-bas">
                      <div className="carte-score">
                        <span className="muted petit">Score final</span>
                        <b className={`txt-${classeSignal(a.signal)}`}>{note(a.score_final)}</b>
                      </div>
                      <ScoreBar score={a.score_final} seuil={seuil} compacte />
                      <span className="muted petit carte-date">Clôture du {dateCourte(a.date)}</span>
                    </div>
                  </Link>
                ))}
          </div>
        )}
      </section>

      <section className="methode card">
        <div>
          <h2>Comment le conseil est construit</h2>
          <p className="muted">
            Quatre analyses notent chaque action de −1 à +1. Leur moyenne pondérée donne le score final :
            au-dessus de +0,3 nous conseillons d'acheter, sous −0,3 de vendre, sinon de ne rien faire.
          </p>
        </div>
        <div className="methode-poids">
          {[
            ["Information", "45 %", "Actualités des 7 derniers jours, lues par un LLM"],
            ["Technique", "30 %", "Moyennes mobiles, RSI, MACD, Bollinger, supports"],
            ["Financier", "15 %", "PER, croissance, marge, dette, dividende"],
            ["Risque", "10 %", "Volatilité et simulation de Monte-Carlo"],
          ].map(([nom, poids, detail]) => (
            <div key={nom} className="methode-ligne">
              <b>{poids}</b>
              <div><strong>{nom}</strong><span className="muted petit">{detail}</span></div>
            </div>
          ))}
          <p className="muted petit">Sans actualité récente : Technique 65 %, Financier 20 %, Risque 15 %.</p>
        </div>
      </section>

      <Pied />
    </>
  );
}
