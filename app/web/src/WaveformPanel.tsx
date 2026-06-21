import { useMemo, useState } from "react";

import { simulate } from "./bridge";
import type { Netlist } from "./netlist";
import {
  overrideKey,
  type ConversionResult,
  type Overrides,
  type SimResult,
} from "./spice";

const COLORS = ["#4f8cff", "#2ea043", "#e3b341", "#f85149", "#a371f7", "#39c5cf"];

export function WaveformPanel({
  netlist,
  conversion,
  onClose,
}: {
  netlist: Netlist;
  conversion: ConversionResult;
  onClose: () => void;
}) {
  // Seed the override boxes with the heuristic's chosen sources so the user edits in place.
  const [overrides, setOverrides] = useState<Overrides>(() =>
    Object.fromEntries(conversion.replacements.map((r) => [overrideKey(r), r.source])),
  );
  const [plotNodes, setPlotNodes] = useState<string[]>(conversion.nodes);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);

  const toggleNode = (n: string) =>
    setPlotNodes((ns) => (ns.includes(n) ? ns.filter((x) => x !== n) : [...ns, n]));

  const run = async () => {
    setBusy(true);
    try {
      // Only send overrides the user actually changed from the heuristic default.
      const changed: Overrides = {};
      for (const r of conversion.replacements) {
        const k = overrideKey(r);
        if (overrides[k] && overrides[k] !== r.source) changed[k] = overrides[k];
      }
      setResult(await simulate(netlist, changed, plotNodes.length ? plotNodes : null));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sim-panel">
      <div className="sim-head">
        <span className="panel-title">Simulate · ngspice</span>
        <button className="sim-close" onClick={onClose} title="Close">
          ×
        </button>
      </div>

      {conversion.replacements.length > 0 && (
        <div className="sim-section">
          <span className="sim-label">Replaced sources (editable)</span>
          {conversion.replacements.map((r) => {
            const k = overrideKey(r);
            return (
              <label key={k} className="sim-repl">
                <span title={`${r.kind} → node ${r.node}`}>
                  {r.component}.{r.pin}
                </span>
                <input
                  value={overrides[k] ?? ""}
                  onChange={(e) => setOverrides((o) => ({ ...o, [k]: e.target.value }))}
                />
              </label>
            );
          })}
        </div>
      )}

      <div className="sim-section">
        <span className="sim-label">Plot nodes</span>
        <div className="sim-nodes">
          {conversion.nodes.length === 0 && <span className="hint">no plottable nodes</span>}
          {conversion.nodes.map((n) => (
            <label key={n} className="sim-node">
              <input
                type="checkbox"
                checked={plotNodes.includes(n)}
                onChange={() => toggleNode(n)}
              />
              {n}
            </label>
          ))}
        </div>
      </div>

      {conversion.warnings.length > 0 && (
        <ul className="sim-warn">
          {conversion.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}

      <button className="sim-run" onClick={run} disabled={busy}>
        {busy ? "Simulating…" : "Run simulation"}
      </button>

      {result?.status === "error" && <div className="sim-error">{result.error}</div>}
      {result?.status === "ok" && <Plot time={result.time} signals={result.signals} />}
    </div>
  );
}

function Plot({ time, signals }: { time: number[]; signals: Record<string, number[]> }) {
  const W = 640;
  const H = 260;
  const PAD = { l: 52, r: 12, t: 12, b: 28 };

  const traces = useMemo(() => {
    const names = Object.keys(signals);
    const n = time.length;
    const stride = Math.max(1, Math.ceil(n / 600)); // downsample to ~600 pts
    const idx: number[] = [];
    for (let i = 0; i < n; i += stride) idx.push(i);
    if (idx[idx.length - 1] !== n - 1 && n > 0) idx.push(n - 1);

    let yMin = Infinity;
    let yMax = -Infinity;
    for (const name of names) {
      for (const i of idx) {
        const v = signals[name][i];
        if (v < yMin) yMin = v;
        if (v > yMax) yMax = v;
      }
    }
    if (!isFinite(yMin)) {
      yMin = 0;
      yMax = 1;
    }
    if (yMin === yMax) {
      yMin -= 1;
      yMax += 1;
    }
    return { names, idx, yMin, yMax };
  }, [time, signals]);

  const xMin = time[0] ?? 0;
  const xMax = time[time.length - 1] ?? 1;
  const sx = (t: number) =>
    PAD.l + ((t - xMin) / (xMax - xMin || 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) =>
    H - PAD.b - ((v - traces.yMin) / (traces.yMax - traces.yMin)) * (H - PAD.t - PAD.b);

  return (
    <div className="sim-plot">
      <svg viewBox={`0 0 ${W} ${H}`} className="sim-svg">
        {/* axes */}
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} className="axis" />
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} className="axis" />
        <text x={4} y={PAD.t + 8} className="axis-lbl">
          {traces.yMax.toPrecision(3)}
        </text>
        <text x={4} y={H - PAD.b} className="axis-lbl">
          {traces.yMin.toPrecision(3)}
        </text>
        <text x={PAD.l} y={H - 6} className="axis-lbl">
          {(xMin * 1e3).toPrecision(2)} ms
        </text>
        <text x={W - PAD.r} y={H - 6} className="axis-lbl" textAnchor="end">
          {(xMax * 1e3).toPrecision(2)} ms
        </text>
        {traces.names.map((name, ci) => (
          <polyline
            key={name}
            className="trace"
            stroke={COLORS[ci % COLORS.length]}
            points={traces.idx.map((i) => `${sx(time[i])},${sy(signals[name][i])}`).join(" ")}
          />
        ))}
      </svg>
      <div className="sim-legend">
        {traces.names.map((name, ci) => (
          <span key={name}>
            <i style={{ background: COLORS[ci % COLORS.length] }} />
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}
