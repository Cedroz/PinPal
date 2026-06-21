import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CompNode } from "./netlist";

// Icon/emoji per known component type — purely cosmetic, helps the user eyeball parts.
const ICONS: Record<string, string> = {
  led: "💡",
  resistor: "▭",
  capacitor: "⊥",
  diode: "▷",
  transistor: "⎔",
  ic: "▦",
  sensor: "◈",
  switch: "⏼",
  power: "＋",
  ground: "⏚",
  header: "⋮",
  wire: "—",
  other: "▢",
};

// All handles are type="source"; the canvas uses ConnectionMode.Loose so any pin can
// connect to any pin (circuit wires are undirected).
export function ComponentNode({ data, selected }: NodeProps<CompNode>) {
  const pins = data.pins;
  const leftCount = Math.ceil(pins.length / 2);

  return (
    <div className={`component-node${selected ? " selected" : ""}`}>
      <div className="component-header">
        <span className="component-icon">{ICONS[data.type] ?? ICONS.other}</span>
        <span className="component-label">{data.label}</span>
      </div>
      {data.value ? <div className="component-value">{data.value}</div> : null}

      {pins.map((pin, i) => {
        const onLeft = i < leftCount;
        const sideIndex = onLeft ? i : i - leftCount;
        const sideCount = onLeft ? leftCount : pins.length - leftCount;
        const top = `${((sideIndex + 1) / (sideCount + 1)) * 100}%`;
        return (
          <Handle
            key={pin}
            id={pin}
            type="source"
            position={onLeft ? Position.Left : Position.Right}
            style={{ top }}
          >
            <span className={`pin-label ${onLeft ? "left" : "right"}`}>{pin}</span>
          </Handle>
        );
      })}
    </div>
  );
}
