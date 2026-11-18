"""Free-space link budget / range estimate for the HF LoRa link.

Range = distance where received power falls to (sensitivity + margin):
    P_tx + G_tx + G_rx − FSPL(d, f) ≥ S + M
    FSPL[dB] = 20·log10(d_km) + 20·log10(f_MHz) + 32.44

Line of sight assumed (no terrain, no foliage): an UPPER bound that is
realistic air-to-air or air-to-ground with clearance. The vehicle antenna
gain is G = D_avg + 10·log10(η_total) — η_total from the openEMS runs
(mismatch included); the roll pattern's minimum is covered by `margin_db`.
"""
from __future__ import annotations

import dataclasses
import math

# LR2021 LoRa 2.4 GHz sensitivity, 64 B payload, 1 % PER (DS v2.2 Table 3-18),
# BW 800 kHz (mLRS LR20xx 2.4 GHz modes run BW 812, SF5–SF7).
LR2021_2G4_BW800_SENS_DBM = {5: -111.0, 6: -114.0, 7: -116.5, 8: -119.5,
                              9: -122.5, 10: -125.0, 11: -128.0, 12: -130.5}
LR2021_HF_TX_MAX_DBM = 12.0

# S4 transverter, 4.4-5.0 GHz (2026-11-18): GRF5126 at 5 V, OP1dB 22.0-22.3 dBm
# (Guerrilla 4400-5000 MHz tune), run ~1 dB into compression (LoRa is
# constant-envelope) minus T/R switch 0.5 dB (BGS12P2L6 DS) and BPF + match
# ~1.3 dB (estimate) → ≈ +21 dBm at the S4 feed. RX: ~1.8 dB front loss +
# GRF2073W NF ~1 dB ahead of 16 dB gain — no worse than the bare LR2021,
# so the LR2021 sensitivity table is reused (sens_offset 0).
S4_XV_TX_DBM = 21.0
S4_F_MHZ = 4700.0


@dataclasses.dataclass(frozen=True)
class Station:
    name: str
    p_tx_dbm: float
    gain_dbi: float          # antenna gain incl. its efficiency
    sens_offset_db: float = 0.0   # receiver NF penalty vs the LR2021 figure


# Affordable ground / relay equipment (assumptions — hobby-grade 2.4 GHz gear):
GROUND_OMNI = Station("ground: LR2021/SX1280 module, +20 dBm PA, 2 dBi dipole", 20.0, 2.0)
GROUND_PANEL = Station("ground: same module, 12 dBi panel/patch antenna", 20.0, 12.0)
GROUND_NO_PA = Station("ground: bare LR2021 (+12 dBm), 2 dBi dipole", 12.0, 2.0)


def fspl_db(d_km: float, f_mhz: float) -> float:
    return 20 * math.log10(d_km) + 20 * math.log10(f_mhz) + 32.44


def range_km(p_tx_dbm, g_tx_dbi, g_rx_dbi, sens_dbm, f_mhz, margin_db=10.0) -> float:
    allowed = p_tx_dbm + g_tx_dbi + g_rx_dbi - (sens_dbm + margin_db)
    return 10 ** ((allowed - 20 * math.log10(f_mhz) - 32.44) / 20)


def vehicle_gain_dbi(eff_total: float, directivity_avg_dbi: float = 0.0) -> float:
    """Average gain of the vehicle antenna; D_avg ≈ 0 dBi for the roll-averaged
    donut (the peak D is ~2–5 dBi, the roll minimum sits in the margin)."""
    return directivity_avg_dbi + 10 * math.log10(max(eff_total, 1e-6))


def table(eff_total: float, f_mhz: float = 2400.0, sfs=(5, 7, 9),
          margin_db: float = 10.0, stations=(GROUND_NO_PA, GROUND_OMNI, GROUND_PANEL),
          p_vehicle_dbm: float = LR2021_HF_TX_MAX_DBM):
    """Rows: (station, SF, downlink km [vehicle → ground], uplink km [ground → vehicle]).
    p_vehicle_dbm: vehicle TX power at its antenna feed (S1: the bare LR2021;
    S4: S4_XV_TX_DBM with f_mhz=S4_F_MHZ)."""
    gv = vehicle_gain_dbi(eff_total)
    rows = []
    for st in stations:
        for sf in sfs:
            s = LR2021_2G4_BW800_SENS_DBM[sf]
            down = range_km(p_vehicle_dbm, gv, st.gain_dbi, s + st.sens_offset_db,
                            f_mhz, margin_db)
            up = range_km(st.p_tx_dbm, st.gain_dbi, gv, s, f_mhz, margin_db)
            rows.append((st.name, sf, down, up))
    return rows
