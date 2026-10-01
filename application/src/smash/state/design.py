"""Design — top-level container for the design state.

Bundles three API helpers that exist purely to serve the Design
object: `BoardView` (tile-scoped lens), `NetHandle` (fluent
connect builder), and the built-in `@validator` checks. None of
these are state — they only exist as a thin API surface, so they
live alongside Design rather than in their own modules.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Callable

from smash.state.battery import Battery
from smash.state.chip import Chip
from smash.state.footprint import Footprint
from smash.state.issue import Issue
from smash.state.net import Net, NET_KINDS
from smash.state.pad import Pad
from smash.state.pin import Pin
from smash.state.validators import validator, VALIDATORS


class BoardView:
    """Thin view onto one tile of a Design. Provides chip lookup
    scoped to the board_tag. The actual Chip records live in
    `design.chips` (flat); this view just filters by board_tag and
    adds readable accessors.

    A BoardView does NOT own the chips — it's a lens, not a container.
    Mutations go through the Design as usual.
    """

    def __init__(self, design: "Design", board_tag: str):
        self.design = design
        self.board_tag = board_tag

    def chip(self, ref: str) -> Chip:
        """Look up a Chip on this board by KiCad reference. Raises
        if the chip isn't on this tile (or doesn't exist)."""
        chip = self.design.chip_by_ref(ref)
        if chip is None:
            raise KeyError(f"no chip {ref!r} in design")
        if chip.board_tag != self.board_tag:
            raise KeyError(
                f"chip {ref!r} is on {chip.board_tag!r}, "
                f"not {self.board_tag!r}")
        return chip

    @property
    def chips(self) -> list:
        """Every Chip on this tile (filtered from design.chips by
        board_tag)."""
        return self.design.chips_on_board(self.board_tag)


# ── net handle (fluent connect helper) ────────────────────────────────────

class NetHandle:
    """Returned by `Design.add_net()` so callers can chain
    `.connect()` calls. Thin wrapper that forwards to Design."""

    def __init__(self, design: "Design", net: Net):
        self.design = design
        self.net = net

    def connect(self, pin: Pin, *,
                af: str | None = None,
                intent: str | None = None) -> "NetHandle":
        """Wire one Pin onto this net. Returns self for chaining.

            design.add_signal_net("WIFI_SDIO_CLK") \\
                  .connect(mpu.pin("PE3"),
                           af="SDMMC1_CK",
                           intent="WiFi SDIO clock to Murata module") \\
                  .connect(wifi.pin("SDIO_CLK"))

        `af` is the structured alternate-function name (programmable AF
        on STM32 GPIOs). Validated against `Pin.alt_functions` by the
        pinmux validator. Use `af="GPIO"` for pins explicitly muxed to
        plain digital I/O.

        `intent` is free-form human prose describing what this wire
        does ("clock to TCAN chip", "active-low reset to AR0234").
        Pure documentation — never typechecked.
        """
        self.design.connect(self.net.name, pin, af=af, intent=intent)
        return self

    def connect_all(self, pins, *,
                    af: str | None = None,
                    intent: str | None = None) -> "NetHandle":
        """Wire every Pin in the iterable onto this net. Designed for
        power / ground rails where a chip has many same-named pins:

            design.add_power_net("VDD", voltage_v=3.3) \\
                  .connect_all(mcu.pins_by_name("VDD")) \\
                  .connect_all(mcu.pins_by_name("VDDA"))

        `af` and `intent` apply to every Pin in the iterable — useful
        when annotating a whole bus or supply rail with one phrase.
        """
        for p in pins:
            self.design.connect(self.net.name, p, af=af, intent=intent)
        return self

    @property
    def name(self) -> str:
        return self.net.name


# ── design (top level) ────────────────────────────────────────────────────

class Design:
    """Canonical electrical snapshot — chips, nets, and any cross-
    design rules. Loaded from a serialized sidecar via
    `Design.load_json()` or built natively via `add_chip()` /
    `add_*_net()`.
    """

    def __init__(self, *, apply_assumptions: bool = True):
        self.chips: list = []                # list[Chip]
        self.batteries: list = []            # list[Battery]
        self.antennas: list = []             # list[Antenna]
        self.nets: list = []                 # list[Net]
        # When False, `add_chip` / `add_battery` skip the
        # smash/data/assumptions.json overlay so factories produce
        # their raw ground-truth output. Tests use this to assert
        # the un-overlaid surface (price/currency/fab_country = None
        # for parts the catalog hasn't curated by hand).
        self.apply_assumptions: bool = apply_assumptions
        # No separate footprint library — each Chip / Battery owns its
        # footprint inline (Chip.footprint is a Footprint object, not a
        # string). Library / catalog concerns live in the upstream
        # producer (SamacSys ingest, KiCad parser), not in design state.

    # ── chip producer ───────────────────────────────────────────────

    def add_chip(self,
                 ref: str,
                 *,
                 manf_pn: str | None = None,
                 footprint: "Footprint | None" = None,
                 board_tag: str | None = None,
                 pins: list | None = None,
                 **fields) -> Chip:
        """Add one component to the design.

        `footprint` is a `Footprint` instance (or None — chip not yet
        ready to place). `pins` is a list of either Pin dataclasses or
        (num, name) tuples — pins start unconnected (net=None) and are
        wired up via a Net constructor's `.connect()` afterwards.

        Any additional Chip field (manf, description, datasheet,
        fab_*, price_*, package, weight_g, p_active_w, dnp, feature,
        etc.) is accepted as a keyword argument.

        Raises if `ref` is already in use, or if `footprint` is a
        non-None non-Footprint (catches stale callers passing strings).
        """
        if any(c.ref == ref for c in self.chips):
            raise ValueError(f"duplicate chip ref: {ref!r}")
        if footprint is not None and not isinstance(footprint, Footprint):
            raise TypeError(
                f"footprint must be a Footprint instance (or None), "
                f"got {type(footprint).__name__}: {footprint!r}")
        if footprint is not None:
            # Apply any per-footprint courtyard-growth override (idempotent,
            # no-op for un-listed footprints) here so it covers every factory
            # uniformly, before the part is placed.
            footprint.apply_courtyard_growth()
        pin_objs: list = []
        for pin in (pins or []):
            if isinstance(pin, Pin):
                pin_objs.append(pin)
            elif isinstance(pin, tuple):
                num, name = pin[0], (pin[1] if len(pin) > 1 else None)
                pin_objs.append(Pin(num=str(num), name=name))
            else:
                pin_objs.append(Pin(num=str(pin)))
        # Set the chip_ref back-reference on every pin so callers can
        # pass the Pin object directly to Design.connect().
        for p in pin_objs:
            p.chip_ref = ref
        # Validate pin-number / pin-name namespace separation: no pin's
        # `num` may collide with another pin's `name` or alias on the
        # same chip. A collision means `chip.pin(key)` becomes ambiguous
        # at the call site — the factory must namespace one side or the
        # other (e.g. prefix BGA ball coords with "BALL_") to fix.
        nums = {p.num for p in pin_objs}
        for p in pin_objs:
            names_here = {p.name, *p.aliases} - {None}
            collision = names_here & nums
            # A pin's own name/alias may equal its own num (e.g. SOIC
            # pin "1" with name "1") — that's harmless. Only flag cases
            # where the collision points to a DIFFERENT pin.
            real_collisions = {
                k for k in collision
                if any(o.num == k and o is not p for o in pin_objs)
            }
            if real_collisions:
                examples = []
                for k in sorted(real_collisions):
                    other = next(o for o in pin_objs
                                 if o.num == k and o is not p)
                    examples.append(
                        f"{k!r}: pin name on {p.num!r} (= {p.name!r}) "
                        f"AND ball-coord of pin {other.num!r} "
                        f"(= {other.name!r})"
                    )
                raise ValueError(
                    f"add_chip({ref!r}): pin-name vs pin-number namespace "
                    f"collision — `chip.pin(key)` would silently return "
                    f"the wrong pin. Fix the factory: rename one side or "
                    f"namespace ball coords (e.g. prefix with 'BALL_'). "
                    f"Collisions: {'; '.join(examples)}"
                )
        chip = Chip(ref=ref, manf_pn=manf_pn, footprint=footprint,
                    board_tag=board_tag, pins=pin_objs, **fields)
        # Layer in soft sourcing data (price, fab country, ...) from
        # smash/data/assumptions.json. Skipped if the Design was
        # constructed with `apply_assumptions=False` (tests asserting
        # the raw factory surface). Lazy import avoids a circular
        # dependency between smash.parts and smash.state.
        if self.apply_assumptions:
            from smash.parts._assumptions import apply as _apply_assumptions
            _apply_assumptions(chip)
        self.chips.append(chip)
        return chip

    def add_battery(self,
                    ref: str,
                    *,
                    manf_pn: str | None = None,
                    board_tag: str | None = None,
                    pins: list | None = None,
                    **fields) -> Battery:
        """Add a Battery (primary or secondary cell). Same shape as
        add_chip — pins are normalized, ref uniqueness enforced
        across BOTH chips and batteries.

        Default pins for a 2-terminal cell:
            [Pin(num="1", name="+"), Pin(num="2", name="-")]
        unless `pins` is given explicitly.
        """
        # Refs must be unique across the union of chips + batteries.
        if any(c.ref == ref for c in self.chips):
            raise ValueError(f"ref {ref!r} already used by a chip")
        if any(b.ref == ref for b in self.batteries):
            raise ValueError(f"duplicate battery ref: {ref!r}")
        # If a Footprint was passed inline, validate its type
        fp_arg = fields.get("footprint")
        if fp_arg is not None and not isinstance(fp_arg, Footprint):
            raise TypeError(
                f"footprint must be a Footprint instance (or None), "
                f"got {type(fp_arg).__name__}: {fp_arg!r}")
        if pins is None:
            pins = [Pin(num="1", name="+"), Pin(num="2", name="-")]
        pin_objs: list = []
        for pin in pins:
            if isinstance(pin, Pin):
                pin_objs.append(pin)
            elif isinstance(pin, tuple):
                num, name = pin[0], (pin[1] if len(pin) > 1 else None)
                pin_objs.append(Pin(num=str(num), name=name))
            else:
                pin_objs.append(Pin(num=str(pin)))
        for p in pin_objs:
            p.chip_ref = ref          # same back-ref scheme as chips
        bat = Battery(ref=ref, manf_pn=manf_pn, board_tag=board_tag,
                      pins=pin_objs, **fields)
        if self.apply_assumptions:
            from smash.parts._assumptions import apply as _apply_assumptions
            _apply_assumptions(bat)
        self.batteries.append(bat)
        return bat

    def add_antenna(self,
                    ref: str,
                    *,
                    manf_pn: str | None = None,
                    board_tag: str | None = None,
                    pins: list | None = None,
                    **fields) -> "Antenna":
        """Add an Antenna (RF radiator). Same shape as add_chip /
        add_battery — pins normalised, ref uniqueness enforced across
        chips + batteries + antennas. Default pin set: a single feed pin
        `Pin(num="1", name="FEED")` unless `pins` is passed explicitly.
        """
        # Lazy import — same circular-dependency story as add_chip.
        from smash.state.antenna import Antenna
        if any(c.ref == ref for c in self.chips):
            raise ValueError(f"ref {ref!r} already used by a chip")
        if any(b.ref == ref for b in self.batteries):
            raise ValueError(f"ref {ref!r} already used by a battery")
        if any(a.ref == ref for a in self.antennas):
            raise ValueError(f"duplicate antenna ref: {ref!r}")
        fp_arg = fields.get("footprint")
        if fp_arg is not None and not isinstance(fp_arg, Footprint):
            raise TypeError(
                f"footprint must be a Footprint instance (or None), "
                f"got {type(fp_arg).__name__}: {fp_arg!r}")
        if pins is None:
            pins = [Pin(num="1", name="FEED")]
        pin_objs: list = []
        for pin in pins:
            if isinstance(pin, Pin):
                pin_objs.append(pin)
            elif isinstance(pin, tuple):
                num, name = pin[0], (pin[1] if len(pin) > 1 else None)
                pin_objs.append(Pin(num=str(num), name=name))
            else:
                pin_objs.append(Pin(num=str(pin)))
        for p in pin_objs:
            p.chip_ref = ref          # same back-ref scheme as chips
        ant = Antenna(ref=ref, manf_pn=manf_pn, board_tag=board_tag,
                      pins=pin_objs, **fields)
        if self.apply_assumptions:
            from smash.parts._assumptions import apply as _apply_assumptions
            _apply_assumptions(ant)
        self.antennas.append(ant)
        return ant

    # ── footprint accessor ─────────────────────────────────────────

    def footprint_of(self, component) -> Footprint | None:
        """Thin accessor — returns whatever Footprint a component
        carries inline, or None if it doesn't have one yet. Kept on
        Design so consumers don't have to know whether a component
        is a Chip or Battery to pull its footprint."""
        if component is None:
            return None
        fp = getattr(component, "footprint", None)
        return fp if isinstance(fp, Footprint) else None

    # ── net producers (typed) ────────────────────────────────────────

    def _add_net(self, net: Net) -> "NetHandle":
        if any(n.name == net.name for n in self.nets):
            raise ValueError(f"duplicate net name: {net.name!r}")
        self.nets.append(net)
        return NetHandle(self, net)

    def add_net(self, name: str, **fields) -> "NetHandle":
        """Generic net (kind='signal' by default). Prefer one of the
        typed constructors below when the role is known."""
        return self._add_net(Net(name=name, **fields))

    def add_power_net(self, name: str, voltage_v: float,
                      **fields) -> "NetHandle":
        """Voltage rail. `voltage_v` is the nominal in V (e.g. 1.35
        for VDD_DDR, 3.3 for COMP_3V3). Defaults to its own netclass
        if no plane is yet defined."""
        return self._add_net(Net(name=name, kind="power",
                                 voltage_v=voltage_v, **fields))

    def add_ground_net(self, name: str = "GND", **fields) -> "NetHandle":
        """Ground / return-current net. Multiple grounds (GND, AGND,
        FLEX_GND) are allowed — each is its own Net with kind='ground'."""
        return self._add_net(Net(name=name, kind="ground", **fields))

    def add_signal_net(self, name: str, **fields) -> "NetHandle":
        """Single-ended signal with no group / no special routing
        constraints beyond its netclass."""
        return self._add_net(Net(name=name, kind="signal", **fields))

    def add_bus_net(self, name: str, *,
                    bus_group: str,
                    bit_index: int | None = None,
                    impedance_ohms: float | None = None,
                    length_match_group: str | None = None,
                    **fields) -> "NetHandle":
        """One bit of a parallel bus. `bus_group` is the bus this net
        belongs to (e.g. 'DDR3_ADDR', 'DDR3_BYTE0', 'MIPI_CSI_DATA').
        `bit_index` is the bus-bit position (0..N).

        `length_match_group` is the name of the length-match cohort
        (often == bus_group, but byte lanes group separately).
        Defaults to `bus_group` if not given."""
        if length_match_group is None:
            length_match_group = bus_group
        return self._add_net(Net(name=name, kind="bus",
                                 bus_group=bus_group, bit_index=bit_index,
                                 impedance_ohms=impedance_ohms,
                                 length_match_group=length_match_group,
                                 **fields))

    def add_diff_pair(self, p_name: str, n_name: str, *,
                      impedance_ohms: float = 100.0,
                      bus_group: str | None = None,
                      length_match_group: str | None = None,
                      **fields) -> tuple:
        """Differential pair — creates BOTH legs at once with
        cross-references via `diff_pair`. Returns (p_handle, n_handle)
        so callers can `.connect()` each end:

            ck_p, ck_n = design.add_diff_pair("DDR3_CK_P","DDR3_CK_N")
            ck_p.connect("U_MPU","K1").connect("U_DDR3","M8")
            ck_n.connect("U_MPU","K2").connect("U_DDR3","N8")
        """
        p = self._add_net(Net(name=p_name, kind="diff",
                              diff_pair=n_name,
                              impedance_ohms=impedance_ohms,
                              bus_group=bus_group,
                              length_match_group=length_match_group,
                              **fields))
        n = self._add_net(Net(name=n_name, kind="diff",
                              diff_pair=p_name,
                              impedance_ohms=impedance_ohms,
                              bus_group=bus_group,
                              length_match_group=length_match_group,
                              **fields))
        return p, n

    def add_clock_net(self, name: str, *,
                      frequency_hz: float | None = None,
                      impedance_ohms: float | None = None,
                      length_match_group: str | None = None,
                      **fields) -> "NetHandle":
        """Clock / strobe net. Carries timing constraints; usually
        impedance-controlled and length-matched against its bus.

        `frequency_hz` declares the nominal frequency this net carries
        (e.g. 8e6 for an 8 MHz HSE, 32768 for an LSE). The
        `_v_clock_pin_frequency` validator cross-checks it against
        connected chips' clock-input ranges (per pinspec).
        """
        return self._add_net(Net(name=name, kind="clock",
                                 frequency_hz=frequency_hz,
                                 impedance_ohms=impedance_ohms,
                                 length_match_group=length_match_group,
                                 **fields))

    # ── connection primitive ────────────────────────────────────────

    def connect(self, net_name: str, *pin_objs,
                af: str | None = None,
                intent: str | None = None) -> None:
        """Wire one or more Pin objects onto `net_name`. Takes Pin
        records directly — no string lookups, no ambiguity between
        same-named pins on different chips/batteries. Each Pin carries
        its own back-reference (Chip.ref or Battery.ref).

            mpu = design.chip_by_ref("U_MPU")
            bat = design.battery_by_ref("BT1")
            design.connect("DDR3_A0", mpu.pin("DDR_A0"), ddr.pin("A0"))
            design.connect("BAT_RAW", bat.pin("+"), efuse.pin("VIN"))

        Optional kwargs (applied to every Pin in the call):

          `af`: structured alternate-function name — the AF the firmware
                programs the MCU register to (e.g. "SDMMC1_CK", "GPIO").
                Validated against `Pin.alt_functions` by the pinmux
                validator. Use `"GPIO"` for plain digital I/O.
          `intent`: free-form human description ("clock to TCAN chip",
                "active-low reset to AR0234"). Pure documentation.

        Updates both the Net's pin list AND each Pin's `net` /
        `af_assigned` / `intent` fields so consumers can navigate
        either way."""
        net = self.net_by_name(net_name)
        if net is None:
            # Net doesn't exist by this name — but it may exist as an
            # alias on another net (from a prior merge). Find it.
            for n in self.nets:
                if net_name in n.aliases:
                    net = n
                    break
        if net is None:
            net = Net(name=net_name)
            self.nets.append(net)

        for pin in pin_objs:
            if not isinstance(pin, Pin):
                raise TypeError(
                    f"connect() takes Pin objects, got {type(pin).__name__}: "
                    f"{pin!r} — use chip.pin('name_or_num') to retrieve")
            if pin.chip_ref is None:
                raise ValueError(
                    f"Pin {pin.num!r} has no chip_ref back-reference — "
                    f"was it added to a Chip / Battery via the Design API?")

            pin_key = (pin.chip_ref, pin.num)

            # If this pin is already on a DIFFERENT net, merge the two:
            # the destination net (`net`) absorbs the other net's pins,
            # its name, and its aliases. Same electrical net, two
            # design-time names — both remembered.
            other = self._net_holding_pin(pin_key)
            if other is not None and other is not net:
                # Move every pin from `other` into `net` (deduped).
                for ref_num in other.pins:
                    if ref_num not in net.pins:
                        net.pins.append(ref_num)
                # Other's name + aliases become aliases on `net`.
                for n in [other.name, *other.aliases]:
                    if n != net.name and n not in net.aliases:
                        net.aliases.append(n)
                # Update every pin that was pointing at `other` so its
                # `pin.net` back-ref now names the surviving net.
                for ref_num in other.pins:
                    chip = self.chip_by_ref(ref_num[0]) \
                           or self.battery_by_ref(ref_num[0])
                    if chip is None:
                        continue
                    for p in chip.pins:
                        if p.num == ref_num[1] and p.net == other.name:
                            p.net = net.name
                self.nets.remove(other)

            if pin_key not in net.pins:
                net.pins.append(pin_key)
            pin.net = net.name
            if af is not None:
                pin.af_assigned = af
            if intent is not None:
                pin.intent = intent

    def _net_holding_pin(self, pin_key) -> "Net | None":
        """Return the existing Net that already has `pin_key`, or None."""
        for n in self.nets:
            if pin_key in n.pins:
                return n
        return None

    def merge_nets(self, name_a: str, name_b: str) -> "NetHandle":
        """Merge two named nets into a single electrical node. Both names
        survive as aliases on the surviving Net so downstream consumers
        can look the net up by either name.

        Mirrors SKiDL's `net_a += net_b` net-to-net merge in `system.py`.
        Use cases: declaring `FLEX_GND` as an alias of `GND` for parts on
        the flex side of the rigid-flex; tying `VDDA` rails into the
        common `VDD` plane.

        The net named `name_a` is kept as the surviving Net; `name_b`'s
        pins move into it and `name_b` becomes an alias. Use the lex-min
        of the two names as `name_a` to keep the canonical-netlist
        primary name stable across runs (the canonical writer picks the
        lex-min of `{name, *aliases}` regardless of which is "primary"
        in memory).

        Returns a NetHandle for the merged net. No-op if both names
        already resolve to the same Net.
        """
        net_a = self.net_by_name(name_a)
        if net_a is None:
            for n in self.nets:
                if name_a in n.aliases:
                    net_a = n
                    break
        if net_a is None:
            net_a = Net(name=name_a)
            self.nets.append(net_a)

        net_b = self.net_by_name(name_b)
        if net_b is None:
            for n in self.nets:
                if name_b in n.aliases:
                    net_b = n
                    break
        if net_b is None:
            # name_b doesn't exist yet — just add it as an alias on a.
            if name_b not in net_a.aliases and name_b != net_a.name:
                net_a.aliases.append(name_b)
            return NetHandle(self, net_a)

        if net_b is net_a:
            return NetHandle(self, net_a)

        # Absorb b into a.
        for ref_num in net_b.pins:
            if ref_num not in net_a.pins:
                net_a.pins.append(ref_num)
        for n in [net_b.name, *net_b.aliases]:
            if n != net_a.name and n not in net_a.aliases:
                net_a.aliases.append(n)
        for ref_num in net_b.pins:
            chip = self.chip_by_ref(ref_num[0]) \
                   or self.battery_by_ref(ref_num[0])
            if chip is None:
                continue
            for p in chip.pins:
                if p.num == ref_num[1] and p.net == net_b.name:
                    p.net = net_a.name
        self.nets.remove(net_b)
        return NetHandle(self, net_a)

    # ── lookup helpers ───────────────────────────────────────────────

    def chip_by_ref(self, ref: str) -> Chip | None:
        for c in self.chips:
            if c.ref == ref:
                return c
        return None

    def battery_by_ref(self, ref: str) -> "Battery | None":
        for b in self.batteries:
            if b.ref == ref:
                return b
        return None

    def component_by_ref(self, ref: str):
        """Look up either a Chip or a Battery by ref. Returns whichever
        type holds the record, or None if neither has it."""
        return self.chip_by_ref(ref) or self.battery_by_ref(ref)

    def net_by_name(self, name: str) -> Net | None:
        for n in self.nets:
            if n.name == name:
                return n
        return None

    def chips_on_board(self, board_tag: str) -> list:
        return [c for c in self.chips if c.board_tag == board_tag]

    def batteries_on_board(self, board_tag: str) -> list:
        return [b for b in self.batteries if b.board_tag == board_tag]

    def populated_chips(self) -> list:
        return [c for c in self.chips if not c.dnp]

    def populated_batteries(self) -> list:
        return [b for b in self.batteries if not b.dnp]

    def apply_default_underfill(self, *, material: str | None = None,
                                fab=None) -> int:
        """Tag every chip lacking an explicit `underfill` with a default
        material (the FabProfile's first underfill — Loctite Eccobond
        UF1173 in the stock catalog). Conservative: over-applies, since
        the board's vacuum-potting underfills everything by capillary
        anyway. Skips chips without a footprint (they can't be
        physically underfilled). Returns the number of chips tagged.
        Per-chip overrides set before this call are preserved."""
        from smash.state.fab import default_fab_profile
        prof = fab or default_fab_profile()
        if material is None:
            if not prof.adhesives:
                raise ValueError(
                    f"{prof.name}: no adhesives stocked — can't pick default")
            material = next((a.name for a in prof.adhesives
                             if a.role == "underfill"),
                            prof.adhesives[0].name)
        count = 0
        for c in self.chips:
            if c.underfill is None and c.footprint is not None:
                c.underfill = material
                count += 1
        return count

    def nets_by_bus(self, bus_group: str) -> list:
        return [n for n in self.nets if n.bus_group == bus_group]

    # ── navigable hierarchy: design.board(tag).chip(ref).pin(name) ──

    def board(self, board_tag: str) -> "BoardView":
        """Return a navigable view scoped to one tile. Use for
        readable build code:

            mpu = design.board("companion_compute").chip("U_MPU")
            ddr = design.board("companion_compute").chip("U_DDR3")
            design.add_bus_net("DDR3_A0", bus_group="DDR3_ADDR") \\
                  .connect(mpu.pin("DDR_A0")).connect(ddr.pin("A0"))
        """
        return BoardView(self, board_tag)

    # ── validation ───────────────────────────────────────────────────

    def validate(self, extra: list | None = None) -> list:
        """Run every registered validator against this design plus any
        extras passed in. Returns the flat list of issues found."""
        issues: list = []
        for fn in VALIDATORS + (extra or []):
            for issue in (fn(self) or []):
                issues.append(issue)
        return issues

    # ── serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "chips":     [c.to_dict() for c in self.chips],
            "batteries": [b.to_dict() for b in self.batteries],
            "nets":      [n.to_dict() for n in self.nets],
        }

    def dump_json(self, path: pathlib.Path | str) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @staticmethod
    def _footprint_from_dict(fp_d: dict) -> "Footprint":
        """Reconstruct a Footprint dataclass from a serialized dict."""
        pads = []
        for pad_d in fp_d.get("pads", []) or []:
            pad_kw = dict(pad_d)
            pad_kw["position_mm"] = tuple(pad_kw["position_mm"])
            pad_kw["size_mm"]     = tuple(pad_kw["size_mm"])
            pads.append(Pad(**pad_kw))
        fp_kw = {k: v for k, v in fp_d.items() if k != "pads"}
        if fp_kw.get("size_mm") is not None:
            fp_kw["size_mm"] = tuple(fp_kw["size_mm"])
        fp_kw["body_outline"] = [tuple(pt) for pt in (fp_kw.get("body_outline") or [])]
        fp_kw["courtyard"]    = [tuple(pt) for pt in (fp_kw.get("courtyard")    or [])]
        return Footprint(pads=pads, **fp_kw)

    @classmethod
    def load_json(cls, path: pathlib.Path | str) -> "Design":
        data = json.loads(pathlib.Path(path).read_text())
        d = cls()
        for cd in data.get("chips", []):
            pins = [Pin(**pin_d) for pin_d in cd.get("pins", [])]
            cd2 = {k: v for k, v in cd.items() if k != "pins"}
            # Restore tuple shapes
            if cd2.get("size_mm") is not None:
                cd2["size_mm"] = tuple(cd2["size_mm"])
            if cd2.get("temp_range_c") is not None:
                cd2["temp_range_c"] = tuple(cd2["temp_range_c"])
            # Inline footprint serialized as a nested dict — rebuild
            if isinstance(cd2.get("footprint"), dict):
                cd2["footprint"] = cls._footprint_from_dict(cd2["footprint"])
            d.chips.append(Chip(pins=pins, **cd2))
        for bd in data.get("batteries", []):
            pins = [Pin(**pin_d) for pin_d in bd.get("pins", [])]
            bd2 = {k: v for k, v in bd.items() if k != "pins"}
            if bd2.get("size_mm") is not None:
                bd2["size_mm"] = tuple(bd2["size_mm"])
            if bd2.get("temp_range_c") is not None:
                bd2["temp_range_c"] = tuple(bd2["temp_range_c"])
            if bd2.get("position_mm") is not None:
                bd2["position_mm"] = tuple(bd2["position_mm"])
            if bd2.get("pad_bbox") is not None:
                bd2["pad_bbox"] = tuple(bd2["pad_bbox"])
            if bd2.get("courtyard_bbox") is not None:
                bd2["courtyard_bbox"] = tuple(bd2["courtyard_bbox"])
            if isinstance(bd2.get("footprint"), dict):
                bd2["footprint"] = cls._footprint_from_dict(bd2["footprint"])
            d.batteries.append(Battery(pins=pins, **bd2))
        for nd in data.get("nets", []):
            nd2 = dict(nd)
            nd2["pins"] = [tuple(p) for p in nd.get("pins", [])]
            d.nets.append(Net(**nd2))
        return d


# ── built-in validators ───────────────────────────────────────────────────

@validator
def _v_no_floating_chips(design: Design):
    """Every chip should have at least one pin connected to a non-
    autogenerated net. Pure-floating chips are usually a wiring miss."""
    for c in design.chips:
        if c.dnp:
            continue
        nets = {pin.net for pin in c.pins if pin.net}
        real = {n for n in nets if n and not n.startswith(("N$", "Net-"))}
        if not real and len(c.pins) >= 2:
            yield Issue(
                severity="warning",
                rule="floating_chip",
                message=f"{c.ref} ({c.manf_pn or c.value}) has no real "
                        f"net connections (all pins autogenerated)",
                refs=[c.ref],
            )


@validator
def _v_unique_refs(design: Design):
    """No two chips may share a KiCad reference."""
    seen: dict = {}
    for c in design.chips:
        if c.ref in seen:
            yield Issue(
                severity="error",
                rule="duplicate_ref",
                message=f"duplicate chip reference {c.ref!r}",
                refs=[c.ref],
            )
        else:
            seen[c.ref] = c


@validator
def _v_datasheet_required(design: Design):
    """Every commercial IC (≥ 4 pads, non-DNP) should have a datasheet
    attached. Project-internal mechanical pad clusters (manf='project',
    no manf_pn) are skipped — they're custom geometry from the project's
    own CAD, not a sourced part."""
    for c in design.chips:
        if c.dnp or len(c.pins) < 4:
            continue
        if c.manf == "project" or not c.manf_pn:
            continue
        if not c.datasheet:
            yield Issue(
                severity="warning",
                rule="missing_datasheet",
                message=f"{c.ref} ({c.manf_pn or c.value}) has no "
                        f"datasheet path — add one in Research/",
                refs=[c.ref],
            )


@validator
def _v_fab_country_allowed(design: Design):
    """Block chips fab'd in countries our sourcing policy excludes.

    Policy lives in the function — not as a SourcingPolicy data object —
    because it's a fixed rule that doesn't vary per-design. To change
    the rule (e.g. re-allow TW after geopolitical shift), edit this
    function. The forbidden set is the inverse of "everything else
    allowed."

    `fab_country` strings use the convention "FR/IT" (multi-country
    assembly), "USA (Micron Lehi UT)" (with location detail), etc.
    We split on '/' and strip parenthetical location detail to get the
    country tokens; flag if ANY of them is forbidden.
    """
    import re
    FORBIDDEN = {"CN", "TW"}                # TSMC / annexation risk
    paren_rx = re.compile(r"\s*\(.*?\)")
    for c in design.chips:
        if not c.fab_country:
            continue
        cleaned = paren_rx.sub("", c.fab_country).strip()
        countries = {x.strip() for x in cleaned.split("/")}
        bad = countries & FORBIDDEN
        if bad:
            yield Issue(
                severity="error",
                rule="forbidden_fab",
                message=f"{c.ref} ({c.manf_pn}) sourced from "
                        f"{'/'.join(sorted(bad))} (forbidden by "
                        f"sourcing policy)",
                refs=[c.ref],
            )


@validator
def _v_substitute_consistency(design: Design):
    """If a chip declares `substitutes`, each entry should be a
    (manf_pn, reason) tuple with the substitute different from the
    chip's actual manf_pn (otherwise it's a degenerate self-reference).
    """
    for c in design.chips:
        if not c.substitutes:
            continue
        for entry in c.substitutes:
            if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
                yield Issue(
                    severity="error", rule="substitute_malformed",
                    message=f"{c.ref}: substitute entry {entry!r} "
                            f"isn't a (manf_pn, reason) tuple",
                    refs=[c.ref])
                continue
            sub_pn, _reason = entry
            if sub_pn == c.manf_pn:
                yield Issue(
                    severity="warning", rule="substitute_self",
                    message=f"{c.ref}: substitute {sub_pn!r} equals "
                            f"this chip's manf_pn — remove the entry",
                    refs=[c.ref])


@validator
def _v_pins_match_footprint_pads(design: Design):
    """For each component with a resolved footprint, every Pin.num
    must correspond to a real Pad on that footprint. Catches stale
    pin renames after a footprint swap.

    Strips the smash-internal `BALL_` prefix on pin numbers — that
    prefix is a smash-side namespace marker (see
    `_namespace_ball_collisions` in `smash.parts.flash`), the
    footprint side stores the raw ball coord.
    """
    components = list(design.chips) + list(getattr(design, "batteries", [])) + list(getattr(design, "antennas", []))
    for c in components:
        fp = design.footprint_of(c)
        if fp is None:
            continue
        pad_nums = {p.num for p in fp.pads}
        for pin in c.pins:
            num = pin.num[len("BALL_"):] if pin.num.startswith("BALL_") else pin.num
            if num not in pad_nums:
                yield Issue(
                    severity="error",
                    rule="pin_pad_mismatch",
                    message=f"{c.ref}: pin {pin.num!r} ({pin.name}) "
                            f"has no matching pad on footprint "
                            f"{fp.name!r}",
                    refs=[c.ref],
                )


@validator
def _v_diff_pairs_symmetric(design: Design):
    """Every kind='diff' net must reference a partner that also exists
    and points back. Catches half-declared pairs."""
    for n in design.nets:
        if n.kind != "diff":
            continue
        if not n.diff_pair:
            yield Issue(severity="error", rule="diff_no_partner",
                        message=f"diff net {n.name!r} has no diff_pair set",
                        refs=[n.name])
            continue
        partner = design.net_by_name(n.diff_pair)
        if partner is None:
            yield Issue(severity="error", rule="diff_partner_missing",
                        message=f"diff net {n.name!r} → partner "
                                f"{n.diff_pair!r} not in design",
                        refs=[n.name])
        elif partner.diff_pair != n.name:
            yield Issue(severity="error", rule="diff_asymmetric",
                        message=f"diff pair asymmetric: {n.name!r}→"
                                f"{n.diff_pair!r} but {partner.name!r}→"
                                f"{partner.diff_pair!r}",
                        refs=[n.name, partner.name])


@validator
def _v_pin_type_vs_net_kind(design: Design):
    """Catch wiring mistakes: a power-type pin on a non-power net, or
    a ground-type pin on a non-ground net.

    Symmetric with the user's intent ("don't connect signal to power"):
    if a regulator's `VOUT` pin (Pin.type='power') lands on a net that
    was created with `add_signal_net`, the net almost certainly should
    have been a power net — the developer either forgot to use
    `add_power_net` or wired the wrong pin.

    Signal-type and io-type pins are free to land on any net (a logic
    output tying high to VDD is normal; a strap input pulled to GND is
    normal). The validator only flags the unambiguous mistakes:
    `power` pin or `ground` pin connecting to a net of the wrong kind.
    """
    for n in design.nets:
        # `power` and `ground` net kinds are the only ones this check
        # speaks to. `bus`, `clock`, `diff` carry signal pins — never
        # power.
        for ref, pin_num in n.pins:
            chip = design.chip_by_ref(ref) or design.battery_by_ref(ref)
            if chip is None:
                continue
            pin = next((p for p in chip.pins if p.num == pin_num), None)
            if pin is None or pin.type is None:
                continue
            if pin.type == "power" and n.kind != "power":
                yield Issue(
                    severity="error",
                    rule="power_pin_on_non_power_net",
                    message=(
                        f"net {n.name!r} (kind={n.kind!r}) carries "
                        f"power-type pin {ref}.{pin_num} "
                        f"({pin.name!r}) — either mark the net "
                        f"`kind='power'` (via add_power_net) or check "
                        f"whether the wrong pin was wired"
                    ),
                    refs=[n.name, ref],
                )
            elif pin.type == "ground" and n.kind != "ground":
                yield Issue(
                    severity="error",
                    rule="ground_pin_on_non_ground_net",
                    message=(
                        f"net {n.name!r} (kind={n.kind!r}) carries "
                        f"ground-type pin {ref}.{pin_num} "
                        f"({pin.name!r}) — either mark the net "
                        f"`kind='ground'` (via add_ground_net) or "
                        f"check whether the wrong pin was wired"
                    ),
                    refs=[n.name, ref],
                )


# Pin types that MUST be on a net to function correctly. Excludes:
#   "nc"        — explicit no-connect; floating is correct
#   "reserved"  — datasheet "do not connect to a signal"; many reserved
#                 pins ARE tied to GND/VDD per app notes — don't enforce
#                 connectivity. The factory note documents the tie.
#   "passive"   — passive R/C/L pins are pure wiring infrastructure
#   "output"    — multi-interface chips (e.g. AR0234 CSI-2 + parallel)
#                 legitimately tri-state outputs in the inactive mode.
#                 Floating outputs are common and not a bug.
#   "clock"     — same reason; pixel clocks etc. tri-state in CSI-2 mode
# We keep power/ground/input/io/analog: a floating supply, input, or
# bidirectional pin almost always means a forgotten wire.
_PIN_TYPES_REQUIRING_NET = {
    "power", "ground", "input", "io", "analog",
}


@validator
def _v_typed_pin_must_be_connected(design: Design):
    """Every chip pin with a *functional* type (power, ground, input,
    output, io, analog, clock) must be on some net. Floating typed
    pins are almost always a forgotten wire — only `nc` / `reserved`
    are legitimately floatable, and they're tracked separately.

    The check works by building the set of (ref, num) tuples that
    appear on any net's pin list, then iterating chip pins to find
    typed ones not in that set."""
    connected: set = set()
    for n in design.nets:
        for ref, num in n.pins:
            connected.add((ref, num))
    components = list(design.chips) + list(getattr(design, "batteries", [])) + list(getattr(design, "antennas", []))
    for c in components:
        if c.dnp:
            continue
        for p in c.pins:
            if (p.type or "") not in _PIN_TYPES_REQUIRING_NET:
                continue
            if (c.ref, p.num) in connected:
                continue
            yield Issue(
                severity="error",
                rule="floating_typed_pin",
                message=(
                    f"{c.ref}.{p.num} ({p.name!r}, type={p.type!r}) is "
                    f"not connected to any net — typed pins must be "
                    f"wired. If the datasheet permits floating, change "
                    f"the pin type to 'nc' in the factory."
                ),
                refs=[c.ref],
            )


@validator
def _v_nc_pin_must_not_be_connected(design: Design):
    """`type=nc` pins are no-connect by datasheet — leaving them on
    a net almost always indicates a copy-paste wiring error (e.g. tying
    an NC pin to GND when the datasheet says "do not connect"). Some
    parts genuinely accept NC pins tied to GND for ESD; those should
    be retyped to 'reserved' (with a note) rather than 'nc'."""
    components = list(design.chips) + list(getattr(design, "batteries", [])) + list(getattr(design, "antennas", []))
    for c in components:
        if c.dnp:
            continue
        for p in c.pins:
            if (p.type or "") != "nc":
                continue
            if p.net is None:
                continue
            yield Issue(
                severity="error",
                rule="nc_pin_connected",
                message=(
                    f"{c.ref}.{p.num} ({p.name!r}) is `type='nc'` but "
                    f"is connected to net {p.net!r} — datasheet says "
                    f"do-not-connect. If the chip actually allows GND/"
                    f"VDD tie, retype as 'reserved' in the factory."
                ),
                refs=[c.ref],
            )


# Tolerance for "this rail voltage matches the pin's expected voltage."
# 10 % is wide enough to cover normal rail droop and brown-out trip
# settings, narrow enough that a 3.3 V vs 1.8 V mix-up still fires.
_VOLTAGE_TOLERANCE = 0.10


@validator
def _v_power_net_has_voltage(design: Design):
    """Every net with kind='power' must have `voltage_v` set. A power
    rail without a declared voltage means downstream validators (the
    voltage cross-checks below, plus the placer's embedded-cap plane
    picker) can't verify the design — silent failure modes.

    `add_power_net(name, voltage_v=...)` requires the voltage; this
    catches power nets created via the bare-net Design.connect()
    auto-creation path (which defaults to kind='signal' anyway —
    so a kind='power' net WITHOUT voltage is suspicious)."""
    for n in design.nets:
        if n.kind != "power":
            continue
        if n.voltage_v is None:
            yield Issue(
                severity="error",
                rule="power_net_missing_voltage",
                message=(
                    f"net {n.name!r} (kind='power') has no voltage_v "
                    f"set — declare it via add_power_net(name, "
                    f"voltage_v=...) or assign Net.voltage_v post-hoc"
                ),
                refs=[n.name],
            )


@validator
def _v_net_voltage_matches_pinspec(design: Design):
    """For each pin connection where the chip has a pinspec sidecar AND
    that pinspec declares voltage_v or voltage_range_v for the pin:
    check that the connected net's voltage is consistent.

    Two sub-checks per pin:
      - If pinspec has `voltage_range_v=[min, max]`: net voltage must
        fall inside [min, max] (chip abs-max envelope).
      - If pinspec has `voltage_v=N`: net voltage must equal N within
        ±10 % (chip nominal operating-point check).

    Skipped silently when the pinspec doesn't constrain voltage —
    sidecar coverage is opt-in per chip."""
    from smash.parts._pinspec import load_pinspec

    for n in design.nets:
        if n.kind != "power" or n.voltage_v is None:
            continue
        for ref, pin_num in n.pins:
            chip = design.chip_by_ref(ref) or design.battery_by_ref(ref)
            if chip is None or not chip.manf_pn:
                continue
            spec = load_pinspec(chip.manf_pn)
            if spec is None:
                continue
            entry = next((p for p in spec.pins if p.num == pin_num), None)
            if entry is None:
                continue

            # Abs-max range check
            if entry.voltage_range_v:
                lo, hi = entry.voltage_range_v
                if not (lo <= n.voltage_v <= hi):
                    yield Issue(
                        severity="error",
                        rule="voltage_outside_pin_rating",
                        message=(
                            f"net {n.name!r} (V={n.voltage_v}) feeds "
                            f"{ref}.{pin_num} ({entry.name!r}) whose "
                            f"datasheet abs-max range is "
                            f"[{lo}, {hi}] V — chip damage / "
                            f"undervolt risk"
                        ),
                        refs=[n.name, ref],
                    )

            # Nominal match check (within ±10 %)
            if entry.voltage_v is not None:
                nv = entry.voltage_v
                low, high = nv * (1 - _VOLTAGE_TOLERANCE), nv * (1 + _VOLTAGE_TOLERANCE)
                if not (low <= n.voltage_v <= high):
                    yield Issue(
                        severity="error",
                        rule="voltage_mismatch_pin_nominal",
                        message=(
                            f"net {n.name!r} (V={n.voltage_v}) feeds "
                            f"{ref}.{pin_num} ({entry.name!r}) whose "
                            f"datasheet nominal is {nv} V "
                            f"(tolerance ±{int(_VOLTAGE_TOLERANCE*100)}%) — "
                            f"under/overvolt mismatch"
                        ),
                        refs=[n.name, ref],
                    )


# Tolerance for "this clock net frequency matches a point-value pin
# constraint." 1 % covers normal crystal/MEMS trim error, narrow enough
# that 32 kHz vs 8 MHz still fires.
_FREQUENCY_TOLERANCE = 0.01


@validator
def _v_clock_net_has_frequency(design: Design):
    """Every kind='clock' net must declare `frequency_hz`. Without it
    the validator can't cross-check connected chip pin ranges (HSE
    input accepts 4-50 MHz vs an LSE input that expects 32.768 kHz —
    plugging the wrong oscillator into the wrong input is a silent
    failure at first boot)."""
    for n in design.nets:
        if n.kind != "clock":
            continue
        if n.frequency_hz is None:
            yield Issue(
                severity="error",
                rule="clock_net_missing_frequency",
                message=(
                    f"net {n.name!r} (kind='clock') has no "
                    f"frequency_hz set — declare it via "
                    f"add_clock_net(name, frequency_hz=...)"
                ),
                refs=[n.name],
            )


@validator
def _v_clock_pin_frequency(design: Design):
    """Cross-check clock-net frequency against connected pins' pinspec
    constraints.

    Two cases per connection:
      - Pin has `frequency_range_hz=[lo, hi]` (input clock): net's
        frequency_hz must fall in [lo, hi].
      - Pin has `frequency_hz=N` (oscillator output): net's
        frequency_hz must equal N within ±1 %.

    Pins/chips without pinspec constraints are skipped (opt-in)."""
    from smash.parts._pinspec import load_pinspec

    for n in design.nets:
        if n.kind != "clock" or n.frequency_hz is None:
            continue
        for ref, pin_num in n.pins:
            chip = design.chip_by_ref(ref) or design.battery_by_ref(ref)
            if chip is None or not chip.manf_pn:
                continue
            spec = load_pinspec(chip.manf_pn)
            if spec is None:
                continue
            entry = next((p for p in spec.pins if p.num == pin_num), None)
            if entry is None:
                continue

            # Input-range check
            if entry.frequency_range_hz:
                lo, hi = entry.frequency_range_hz
                if not (lo <= n.frequency_hz <= hi):
                    yield Issue(
                        severity="error",
                        rule="frequency_outside_pin_range",
                        message=(
                            f"net {n.name!r} (f={n.frequency_hz} Hz) "
                            f"feeds {ref}.{pin_num} ({entry.name!r}) "
                            f"whose datasheet range is [{lo}, {hi}] Hz"
                        ),
                        refs=[n.name, ref],
                    )

            # Output point-value check (±1 %)
            if entry.frequency_hz is not None:
                nf = entry.frequency_hz
                low = nf * (1 - _FREQUENCY_TOLERANCE)
                high = nf * (1 + _FREQUENCY_TOLERANCE)
                if not (low <= n.frequency_hz <= high):
                    yield Issue(
                        severity="error",
                        rule="frequency_mismatch_pin_nominal",
                        message=(
                            f"net {n.name!r} (f={n.frequency_hz} Hz) "
                            f"is driven by {ref}.{pin_num} "
                            f"({entry.name!r}) whose datasheet nominal "
                            f"is {nf} Hz (tolerance "
                            f"±{int(_FREQUENCY_TOLERANCE*100)}%)"
                        ),
                        refs=[n.name, ref],
                    )


@validator
def _v_factory_matches_pinspec(design: Design):
    """For every chip whose factory has a `pinspec.json` sidecar (in
    `parts/sources/<manf_pn>/pinspec.json`), check that the live
    chip's pins match the datasheet-derived spec on (num, name, type,
    aliases). Chips without a pinspec are skipped — the framework is
    opt-in per factory.

    The pinspec is the datasheet ground truth (PDF → JSON, transcribed
    with citation). The factory is a code-level translation. Drift
    between them = either factory bug or pinspec stale-ness; the
    validator surfaces it loudly."""
    # Lazy import to avoid circular dep between state and parts.
    from smash.parts._pinspec import load_pinspec, compare

    components = list(design.chips) + list(getattr(design, "batteries", [])) + list(getattr(design, "antennas", []))
    seen_pns: set = set()
    for c in components:
        pn = c.manf_pn
        if not pn or pn in seen_pns:
            continue
        seen_pns.add(pn)
        spec = load_pinspec(pn)
        if spec is None:
            continue
        for rule, msg in compare(c, spec):
            yield Issue(
                severity="error",
                rule=rule,
                message=f"{c.ref} ({pn}): {msg} [datasheet: {spec.datasheet}]",
                refs=[c.ref],
            )


@validator
def _v_output_pin_not_driving_power(design: Design):
    """A `type=output` pin (logic output, e.g. MCU GPIO drive) must
    never land on a kind=power or kind=ground net — that would mean
    the GPIO is fighting a power rail. Common bug: wiring a regulator-
    EN signal to the rail it's supposed to gate, instead of to the
    enable input.

    Bidirectional pins (`type=io`) are exempt — strap-tied I/O is
    normal (e.g. an I²C address-select pin pulled to VDD)."""
    for n in design.nets:
        if n.kind not in ("power", "ground"):
            continue
        for ref, pin_num in n.pins:
            chip = design.chip_by_ref(ref) or design.battery_by_ref(ref)
            if chip is None:
                continue
            pin = next((p for p in chip.pins if p.num == pin_num), None)
            if pin is None or pin.type != "output":
                continue
            yield Issue(
                severity="error",
                rule="output_pin_drives_power_net",
                message=(
                    f"net {n.name!r} (kind={n.kind!r}) is driven by "
                    f"output pin {ref}.{pin_num} ({pin.name!r}) — a "
                    f"logic output should not drive a power/ground "
                    f"rail. Check whether the wrong pin was wired."
                ),
                refs=[n.name, ref],
            )
