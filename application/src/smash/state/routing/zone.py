"""Zone — one copper pour / plane region on a single layer."""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Zone:
    """One copper pour or plane region — a filled polygon on `layer`,
    tied to `net`.

    `outline_mm` is the pour boundary in board-local mm (math-y-up), a
    closed polygon as a list of `(x, y)` vertices. `filled` marks a
    poured (copper-present) zone vs. a keepout/rule region.

    Zones are the dominant *in-plane* heat path for the thermal model
    (a ground/power plane spreads heat far better than the FR4 around
    it), and `planes_for_net()` on the Board can already reason about
    rail planes from the stackup — a Zone adds the actual filled area.

    Note: a KiCad routing session (.ses) carries copper as wires, not
    filled zones, so the .ses importer does not populate this; zones
    come from manual authoring or a future .kicad_pcb import path.
    """
    net: str | None                     # net the pour ties to (None = unbound)
    layer: str                          # "In1", "B.Cu", ...
    outline_mm: list                    # [(x, y), ...] board-local, math-y-up
    filled: bool = True                 # poured (copper present) vs. keepout
    fill_polygons_mm: list = dataclasses.field(default_factory=list)
                                        # the COMPUTED pour, one entry per
                                        # island: {"layer", "pts"} with pts
                                        # board-local math-y-up. A zone
                                        # OUTLINE plots no copper — KiCad
                                        # stores the fill separately and
                                        # kicad-cli does not refill on
                                        # export — so a plane imported
                                        # without this yields an empty
                                        # gerber layer.
    note: str | None = None             # free-form catch-all

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["outline_mm"] = [list(pt) for pt in self.outline_mm]
        d["fill_polygons_mm"] = [
            {"layer": f.get("layer"), "pts": [list(q) for q in f["pts"]]}
            for f in (self.fill_polygons_mm or [])]
        return d
