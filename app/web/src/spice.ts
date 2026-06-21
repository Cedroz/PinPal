// SPICE export/simulation types mirroring app/spice.py, plus a .cir download helper.

export interface Replacement {
  component: string;
  pin: string;
  node: string;
  kind: string;
  source: string;
}

export interface ConversionResult {
  cir: string;
  nodes: string[];
  replacements: Replacement[];
  warnings: string[];
}

export interface SimOk {
  status: "ok";
  time: number[];
  signals: Record<string, number[]>;
  nodes: string[];
  replacements: Replacement[];
  warnings: string[];
  cir: string;
}

export interface SimError {
  status: "error";
  error: string;
  cir?: string;
}

export type SimResult = SimOk | SimError;

// "<component> <pin>" -> SPICE source string (user edits to a replacement's stimulus).
export type Overrides = Record<string, string>;

export const overrideKey = (r: Replacement) => `${r.component} ${r.pin}`;

// Trigger a browser download of the generated .cir text.
export function downloadCir(cir: string, filename = "netlist.cir"): void {
  const blob = new Blob([cir], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
