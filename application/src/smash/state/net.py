"""Net + NET_KINDS — one electrical net plus the kind discriminator."""
from __future__ import annotations

import dataclasses


NET_KINDS = ("power", "ground", "signal", "bus", "diff", "clock")


@dataclasses.dataclass
class Net:
    """One electrical net. The `kind` discriminates how the routing /
    validation pipeline treats it:

      - "power":  voltage rail (carries `voltage_v`); usually plane
      - "ground": return current / shield
      - "signal": single-ended signal, no grouping
      - "bus":    member of a parallel bus (`bus_group` + `bit_index`,
                  e.g. DDR3_A0 has bus_group="DDR3_ADDR", bit_index=0)
      - "diff":   one leg of a differential pair (`diff_pair` = name
                  of complement, `impedance_ohms` = target Z₀)
      - "clock":  has timing / skew constraints

    Use the typed constructors on `Design` (add_power_net,
    add_ground_net, add_signal_net, add_bus_net, add_diff_pair) so
    every Net is created with a kind appropriate to its role. Plain
    `add_net(name)` is the fallback when the kind isn't yet known
    (e.g. mid-refactor).
    """
    name: str
    kind: str = "signal"                # one of NET_KINDS
    # Pin connections — list of (part_ref, pin_num) tuples.
    pins: list = dataclasses.field(default_factory=list)
    # Other names the same electrical net is known by. Populated when
    # two named nets get merged via a shared pin (`Design.connect`
    # detects the existing pin, absorbs the other net, and appends its
    # name + aliases here). The canonical exporter normalises across
    # primary + aliases so the choice of primary doesn't perturb
    # downstream diffs.
    aliases: list = dataclasses.field(default_factory=list)
    # Routing rule fields — populated per kind.
    netclass: str | None = None         # rule-class name
    voltage_v: float | None = None      # power nets
    frequency_hz: float | None = None   # clock nets (oscillator nominal,
                                        # validated against connected
                                        # chip clock-input ranges)
    bus_group: str | None = None        # bus nets (e.g. "DDR3_ADDR")
    bit_index: int | None = None        # bus nets (e.g. 0..15)
    diff_pair: str | None = None        # diff nets — name of complement
    impedance_ohms: float | None = None # target Z₀ (55 SE, 100 diff)
    length_match_group: str | None = None  # e.g. "DDR3_BYTE0"
    note: str | None = None             # free-form, see Pin.note

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["pins"] = [list(p) for p in self.pins]
        return d
