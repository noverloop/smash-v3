"""Unit tests for smash.state.routing — Track / Via / Zone data model
and their JSON round-trip through SmashState."""

import pytest

from smash import Track, Via, Zone, Board, SmashState
from smash.state.routing import VIA_KINDS


class TestRoutingDataclasses:
    def test_track_to_dict_lists_points(self):
        t = Track(net="COMP_1V35", layer="In3", width_mm=0.2,
                  path=[(1.0, 2.0), (3.0, 4.0)])
        d = t.to_dict()
        assert d["path"] == [[1.0, 2.0], [3.0, 4.0]]
        assert d["layer"] == "In3" and d["width_mm"] == 0.2

    def test_via_defaults_and_to_dict(self):
        v = Via(net="GND", position_mm=(5.0, 6.0), drill_mm=0.3,
                pad_diameter_mm=0.6)
        assert v.from_layer == "F.Cu" and v.to_layer == "B.Cu"
        assert v.kind == "signal" and v.filled is False
        assert v.to_dict()["position_mm"] == [5.0, 6.0]
        assert v.kind in VIA_KINDS

    def test_zone_to_dict_lists_outline(self):
        z = Zone(net="GND", layer="In1",
                 outline_mm=[(0, 0), (10, 0), (10, 10)])
        assert z.filled is True
        assert z.to_dict()["outline_mm"] == [[0, 0], [10, 0], [10, 10]]


class TestRoutingRoundTrip:
    def _board_with_routing(self):
        b = Board(name="flight_board", kind="rigid")
        b.tracks.append(Track(net="COMP_1V35", layer="In3", width_mm=0.2,
                              path=[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]))
        b.vias.append(Via(net="GND", position_mm=(5.0, 6.0), drill_mm=0.3,
                          pad_diameter_mm=0.6, kind="thermal", filled=True))
        b.zones.append(Zone(net="GND", layer="In1",
                           outline_mm=[(0, 0), (10, 0), (10, 10), (0, 10)]))
        return b

    def test_routing_survives_dump_load(self, tmp_path):
        s = SmashState.new()
        s.boards["flight_board"] = self._board_with_routing()
        out = tmp_path / "smash.json"
        s.dump_json(out)
        fb = SmashState.load_json(out).boards["flight_board"]

        assert len(fb.tracks) == 1 and len(fb.vias) == 1 and len(fb.zones) == 1

        t = fb.tracks[0]
        assert isinstance(t, Track)
        assert t.path == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
        assert isinstance(t.path[0], tuple)        # tuple, not list

        v = fb.vias[0]
        assert isinstance(v, Via)
        assert v.position_mm == (5.0, 6.0) and isinstance(v.position_mm, tuple)
        assert v.kind == "thermal" and v.filled is True
        assert (v.drill_mm, v.pad_diameter_mm) == (0.3, 0.6)

        z = fb.zones[0]
        assert isinstance(z, Zone)
        assert z.outline_mm[2] == (10.0, 10.0) and isinstance(z.outline_mm[0], tuple)

    def test_empty_routing_round_trips(self, tmp_path):
        # A board with no routing must still survive (default-empty lists).
        s = SmashState.new()
        out = tmp_path / "smash.json"
        s.dump_json(out)
        for b in SmashState.load_json(out).boards.values():
            assert b.tracks == [] and b.vias == [] and b.zones == []
