import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CompNode } from "./netlist";
import { SYMBOLS, type SchematicSymbol } from "./symbols";

// A component renders as a real schematic symbol when we have one whose pin count matches
// (resistor, LED, transistor, …). Anything else — microcontrollers, ICs, sensors, odd pin
// counts — falls back to an IC body (ChipNode) with pins laid out down its sides.
export function ComponentNode({ data, selected }: NodeProps<CompNode>) {
  const sym = SYMBOLS[data.type];
  if (sym && sym.pins.length === data.pins.length) {
    return <SymbolNode data={data} sym={sym} selected={selected} />;
  }
  return <ChipNode data={data} selected={selected} />;
}

function SymbolNode({
  data,
  sym,
  selected,
}: {
  data: CompNode["data"];
  sym: SchematicSymbol;
  selected: boolean;
}) {
  const labelStyle =
    sym.label === "right"
      ? { left: sym.w + 10, top: "50%", transform: "translateY(-50%)" }
      : sym.label === "bottom"
        ? { left: "50%", top: sym.h + 6, transform: "translateX(-50%)" }
        : { left: "50%", top: -8, transform: "translate(-50%,-100%)" };

  return (
    <div
      className={`schematic-node${selected ? " selected" : ""}`}
      style={{ width: sym.w, height: sym.h }}
    >
      <svg className="sym" width={sym.w} height={sym.h} viewBox={`0 0 ${sym.w} ${sym.h}`} overflow="visible">
        {sym.body}
      </svg>

      <div className="sym-label" style={labelStyle}>
        <span className="lbl">{data.label}</span>
        {data.value ? <span className="val">{data.value}</span> : null}
      </div>

      {data.pins.map((pin, i) => {
        const p = sym.pins[i];
        return (
          <Handle
            key={pin}
            id={pin}
            type="source"
            position={p.position}
            style={{ left: p.x, top: p.y, transform: "translate(-50%, -50%)" }}
          />
        );
      })}
    </div>
  );
}

// Generic IC / microcontroller body: a labelled package with a pin-1 notch and pins
// evenly spaced down both sides. The box grows with pin count so leads never overlap.
function ChipNode({ data, selected }: { data: CompNode["data"]; selected: boolean }) {
  const pins = data.pins;
  const leftCount = Math.ceil(pins.length / 2);
  const rightCount = pins.length - leftCount;
  const rows = Math.max(leftCount, rightCount, 1);

  const TOP_INSET = 16; // clear the notch
  const BOT_INSET = 10;
  const PITCH = 22; // vertical gap between adjacent pins
  const height = TOP_INSET + BOT_INSET + rows * PITCH;
  const span = height - TOP_INSET - BOT_INSET;

  return (
    <div className={`chip-node${selected ? " selected" : ""}`} style={{ height }}>
      <span className="chip-notch" />
      <span className="chip-label">{data.label}</span>
      {data.value ? <span className="chip-value">{data.value}</span> : null}

      {pins.map((pin, i) => {
        const onLeft = i < leftCount;
        const sideIndex = onLeft ? i : i - leftCount;
        const sideCount = onLeft ? leftCount : rightCount;
        const top = TOP_INSET + ((sideIndex + 0.5) / sideCount) * span;
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
