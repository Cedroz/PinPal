"""Netlist -> ngspice. Converts an approved Pin Pal netlist into a SPICE deck and runs a
transient simulation, returning waveform traces for the UI to plot.

ngspice models analog parts but cannot simulate microcontrollers / digital logic, so any
component type ngspice can't represent (ic, sensor, header, unknown types) is *replaced*
with a stimulus source — e.g. an amplifier input gets a small SIN, an ambiguous digital
line gets a PULSE. Every replacement is reported back so the user can review and override
the chosen source before simulating.

Public surface:
  to_spice(netlist, overrides=None) -> ConversionResult dict   (no ngspice needed)
  simulate(netlist, overrides=None, plot_nodes=None) -> dict    (shells out to ngspice)

Keep the netlist shape in lockstep with schema.py / web/src/netlist.ts.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import struct
import subprocess
import tempfile
import unicodedata

import schema

# Types ngspice can model directly. Anything else is treated as a signal source and gets
# replaced with a stimulus (see _replace).
SIM_TYPES = {
    "resistor",
    "capacitor",
    "led",
    "diode",
    "transistor",
    "power",
    "ground",
    "switch",
    "wire",
}

_GROUND_NAMES = {"GND", "0", "GROUND", "VSS", "AGND", "DGND"}
_GND_PIN_NAMES = {"gnd", "vss", "agnd", "dgnd", "ground", "-", "0"}
_PWR_PIN_NAMES = {"vcc", "vdd", "vin", "v+", "vbat", "vsup", "3v3", "5v", "3.3v"}

_SAFE_NODE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
       "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12}

_DEFAULTS = {"resistor": "1k", "capacitor": "1u", "voltage": "5"}


# ---- value parsing ----------------------------------------------------------

def parse_value(raw: str | None, kind: str) -> tuple[str, str | None]:
    """Normalize a human value ("220Ω", "10µF", "+5V") to a SPICE token ("220", "10u",
    "5"). Returns (token, warning_or_None); falls back to a kind default on failure."""
    default = _DEFAULTS.get(kind, "1")
    if not raw or not str(raw).strip():
        return default, None
    s = unicodedata.normalize("NFKC", str(raw)).strip().lower()
    s = s.replace("µ", "u").replace("μ", "u").replace("ω", "").replace("ohm", "")
    m = re.match(r"([0-9]*\.?[0-9]+)\s*(meg|[fpnumkgt])?", s)
    if not m:
        return default, f"could not parse value {raw!r}; using {default}"
    num, suf = m.group(1), m.group(2) or ""
    return num + suf, None


def _si_to_float(tok: str) -> float | None:
    m = re.match(r"([0-9]*\.?[0-9]+)\s*(meg|[fpnumkgt])?", tok.strip().lower())
    if not m:
        return None
    return float(m.group(1)) * _SI.get(m.group(2) or "", 1.0)


# ---- conversion -------------------------------------------------------------

def to_spice(netlist: dict, overrides: dict[str, str] | None = None) -> dict:
    """Build a SPICE deck from a netlist dict.

    overrides maps "<component> <pin>" -> a SPICE source string (e.g. "SIN(0 1 1k)") to
    replace the heuristic choice for a stimulus.

    Returns {cir, nodes, replacements, warnings}.
    """
    overrides = overrides or {}
    nl = schema.from_dict(netlist)
    warnings: list[str] = []

    pin2net = {(nd.component, nd.pin): net.id for net in nl.nets for nd in net.nodes}
    ground_comp_ids = {c.id for c in nl.components if c.type == "ground"}

    def is_ground(net: schema.Net) -> bool:
        if net.name and net.name.strip().upper() in _GROUND_NAMES:
            return True
        return any(nd.component in ground_comp_ids for nd in net.nodes)

    # Net id -> SPICE node label. All ground nets collapse to "0".
    labels: dict[str, str] = {}
    used: set[str] = {"0"}
    counter = 1
    for net in nl.nets:
        if is_ground(net):
            labels[net.id] = "0"
            continue
        name = (net.name or "").strip()
        m = _SAFE_NODE.fullmatch(name)
        if m and name.upper() not in _GROUND_NAMES and name not in used:
            labels[net.id] = name
        else:
            while f"n{counter}" in used:
                counter += 1
            labels[net.id] = f"n{counter}"
        used.add(labels[net.id])

    float_nodes: dict[tuple[str, str], str] = {}

    def node_of(comp: str, pin: str) -> str:
        nid = pin2net.get((comp, pin))
        if nid is not None:
            return labels[nid]
        key = (comp, pin)
        if key not in float_nodes:
            float_nodes[key] = f"flt_{_san(comp)}_{_san(pin)}"
        return float_nodes[key]

    lines: list[str] = []
    models: set[str] = set()
    replacements: list[dict] = []
    conns: dict[str, int] = {}  # node -> # of device terminals on it (for bleeders)
    # Nodes already driven by a real supply — don't stack another source on top (that
    # would be a SPICE voltage-source loop). Seed with the power components' nodes.
    driven: set[str] = {
        node_of(c.id, _p(c, 0)) for c in nl.components if c.type == "power"
    }
    driven.discard("0")

    def emit(line: str, *nodes: str) -> None:
        lines.append(line)
        for n in nodes:
            if n != "0":
                conns[n] = conns.get(n, 0) + 1

    for c in nl.components:
        cid = _san(c.id)
        if c.type in ("ground", "wire"):
            continue
        elif c.type == "resistor":
            val, w = parse_value(c.value, "resistor")
            if w:
                warnings.append(f"{c.id}: {w}")
            a, b = node_of(c.id, _p(c, 0)), node_of(c.id, _p(c, 1))
            emit(f"R{cid} {a} {b} {val}", a, b)
        elif c.type == "capacitor":
            val, w = parse_value(c.value, "capacitor")
            if w:
                warnings.append(f"{c.id}: {w}")
            a, b = node_of(c.id, _p(c, 0)), node_of(c.id, _p(c, 1))
            emit(f"C{cid} {a} {b} {val}", a, b)
        elif c.type in ("led", "diode"):
            ap, kp = _diode_pins(c)
            a, k = node_of(c.id, ap), node_of(c.id, kp)
            models.add(".model DLED D(Is=1e-14 N=2)")
            emit(f"D{cid} {a} {k} DLED", a, k)
        elif c.type == "transistor":
            colp, basep, emitp, w = _bjt_pins(c)
            if w:
                warnings.append(f"{c.id}: {w}")
            col, base, em = node_of(c.id, colp), node_of(c.id, basep), node_of(c.id, emitp)
            models.add(".model QNPN NPN(Bf=100)")
            emit(f"Q{cid} {col} {base} {em} QNPN", col, base, em)
        elif c.type == "power":
            val, w = parse_value(c.value, "voltage")
            if w:
                warnings.append(f"{c.id}: {w}")
            a = node_of(c.id, _p(c, 0))
            emit(f"V{cid} {a} 0 DC {val}", a)
        elif c.type == "switch":
            warnings.append(f"{c.id}: switch modeled as closed (1mΩ); no control net available")
            a, b = node_of(c.id, _p(c, 0)), node_of(c.id, _p(c, 1))
            emit(f"R{cid} {a} {b} 1m", a, b)
        else:
            # Unsimulatable (ic / sensor / header / unknown): replace signal pins with
            # stimulus sources; treat power/ground pins as supplies.
            _replace(c, node_of, pin2net, nl, overrides, emit, driven, replacements, warnings)

    # Bleeders for any node that ends up with a single connection — ngspice rejects nodes
    # with < 2 connections. rshunt below gives every node a DC path to ground.
    for i, (node, n) in enumerate(conns.items()):
        if n < 2:
            lines.append(f"Rblz{i} {node} 0 1G")

    nodes = sorted(n for n in used if n != "0")
    header = ["* Pin Pal netlist -> ngspice", f"* {len(replacements)} replaced component pin(s)"]
    for r in replacements:
        header.append(f"*   {r['component']}.{r['pin']} ({r['kind']}) -> {r['source']}")

    step, stop = _tran_params([r["source"] for r in replacements])
    body = (
        header
        + [""]
        + lines
        + [""]
        + sorted(models)
        + [".options rshunt=1e12", f".tran {step:.3e} {stop:.3e}", ".end"]
    )
    return {
        "cir": "\n".join(body) + "\n",
        "nodes": nodes,
        "replacements": replacements,
        "warnings": warnings,
    }


def _replace(c, node_of, pin2net, nl, overrides, emit, driven, replacements, warnings):
    """Emit stimulus / supply sources for an unsimulatable component's pins. `driven` is
    the set of nodes already powered — we never stack a second source on them."""
    for pin in c.pins:
        node = node_of(c.id, pin)
        if node == "0":
            continue  # tied to ground already
        pn = pin.strip().lower()
        cid = _san(c.id)
        sp = _san(pin)
        if pn in _GND_PIN_NAMES:
            continue
        if node in driven:
            continue  # already powered by a real supply or an earlier source
        if pn in _PWR_PIN_NAMES:
            volts = "3.3" if "3" in pn else "5"
            emit(f"V{cid}_{sp} {node} 0 DC {volts}", node)
            driven.add(node)
            continue
        if (c.id, pin) not in pin2net:
            continue  # floating signal pin — nothing else references it
        key = f"{c.id} {pin}"
        if key in overrides:
            kind, source = "override", overrides[key]
        else:
            kind, source = _choose_stimulus(c, pin, pin2net, nl)
            warnings.append(f"{c.id}.{pin}: replaced with {kind} stimulus ({source})")
        emit(f"V{cid}_{sp} {node} 0 {source}", node)
        replacements.append(
            {"component": c.id, "pin": pin, "node": node, "kind": kind, "source": source}
        )
        driven.add(node)


def _choose_stimulus(c, pin, pin2net, nl) -> tuple[str, str]:
    """Pick a stimulus source for a replaced signal pin."""
    if _reaches_amplifier(c.id, pin, pin2net, nl):
        return "amplifier-input", "SIN(0 0.1 1k)"
    if c.type == "sensor":
        return "sensor-analog", "SIN(2.5 2 10)"
    return "digital-default", "PULSE(0 5 0 1u 1u 0.5m 1m)"


def _reaches_amplifier(comp: str, pin: str, pin2net, nl) -> bool:
    """True if this pin's net reaches a transistor base — directly or through one
    capacitor (the classic AC-coupled amplifier input)."""
    net = pin2net.get((comp, pin))
    if net is None:
        return False

    def base_on(net_id) -> bool:
        for c in nl.components:
            if c.type != "transistor":
                continue
            for p in c.pins:
                if pin2net.get((c.id, p)) == net_id and p.strip().lower() in ("base", "b"):
                    return True
        return False

    if base_on(net):
        return True
    # one capacitor hop
    for c in nl.components:
        if c.type != "capacitor":
            continue
        cap_nets = [pin2net.get((c.id, p)) for p in c.pins]
        if net in cap_nets:
            for other in cap_nets:
                if other is not None and other != net and base_on(other):
                    return True
    return False


# ---- pin helpers ------------------------------------------------------------

def _san(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s) or "X"


def _p(c, i: int) -> str:
    """i-th pin name, tolerating short pin lists."""
    return c.pins[i] if i < len(c.pins) else str(i + 1)


def _diode_pins(c) -> tuple[str, str]:
    anode = cathode = None
    for p in c.pins:
        pl = p.strip().lower()
        if pl in ("anode", "a", "+") and anode is None:
            anode = p
        elif pl in ("cathode", "c", "k", "-") and cathode is None:
            cathode = p
    anode = anode or _p(c, 0)
    cathode = cathode or _p(c, 1)
    return anode, cathode


def _bjt_pins(c) -> tuple[str, str, str, str | None]:
    col = base = emit = None
    for p in c.pins:
        pl = p.strip().lower()
        if pl in ("collector", "c") and col is None:
            col = p
        elif pl in ("base", "b") and base is None:
            base = p
        elif pl in ("emitter", "e") and emit is None:
            emit = p
    if col and base and emit:
        return col, base, emit, None
    # Fall back to declared order C,B,E.
    return _p(c, 0), _p(c, 1), _p(c, 2), "transistor pins unlabeled; assumed order C,B,E"


def _tran_params(sources: list[str]) -> tuple[float, float]:
    """Pick .tran step/stop so a few cycles of the slowest stimulus are visible."""
    periods: list[float] = []
    for s in sources:
        m = re.search(r"sin\s*\(([^)]*)\)", s, re.I)
        if m:
            parts = m.group(1).split()
            if len(parts) >= 3:
                f = _si_to_float(parts[2])
                if f:
                    periods.append(1.0 / f)
            continue
        m = re.search(r"pulse\s*\(([^)]*)\)", s, re.I)
        if m:
            parts = m.group(1).split()
            if len(parts) >= 7:
                per = _si_to_float(parts[6])
                if per:
                    periods.append(per)
    stop = max(periods) * 4 if periods else 5e-3
    stop = min(max(stop, 1e-3), 1.0)
    return stop / 500.0, stop


# ---- simulation -------------------------------------------------------------

def ngspice_path() -> str | None:
    return shutil.which("ngspice")


def simulate(
    netlist: dict,
    overrides: dict[str, str] | None = None,
    plot_nodes: list[str] | None = None,
) -> dict:
    """Convert + run a transient simulation. Returns
    {status:"ok", time, signals, nodes, replacements, warnings, cir} or
    {status:"error", error, ...}."""
    exe = ngspice_path()
    if not exe:
        return {
            "status": "error",
            "error": "ngspice not found. Install it (apt install ngspice / brew install "
            "ngspice) to simulate. Export .cir still works without it.",
        }
    try:
        conv = to_spice(netlist, overrides)
    except schema.NetlistError as e:
        return {"status": "error", "error": f"invalid netlist: {e}"}

    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        cir_path, raw_path = dp / "deck.cir", dp / "out.raw"
        cir_path.write_text(_inject_control(conv["cir"], raw_path))
        try:
            proc = subprocess.run(
                [exe, "-b", str(cir_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "ngspice timed out after 30s", "cir": conv["cir"]}

        if not raw_path.exists():
            return {
                "status": "error",
                "error": "ngspice produced no output:\n" + (proc.stderr or proc.stdout)[-2000:],
                "cir": conv["cir"],
            }
        try:
            time, signals = parse_rawfile(raw_path)
        except Exception as e:  # noqa: BLE001 — surface any parse failure to the UI
            return {"status": "error", "error": f"could not parse ngspice output: {e}",
                    "cir": conv["cir"]}

    if plot_nodes:
        want = {n.lower() for n in plot_nodes}
        signals = {k: v for k, v in signals.items() if k.lower() in want}

    return {
        "status": "ok",
        "time": time,
        "signals": signals,
        "nodes": conv["nodes"],
        "replacements": conv["replacements"],
        "warnings": conv["warnings"],
        "cir": conv["cir"],
    }


def _inject_control(cir: str, raw_path: pathlib.Path) -> str:
    """Append a control block that runs the analysis and writes an ASCII rawfile."""
    out = [ln for ln in cir.rstrip().splitlines() if ln.strip().lower() != ".end"]
    out += [
        ".control",
        "run",
        "set filetype=ascii",
        f"write {raw_path}",
        ".endc",
        ".end",
    ]
    return "\n".join(out) + "\n"


def parse_rawfile(path: pathlib.Path) -> tuple[list[float], dict[str, list[float]]]:
    """Parse an ngspice rawfile (ASCII primary, binary fallback) into
    (time[], {label: values[]}). The first variable of a .tran run is time."""
    data = path.read_bytes()
    for marker, binary in ((b"Values:", False), (b"Binary:", True)):
        if marker in data:
            head, rest = data.split(marker, 1)
            return _parse_body(head.decode("latin-1"), rest, binary)
    raise ValueError("no Values:/Binary: section")


def _parse_body(header: str, rest: bytes, binary: bool):
    nvars = npoints = 0
    names: list[str] = []
    types: list[str] = []
    in_vars = False
    for line in header.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("no. variables:"):
            nvars = int(s.split(":")[1])
        elif low.startswith("no. points:"):
            npoints = int(s.split(":")[1])
        elif low.startswith("variables:"):
            in_vars = True
        elif in_vars and s:
            parts = s.split()
            if len(parts) >= 2:
                names.append(_clean_name(parts[1]))
                types.append(parts[2].lower() if len(parts) >= 3 else "")

    cols: list[list[float]] = [[] for _ in range(nvars)]
    if binary:
        # A single newline separates the "Binary:" marker from the raw f64 block.
        if rest.startswith(b"\r\n"):
            rest = rest[2:]
        elif rest.startswith(b"\n"):
            rest = rest[1:]
        vals = struct.unpack(f"<{npoints * nvars}d", rest[: npoints * nvars * 8])
        for i, v in enumerate(vals):
            cols[i % nvars].append(v)
    else:
        toks = rest.split()
        group = nvars + 1  # leading point index + nvars values
        for p in range(npoints):
            base = p * group
            if base + group > len(toks):
                break
            for j in range(nvars):
                cols[j].append(float(toks[base + 1 + j]))

    time = cols[0] if cols else []
    # Keep node voltages only; drop voltage-source branch currents ngspice also records.
    signals = {names[i]: cols[i] for i in range(1, nvars) if types[i] != "current"}
    return time, signals


def _clean_name(raw: str) -> str:
    m = re.fullmatch(r"[vi]\((.+)\)", raw, re.I)
    return m.group(1) if m else raw
