"""Nose lens for the optical cups (QPD / camera), 2026-11-18.

The QPD and camera cups carry a **plano-convex lens** in the flat nose face
(meplat): flat side OUT, flush with the meplat so the nose stays flat and
aerodynamic, convex side in, towards the sensor. With the flat side facing the
scene the back focal distance from the convex vertex equals the focal length,
f = R / (n(λ) − 1), so the lens height above the sensor depends on the
wavelength through the glass's dispersion:

    z_flat_face = z_sensor + f(λ) + t_c + defocus

Each optical config gets one cup per wavelength BAND ("laser" / "ir");
the bands, lens geometry and material are placeholders until the optics are
specified. The QPD wants a deliberately DEFOCUSED spot (a sharp spot on a
quadrant detector only tells which quadrant, not how far off-axis), hence
`defocus_mm`; the camera sits in focus.
"""
from __future__ import annotations

import dataclasses
import math

# Sellmeier coefficients, λ in µm: n² = 1 + Σ Bᵢ λ² / (λ² − Cᵢ).
# Sapphire (ordinary ray, Malitson & Dodge 1972), 0.2–5.5 µm — hard, erosion /
# thermal-shock resistant: the default for a nose window.
# Fused silica (Malitson 1965), 0.21–3.71 µm.
SELLMEIER = {
    "sapphire":     ((1.4313493, 0.65054713, 5.3414021),
                     (0.0726631 ** 2, 0.1193242 ** 2, 18.028251 ** 2), (0.2, 5.5)),
    "fused_silica": ((0.6961663, 0.4079426, 0.8974794),
                     (0.0684043 ** 2, 0.1162414 ** 2, 9.896161 ** 2), (0.21, 3.71)),
}


def refractive_index(material: str, wavelength_nm: float) -> float:
    B, C, (lo, hi) = SELLMEIER[material]
    lam = wavelength_nm / 1000.0
    if not lo <= lam <= hi:
        raise ValueError(f"{material} Sellmeier valid {lo}–{hi} µm, not {lam:g} µm "
                         "(LWIR needs Ge / ZnSe)")
    l2 = lam * lam
    return math.sqrt(1.0 + sum(b * l2 / (l2 - c) for b, c in zip(B, C)))


@dataclasses.dataclass(frozen=True)
class Lens:
    material: str = "sapphire"
    diameter_mm: float = 10.0
    radius_mm: float = 6.0          # convex surface radius (flat side out)
    edge_mm: float = 0.8            # edge thickness

    @property
    def sag_mm(self) -> float:
        a = self.diameter_mm / 2.0
        if a >= self.radius_mm:
            raise ValueError("lens radius must exceed its semi-diameter")
        return self.radius_mm - math.sqrt(self.radius_mm ** 2 - a * a)

    @property
    def centre_thickness_mm(self) -> float:
        return self.edge_mm + self.sag_mm

    def focal_mm(self, wavelength_nm: float) -> float:
        return self.radius_mm / (refractive_index(self.material, wavelength_nm) - 1.0)

    def height_above_sensor_mm(self, wavelength_nm: float, defocus_mm: float = 0.0) -> float:
        """Sensor surface → flat (outer) lens face, flat side out: BFL = f."""
        return self.focal_mm(wavelength_nm) + self.centre_thickness_mm + defocus_mm


# Per optical payload: sensor ref, wavelength bands (nm, ⚠ placeholders —
# set to the real designator / illuminator), lens, defocus, sensor half-
# diagonal for the field-of-view report.
OPTICS = {
    "qpd_module": {
        "sensor": "U_QPD",
        "bands": {"laser": 1064.0, "ir": 1550.0},    # Si QPD @ 1064 / InGaAs @ 1550
        "lens": Lens(),
        "defocus_mm": 0.5,                          # blur the spot across the quadrants
        "sensor_half_diag_mm": None,
    },
    "camera_module": {
        "sensor": "U_CAM",
        "bands": {"ir": 850.0, "laser": 1064.0},
        "lens": Lens(),
        "defocus_mm": 0.0,
        "sensor_half_diag_mm": 3.40,                # AR0234 1920×1200 × 3 µm
    },
}
LENS_COLLAR_WALL_MM = 1.0       # moulded collar round the lens bore
LENS_LEDGE_MM = 0.5             # radial ledge the lens's convex edge rests on
LENS_BORE_CLEAR_MM = 0.05       # radial bore clearance (bonded in)


def band_table(payload: str) -> list:
    """[(band, λ nm, n, f, height above sensor)] for the CAM notes."""
    o = OPTICS[payload]
    L = o["lens"]
    return [(b, lam, refractive_index(L.material, lam), L.focal_mm(lam),
             L.height_above_sensor_mm(lam, o["defocus_mm"]))
            for b, lam in o["bands"].items()]
