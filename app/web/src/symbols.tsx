// Schematic symbols, one per component type. Each defines its own little SVG coordinate
// space, the lines that draw the symbol, and where its pins sit — so ComponentNode can
// drop a react-flow Handle exactly on each lead. Pins are index-aligned with
// component.pins (pins[0] = first lead, etc.). Stroke comes from `currentColor` so the
// node can recolor on select; filled bits use the `fill` class.

import type { ReactNode } from "react";
import { Position } from "@xyflow/react";

export interface SymbolPin {
  x: number;
  y: number;
  position: Position;
}

export interface SchematicSymbol {
  w: number;
  h: number;
  pins: SymbolPin[];
  label: "top" | "right" | "bottom";
  body: ReactNode;
}

const L = Position.Left;
const R = Position.Right;
const T = Position.Top;
const B = Position.Bottom;

export const SYMBOLS: Record<string, SchematicSymbol> = {
  // ── two-terminal, horizontal ──────────────────────────────────────────────
  resistor: {
    w: 120,
    h: 40,
    label: "top",
    pins: [{ x: 0, y: 20, position: L }, { x: 120, y: 20, position: R }],
    body: <path d="M0,20 H30 L36,8 L48,32 L60,8 L72,32 L84,8 L90,20 H120" />,
  },
  capacitor: {
    w: 90,
    h: 50,
    label: "top",
    pins: [{ x: 0, y: 25, position: L }, { x: 90, y: 25, position: R }],
    body: (
      <>
        <path d="M0,25 H40" />
        <path d="M50,25 H90" />
        <path d="M40,8 V42" />
        <path d="M50,8 V42" />
      </>
    ),
  },
  led: {
    w: 120,
    h: 56,
    label: "top",
    pins: [{ x: 0, y: 34, position: L }, { x: 120, y: 34, position: R }],
    body: (
      <>
        <path d="M0,34 H46" />
        <path className="fill" d="M46,20 L46,48 L76,34 Z" />
        <path d="M76,20 V48" />
        <path d="M76,34 H120" />
        {/* emission arrows */}
        <path d="M60,18 L72,6" />
        <path className="fill" d="M72,6 l-6,1 l4,4 Z" />
        <path d="M68,22 L80,10" />
        <path className="fill" d="M80,10 l-6,1 l4,4 Z" />
      </>
    ),
  },
  diode: {
    w: 110,
    h: 50,
    label: "top",
    pins: [{ x: 0, y: 25, position: L }, { x: 110, y: 25, position: R }],
    body: (
      <>
        <path d="M0,25 H44" />
        <path className="fill" d="M44,12 L44,38 L72,25 Z" />
        <path d="M72,12 V38" />
        <path d="M72,25 H110" />
      </>
    ),
  },
  // ── three-terminal: NPN transistor ────────────────────────────────────────
  transistor: {
    w: 84,
    h: 84,
    label: "right",
    pins: [
      { x: 0, y: 42, position: L }, // base
      { x: 54, y: 0, position: T }, // collector
      { x: 54, y: 84, position: B }, // emitter
    ],
    body: (
      <>
        <circle cx="42" cy="42" r="24" />
        <path d="M0,42 H20" />
        <path d="M20,28 V56" />
        <path d="M20,36 L54,18" />
        <path d="M54,18 V0" />
        <path d="M20,48 L54,66" />
        <path className="fill" d="M40,52 l10,4 l-3,-9 Z" />
        <path d="M54,66 V84" />
      </>
    ),
  },
  // ── single-terminal: power & ground ───────────────────────────────────────
  power: {
    w: 56,
    h: 46,
    label: "top",
    pins: [{ x: 28, y: 46, position: B }],
    body: (
      <>
        <path d="M28,46 V16" />
        <path d="M10,16 H46" />
        <path d="M24,8 H32 M28,4 V12" />
      </>
    ),
  },
  ground: {
    w: 56,
    h: 48,
    label: "right",
    pins: [{ x: 28, y: 0, position: T }],
    body: (
      <>
        <path d="M28,0 V22" />
        <path d="M10,22 H46" />
        <path d="M17,31 H39" />
        <path d="M23,40 H33" />
      </>
    ),
  },
  // switch — horizontal, two leads
  switch: {
    w: 100,
    h: 44,
    label: "top",
    pins: [{ x: 0, y: 30, position: L }, { x: 100, y: 30, position: R }],
    body: (
      <>
        <path d="M0,30 H32" />
        <circle cx="34" cy="30" r="3" className="fill" />
        <path d="M34,30 L70,12" />
        <circle cx="68" cy="30" r="3" className="fill" />
        <path d="M68,30 H100" />
      </>
    ),
  },
};
