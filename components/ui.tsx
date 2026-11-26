"use client";

// Petits composants visuels réutilisés sur toutes les pages.

import { useId } from "react";
import type { Signal } from "@/lib/api";
import { classeSignal, initiales, libelleSignal, note, pourcent } from "@/lib/format";

export function SignalBadge({ signal, grand = false }: { signal: Signal | null; grand?: boolean }) {
  return (
    <span className={`badge badge-${classeSignal(signal)} ${grand ? "badge-lg" : ""}`}>
      <span className="badge-dot" />
      {libelleSignal(signal)}
    </span>
  );
}

export function Variation({ valeur }: { valeur: number | null }) {
  const sens = valeur == null ? "flat" : valeur > 0 ? "up" : valeur < 0 ? "down" : "flat";
  return (
    <span className={`variation variation-${sens}`}>
      {sens === "up" ? "▲" : sens === "down" ? "▼" : "•"} {pourcent(valeur)}
    </span>
  );
}

export function Avatar({ nom, signal, taille = 44 }: { nom: string; signal?: Signal | null; taille?: number }) {
  return (
    <span className={`avatar avatar-${classeSignal(signal)}`} style={{ width: taille, height: taille, fontSize: taille * 0.36 }}>
      {initiales(nom)}
    </span>
  );
}

/** Barre de -1 à +1 avec les zones Vendre / Ne rien faire / Acheter et un repère sur la note. */
export function ScoreBar({ score, seuil = 0.3, compacte = false }: { score: number | null; seuil?: number; compacte?: boolean }) {
  const pos = score == null ? null : ((Math.max(-1, Math.min(1, score)) + 1) / 2) * 100;
  const zone = (1 - seuil) / 2 * 100;
  return (
    <div className={`scorebar ${compacte ? "scorebar-compact" : ""}`}>
      <div className="scorebar-track">
        <span className="scorebar-zone sell" style={{ width: `${zone}%` }} />
        <span className="scorebar-zone hold" style={{ left: `${zone}%`, width: `${100 - 2 * zone}%` }} />
        <span className="scorebar-zone buy" style={{ left: `${100 - zone}%`, width: `${zone}%` }} />
        <span className="scorebar-center" />
        {pos != null && <span className="scorebar-marker" style={{ left: `${pos}%` }} />}
      </div>
      {!compacte && (
        <div className="scorebar-labels">
          <span>−1</span><span>0</span><span>+1</span>
        </div>
      )}
    </div>
  );
}

/** Barre divergente pour une note de -1 à +1 (partie gauche rouge, droite verte). */
export function BarreNote({ valeur }: { valeur: number | null }) {
  const v = valeur == null ? 0 : Math.max(-1, Math.min(1, valeur));
  return (
    <div className="divbar">
      <span className="divbar-axis" />
      {valeur != null && (
        <span
          className={`divbar-fill ${v >= 0 ? "pos" : "neg"}`}
          style={v >= 0 ? { left: "50%", width: `${v * 50}%` } : { right: "50%", width: `${-v * 50}%` }}
        />
      )}
    </div>
  );
}

export function Sparkline({ valeurs, hauteur = 56 }: { valeurs: number[]; hauteur?: number }) {
  const id = useId().replace(/:/g, "");
  if (valeurs.length < 2) return <div className="sparkline-vide" style={{ height: hauteur }} />;
  const largeur = 240;
  const min = Math.min(...valeurs), max = Math.max(...valeurs);
  const etendue = max - min || 1;
  const pts = valeurs.map((v, i) => [
    (i / (valeurs.length - 1)) * largeur,
    hauteur - 4 - ((v - min) / etendue) * (hauteur - 8),
  ]);
  const ligne = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const hausse = valeurs.at(-1)! >= valeurs[0]!;
  const couleur = hausse ? "var(--buy)" : "var(--sell)";
  const [xf, yf] = pts.at(-1)!;
  return (
    <svg className="sparkline" viewBox={`0 0 ${largeur} ${hauteur}`} preserveAspectRatio="none" style={{ height: hauteur }}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={couleur} stopOpacity="0.32" />
          <stop offset="100%" stopColor={couleur} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${ligne} L${largeur} ${hauteur} L0 ${hauteur} Z`} fill={`url(#g${id})`} />
      <path d={ligne} fill="none" stroke={couleur} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <circle cx={xf} cy={yf} r="2.6" fill={couleur} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Jauge en demi-cercle du score final, avec les zones de décision. */
export function Jauge({ score, seuilAchat = 0.3, seuilVente = -0.3 }: { score: number | null; seuilAchat?: number; seuilVente?: number }) {
  const R = 92, cx = 110, cy = 108;
  const angle = (s: number) => Math.PI * (1 - (s + 1) / 2);           // -1 -> gauche, +1 -> droite
  const point = (s: number, r = R) => [cx + r * Math.cos(angle(s)), cy - r * Math.sin(angle(s))];
  const arc = (a: number, b: number) => {
    const [x1, y1] = point(a), [x2, y2] = point(b);
    return `M${x1} ${y1} A${R} ${R} 0 0 1 ${x2} ${y2}`;
  };
  const s = score == null ? 0 : Math.max(-1, Math.min(1, score));
  const [nx, ny] = point(s, R - 22);
  return (
    <svg className="jauge" viewBox="0 0 220 128" role="img" aria-label={`Score final ${note(score)}`}>
      <path d={arc(-1, seuilVente)} className="jauge-arc sell" />
      <path d={arc(seuilVente, seuilAchat)} className="jauge-arc hold" />
      <path d={arc(seuilAchat, 1)} className="jauge-arc buy" />
      {score != null && (
        <>
          <line x1={cx} y1={cy} x2={nx} y2={ny} className="jauge-aiguille" />
          <circle cx={cx} cy={cy} r="7" className="jauge-pivot" />
        </>
      )}
      <text x={18} y={126} className="jauge-legende">−1</text>
      <text x={202} y={126} className="jauge-legende" textAnchor="end">+1</text>
    </svg>
  );
}

export function IconeModule({ module }: { module: string }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      {module === "information" && <><path {...p} d="M4 5h12v14H6a2 2 0 0 1-2-2z" /><path {...p} d="M16 9h4v8a2 2 0 0 1-2 2h-2" /><path {...p} d="M7 9h6M7 13h6M7 16h4" /></>}
      {module === "technique" && <><path {...p} d="M3 20h18" /><path {...p} d="M4 16l5-5 4 3 7-8" /><path {...p} d="M16 6h4v4" /></>}
      {module === "financier" && <><rect {...p} x="4" y="10" width="3.5" height="9" rx="1" /><rect {...p} x="10.25" y="6" width="3.5" height="13" rx="1" /><rect {...p} x="16.5" y="3" width="3.5" height="16" rx="1" /></>}
      {module === "risque" && <><path {...p} d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" /><path {...p} d="M12 8v5M12 16.5v.01" /></>}
    </svg>
  );
}

export function Squelette({ hauteur = 120 }: { hauteur?: number }) {
  return <div className="squelette" style={{ height: hauteur }} />;
}

export function EtatErreur({ message, onReessayer }: { message: string; onReessayer?: () => void }) {
  return (
    <div className="card erreur-carte">
      <div className="erreur-icone">!</div>
      <div>
        <h3>Données momentanément indisponibles</h3>
        <p>{message}</p>
        <p className="muted petit">Lancez l'API avec <code>uvicorn serveur:app --port 8000</code> à la racine du projet.</p>
      </div>
      {onReessayer && <button className="btn btn-ghost" onClick={onReessayer}>Réessayer</button>}
    </div>
  );
}
