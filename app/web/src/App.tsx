import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  Background,
  ConnectionLineType,
  ConnectionMode,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  useEdgesState,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { ComponentNode } from "./ComponentNode";
import { cancel, exportSpice, getNetlist, submit } from "./bridge";
import { layoutGraph } from "./layout";
import {
  graphToNetlist,
  netlistToGraph,
  pinnedIds,
  type CompNode,
  type Netlist,
} from "./netlist";
import { downloadCir, type ConversionResult } from "./spice";
import { WaveformPanel } from "./WaveformPanel";
import "./styles.css";

// Default pin sets for "Add component" so new parts get sensible handles.
const DEFAULT_PINS: Record<string, string[]> = {
  led: ["anode", "cathode"],
  resistor: ["1", "2"],
  capacitor: ["1", "2"],
  diode: ["anode", "cathode"],
  power: ["+"],
  ground: ["-"],
  switch: ["1", "2"],
  ic: ["1", "2", "3", "4"],
  sensor: ["vcc", "gnd", "sda", "scl"],
  other: ["1", "2"],
};
const TYPES = Object.keys(DEFAULT_PINS);

export default function App() {
  const nodeTypes = useMemo(() => ({ component: ComponentNode }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<CompNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [sim, setSim] = useState<{ netlist: Netlist; conversion: ConversionResult } | null>(null);
  const original = useRef<Netlist>({ components: [], nets: [] });
  const { fitView } = useReactFlow();
  const nodesInitialized = useNodesInitialized();
  const didInitialLayout = useRef(false);

  useEffect(() => {
    getNetlist().then((nl) => {
      original.current = nl;
      const { nodes, edges } = netlistToGraph(nl);
      setNodes(nodes);
      setEdges(edges);
      setLoaded(true);
    });
  }, [setNodes, setEdges]);

  // Auto-arrange once, after React Flow has measured node sizes. The ref latch keeps
  // this to a single run so later edits (e.g. adding a part) don't reshuffle the graph;
  // the Tidy button is the explicit re-layout path.
  useEffect(() => {
    if (!loaded || !nodesInitialized || didInitialLayout.current) return;
    didInitialLayout.current = true;
    setNodes((ns) => layoutGraph(ns, edges, { pinned: pinnedIds(original.current) }));
    requestAnimationFrame(() => fitView());
  }, [loaded, nodesInitialized, edges, setNodes, fitView]);

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds) => addEdge({ ...c, type: "step" }, eds)),
    [setEdges],
  );

  const selected = nodes.find((n) => n.id === selectedId) ?? null;

  const patchSelected = useCallback(
    (patch: Partial<CompNode["data"]>) => {
      if (!selectedId) return;
      setNodes((ns) =>
        ns.map((n) => (n.id === selectedId ? { ...n, data: { ...n.data, ...patch } } : n)),
      );
    },
    [selectedId, setNodes],
  );

  const addComponent = useCallback(
    (type: string) => {
      const ids = new Set(nodes.map((n) => n.id));
      const prefix = type.slice(0, 3).toUpperCase();
      let i = 1;
      while (ids.has(`${prefix}${i}`)) i++;
      const id = `${prefix}${i}`;
      const node: CompNode = {
        id,
        type: "component",
        position: { x: 60 + nodes.length * 24, y: 60 + nodes.length * 24 },
        data: { type, label: id, pins: DEFAULT_PINS[type] ?? ["1", "2"], value: null },
      };
      setNodes((ns) => [...ns, node]);
      setSelectedId(id);
    },
    [nodes, setNodes],
  );

  const onApprove = useCallback(() => {
    submit(graphToNetlist(nodes, edges, original.current));
  }, [nodes, edges]);

  const onExport = useCallback(async () => {
    const nl = graphToNetlist(nodes, edges, original.current);
    const conv = await exportSpice(nl);
    downloadCir(conv.cir, "netlist.cir");
  }, [nodes, edges]);

  const onSimulate = useCallback(async () => {
    const nl = graphToNetlist(nodes, edges, original.current);
    const conv = await exportSpice(nl);
    setSim({ netlist: nl, conversion: conv });
  }, [nodes, edges]);

  return (
    <div className="app">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        connectionMode={ConnectionMode.Loose}
        connectionLineType={ConnectionLineType.Step}
        defaultEdgeOptions={{ type: "step" }}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onSelectionChange={({ nodes }) => setSelectedId(nodes[0]?.id ?? null)}
        deleteKeyCode={["Backspace", "Delete"]}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />

        <Panel position="top-left" className="toolbar">
          <strong>Confirm the circuit</strong>
          <span className="hint">
            Drag pins to wire · select + Delete to remove · edit the selected part →
          </span>
        </Panel>

        <Panel position="top-right" className="add-panel">
          <span className="panel-title">Add part</span>
          <div className="add-buttons">
            {TYPES.map((t) => (
              <button key={t} onClick={() => addComponent(t)} title={`Add ${t}`}>
                {t}
              </button>
            ))}
          </div>
        </Panel>

        {selected ? (
          <Panel position="bottom-right" className="inspector">
            <span className="panel-title">Edit · {selected.id}</span>
            <label>
              Label
              <input
                value={selected.data.label}
                onChange={(e) => patchSelected({ label: e.target.value })}
              />
            </label>
            <label>
              Type
              <select
                value={selected.data.type}
                onChange={(e) => patchSelected({ type: e.target.value })}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Value
              <input
                value={selected.data.value ?? ""}
                placeholder="e.g. 220Ω"
                onChange={(e) => patchSelected({ value: e.target.value || null })}
              />
            </label>
          </Panel>
        ) : null}

        <Panel position="bottom-center" className="actions">
          <button className="cancel" onClick={() => cancel()}>
            Cancel
          </button>
          <button className="spice" onClick={onExport} disabled={!loaded}>
            Export .cir
          </button>
          <button className="spice" onClick={onSimulate} disabled={!loaded}>
            Simulate
          </button>
          <button className="approve" onClick={onApprove} disabled={!loaded}>
            Approve netlist
          </button>
        </Panel>

        {sim ? (
          <Panel position="bottom-left">
            <WaveformPanel
              netlist={sim.netlist}
              conversion={sim.conversion}
              onClose={() => setSim(null)}
            />
          </Panel>
        ) : null}
      </ReactFlow>
    </div>
  );
}
