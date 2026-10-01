"""SmashState — top-level project state container.

Bundles boards + netlist snapshot. Builder-style API for declaring
optional subsystems (companion computer, radar, …) on top of the
Core configuration.
"""
from __future__ import annotations

import json
import pathlib

from smash.state.board import Board
from smash.state.netlist import Netlist
from smash.state.stackup.dielectric import Dielectric
from smash.state.stackup.layer import Layer
from smash.state.routing import Track, Via, Zone


class SmashState:
    """Top-level Smash design state: the set of boards (tiles) plus
    the captured SKiDL netlist. Lives across the whole system.py
    build — instantiated once, populated as the build runs,
    serialized to JSON at the end.

    Typical lifecycle in system.py:

        smash = SmashState()
        smash.add_board("power_board",   kind="rigid",
                        description="Battery + eFuse + bulk caps")
        smash.add_board("wakeup_board",  kind="rigid",
                        description="WLE5 + always-on LDO + NAND")
        ...  # all tiles
        # ... add_*() functions run, attaching parts to _BOARD_TAG ...
        smash.capture_netlist(default_circuit)
        smash.dump_json("output/smash_state.json")
    """

    def __init__(self):
        self.boards: dict = {}               # name → Board
        self.netlist: Netlist | None = None

    @classmethod
    def new(cls) -> "SmashState":
        """Create a fresh SmashState pre-loaded with the Core boards.

        Every Smash configuration shares the same Core tiles (per the
        "Order Configurations" table in components.md), so they're
        declared up-front. Optional subsystems — companion_computer,
        radar, actuators, qpd, wifi, camera — are added on top via
        the `add_*` chain:

            smash = (SmashState.new()
                     .add_companion_computer()
                     .add_radar()
                     .add_camera())

        Core boards declared here:
          - power_board:          battery cells + eFuse + bulk caps
          - wakeup_board:         always-on WLE5 + LoRa + wakeup NAND
          - flight_board:         H562 MCU + IMU/mag/baro + nav sensors
          - activation_interface: pogo-pad activation channel detect
          - nfc_antenna_flex:     ST25DV NFC tag + 13.56 MHz antenna
          - nose_cap:             USB-C + LED nose cap (radar forward-end)
        """
        s = cls()
        s.add_board(
            "power_board", kind="rigid",
            description="3× Tadiran TLM-1520HPM/S Li-MnO₂ cells + "
                        "TPS25940 eFuse + 470 µF bulk caps")
        s.add_board(
            "wakeup_board", kind="rigid",
            description="STM32WLE5JCI6 always-on MCU + MCP1640 5 V "
                        "boost + STLQ020 nano-power LDO + MT29F4G01 "
                        "OTA-buffer NAND")
        s.add_board(
            "flight_board", kind="rigid",
            description="STM32H562AII6 main MCU + 3× ISM330DHCX IMU "
                        "+ IIS2MDC mag + H3LIS331 hi-g accelerometer "
                        "+ TMP117 temp + S25HL512 64 MB QSPI flash")
        s.add_board(
            "activation_interface", kind="rigid",
            description="Pogo-pad tile: 22 TestPoints + DRV5023 Hall "
                        "channel-detect + activation")
        s.add_board(
            "nfc_antenna_flex", kind="flex", standalone=True,
            description="ST25DV16KC-IE8T3 dynamic NFC tag + etched "
                        "13.56 MHz spiral antenna on flex substrate")
        s.add_board(
            "nose_cap", kind="rigid",
            description="Nose cap (radar forward-end): UJ31 USB-C depot "
                        "port + status LEDs + aluminium waveguide-disk "
                        "mount")
        return s

    # ── boards ───────────────────────────────────────────────────────

    def add_board(self, name: str, kind: str = "rigid",
                  description: str | None = None,
                  standalone: bool = False) -> Board:
        """Declare one tile. Returns the Board record. Idempotent —
        calling with the same name updates the existing record."""
        if kind not in ("rigid", "spacer", "flex"):
            raise ValueError(f"unknown board kind: {kind!r}")
        b = self.boards.get(name)
        if b is None:
            b = Board(name=name, kind=kind,
                      description=description, standalone=standalone)
            self.boards[name] = b
        else:
            b.kind = kind
            if description is not None:
                b.description = description
            b.standalone = standalone
        return b

    # ── board configurations (optional subsystems) ───────────────────
    # Each `add_*` method declares the tile(s) for one subsystem
    # listed in components.md's "Order Configurations" section. The
    # Core (flight + wakeup + power + activation + nfc + nose) is
    # always present; these are the optional add-ons that vary
    # between SKUs. Each method returns `self` for chaining:
    #
    #     smash = (SmashState.new()
    #              .add_companion_computer()
    #              .add_radar()
    #              .add_camera())

    def add_companion_computer(self) -> "SmashState":
        """Linux companion stack — Cortex-A35 + DDR3L + NAND + PMIC,
        plus the I/O tile carrying NAND, WiFi, and 4.4 GHz "last-mile"
        RF telemetry. Two rigid tiles snake-folded together.

        Two optional payloads live on companion_io's footprint but are
        **DNP by default**:
          - `wifi` (LBEE5KL1YN) — enable with `add_wifi()`
          - `rf44` (ADF4351 PLL — 4.4 GHz OOK last-mile telemetry) —
            enable with `add_last_mile_telemetry()`
        Their pads and routing are always on the board; the populate
        flag controls whether the module gets soldered."""
        self.add_board(
            "companion_compute", kind="rigid",
            description="STM32MP255FAK3 + AS4C512M16D3LC DDR3L + "
                        "STPMIC25APQR + TPS61085 5 V boost")
        io = self.add_board(
            "companion_io", kind="rigid",
            description="MT29F8G08 1 GB SLC NAND + optional WiFi/BT "
                        "(LBEE5KL1YN, DNP) + optional 4.4 GHz "
                        "last-mile telemetry (ADF4351, DNP)")
        io.features.setdefault("wifi", False)   # DNP unless add_wifi()
        io.features.setdefault("rf44", False)   # DNP unless add_last_mile_telemetry()
        return self

    def add_radar(self) -> "SmashState":
        """77 GHz FMCW radar subsystem on a hybrid Rogers/FR4 tile."""
        self.add_board(
            "radar_module", kind="rigid",
            description="AWR2944ABGALTQ1 mmWave radar + LDL112PV18R "
                        "LDO + LMR10510 buck + TCAN1042 CAN PHY "
                        "(RO4350B 5 mil top layer over FR4)")
        return self

    def add_actuators(self) -> "SmashState":
        """Fin actuator subsystem — one DroneCAN node driving the four fin
        steppers."""
        self.add_board(
            "fins_module", kind="rigid",
            description="STM32G0B1 DroneCAN node + TCAN1042 CAN-FD PHY + "
                        "4× DRV8428E integrated bipolar-stepper drivers + "
                        "TPS61085 5 V VMOT boost + DRV5023 Hall sensor")
        return self

    def add_qpd(self) -> "SmashState":
        """Quadrant photodetector tile"""
        self.add_board(
            "qpd_module", kind="rigid", standalone=True,
            description="MT03-092 Si or InGaAs QPD + 4× AD8603 TIA "
                        "opamps + ADF4351 PLL synth")
        return self

    def add_nfc(self) -> "SmashState":
        """NFC dynamic-tag + 13.56 MHz spiral antenna on a flex-only
        sub-board. Part of every Smash config (wake / on-the-fly
        config)."""
        self.add_board(
            "nfc_antenna_flex", kind="flex", standalone=True,
            description="ST25DV16KC-IE8T3 dynamic NFC tag + etched "
                        "13.56 MHz spiral antenna on flex substrate")
        return self

    def add_wifi(self) -> "SmashState":
        """Enable the LBEE5KL1YN WiFi+BT module on companion_io.

        The WiFi footprint is always present on companion_io but
        defaults to DNP. This flips `companion_io.features["wifi"]`
        to True so the module gets soldered in the assembly.
        Requires `add_companion_computer()` to have been called
        first — the module physically lives on that tile."""
        io = self.boards.get("companion_io")
        if io is None:
            raise RuntimeError(
                "add_wifi() requires companion_io — "
                "call add_companion_computer() first")
        io.features["wifi"] = True
        return self

    def add_last_mile_telemetry(self) -> "SmashState":
        """Enable thedd ADF4351 4.4 GHz PLL synth (rf44) on companion_io. Requires `add_companion_computer()`. [DEPRECATED]"""
        io = self.boards.get("companion_io")
        if io is None:
            raise RuntimeError(
                "add_last_mile_telemetry() requires companion_io — "
                "call add_companion_computer() first")
        io.features["rf44"] = True
        return self

    def add_camera(self) -> "SmashState":
        """Camera module — global-shutter CMOS sensor on a small tile
        behind the optics. Only populated for visual-processing configs.
        """
        self.add_board(
            "camera_module", kind="rigid", standalone=True,
            description="AR0234CSSM00SUKA0-CP 2.3 MP mono CMOS "
                        "(1064 nm bandpass) + LP5907 VDD/VAA LDOs")
        return self

    def add_all(self) -> "SmashState":
        """Add every optional subsystem on top of Core, with every
        DNP-capable feature populated. The everything-on flagship
        configuration."""
        return (self
                .add_companion_computer()
                .add_wifi()                   # populate WiFi on companion_io
                .add_last_mile_telemetry()    # populate ADF4351 rf44 on companion_io
                .add_radar()
                .add_actuators()
                .add_qpd()
                .add_nfc()                    # no-op vs Core, kept for symmetry
                .add_camera())

    def set_snake_chain(self, chain: list) -> None:
        """Record the accordion-fold ordering. `chain` is a list of
        tile names from one end of the snake to the other. Tiles not
        in the chain are marked standalone."""
        in_chain = set(chain)
        for i, name in enumerate(chain):
            b = self.boards.get(name)
            if b is None:
                b = self.add_board(name)
            b.snake_index = i
            b.standalone = False
        for name, b in self.boards.items():
            if name not in in_chain:
                b.snake_index = None
                b.standalone = True

    # ── netlist ──────────────────────────────────────────────────────

    def capture_netlist(self, design) -> Netlist:
        """Project a Design into this SmashState's netlist snapshot.
        Pure read; doesn't mutate the Design."""
        self.netlist = Netlist.from_design(design)
        return self.netlist

    # ── cost / weight rollups (whole configuration) ─────────────────
    # Each chip has price_1pc / price_20kpc in its own currency.
    # These methods either return per-currency dicts or convert to
    # a target via an explicit fx_rates table — never guess FX.

    def cost_1pc(self, design, *,
                 target: str | None = None,
                 fx_rates: dict | None = None,
                 populated_only: bool = True):
        """Total per-piece cost. See `Board.cost_1pc` for the
        currency / fx_rates semantics."""
        if target is None:
            total: dict = {}
            for b in self.boards.values():
                for cur, amount in b.cost_1pc(
                        design, populated_only=populated_only).items():
                    total[cur] = total.get(cur, 0.0) + amount
            return total
        return sum(b.cost_1pc(design, target=target, fx_rates=fx_rates,
                              populated_only=populated_only)
                   for b in self.boards.values())

    def cost_20kpc(self, design, *,
                   target: str | None = None,
                   fx_rates: dict | None = None,
                   populated_only: bool = True):
        """Total 20k-volume cost. See `cost_1pc` for currency semantics."""
        if target is None:
            total: dict = {}
            for b in self.boards.values():
                for cur, amount in b.cost_20kpc(
                        design, populated_only=populated_only).items():
                    total[cur] = total.get(cur, 0.0) + amount
            return total
        return sum(b.cost_20kpc(design, target=target, fx_rates=fx_rates,
                                populated_only=populated_only)
                   for b in self.boards.values())

    def weight_g(self, design, populated_only: bool = True) -> float:
        """Total assembled weight in grams (chips only — not the PCB
        substrate or potting)."""
        return sum(b.weight_g(design, populated_only)
                   for b in self.boards.values())

    def cost_summary(self, design, *,
                     target: str | None = None,
                     fx_rates: dict | None = None,
                     populated_only: bool = True) -> dict:
        """Per-board + total cost rollup.

        - target=None: per-board totals are `{currency: amount}` dicts
        - target="EUR": per-board totals are floats in `target` currency
        """
        per_board = {}
        for name, b in self.boards.items():
            n_chips = len([c for c in design.chips_on_board(name)
                           if not (populated_only and c.dnp)])
            per_board[name] = {
                "1pc":      b.cost_1pc(design, target=target,
                                       fx_rates=fx_rates,
                                       populated_only=populated_only),
                "20kpc":    b.cost_20kpc(design, target=target,
                                         fx_rates=fx_rates,
                                         populated_only=populated_only),
                "weight_g": b.weight_g(design, populated_only),
                "n_chips":  n_chips,
            }
        return {
            "total_1pc":      self.cost_1pc(design, target=target,
                                            fx_rates=fx_rates,
                                            populated_only=populated_only),
            "total_20kpc":    self.cost_20kpc(design, target=target,
                                              fx_rates=fx_rates,
                                              populated_only=populated_only),
            "total_weight_g": self.weight_g(design, populated_only),
            "per_board":      per_board,
            "target":         target,
        }

    # ── serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "boards":  {name: b.to_dict() for name, b in self.boards.items()},
            "netlist": self.netlist.to_dict() if self.netlist else None,
        }

    def dump_json(self, path: pathlib.Path | str) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load_json(cls, path: pathlib.Path | str) -> "SmashState":
        """Rebuild a SmashState from a previously-dumped JSON sidecar.
        Used by downstream tools (router, BoardState, BOM) that want
        the design summary without re-running system.py."""
        data = json.loads(pathlib.Path(path).read_text())
        s = cls()
        for name, bd in (data.get("boards") or {}).items():
            s.add_board(
                name=name, kind=bd["kind"],
                description=bd.get("description"),
                standalone=bd.get("standalone", False),
            )
            s.boards[name].snake_index = bd.get("snake_index")
            s.boards[name].features = dict(bd.get("features") or {})
            # Restore stackup, hydrating Layer + Dielectric dataclasses.
            stackup = []
            for layer_d in (bd.get("stackup") or []):
                di_d = layer_d.get("dielectric_below")
                di = Dielectric(**di_d) if di_d else None
                layer_kw = {k: v for k, v in layer_d.items()
                            if k != "dielectric_below"}
                stackup.append(Layer(dielectric_below=di, **layer_kw))
            s.boards[name].stackup = stackup
            # Restore routing, hydrating Track / Via / Zone dataclasses
            # (and the tuple shapes asdict() flattened to lists).
            s.boards[name].tracks = [
                Track(**{**t, "path": [tuple(pt) for pt in t["path"]]})
                for t in (bd.get("tracks") or [])
            ]
            s.boards[name].vias = [
                Via(**{**v, "position_mm": tuple(v["position_mm"])})
                for v in (bd.get("vias") or [])
            ]
            s.boards[name].zones = [
                Zone(**{**z, "outline_mm": [tuple(pt) for pt in z["outline_mm"]]})
                for z in (bd.get("zones") or [])
            ]
        nl_data = data.get("netlist")
        if nl_data:
            nl = Netlist()
            for p in nl_data.get("parts", []):
                nl.parts.append(NetlistPart(**p))
            for n in nl_data.get("nets", []):
                net = NetlistNet(name=n["name"],
                                 pins=[tuple(x) for x in n["pins"]])
                nl.nets.append(net)
            s.netlist = nl
        return s
