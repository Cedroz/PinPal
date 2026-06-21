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
  useNodesState,
  type Connection,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { ComponentNode } from "./ComponentNode";
import { cancel, getNetlist, submit } from "./bridge";
import {
  graphToNetlist,
  netlistToGraph,
  type CompNode,
  type Netlist,
} from "./netlist";
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
  const original = useRef<Netlist>({ components: [], nets: [] });

  useEffect(() => {
    getNetlist().then((nl) => {
      original.current = nl;
      const { nodes, edges } = netlistToGraph(nl);
      setNodes(nodes);
      setEdges(edges);
      setLoaded(true);
    });
  }, [setNodes, setEdges]);

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
          <button className="approve" onClick={onApprove} disabled={!loaded}>
            Approve netlist
          </button>
        </Panel>
      </ReactFlow>
    </div>
  );
}
