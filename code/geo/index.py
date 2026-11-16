"""Chapter 08: index a position as an H3 cell.

The cell id is the whole point: it is a stable 64-bit key derived from position,
so "find drivers near here" becomes an indexed equality lookup plus a ring
expansion instead of a two-dimensional bounding-box scan.
"""

from __future__ import annotations

import h3

RES_INDEX = 9   # driver position index: ~0.105 km2, a few city blocks
RES_ZONE = 7    # surge / demand zones: ~5.16 km2


def cell_for(lat: float, lng: float, res: int = RES_INDEX) -> str:
    return h3.latlng_to_cell(lat, lng, res)


def describe(lat: float, lng: float) -> dict:
    c9 = cell_for(lat, lng, RES_INDEX)
    c7 = cell_for(lat, lng, RES_ZONE)
    return {
        "cell_r9": c9,
        "cell_r7": c7,
        "res9_area_km2": round(h3.cell_area(c9, unit="km^2"), 4),
        "res7_area_km2": round(h3.cell_area(c7, unit="km^2"), 3),
        "ring1_cells": len(h3.grid_disk(c9, 1)),
        "ring3_cells": len(h3.grid_disk(c9, 3)),
        "neighbours": sorted(h3.grid_disk(c9, 1) - {c9}),
    }


def expansion_plan(cell: str, max_k: int = 5) -> list[dict]:
    """How much ground each ring step buys you. Print this before you tune k."""
    out = []
    for k in range(1, max_k + 1):
        cells = h3.grid_disk(cell, k)
        area = sum(h3.cell_area(c, unit="km^2") for c in cells)
        out.append({"k": k, "cells": len(cells), "area_km2": round(area, 3)})
    return out


if __name__ == "__main__":
    # Bandra Kurla Complex, Mumbai
    lat, lng = 19.0670, 72.8680
    info = describe(lat, lng)
    print(f"cell r9 = {info['cell_r9']}  ({info['res9_area_km2']} km2)")
    print(f"cell r7 = {info['cell_r7']}  ({info['res7_area_km2']} km2)")
    print(f"ring(1) = {info['ring1_cells']} cells, ring(3) = {info['ring3_cells']} cells")
    for step in expansion_plan(info["cell_r9"]):
        print(f"  k={step['k']}: {step['cells']:>3} cells, {step['area_km2']:>8} km2")
