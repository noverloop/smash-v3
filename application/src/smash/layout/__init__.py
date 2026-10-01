"""smash.layout — algorithms over `smash.state`.

This package holds construction algorithms + geometry helpers:
  - `board.panel_from_root`     graph → PanelLayout traversal
  - `geometry`                  Line / Arc / Circle math + tile outlines
  - `cavities`                  fold-projection + shapely polygon merge
  - `flex`                      builder functions for FlexStrip / Keepout
  - `locked`                    locked_placements.json loader
  - `constants`                 packing knobs

State dataclasses (Board, Flex, Placement, KeepoutRegion, CavityRegion,
FlexStrip, Panel, …) live in `smash.state`. Import them from there.
"""
from smash.layout.panel import PanelLayout
from smash.layout       import constants


__all__ = ["PanelLayout", "constants"]
