// Auto-layout for the netlist graph using Dagre (layered, left-to-right).
//
// Components are placed so they don't overlap and wire crossings are minimized.
// We feed Dagre each node's *measured* size (chip width/height are render-dependent),
// so this must run after React Flow has measured the nodes — see useNodesInitialized
// in App.tsx. Results are written back into node.position (top-left), which graphToNetlist
// already round-trips, so no other code needs to change.

import dagre from "@dagrejs/dagre";
import type { Edge } from "@xyflow/react";

import type { CompNode } from "./netlist";

// Used only if a node hasn't been measured yet (layout is gated on measurement, so
// these are a safety net rather than the common path).
const FALLBACK_W = 140;
const FALLBACK_H = 80;

export function layoutGraph(
  nodes: CompNode[],
  edges: Edge[],
  opts: { pinned?: Set<string> } = {},
): CompNode[] {
  const pinned = opts.pinned ?? new Set<string>();

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 90 });
  g.setDefaultEdgeLabel(() => ({}));

  const size = (n: CompNode) => ({
    width: n.measured?.width ?? FALLBACK_W,
    height: n.measured?.height ?? FALLBACK_H,
  });

  for (const n of nodes) g.setNode(n.id, size(n));
  for (const e of edges) g.setEdge(e.source, e.target);

  dagre.layout(g);

  return nodes.map((n) => {
    if (pinned.has(n.id)) return n;
    const d = g.node(n.id);
    if (!d) return n;
    const { width, height } = size(n);
    // Dagre returns node centers; React Flow positions by top-left corner.
    return { ...n, position: { x: d.x - width / 2, y: d.y - height / 2 } };
  });
}
