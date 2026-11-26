// Mise en forme à la française des nombres et des dates.

import type { Signal } from "./api";

const fmtEuros = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const fmtNombre = (d: number) =>
  new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

export const euros = (x: number | null | undefined) => (x == null ? "—" : fmtEuros.format(x));
export const nombre = (x: number | null | undefined, d = 1) => (x == null ? "—" : fmtNombre(d).format(x));

/** 0.0123 -> « +1,23 % » */
export const pourcent = (x: number | null | undefined, d = 2, signe = true) =>
  x == null ? "—" : `${signe && x > 0 ? "+" : ""}${fmtNombre(d).format(x * 100)} %`;

/** -0.35 -> « −0,35 » ; 0.274 -> « +0,27 » */
export const note = (x: number | null | undefined) =>
  x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${fmtNombre(2).format(Math.abs(x))}`;

/** « 2026-11-25 » -> « 25 nov. 2026 » */
export function dateCourte(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso.replace(" ", "T"));
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

/** « 2026-11-26 00:45 » -> « aujourd'hui à 00:45 », « hier à 17:40 », « 24 nov. à 09:10 » */
export function dateHeure(iso: string | null | undefined) {
  if (!iso) return "jamais";
  const d = new Date(iso.replace(" ", "T"));
  const jour = new Date(d); jour.setHours(0, 0, 0, 0);
  const auj = new Date(); auj.setHours(0, 0, 0, 0);
  const ecart = Math.round((auj.getTime() - jour.getTime()) / 864e5);
  const heure = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (ecart === 0) return `aujourd'hui à ${heure}`;
  if (ecart === 1) return `hier à ${heure}`;
  return `${d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })} à ${heure}`;
}

/** Il y a combien de temps ? « il y a 3 h », « il y a 2 j » */
export function ilYa(iso: string) {
  const minutes = Math.max(0, (Date.now() - new Date(iso.replace(" ", "T")).getTime()) / 6e4);
  if (minutes < 60) return `il y a ${Math.round(minutes)} min`;
  if (minutes < 60 * 24) return `il y a ${Math.round(minutes / 60)} h`;
  return `il y a ${Math.round(minutes / 1440)} j`;
}

export const dateDuJour = () =>
  new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

/** Classe CSS d'un signal : buy / sell / hold / none */
export function classeSignal(s: Signal | null | undefined) {
  if (s === "ACHETER") return "buy";
  if (s === "VENDRE") return "sell";
  if (s === "NE RIEN FAIRE") return "hold";
  return "none";
}

export const libelleSignal = (s: Signal | null | undefined) =>
  s === "ACHETER" ? "Acheter" : s === "VENDRE" ? "Vendre" : s === "NE RIEN FAIRE" ? "Ne rien faire" : "En attente";

/** « Air Liquide » -> « AL » */
export const initiales = (nom: string) =>
  nom.split(/[\s-]+/).filter(Boolean).slice(0, 2).map((m) => m[0]!.toUpperCase()).join("");
