"""Generate a synthetic reagent-stockroom export.

Closes the corpus gap the Phase 2 verification found: `reagent-inventory.yaml`
is the preset that proves no biology is compiled into the mapper, but no
fixture existed for it, so the claim "Claude maps a messy file onto a
brand-new field set with no code change" was never actually demonstrated
against real data.

Deliberately messy in the ways a real stockroom export is, and deliberately
*not* named like the preset's fields — the mapper has to earn every mapping:

  - a merged title row and a blank row above the header (header is not row 1)
  - column names nothing like the field names (`SKU`, `Use By`, `Location`)
  - an extra column the field set never asked for (`Reordered?`)
  - quantities that are plain decimal-point floats
  - ISO expiry dates, which the preset declares via `date_format: "%Y-%m-%d"`

All data is invented. Nothing here comes from any real vendor or stockroom.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

_OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"

_HEADERS = ["SKU", "Item", "On hand", "Units", "Use By", "Location", "Reordered?"]

_ROWS = [
    ["AB-11023", "Anti-FLAG M2 antibody", 2.5, "mL", "2026-03-01", "Freezer B / rack 4", "no"],
    ["TH-90455", "Trypsin-EDTA 0.25%", 12.0, "mL", "2026-01-15", "Fridge 2 / shelf 1", "yes"],
    ["SG-20881", "SYBR Green master mix", 8.0, "vials", "2025-11-30", "Freezer A / rack 1", "no"],
    ["DM-33017", "DMEM high glucose", 500.0, "mL", "2026-06-20", "Fridge 1 / shelf 3", "no"],
    ["PS-14200", "Penicillin-Streptomycin", 100.0, "mL", "2026-02-28", "Fridge 2 / shelf 2", "yes"],
    ["BS-77310", "Bovine serum albumin", 25.0, "g", "2027-01-10", "Cabinet C / shelf 2", "no"],
    ["PB-50012", "PBS tablets", 1000.0, "tablets", "2028-09-01", "Cabinet C / shelf 1", "no"],
    ["LP-60934", "Lipofectamine 3000", 0.75, "mL", "2025-12-05", "Freezer B / rack 2", "yes"],
]


def build() -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Stock on hand"

    sheet.append(["Verity Labs — reagent stockroom export"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_HEADERS))
    sheet.append([])
    sheet.append(_HEADERS)
    for row in _ROWS:
        sheet.append(row)

    _OUT.mkdir(parents=True, exist_ok=True)
    destination = _OUT / "verity_reagents_stock.xlsx"
    workbook.save(destination)
    return destination


if __name__ == "__main__":
    print(f"wrote {build()}")
