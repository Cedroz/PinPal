// Bridge to the pywebview host. When running inside the pywebview window, the Python
// side injects `window.pywebview.api` with get_netlist / submit / cancel. When running
// in a plain browser (`npm run dev`), we fall back to a baked-in sample so the editor is
// fully usable standalone.

import type { Netlist } from "./netlist";

interface PywebviewApi {
  get_netlist: () => Promise<Netlist>;
  submit: (netlist: Netlist) => Promise<void>;
  cancel: () => Promise<void>;
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
