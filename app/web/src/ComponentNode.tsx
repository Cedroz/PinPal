import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CompNode } from "./netlist";
import { SYMBOLS, type SchematicSymbol } from "./symbols";

// A component renders as a real schematic symbol when we have one whose pin count matches
// (resistor, LED, transistor, …). Anything else — ICs, sensors, odd pin counts — falls
// back to a labelled chip with pins on its sides.
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

function ChipNode({ data, selected }: { data: CompNode["data"]; selected: boolean }) {
  const pins = data.pins;
  const leftCount = Math.ceil(pins.length / 2);

  return (
    <div className={`chip-node${selected ? " selected" : ""}`}>
      <span className="chip-label">{data.label}</span>
      {data.value ? <span className="chip-value">{data.value}</span> : null}

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
