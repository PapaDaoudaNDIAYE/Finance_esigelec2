"use client";

// Portefeuille simulé : acheter et vendre les 5 actions avec un capital virtuel.
// Les ordres sont exécutés par l'API (portefeuille.py) au dernier cours connu, pendant la séance.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Entete from "@/components/Entete";
import Pied from "@/components/Pied";
import { Avatar, EtatErreur, SignalBadge, Squelette } from "@/components/ui";
import {
  envoyerOrdre, reinitialiserPortefeuille, useApi,
  type ActionOrdre, type Etat, type Portefeuille, type Signal,
} from "@/lib/api";
import { classeSignal, dateCourte, euros, libelleSignal, nombre, pourcent } from "@/lib/format";

type Sens = "achat" | "vente";
type Message = { type: "ok" | "erreur"; titre: string; texte: string };

const signe = (x: number) => (x > 0 ? "+" : x < 0 ? "−" : "");
const eurosSigne = (x: number) => `${signe(x)}${euros(Math.abs(x))}`;
const classeGain = (x: number | null | undefined) => (x == null || Math.abs(x) < 0.005 ? "txt-none" : x > 0 ? "txt-buy" : "txt-sell");
const heure = (iso: string) => new Date(iso.replace(" ", "T")).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

export default function PagePortefeuille() {
  const etat = useApi<Etat>("/api/etat");
  const pf = useApi<Portefeuille>("/api/portefeuille");
  const [ticker, setTicker] = useState("");
  const [sens, setSens] = useState<Sens>("achat");
  const [message, setMessage] = useState<Message | null>(null);
  const toutRecharger = () => { etat.recharger(); pf.recharger(); };

  // Arrivée depuis une page action : /portefeuille/?action=AI.PA&sens=vente
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (p.get("action")) setTicker(p.get("action")!.toUpperCase());
    if (p.get("sens") === "vente") setSens("vente");
  }, []);

  const d = pf.data;
  const choisir = (t: string, s: Sens) => {
    setTicker(t); setSens(s);
    document.getElementById("ordre")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const reinitialiser = async () => {
    if (!window.confirm("Effacer tous les ordres et repartir du capital de départ ?")) return;
    try {
      pf.remplacer(await reinitialiserPortefeuille());
      setMessage({ type: "ok", titre: "Portefeuille réinitialisé", texte: "Vous repartez du capital de départ." });
    } catch (e) {
      setMessage({ type: "erreur", titre: "Réinitialisation impossible", texte: e instanceof Error ? e.message : "" });
    }
  };

  return (
    <>
      <Entete etat={etat.data} quandActualise={toutRecharger} />

      <section className="hero hero-compact">
        <p className="hero-date">Portefeuille simulé · argent virtuel</p>
        <h1>Votre <em>portefeuille</em></h1>
        <p className="hero-sous-titre">
          Achetez et vendez vos cinq actions avec un capital virtuel de {d ? euros(d.capital_depart).replace(",00", "") : "500 000 €"}.
          Les ordres sont exécutés au dernier cours connu, pendant la séance d'Euronext Paris.
        </p>

        <div className="resume">
          <div className="resume-carte">
            <span className="muted petit">Valeur totale</span>
            <strong>{d ? euros(d.valeur_totale) : "–"}</strong>
            {d && <span className={`petit ${classeGain(d.gain)}`}>{eurosSigne(d.gain)} · {pourcent(d.performance)}</span>}
          </div>
          <div className="resume-carte cash">
            <span className="muted petit">Liquidités</span>
            <strong>{d ? euros(d.liquidites) : "–"}</strong>
            {d && <span className="muted petit">{pourcent(d.valeur_totale ? d.liquidites / d.valeur_totale : null, 1, false)} du portefeuille</span>}
          </div>
          <div className="resume-carte">
            <span className="muted petit">Investi en actions</span>
            <strong>{d ? euros(d.valeur_titres) : "–"}</strong>
            {d && <span className="muted petit">{d.positions.length} ligne{d.positions.length > 1 ? "s" : ""}</span>}
          </div>
          <div className={`resume-carte ${d && d.plus_value_latente + d.plus_value_realisee < 0 ? "sell" : "buy"}`}>
            <span className="muted petit">Plus-values</span>
            <strong className={d ? classeGain(d.plus_value_latente + d.plus_value_realisee) : ""}>
              {d ? eurosSigne(d.plus_value_latente + d.plus_value_realisee) : "–"}
            </strong>
            {d && <span className="muted petit">latentes {eurosSigne(d.plus_value_latente)} · réalisées {eurosSigne(d.plus_value_realisee)}</span>}
          </div>
        </div>
      </section>

      {pf.erreur && !d ? (
        <EtatErreur message={pf.erreur} onReessayer={toutRecharger} />
      ) : !d ? (
        <div className="grille-portefeuille"><Squelette hauteur={360} /><Squelette hauteur={520} /></div>
      ) : (
        <>
          <div className="grille-portefeuille">
            <section className="card">
              <div className="carte-titre">
                <h2>Vos positions</h2>
                <span className="muted petit">valorisées au dernier cours connu</span>
              </div>
              {d.positions.length === 0 ? (
                <div className="vide-portefeuille">
                  <p>Vous ne détenez encore aucune action.</p>
                  <p className="muted petit">Choisissez une action dans le panneau « Passer un ordre » pour commencer.</p>
                </div>
              ) : (
                <div className="tableau-defile">
                  <table className="tableau">
                    <thead>
                      <tr>
                        <th>Action</th><th className="nb">Quantité</th><th className="nb">Cours</th>
                        <th className="nb">Valeur</th><th className="nb">Plus-value</th><th />
                      </tr>
                    </thead>
                    <tbody>
                      {d.positions.map((p) => (
                        <tr key={p.ticker}>
                          <td>
                            <Link href={`/action/${p.ticker}/`} className="cellule-action">
                              <Avatar nom={p.nom} signal={p.signal} taille={32} />
                              <span>
                                <b>{p.nom}</b>
                                <span className={`conseil-mini txt-${classeSignal(p.signal)}`}>Conseil : {libelleSignal(p.signal).toLowerCase()}</span>
                              </span>
                            </Link>
                          </td>
                          <td className="nb">{nombre(p.quantite, 0)}<span className="sous-valeur">{pourcent(p.poids, 1, false)} du total</span></td>
                          <td className="nb">{euros(p.cours)}<span className="sous-valeur">revient {euros(p.pru)}</span></td>
                          <td className="nb"><b>{euros(p.valeur)}</b></td>
                          <td className={`nb ${classeGain(p.plus_value)}`}>
                            {eurosSigne(p.plus_value)}<span className="petit bloc">{pourcent(p.plus_value_pct)}</span>
                          </td>
                          <td>
                            <div className="boutons-ligne">
                              <button className="btn-mini buy" onClick={() => choisir(p.ticker, "achat")}>Acheter</button>
                              <button className="btn-mini sell" onClick={() => choisir(p.ticker, "vente")}>Vendre</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <PanneauOrdre
              p={d} ticker={ticker} setTicker={setTicker} sens={sens} setSens={setSens}
              quandExecute={(nouveau, texte) => {
                pf.remplacer(nouveau);
                setMessage({ type: "ok", titre: "Ordre exécuté", texte });
              }}
              quandRefuse={(texte) => setMessage({ type: "erreur", titre: "Ordre refusé", texte })}
            />
          </div>

          <section className="card">
            <div className="carte-titre">
              <h2>Historique des ordres</h2>
              <span className="muted petit">frais de courtage {pourcent(d.frais_ordre, 1, false)} · {nombre(d.frais_payes, 2)} € payés au total</span>
            </div>
            {d.ordres.length === 0 ? (
              <p className="muted vide">Aucun ordre pour le moment.</p>
            ) : (
              <div className="tableau-defile">
                <table className="tableau">
                  <thead>
                    <tr>
                      <th>Date</th><th>Ordre</th><th>Action</th><th className="nb">Quantité</th>
                      <th className="nb">Prix</th><th className="nb">Frais</th><th className="nb">Montant</th><th>Conseil du moment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.ordres.map((o) => (
                      <tr key={o.id}>
                        <td className="muted">{dateCourte(o.date)} · {heure(o.date)}</td>
                        <td><span className={`sens sens-${o.sens === "ACHAT" ? "buy" : "sell"}`}>{o.sens === "ACHAT" ? "Achat" : "Vente"}</span></td>
                        <td>{o.nom}</td>
                        <td className="nb">{nombre(o.quantite, 0)}</td>
                        <td className="nb">{euros(o.prix)}</td>
                        <td className="nb muted">{euros(o.frais)}</td>
                        <td className="nb"><b>{euros(o.montant)}</b></td>
                        <td>
                          <span className={`txt-${classeSignal(o.signal)} petit`}>
                            {libelleSignal(o.signal)}
                            {o.signal && (conforme(o.sens, o.signal) ? " · suivi" : contraire(o.sens, o.signal) ? " · contraire" : "")}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="pied-carte">
              <button className="btn btn-ghost btn-petit" onClick={reinitialiser}>Réinitialiser le portefeuille</button>
            </div>
          </section>
        </>
      )}

      {message && (
        <div className={`toast ${message.type === "ok" ? "toast-ok" : "toast-erreur"}`} role="status">
          <div><strong>{message.titre}</strong><span>{message.texte}</span></div>
          <button className="toast-fermer" onClick={() => setMessage(null)} aria-label="Fermer">×</button>
        </div>
      )}

      <Pied />
    </>
  );
}

/** L'ordre va-t-il à l'encontre du conseil ? (acheter quand on conseille de vendre, et inversement) */
function contraire(sens: "ACHAT" | "VENTE", signal: Signal) {
  return (sens === "ACHAT" && signal === "VENDRE") || (sens === "VENTE" && signal === "ACHETER");
}

/** Le client a-t-il suivi le conseil ? (acheter quand on conseille d'acheter, vendre quand on conseille de vendre) */
function conforme(sens: "ACHAT" | "VENTE", signal: Signal) {
  return (sens === "ACHAT" && signal === "ACHETER") || (sens === "VENTE" && signal === "VENDRE");
}

function PanneauOrdre({
  p, ticker, setTicker, sens, setSens, quandExecute, quandRefuse,
}: {
  p: Portefeuille;
  ticker: string;
  setTicker: (t: string) => void;
  sens: Sens;
  setSens: (s: Sens) => void;
  quandExecute: (p: Portefeuille, texte: string) => void;
  quandRefuse: (texte: string) => void;
}) {
  const [quantite, setQuantite] = useState(1);
  const [envoi, setEnvoi] = useState(false);
  const action: ActionOrdre | undefined = p.actions.find((a) => a.ticker === ticker);
  const prix = action?.prix ?? null;

  const montant = prix != null ? quantite * prix : null;
  const frais = montant != null ? Math.round(montant * p.frais_ordre * 100) / 100 : null;
  const total = montant != null && frais != null ? (sens === "achat" ? montant + frais : montant - frais) : null;
  const max = useMemo(() => {
    if (!action || prix == null) return 0;
    if (sens === "vente") return action.detenues;
    return Math.max(0, Math.floor(p.liquidites / (prix * (1 + p.frais_ordre))));
  }, [action, prix, sens, p.liquidites, p.frais_ordre]);

  const probleme =
    !action ? "Choisissez une action."
    : prix == null ? "Cours indisponible pour le moment."
    : !p.marche_ouvert ? "Marché fermé : les ordres sont acceptés de 9 h à 17 h 30, du lundi au vendredi."
    : sens === "vente" && action.detenues === 0 ? `Vous ne détenez aucune action ${action.nom}.`
    : quantite < 1 ? "Indiquez une quantité."
    : quantite > max ? (sens === "achat" ? `Liquidités insuffisantes : ${max} action${max > 1 ? "s" : ""} au maximum.` : `Vous ne détenez que ${max} action${max > 1 ? "s" : ""}.`)
    : null;

  const conseilContraire = action?.signal && (
    (sens === "achat" && action.signal === "VENDRE") || (sens === "vente" && action.signal === "ACHETER"));
  const conseilSuivi = action?.signal && (
    (sens === "achat" && action.signal === "ACHETER") || (sens === "vente" && action.signal === "VENDRE"));

  const valider = async () => {
    if (!action || probleme) return;
    setEnvoi(true);
    try {
      const r = await envoyerOrdre(action.ticker, sens, quantite);
      const o = r.ordre;
      quandExecute(r.portefeuille,
        `${o.sens === "ACHAT" ? "Achat" : "Vente"} de ${nombre(o.quantite, 0)} ${o.nom} à ${euros(o.prix)} (frais ${euros(o.frais)}).`);
      setQuantite(1);
    } catch (e) {
      quandRefuse(e instanceof Error ? e.message : "Erreur inconnue.");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <section className={`card panneau-ordre ${sens === "achat" ? "s-buy" : "s-sell"}`} id="ordre">
      <div className="carte-titre">
        <h2>Passer un ordre</h2>
        <span className={`marche ${p.marche_ouvert ? "ouvert" : "ferme"}`}>
          <span className="marche-point" />{p.marche_ouvert ? "Marché ouvert" : "Marché fermé"}
        </span>
      </div>

      <div className="choix-sens" role="tablist">
        <button role="tab" aria-selected={sens === "achat"} className={sens === "achat" ? "actif buy" : ""} onClick={() => setSens("achat")}>Acheter</button>
        <button role="tab" aria-selected={sens === "vente"} className={sens === "vente" ? "actif sell" : ""} onClick={() => setSens("vente")}>Vendre</button>
      </div>

      <div className="choix-actions">
        {p.actions.map((a) => (
          <button key={a.ticker} className={`choix-action ${a.ticker === ticker ? "actif" : ""}`} onClick={() => setTicker(a.ticker)}>
            <Avatar nom={a.nom} signal={a.signal} taille={30} />
            <span className="choix-nom"><b>{a.nom}</b><span className="muted petit">{a.detenues ? `${a.detenues} détenue${a.detenues > 1 ? "s" : ""}` : a.ticker}</span></span>
            <span className="choix-prix">{euros(a.prix)}</span>
          </button>
        ))}
      </div>

      <label className="champ">
        <span className="muted petit">Quantité</span>
        <div className="quantite">
          <button onClick={() => setQuantite((q) => Math.max(1, q - 1))} aria-label="Moins">−</button>
          <input type="number" min={1} step={1} inputMode="numeric" value={quantite}
            onChange={(e) => setQuantite(Math.max(0, Math.floor(Number(e.target.value) || 0)))} />
          <button onClick={() => setQuantite((q) => q + 1)} aria-label="Plus">+</button>
          <button className="quantite-max" onClick={() => max > 0 && setQuantite(max)} disabled={!max}>Max {max ? nombre(max, 0) : ""}</button>
        </div>
      </label>

      <dl className="recap">
        <div><dt>Cours</dt><dd>{euros(prix)}{action?.date && <span className="muted petit"> · {dateCourte(action.date)}</span>}</dd></div>
        <div><dt>Montant</dt><dd>{euros(montant)}</dd></div>
        <div><dt>Frais ({pourcent(p.frais_ordre, 1, false)})</dt><dd>{euros(frais)}</dd></div>
        <div className="recap-total"><dt>{sens === "achat" ? "Total à payer" : "Vous recevez"}</dt><dd>{euros(total)}</dd></div>
        <div><dt>Liquidités après l'ordre</dt><dd>{total != null ? euros(p.liquidites + (sens === "achat" ? -total : total)) : "—"}</dd></div>
      </dl>

      {action?.signal && (
        <div className={`avis ${conseilContraire ? "avis-contraire" : conseilSuivi ? "avis-suivi" : ""}`}>
          <span className="muted petit">Notre conseil pour {action.nom}</span>
          <SignalBadge signal={action.signal} />
          {conseilContraire && <p>Cet ordre va à l'encontre de notre analyse. Vous restez libre de le passer.</p>}
          {conseilSuivi && <p>Cet ordre suit notre analyse.</p>}
        </div>
      )}

      <button className={`btn btn-ordre ${sens === "achat" ? "buy" : "sell"}`} onClick={valider} disabled={!!probleme || envoi}>
        {envoi ? "Envoi…" : action ? `${sens === "achat" ? "Acheter" : "Vendre"} ${nombre(quantite, 0)} ${action.nom}` : sens === "achat" ? "Acheter" : "Vendre"}
      </button>
      {probleme && <p className="muted petit probleme">{probleme}</p>}
      <p className="muted petit">Simulation : aucun ordre réel n'est transmis à un courtier.</p>
    </section>
  );
}
