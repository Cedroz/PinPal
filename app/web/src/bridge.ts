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

export const inPywebview = () => "pywebview" in window;

function ready(): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve();
  return new Promise((resolve) => window.addEventListener("pywebviewready", () => resolve(), { once: true }));
}

export async function getNetlist(): Promise<Netlist> {
  if (!inPywebview()) return structuredClone(SAMPLE);
  await ready();
  return window.pywebview!.api.get_netlist();
}

export async function submit(netlist: Netlist): Promise<void> {
  if (!inPywebview()) {
    console.log("[dev] submit", JSON.stringify(netlist, null, 2));
    return;
  }
  await window.pywebview!.api.submit(netlist);
}

export async function cancel(): Promise<void> {
  if (!inPywebview()) {
    console.log("[dev] cancel");
    return;
  }
  await window.pywebview!.api.cancel();
}
