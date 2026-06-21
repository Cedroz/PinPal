// Bridge to the pywebview host. When running inside the pywebview window, the Python
// side injects `window.pywebview.api` with get_netlist / submit / cancel. When running
// in a plain browser (`npm run dev`), we fall back to a baked-in sample so the editor is
// fully usable standalone.

import type { Netlist } from "./netlist";
import type { ConversionResult, Overrides, SimResult } from "./spice";

interface PywebviewApi {
  get_netlist: () => Promise<Netlist>;
  submit: (netlist: Netlist) => Promise<void>;
  cancel: () => Promise<void>;
  export_spice: (netlist: Netlist) => Promise<ConversionResult>;
  simulate: (
    netlist: Netlist,
    overrides: Overrides | null,
    plot_nodes: string[] | null,
  ) => Promise<SimResult>;
}

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi };
  }
}

const SAMPLE: Netlist = {
  components: [
    { id: "LED1", type: "led", label: "LED", pins: ["anode", "cathode"] },
    { id: "R1", type: "resistor", label: "R1", value: "220Ω", pins: ["1", "2"] },
    { id: "PWR", type: "power", label: "+5V", pins: ["+"] },
    { id: "GND", type: "ground", label: "GND", pins: ["-"] },
  ],
  nets: [
    { id: "N1", name: "VCC", nodes: [{ component: "PWR", pin: "+" }, { component: "R1", pin: "1" }] },
    { id: "N2", name: "ANODE", nodes: [{ component: "R1", pin: "2" }, { component: "LED1", pin: "anode" }] },
    { id: "N3", name: "RTN", nodes: [{ component: "LED1", pin: "cathode" }, { component: "GND", pin: "-" }] },
  ],
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// pywebview injects window.pywebview.api *asynchronously* (after `pywebviewready`), so a
// synchronous "am I in pywebview?" check at mount races and wrongly reads false. Instead
// poll for the API for a grace period: if it shows up we're in the window; if it never
// does, we're in a plain browser (`npm run dev`) and fall back to the sample. Resolved
// once and cached so the wait happens a single time.
let apiPromise: Promise<PywebviewApi | null> | undefined;

function resolveApi(): Promise<PywebviewApi | null> {
  if (!apiPromise) {
    apiPromise = (async () => {
      for (let waited = 0; waited < 2500; waited += 25) {
        const api = window.pywebview?.api;
        if (api && typeof api.get_netlist === "function") {
          console.log("[bridge] pywebview API ready");
          return api;
        }
        await sleep(25);
      }
      console.log("[bridge] no pywebview host — browser fallback (sample netlist)");
      return null;
    })();
  }
  return apiPromise;
}

export async function getNetlist(): Promise<Netlist> {
  const api = await resolveApi();
  return api ? api.get_netlist() : structuredClone(SAMPLE);
}

export async function submit(netlist: Netlist): Promise<void> {
  const api = await resolveApi();
  if (!api) {
    console.log("[dev] submit", JSON.stringify(netlist, null, 2));
    return;
  }
  await api.submit(netlist);
}

export async function cancel(): Promise<void> {
  const api = await resolveApi();
  if (!api) {
    console.log("[dev] cancel");
    return;
  }
  await api.cancel();
}

export async function exportSpice(netlist: Netlist): Promise<ConversionResult> {
  const api = await resolveApi();
  return api ? api.export_spice(netlist) : devConversion();
}

export async function simulate(
  netlist: Netlist,
  overrides: Overrides | null,
  plotNodes: string[] | null,
): Promise<SimResult> {
  const api = await resolveApi();
  return api ? api.simulate(netlist, overrides, plotNodes) : devSim(plotNodes);
}

// ---- browser dev fallbacks (npm run dev, no Python/ngspice) ------------------

function devConversion(): ConversionResult {
  return {
    cir:
      "* Pin Pal netlist -> ngspice (dev sample)\n\n" +
      "DLED1 ANODE 0 DLED\nRR1 VCC ANODE 220\nVPWR VCC 0 DC 5\n\n" +
      ".model DLED D(Is=1e-14 N=2)\n.options rshunt=1e12\n.tran 1.000e-05 5.000e-03\n.end\n",
    nodes: ["ANODE", "VCC"],
    replacements: [],
    warnings: ["dev fallback — install Python host + ngspice for a real deck"],
  };
}

function devSim(plotNodes: string[] | null): SimResult {
  const conv = devConversion();
  const N = 400;
  const time = Array.from({ length: N }, (_, i) => (i / (N - 1)) * 5e-3);
  const all: Record<string, number[]> = {
    VCC: time.map(() => 5),
    ANODE: time.map((t) => 1.8 + 0.2 * Math.sin(2 * Math.PI * 1000 * t)),
  };
  const signals = plotNodes
    ? Object.fromEntries(Object.entries(all).filter(([k]) => plotNodes.includes(k)))
    : all;
  return { status: "ok", time, signals, nodes: conv.nodes, replacements: [], warnings: conv.warnings, cir: conv.cir };
}
