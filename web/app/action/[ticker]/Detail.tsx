"use client";

// UC2, UC3, UC6, UC7 — Page détail d'une action : cours, graphique, conseil et ses raisons,
// notes des 4 modules, indicateurs techniques, chiffres clés et actualités.

import Link from "next/link";
import { useParams } from "next/navigation";
import Entete from "@/components/Entete";
import Graphique from "@/components/Graphique";
import Pied from "@/components/Pied";
import {
  Avatar, BarreNote, EtatErreur, IconeModule, Jauge, SignalBadge, Squelette, Variation,
} from "@/components/ui";
import { useApi, type ActionDetail, type Etat, type Module } from "@/lib/api";
import { classeSignal, dateCourte, euros, ilYa, nombre, note, pourcent } from "@/lib/format";

const MODULES: { cle: Module; nom: string; methode: string }[] = [
  { cle: "information", nom: "Information", methode: "Actualités des 7 derniers jours notées par un LLM" },
  { cle: "technique", nom: "Technique", methode: "Moyennes mobiles, RSI, MACD, Bollinger, supports" },
  { cle: "financier", nom: "Financier", methode: "PER, croissance, marge, dette, dividende" },
  { cle: "risque", nom: "Risque", methode: "Volatilité sur un an et simulation de Monte-Carlo" },
];

const FAMILLES: Record<string, string> = {
  tendance: "Tendance (MM20 · MM50 · MM200)",
  rsi: "RSI 14 jours",
  macd: "MACD 12/26/9",
  bollinger: "Bandes de Bollinger",
  niveaux: "Supports et résistances",
};

const LETTRES = ["A", "B", "C", "D", "E", "F"];

export default function PageAction() {
  const { ticker } = useParams<{ ticker: string }>();
  const code = decodeURIComponent(ticker);
  const etat = useApi<Etat>("/api/etat");
  const detail = useApi<ActionDetail>(`/api/actions/${encodeURIComponent(code)}`);
  const toutRecharger = () => { etat.recharger(); detail.recharger(); };
  const a = detail.data;
  const seuils = etat.data?.seuils ?? { achat: 0.3, vente: -0.3 };

  return (
    <>
      <Entete etat={etat.data} quandActualise={toutRecharger} />

      <Link href="/" className="retour">← Toutes les actions</Link>

      {detail.erreur && !a ? (
        <EtatErreur message={detail.erreur} onReessayer={toutRecharger} />
      ) : !a ? (
        <div className="grille-detail">
          <Squelette hauteur={560} />
          <Squelette hauteur={560} />
        </div>
      ) : (
        <>
          {/* ---------------------------------------------------------- en-tête de l'action */}
          <section className="action-entete">
            <div className="action-identite">
              <Avatar nom={a.nom} signal={a.conseil?.signal} taille={60} />
              <div>
                <h1>{a.nom}</h1>
                <span className="muted">{a.ticker} · {a.secteur} · Euronext Paris</span>
              </div>
            </div>
            <div className="action-cours">
              <span className="prix-grand">{euros(a.dernier)}</span>
              <Variation valeur={a.variation} />
              <span className={`marche-texte ${a.marche_ouvert ? "ouvert" : "ferme"}`}>{a.etat_marche}</span>
            </div>
          </section>

          {/* UC6 : une source n'a pas répondu lors de la dernière mise à jour */}
          {a.sources.some((s) => s.statut === "erreur") && (
            <div className="alerte">
              <b>Certaines données n'ont pas pu être mises à jour.</b>
              <ul>
                {a.sources.filter((s) => s.statut === "erreur").map((s) => (
                  <li key={s.source}>{s.message} — les dernières données connues sont utilisées.</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grille-detail">
            {/* ---------------------------------------------------------- graphique */}
            <div className="card carte-graphique">
              <div className="carte-titre">
                <h2>Cours et analyse technique</h2>
                <span className="muted petit">1 an d'historique · {a.historique.length} séances</span>
              </div>
              {a.historique.length > 0 ? (
                <Graphique historique={a.historique} support={a.indicateurs.support} resistance={a.indicateurs.resistance} />
              ) : (
                <p className="muted vide">Aucun cours disponible pour le moment.</p>
              )}
            </div>

            {/* ---------------------------------------------------------- conseil (UC3) */}
            <aside className={`card carte-conseil s-${classeSignal(a.conseil?.signal)}`}>
              <span className="surtitre">Notre conseil aujourd'hui</span>
              {a.conseil ? (
                <>
                  <div className={`conseil-mot txt-${classeSignal(a.conseil.signal)}`}>
                    {a.conseil.signal === "NE RIEN FAIRE" ? "Ne rien faire" : a.conseil.signal === "ACHETER" ? "Acheter" : "Vendre"}
                  </div>
                  <div className="conseil-jauge">
                    <Jauge score={a.conseil.score_final} seuilAchat={seuils.achat} seuilVente={seuils.vente} />
                    <div className="conseil-score">
                      <b>{note(a.conseil.score_final)}</b>
                      <span className="muted petit">score final</span>
                    </div>
                  </div>
                  <div className="conseil-zones petit">
                    <span className="txt-sell">Vendre &lt; {nombre(seuils.vente, 1)}</span>
                    <span className="txt-hold">Ne rien faire</span>
                    <span className="txt-buy">Acheter &gt; +{nombre(seuils.achat, 1)}</span>
                  </div>

                  <h3 className="raisons-titre">Pour les raisons suivantes</h3>
                  <ol className="raisons">
                    {a.conseil.raisons.map((r, i) => (
                      <li key={i}><span className="lettre">{LETTRES[i]}</span><span>{r.charAt(0).toUpperCase() + r.slice(1)}</span></li>
                    ))}
                  </ol>
                  <p className="conseil-phrase">
                    « Nous vous conseillons de <b>{a.conseil.signal === "ACHETER" ? "ACHETER" : a.conseil.signal === "VENDRE" ? "VENDRE" : "NE RIEN FAIRE"}</b> aujourd'hui, {etat.data?.client ?? "Monsieur Dupont"}. »
                  </p>
                  <span className="muted petit">Calculé le {dateCourte(a.conseil.date)}</span>
                </>
              ) : (
                <p className="muted">Les analyses n'ont pas encore été calculées. Cliquez sur « Actualiser ».</p>
              )}
            </aside>
          </div>

          {/* ---------------------------------------------------------- les 4 modules */}
          <section>
            <div className="titre-section">
              <h2>Le détail des quatre analyses</h2>
              <span className="muted petit">Chaque analyse note l'action de −1 (très négatif) à +1 (très positif)</span>
            </div>
            <div className="grille-modules">
              {MODULES.map((m) => {
                const n = a.scores[m.cle];
                const poids = a.conseil?.poids[m.cle] ?? 0;
                const dispo = !!n?.disponible && n.score != null;
                return (
                  <div key={m.cle} className={`card carte-module ${dispo ? "" : "indispo"}`}>
                    <div className="module-haut">
                      <span className="module-icone"><IconeModule module={m.cle} /></span>
                      <div>
                        <h3>{m.nom}</h3>
                        <span className="muted petit">{m.methode}</span>
                      </div>
                      <span className="module-poids" title="Poids dans le conseil">{Math.round(poids * 100)} %</span>
                    </div>
                    <div className="module-note">
                      <b className={dispo ? (n!.score! > 0.1 ? "txt-buy" : n!.score! < -0.1 ? "txt-sell" : "txt-hold") : "muted"}>
                        {dispo ? note(n!.score) : "Indisponible"}
                      </b>
                      <BarreNote valeur={dispo ? n!.score : null} />
                    </div>
                    <ul className="module-raisons">
                      {(n?.raisons ?? ["module pas encore calculé"]).map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="grille-deux">
            {/* ---------------------------------------------------------- familles techniques */}
            <section className="card">
              <div className="carte-titre">
                <h2>Indicateurs techniques</h2>
                <span className="muted petit">Note de chaque famille</span>
              </div>
              <div className="familles">
                {Object.entries(FAMILLES).map(([cle, nom]) => {
                  const f = a.familles_techniques[cle];
                  return (
                    <div key={cle} className="famille">
                      <div className="famille-haut">
                        <strong>{nom}</strong>
                        <b className={!f ? "muted" : f.note > 0.1 ? "txt-buy" : f.note < -0.1 ? "txt-sell" : "txt-hold"}>{f ? note(f.note) : "—"}</b>
                      </div>
                      <BarreNote valeur={f?.note ?? null} />
                      <span className="muted petit">{f ? f.raison : "historique insuffisant"}</span>
                    </div>
                  );
                })}
              </div>
              <div className="tuiles tuiles-4">
                <Tuile titre="RSI 14" valeur={nombre(a.indicateurs.rsi, 0)} aide={a.indicateurs.rsi == null ? "" : a.indicateurs.rsi < 30 ? "survente" : a.indicateurs.rsi > 70 ? "surachat" : "zone neutre"} />
                <Tuile titre="MACD" valeur={nombre(a.indicateurs.macd, 2)} aide={`signal ${nombre(a.indicateurs.macd_signal, 2)}`} />
                <Tuile titre="Support 60 j" valeur={euros(a.indicateurs.support)} aide="plus bas récent" />
                <Tuile titre="Résistance 60 j" valeur={euros(a.indicateurs.resistance)} aide="plus haut récent" />
              </div>
            </section>

            {/* ---------------------------------------------------------- fondamentaux */}
            <section className="card">
              <div className="carte-titre">
                <h2>Chiffres clés de l'entreprise</h2>
                <span className="muted petit">{a.fondamentaux ? `Relevés le ${dateCourte(a.fondamentaux.date)}` : "Indisponibles"}</span>
              </div>
              {a.fondamentaux ? (
                <div className="tuiles">
                  <Tuile titre="PER" valeur={nombre(a.fondamentaux.per, 1)} aide="cours / bénéfice par action" />
                  <Tuile titre="Croissance du CA" valeur={pourcent(a.fondamentaux.croissance, 1)} aide="sur un an" ton={signe(a.fondamentaux.croissance)} />
                  <Tuile titre="Marge nette" valeur={pourcent(a.fondamentaux.marge, 1, false)} aide="résultat / chiffre d'affaires" />
                  <Tuile titre="Dette nette / EBITDA" valeur={a.fondamentaux.dette == null ? "—" : `${nombre(a.fondamentaux.dette, 1)} ans`} aide="années de résultat pour rembourser" />
                  <Tuile titre="Dividende" valeur={pourcent(a.fondamentaux.dividende, 2, false)} aide="rendement annuel" />
                </div>
              ) : (
                <p className="muted vide">Les chiffres financiers n'ont pas pu être récupérés.</p>
              )}
            </section>
          </div>

          {/* ---------------------------------------------------------- actualités */}
          <section className="card">
            <div className="carte-titre">
              <h2>Actualités des 7 derniers jours</h2>
              <span className="muted petit">{a.actualites.length} article{a.actualites.length > 1 ? "s" : ""} · sentiment noté de −1 à +1</span>
            </div>
            {a.actualites.length === 0 ? (
              <p className="muted vide">
                Aucune actualité récente : le conseil s'appuie principalement sur l'analyse technique.
              </p>
            ) : (
              <ul className="actus">
                {a.actualites.map((n) => {
                  const s = n.score_sentiment;
                  const ton = s == null ? "none" : s > 0.15 ? "buy" : s < -0.15 ? "sell" : "hold";
                  return (
                    <li key={n.lien}>
                      <a href={n.lien} target="_blank" rel="noopener noreferrer" className="actu">
                        <span className={`sentiment sentiment-${ton}`}>{s == null ? "—" : note(s)}</span>
                        <div>
                          <span className="actu-titre">{n.titre}</span>
                          <span className="muted petit">{n.source ?? "Source inconnue"} · {ilYa(n.date)}</span>
                        </div>
                        <span className="actu-fleche" aria-hidden>↗</span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}

      <Pied />
    </>
  );
}

function signe(x: number | null) {
  return x == null ? undefined : x > 0 ? "buy" : x < 0 ? "sell" : undefined;
}

function Tuile({ titre, valeur, aide, ton }: { titre: string; valeur: string; aide?: string; ton?: "buy" | "sell" }) {
  return (
    <div className="tuile">
      <span className="muted petit">{titre}</span>
      <b className={ton ? `txt-${ton}` : ""}>{valeur}</b>
      {aide && <span className="tuile-aide">{aide}</span>}
    </div>
  );
}
