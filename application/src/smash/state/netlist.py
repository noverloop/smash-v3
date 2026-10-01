"""Netlist — compact serialisable snapshot of the electrical network.

Holds plain dicts rather than dedicated NetlistPart / NetlistNet
classes — those were just sub-projections of Chip / Net, so we keep
the projection but skip the bespoke types.

  parts: list[dict] — each entry is a Chip → flat dict (board_tag,
                      ref, manf, manf_pn, value, footprint name,
                      description, datasheet, name)
  nets:  list[dict] — each entry is {"name": ..., "pins": [(ref, pin)…]}

Build via `Netlist.from_design(design)`; serialise with `to_dict()`.
"""
from __future__ import annotations


class Netlist:
    def __init__(self):
        self.parts: list[dict] = []
        self.nets:  list[dict] = []

    def add_part(self, **fields) -> dict:
        self.parts.append(fields)
        return fields

    def add_net(self, name: str, pins: list | None = None) -> dict:
        n = {"name": name, "pins": list(pins or [])}
        self.nets.append(n)
        return n

    @classmethod
    def from_design(cls, design) -> "Netlist":
        nl = cls()
        for c in design.chips:
            fp_name = c.footprint.name if c.footprint else None
            nl.parts.append({
                "ref":         c.ref,
                "name":        c.name,
                "manf":        c.manf,
                "manf_pn":     c.manf_pn,
                "value":       c.value,
                "footprint":   fp_name,
                "description": c.description,
                "board_tag":   c.board_tag,
                "datasheet":   c.datasheet,
            })
        for n in design.nets:
            nl.nets.append({"name": n.name, "pins": [list(p) for p in n.pins]})
        return nl

    def to_dict(self) -> dict:
        return {"parts": list(self.parts),
                "nets":  [{"name": n["name"],
                           "pins": [list(p) for p in n["pins"]]}
                          for n in self.nets]}
