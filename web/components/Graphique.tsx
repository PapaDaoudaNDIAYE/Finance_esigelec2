"use client";

// Graphique des cours (bougies + volumes) avec moyennes mobiles, bandes de Bollinger et RSI.
// Bibliothèque : lightweight-charts (TradingView), chargée seulement dans le navigateur.

import { useEffect, useMemo, useRef, useState } from "react";
import type { Point } from "@/lib/api";
import { euros, nombre, pourcent } from "@/lib/format";

const PERIODES = { "1M": 22, "3M": 66, "6M": 130, "1A": 9999 } as const;
type Periode = keyof typeof PERIODES;

const COUCHES = {
  mm20: { label: "MM20", couleur: "#60a5fa" },
  mm50: { label: "MM50", couleur: "#c084fc" },
  mm200: { label: "MM200", couleur: "#f59e0b" },
  bollinger: { label: "Bollinger", couleur: "#94a3b8" },
} as const;
type Couche = keyof typeof COUCHES;

const THEME = {
  layout: { background: { color: "transparent" }, textColor: "#8b93a7", fontFamily: "var(--font-inter), system-ui, sans-serif" },
  grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
  rightPriceScale: { borderVisible: false },
  timeScale: { borderVisible: false },
  localization: { locale: "fr-FR" },
};

export default function Graphique({ historique, support, resistance }: {
  historique: Point[]; support?: number | null; resistance?: number | null;
}) {
  const zonePrix = useRef<HTMLDivElement>(null);
  const zoneRsi = useRef<HTMLDivElement>(null);
  const [periode, setPeriode] = useState<Periode>("6M");
  const [couches, setCouches] = useState<Record<Couche, boolean>>({ mm20: true, mm50: true, mm200: true, bollinger: false });
  const [survol, setSurvol] = useState<Point | null>(null);

  const points = useMemo(() => historique.slice(-PERIODES[periode]), [historique, periode]);
  const affiche = survol ?? points.at(-1) ?? null;
  const indexAffiche = affiche ? historique.findIndex((p) => p.date === affiche.date) : -1;
  const veille = indexAffiche > 0 ? historique[indexAffiche - 1] : null;

  useEffect(() => {
    if (!zonePrix.current || !zoneRsi.current || points.length === 0) return;
    let fini = false;
    const nettoyages: (() => void)[] = [];

    import("lightweight-charts").then(({ createChart, CrosshairMode, LineStyle }) => {
      if (fini || !zonePrix.current || !zoneRsi.current) return;

      // --- Graphique principal -------------------------------------------------
      const chart = createChart(zonePrix.current, {
        ...THEME,
        autoSize: true,
        crosshair: { mode: CrosshairMode.Normal,
          vertLine: { color: "rgba(129,140,248,0.5)", labelBackgroundColor: "#4f46e5" },
          horzLine: { color: "rgba(129,140,248,0.5)", labelBackgroundColor: "#4f46e5" } },
        localization: { locale: "fr-FR", priceFormatter: (p: number) => `${nombre(p, 2)} €` },
      });
      const parDate = new Map(points.map((p) => [p.date, p]));

      if (couches.bollinger) {
        for (const cle of ["boll_haut", "boll_bas"] as const) {
          chart.addLineSeries({ color: "rgba(148,163,184,0.55)", lineWidth: 1, lineStyle: LineStyle.Dashed,
            priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(points.filter((p) => p[cle] != null).map((p) => ({ time: p.date, value: p[cle]! })));
        }
      }

      const bougies = chart.addCandlestickSeries({
        upColor: "#34d399", downColor: "#fb7185", wickUpColor: "#34d399", wickDownColor: "#fb7185",
        borderVisible: false, priceLineColor: "#818cf8",
      });
      bougies.setData(points.map((p) => ({
        time: p.date, open: p.ouverture ?? p.cloture, high: p.haut ?? p.cloture,
        low: p.bas ?? p.cloture, close: p.cloture,
      })));
      bougies.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.24 } });

      if (support) bougies.createPriceLine({ price: support, color: "rgba(52,211,153,0.55)", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Support" });
      if (resistance) bougies.createPriceLine({ price: resistance, color: "rgba(251,113,133,0.55)", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Résistance" });

      for (const cle of ["mm20", "mm50", "mm200"] as const) {
        if (!couches[cle]) continue;
        chart.addLineSeries({ color: COUCHES[cle].couleur, lineWidth: 2, priceLineVisible: false,
          lastValueVisible: false, crosshairMarkerVisible: false })
          .setData(points.filter((p) => p[cle] != null).map((p) => ({ time: p.date, value: p[cle]! })));
      }

      const volumes = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false });
      volumes.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volumes.setData(points.map((p) => ({
        time: p.date, value: p.volume ?? 0,
        color: p.cloture >= (p.ouverture ?? p.cloture) ? "rgba(52,211,153,0.28)" : "rgba(251,113,133,0.28)",
      })));

      // --- RSI ------------------------------------------------------------------
      const rsiChart = createChart(zoneRsi.current, {
        ...THEME, autoSize: true,
        crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "rgba(129,140,248,0.5)", labelVisible: false }, horzLine: { visible: false, labelVisible: false } },
        timeScale: { borderVisible: false, visible: false },
        handleScroll: false, handleScale: false,
      });
      const rsi = rsiChart.addLineSeries({ color: "#818cf8", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
      rsi.setData(points.filter((p) => p.rsi != null).map((p) => ({ time: p.date, value: p.rsi! })));
      rsi.priceScale().applyOptions({ autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } });
      rsi.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });
      rsi.createPriceLine({ price: 70, color: "rgba(251,113,133,0.6)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "" });
      rsi.createPriceLine({ price: 30, color: "rgba(52,211,153,0.6)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "" });

      // Les deux graphiques défilent ensemble.
      chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r) rsiChart.timeScale().setVisibleLogicalRange(r); });
      chart.timeScale().fitContent();

      chart.subscribeCrosshairMove((param) => {
        const t = param.time as string | undefined;
        setSurvol(t ? parDate.get(t) ?? null : null);
      });

      nettoyages.push(() => { chart.remove(); rsiChart.remove(); });
    });

    return () => { fini = true; nettoyages.forEach((f) => f()); };
  }, [points, couches, support, resistance]);

  const variationJour = affiche && veille ? affiche.cloture / veille.cloture - 1 : null;

  return (
    <div className="graphique">
      <div className="graphique-barre">
        <div className="graphique-legende">
          {affiche && (
            <>
              <span className="muted">{new Date(affiche.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}</span>
              <span>O <b>{euros(affiche.ouverture)}</b></span>
              <span>H <b>{euros(affiche.haut)}</b></span>
              <span>B <b>{euros(affiche.bas)}</b></span>
              <span>C <b>{euros(affiche.cloture)}</b></span>
              {variationJour != null && (
                <span className={variationJour >= 0 ? "txt-buy" : "txt-sell"}>{pourcent(variationJour)}</span>
              )}
            </>
          )}
        </div>
        <div className="segment">
          {(Object.keys(PERIODES) as Periode[]).map((p) => (
            <button key={p} className={p === periode ? "actif" : ""} onClick={() => setPeriode(p)}>{p}</button>
          ))}
        </div>
      </div>

      <div className="couches">
        {(Object.keys(COUCHES) as Couche[]).map((c) => (
          <button key={c} className={`puce ${couches[c] ? "actif" : ""}`}
            onClick={() => setCouches((x) => ({ ...x, [c]: !x[c] }))}>
            <span className="puce-couleur" style={{ background: COUCHES[c].couleur }} />
            {COUCHES[c].label}
            {c !== "bollinger" && affiche?.[c] != null && <b>{nombre(affiche[c], 2)}</b>}
          </button>
        ))}
      </div>

      <div ref={zonePrix} className="graphique-prix" />
      <div className="graphique-rsi-titre">
        <span>RSI 14</span>
        <b>{nombre(affiche?.rsi, 0)}</b>
        <span className="muted petit">survente &lt; 30 · surachat &gt; 70</span>
      </div>
      <div ref={zoneRsi} className="graphique-rsi" />
    </div>
  );
}
