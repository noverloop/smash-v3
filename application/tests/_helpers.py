"""Shared test helpers for the factory-validation suite."""
from __future__ import annotations


def wire_chip_synthetically(d, chip) -> None:
    """Wire every pin on `chip` to a synthetic per-pin net of the right
    kind — power-type pins → power nets, ground-type pins → ground
    nets, everything else → signal nets. Used by the per-factory
    `test_each_factory_validates_clean` tests to exercise every chip
    in isolation without tripping the pin-vs-net-kind validator.

    Pins typed `nc` are skipped — connecting them would trip the
    `_v_nc_pin_must_not_be_connected` validator. Pins typed `reserved`
    are also skipped (no enforced connection); the design code decides
    whether to tie them per datasheet."""
    pwr_net = None
    gnd_net = None
    for p in chip.pins:
        if p.type in ("nc", "reserved"):
            continue
        if p.type == "power":
            if pwr_net is None:
                pwr_net = d.add_power_net(
                    f"PWR_{chip.ref}", voltage_v=3.3)
            pwr_net.connect(p)
        elif p.type == "ground":
            if gnd_net is None:
                gnd_net = d.add_ground_net(f"GND_{chip.ref}")
            gnd_net.connect(p)
        else:
            d.add_signal_net(f"N_{chip.ref}_{p.num}").connect(p)
