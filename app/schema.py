"""Netlist schema — the contract between the vision agent (Person A) and the UI (Person B).

A netlist is *components* (parts with ordered, named pins) plus *nets* (sets of pins
that are electrically tied together). This is the structure the vision agent emits, the
UI renders and edits, and ``confirm_netlist`` returns once the user approves it.

The UI treats wires (react-flow edges) as the source of truth: on approve it rebuilds
nets from the edge graph, so this module only needs to validate the shape, not enforce
how the UI got there.

Keep this in lockstep with ``web/src/netlist.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Component "type" is a free-form hint the UI uses to pick an icon/shape. These are the
# ones the renderer knows about; anything else falls back to a generic box.
KNOWN_TYPES = {
    "led",
    "resistor",
    "capacitor",
    "diode",
    "transistor",
    "ic",
    "sensor",
    "switch",
    "power",
    "ground",
    "header",
    "wire",
    "other",
}


@dataclass
class Component:
    id: str
    type: str
    label: str
    pins: list[str]
    value: str | None = None
    # Optional layout hint from the vision agent. The UI auto-lays-out when absent.
    position: dict[str, float] | None = None


@dataclass
class PinRef:
    component: str
    pin: str


@dataclass
class Net:
    id: str
    nodes: list[PinRef]
    name: str | None = None


@dataclass
class Netlist:
    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)


class NetlistError(ValueError):
    """Raised when a netlist payload is structurally invalid."""


def from_dict(data: dict) -> Netlist:
    """Parse + validate a raw dict (e.g. JSON from the vision agent or the UI)."""
    if not isinstance(data, dict):
        raise NetlistError("netlist must be a JSON object")

    components: list[Component] = []
    seen_ids: set[str] = set()
    for raw in data.get("components", []):
        cid = _require_str(raw, "id", "component")
        if cid in seen_ids:
            raise NetlistError(f"duplicate component id: {cid!r}")
        seen_ids.add(cid)
        pins = raw.get("pins", [])
        if not isinstance(pins, list) or not all(isinstance(p, str) for p in pins):
            raise NetlistError(f"component {cid!r}: pins must be a list of strings")
        components.append(
            Component(
                id=cid,
                type=str(raw.get("type", "other")),
                label=str(raw.get("label", cid)),
                pins=pins,
                value=_opt_str(raw.get("value")),
                position=raw.get("position") if isinstance(raw.get("position"), dict) else None,
            )
        )

    nets: list[Net] = []
    for raw in data.get("nets", []):
        nid = _require_str(raw, "id", "net")
        nodes_raw = raw.get("nodes", [])
        if not isinstance(nodes_raw, list):
            raise NetlistError(f"net {nid!r}: nodes must be a list")
        nodes: list[PinRef] = []
        for n in nodes_raw:
            comp = _require_str(n, "component", "net node")
            pin = _require_str(n, "pin", "net node")
            if comp not in seen_ids:
                raise NetlistError(f"net {nid!r} references unknown component {comp!r}")
            nodes.append(PinRef(component=comp, pin=pin))
        nets.append(Net(id=nid, nodes=nodes, name=_opt_str(raw.get("name"))))

    return Netlist(components=components, nets=nets)


def to_dict(netlist: Netlist) -> dict:
    """Serialize back to the JSON-able dict shape."""
    return {
        "components": [
            _drop_none(
                {
                    "id": c.id,
                    "type": c.type,
                    "label": c.label,
                    "pins": c.pins,
                    "value": c.value,
                    "position": c.position,
                }
            )
            for c in netlist.components
        ],
        "nets": [
            _drop_none(
                {
                    "id": n.id,
                    "name": n.name,
                    "nodes": [{"component": p.component, "pin": p.pin} for p in n.nodes],
                }
            )
            for n in netlist.nets
        ],
    }


def _require_str(obj: object, key: str, what: str) -> str:
    if not isinstance(obj, dict) or not isinstance(obj.get(key), str) or not obj[key]:
        raise NetlistError(f"{what} missing required string field {key!r}")
    return obj[key]


def _opt_str(v: object) -> str | None:
    return v if isinstance(v, str) and v else None


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
