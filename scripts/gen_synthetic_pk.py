"""Generate 10 messy synthetic preclinical-PK / assay files for AssayIngest.

Every "vendor" formats its export differently on purpose — different headers,
units, date formats, sheet layouts and junk — so the mapper has real work to do.
All data is fully synthetic (no real/confidential source). Target fields the
mapper must recover: compound_id, assay_type, value, unit, target,
n_replicates, assay_date.

Run:  uv run python scripts/gen_synthetic_pk.py
Output: data/synthetic/*.xlsx (+ a couple of oddball .csv)
"""

from __future__ import annotations

import csv
import io
import random
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
OUT.mkdir(parents=True, exist_ok=True)

RNG = random.Random(20260709)  # deterministic output

TARGETS = ["EGFR", "JAK2", "BRAF", "ALK", "KRAS", "CDK4", "PARP1", "BTK", "MEK1", "PI3K"]
ASSAYS_CONC = ["IC50", "EC50", "Ki", "Kd"]


def conc_value(unit: str) -> float:
    """A plausible potency for the given unit's typical magnitude."""
    if unit == "nM":
        return round(RNG.uniform(0.2, 950.0), RNG.choice([1, 2, 3]))
    if unit in ("µM", "uM"):
        return round(RNG.uniform(0.003, 40.0), 3)
    return round(RNG.uniform(5.0, 98.0), 1)  # % inhibition


def compound(prefix: str, n: int, width: int = 3) -> str:
    return f"{prefix}-{n:0{width}d}"


def date_iso(day: int) -> tuple[int, int, int]:
    """A (y, m, d) tuple in early 2025, cycling days for variety."""
    d = 1 + (day % 27)
    m = 1 + (day // 27) % 12
    return (2025, m, d)


def european_thousands_decimal(value: float) -> str:
    """Format a number with a '.' thousands separator and ',' decimal --
    e.g. 1234.56 -> "1.234,56". Distinct from the corpus's existing bare
    decimal-comma hazard (pinnacle_labs_export.csv's "11,076", which never
    crosses the 1000 threshold that triggers thousands grouping): this is
    the classic European vendor-export pattern the ten-file corpus never
    exercised (02-RESEARCH.md Pitfall, "1.234,56" gap).
    """
    us_grouped = f"{value:,.2f}"  # "1,234.56"
    placeholder = "\x00"  # never appears in a formatted number; swap-safe
    return (
        us_grouped.replace(",", placeholder)
        .replace(".", ",")
        .replace(placeholder, ".")
    )


def autosize(ws) -> None:
    for col in ws.columns:
        length = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(length + 2, 40)


def save(wb: Workbook, name: str) -> None:
    path = OUT / name
    wb.save(path)
    print(f"  wrote {path.relative_to(OUT.parent.parent)}  ({len(wb.sheetnames)} sheet(s))")


# --------------------------------------------------------------------------
# 1. Zephyr Bio — cover/metadata rows above the real header, one sheet per week
# --------------------------------------------------------------------------
def gen_zephyr() -> None:
    wb = Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)
    for wk in (1, 2, 3):
        ws = wb.create_sheet(f"Week {wk}")
        ws["A1"] = "ZEPHYR BIOSCIENCES — Kinase Panel Study ZB-2025-0" + str(wk)
        ws["A1"].font = bold
        ws["A2"] = "Study Director: Dr. A. Powell     Protocol: KIN-STD-v4"
        ws["A3"] = "Report generated 2025-0%d-15   CONFIDENTIAL (synthetic demo)" % wk
        # blank row 4, header on row 5
        header = ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates", "Run Date"]
        for c, h in enumerate(header, start=1):
            cell = ws.cell(row=5, column=c, value=h)
            cell.font = bold
        r = 6
        for i in range(8):
            unit = RNG.choice(["nM", "uM"])
            assay = RNG.choice(ASSAYS_CONC)
            y, m, d = date_iso(wk * 10 + i)
            ws.cell(row=r, column=1, value=compound("ZB", wk * 100 + i))
            ws.cell(row=r, column=2, value=assay)
            ws.cell(row=r, column=3, value=conc_value(unit))
            ws.cell(row=r, column=4, value=unit)
            ws.cell(row=r, column=5, value=RNG.choice(TARGETS))
            ws.cell(row=r, column=6, value=RNG.choice([2, 3, 3, 4]))
            ws.cell(row=r, column=7, value=f"{y}-{m:02d}-{d:02d}")
            r += 1
        autosize(ws)
    save(wb, "zephyr_bio_ZB-2025.xlsx")


# --------------------------------------------------------------------------
# 2. Meridian CRO — cryptic 3-4 letter column codes, epoch-ish date serials
# --------------------------------------------------------------------------
def gen_meridian() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "DATA"
    header = ["CMP", "ASY", "VAL", "UOM", "TGT", "NREP", "DT"]
    ws.append(header)
    for i in range(14):
        unit = RNG.choice(["nM", "µM"])
        y, m, d = date_iso(i * 2)
        ws.append([
            compound("MER", 4500 + i, width=4),
            RNG.choice(ASSAYS_CONC).lower(),  # lowercase assay labels
            conc_value(unit),
            unit,
            RNG.choice(TARGETS),
            RNG.choice([1, 2, 3]),
            f"{d:02d}-{m:02d}-{y}",  # DD-MM-YYYY
        ])
    autosize(ws)
    # a legend sheet nobody asked for
    legend = wb.create_sheet("LEGEND")
    for row in [
        ["CMP", "compound identifier"],
        ["ASY", "assay type"],
        ["VAL", "measured value"],
        ["UOM", "unit of measure"],
        ["TGT", "biological target"],
        ["NREP", "number of replicates"],
        ["DT", "acquisition date (DD-MM-YYYY)"],
    ]:
        legend.append(row)
    autosize(legend)
    save(wb, "meridian_cro_codes.xlsx")


# --------------------------------------------------------------------------
# 3. Apex Labs — WIDE format: one row per compound, a value column per target
# --------------------------------------------------------------------------
def gen_apex() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "IC50 matrix (nM)"
    used = TARGETS[:5]
    ws.append(["Cmpd"] + used + ["n", "Date tested"])
    for i in range(12):
        y, m, d = date_iso(i)
        row = [compound("APX", i + 1)]
        row += [conc_value("nM") for _ in used]
        row += [RNG.choice([2, 3, 4]), f"{m:02d}/{d:02d}/{y}"]  # MM/DD/YYYY
        ws.append(row)
    autosize(ws)
    save(wb, "apex_labs_wide_matrix.xlsx")


# --------------------------------------------------------------------------
# 4. Helix Genomics — unit embedded in header, comma decimals (European)
# --------------------------------------------------------------------------
def gen_helix_eu() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ergebnisse"
    ws.append(["Substanz", "Methode", "Konz. (µM)", "Zielprotein", "Wdh.", "Datum"])
    for i in range(13):
        val = conc_value("µM")
        y, m, d = date_iso(i * 3)
        ws.append([
            compound("HGX", 200 + i),
            RNG.choice(["IC50", "EC50", "Ki"]),
            str(val).replace(".", ","),  # European decimal comma, as text
            RNG.choice(TARGETS),
            RNG.choice([2, 3]),
            f"{d:02d}.{m:02d}.{y}",  # DD.MM.YYYY
        ])
    autosize(ws)
    save(wb, "helix_genomics_DE.xlsx")


# --------------------------------------------------------------------------
# 5. BioNexus — TRANSPOSED: fields are rows, each compound is a column
# --------------------------------------------------------------------------
def gen_bionexus() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    n = 8
    fields = {
        "Compound": [compound("BNX", i + 1) for i in range(n)],
        "Assay type": [RNG.choice(ASSAYS_CONC) for _ in range(n)],
        "Value (nM)": [conc_value("nM") for _ in range(n)],
        "Target": [RNG.choice(TARGETS) for _ in range(n)],
        "N": [RNG.choice([2, 3, 4]) for _ in range(n)],
        "Assay date": [f"{date_iso(i)[0]}-{date_iso(i)[1]:02d}-{date_iso(i)[2]:02d}" for i in range(n)],
    }
    for field, values in fields.items():
        ws.append([field] + values)
    autosize(ws)
    save(wb, "bionexus_transposed.xlsx")


# --------------------------------------------------------------------------
# 6. Orion PK — dosing/PK-flavoured wording; separate Summary + Raw sheets
# --------------------------------------------------------------------------
def gen_orion() -> None:
    wb = Workbook()
    summ = wb.active
    summ.title = "Summary"
    summ.append(["Test Article", "Parameter", "Mean", "Unit", "Molecular Target", "N animals", "Study Day"])
    for i in range(10):
        unit = RNG.choice(["nM", "uM"])
        y, m, d = date_iso(i * 2)
        summ.append([
            compound("ORN", 700 + i),
            RNG.choice(["IC50", "EC50", "Kd"]),
            conc_value(unit),
            unit,
            RNG.choice(TARGETS),
            RNG.choice([3, 4, 6]),
            f"{y}/{m:02d}/{d:02d}",  # YYYY/MM/DD
        ])
    autosize(summ)
    raw = wb.create_sheet("Raw timepoints")
    raw.append(["Test Article", "Timepoint (h)", "Conc", "Unit"])
    for i in range(10):
        for tp in (0.5, 1, 2, 4, 8):
            raw.append([compound("ORN", 700 + i), tp, conc_value("nM"), "nM"])
    autosize(raw)
    notes = wb.create_sheet("Notes")
    notes["A1"] = "Vehicle: 0.5% MC. Route: PO. Species: mouse (synthetic)."
    save(wb, "orion_pk_report.xlsx")


# --------------------------------------------------------------------------
# 7. Summit Discovery — MERGED assay+unit in one cell, % inhibition mixed in
# --------------------------------------------------------------------------
def gen_summit() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(["id ", "readout", "measurement", "gene", "reps", "date"])  # trailing space in 'id '
    for i in range(15):
        if RNG.random() < 0.4:
            assay, unit = "% inhibition", "%"
            val = conc_value("%")
            readout = "Inhibition %"
            meas = f"{val}"
        else:
            unit = RNG.choice(["nM", "uM"])
            assay = RNG.choice(ASSAYS_CONC)
            val = conc_value(unit)
            readout = f"{assay} ({unit})"  # assay AND unit fused in the header value
            meas = f"{val}"
        y, m, d = date_iso(i)
        ws.append([
            compound("SMT", 30 + i),
            readout,
            meas,
            RNG.choice(TARGETS),
            RNG.choice([2, 3]),
            f"{m}/{d}/{y}",  # M/D/YYYY, no zero padding
        ])
    autosize(ws)
    save(wb, "summit_discovery_mixed.xlsx")


# --------------------------------------------------------------------------
# 8. Cascade Assays — no unit column at all (must be inferred), terse headers
#    + a blank-named column of junk in the middle
# --------------------------------------------------------------------------
def gen_cascade() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # header row: one column intentionally blank
    ws.append(["cmpd", "potency", "", "target_gene", "#", "run"])
    for i in range(12):
        y, m, d = date_iso(i)
        ws.append([
            compound("CAS", 5000 + i, width=4),
            conc_value("nM"),      # unit missing entirely -> infer nM from range
            RNG.choice(["QC-pass", "QC-pass", "flag"]),  # junk in the blank column
            RNG.choice(TARGETS),
            RNG.choice([2, 3, 3]),
            f"{y}{m:02d}{d:02d}",  # YYYYMMDD compact
        ])
    autosize(ws)
    save(wb, "cascade_assays_nounit.xlsx")


# --------------------------------------------------------------------------
# 9. Delta Screening — one sheet PER TARGET, headers differ slightly per sheet
# --------------------------------------------------------------------------
def gen_delta() -> None:
    wb = Workbook()
    wb.remove(wb.active)
    variants = [
        ("EGFR panel", ["Compound", "IC50 (nM)", "Reps", "Date"]),
        ("JAK2 panel", ["Cmpd ID", "IC50 nM", "# runs", "Tested on"]),
        ("BRAF panel", ["compound_id", "ic50_nm", "n", "date"]),
    ]
    for (title, header), target in zip(variants, ["EGFR", "JAK2", "BRAF"]):
        ws = wb.create_sheet(title)
        ws.append(header)
        for i in range(9):
            y, m, d = date_iso(i)
            ws.append([
                compound("DLT", 800 + i),
                conc_value("nM"),
                RNG.choice([2, 3, 4]),
                f"{d:02d}/{m:02d}/{y}",  # DD/MM/YYYY
            ])
        autosize(ws)
    save(wb, "delta_screening_per_target.xlsx")


# --------------------------------------------------------------------------
# 10. Pinnacle — semicolon-delimited CSV, comma decimals, header junk lines
# --------------------------------------------------------------------------
def gen_pinnacle_csv() -> None:
    path = OUT / "pinnacle_labs_export.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Pinnacle Labs — assay export v2 (synthetic)\n")
        fh.write("# generated: 2025-06-01; delimiter=';'; decimal=','\n")
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Compound", "Endpoint", "Value", "Unit", "Target", "Replicates", "Date"])
        for i in range(14):
            unit = RNG.choice(["nM", "uM"])
            y, m, d = date_iso(i)
            val = str(conc_value(unit)).replace(".", ",")
            w.writerow([
                compound("PIN", 10 + i),
                RNG.choice(ASSAYS_CONC),
                val,
                unit,
                RNG.choice(TARGETS),
                RNG.choice([2, 3]),
                f"{d:02d}/{m:02d}/{y}",
            ])
    print(f"  wrote {path.relative_to(OUT.parent.parent)}  (semicolon CSV)")


# --------------------------------------------------------------------------
# 11. Vantage PK — normal data sheet + an embedded chart (D-16): the chart
#    must not disqualify the sheet, pd.read_excel's shape is unaffected by a
#    floating drawing anchor.
# --------------------------------------------------------------------------
def gen_chart_embedded() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    ws.append(["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"])
    for i in range(10):
        unit = RNG.choice(["nM", "uM"])
        assay = RNG.choice(ASSAYS_CONC)
        y, m, d = date_iso(i)
        ws.append([
            compound("VTG", 100 + i),
            assay,
            conc_value(unit),
            unit,
            RNG.choice(TARGETS),
            RNG.choice([2, 3, 4]),
            f"{y}-{m:02d}-{d:02d}",
        ])
    autosize(ws)
    chart = BarChart()
    chart.title = "Result by compound"
    data = Reference(ws, min_col=3, min_row=1, max_row=11)
    chart.add_data(data, titles_from_data=True)
    ws.add_chart(chart, "E2")
    save(wb, "vantage_pk_with_chart.xlsx")


# --------------------------------------------------------------------------
# 12. Nimbus Labs — a data sheet plus a dedicated chartsheet (D-17): ranking
#    must drop the chartsheet automatically and never crash reading it.
# --------------------------------------------------------------------------
def gen_chartsheet() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"])
    for i in range(10):
        unit = RNG.choice(["nM", "uM"])
        assay = RNG.choice(ASSAYS_CONC)
        y, m, d = date_iso(i)
        ws.append([
            compound("NBL", 200 + i),
            assay,
            conc_value(unit),
            unit,
            RNG.choice(TARGETS),
            RNG.choice([2, 3, 4]),
            f"{y}-{m:02d}-{d:02d}",
        ])
    autosize(ws)
    chart = BarChart()
    chart.title = "Result overview"
    data = Reference(ws, min_col=3, min_row=1, max_row=11)
    chart.add_data(data, titles_from_data=True)
    chartsheet = wb.create_chartsheet("Chart Overview")
    chartsheet.add_chart(chart)
    save(wb, "nimbus_labs_chartsheet.xlsx")


# --------------------------------------------------------------------------
# 13. Quantex — a sheet holding only a pasted/scanned image, no cells at all
#    (D-18): must surface a structural question, never "no data rows".
#    Pillow is dev-only (D-19) -- imported here, never from src/assayingest/.
# --------------------------------------------------------------------------
def gen_image_only_sheet() -> None:
    from openpyxl.drawing.image import Image
    from PIL import Image as PILImage

    wb = Workbook()
    ws = wb.active
    ws.title = "Scanned Report"
    buf = io.BytesIO()
    PILImage.new("RGB", (200, 100), color="white").save(buf, format="PNG")
    buf.seek(0)
    ws.add_image(Image(buf), "A1")
    save(wb, "quantex_scanned_report.xlsx")


# --------------------------------------------------------------------------
# 14. Triton Screening — one sheet, two independent data blocks with
#    different headers, separated by >= 2 fully-blank rows (D-10's
#    multiple_tables shape -- previously untested, a real corpus gap).
# --------------------------------------------------------------------------
def gen_multiple_tables() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Combined"
    ws.append(["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"])
    for i in range(8):
        unit = RNG.choice(["nM", "uM"])
        assay = RNG.choice(ASSAYS_CONC)
        y, m, d = date_iso(i)
        ws.append([
            compound("TRX", 300 + i),
            assay,
            conc_value(unit),
            unit,
            RNG.choice(TARGETS),
            RNG.choice([2, 3, 4]),
            f"{y}-{m:02d}-{d:02d}",
        ])
    ws.append([])
    ws.append([])
    ws.append(["Batch ID", "Reviewer", "QC Status", "Notes"])
    for i in range(5):
        ws.append([
            compound("QC", 400 + i),
            RNG.choice(["A. Lin", "M. Reyes", "S. Okafor"]),
            RNG.choice(["pass", "pass", "flag"]),
            "synthetic",
        ])
    autosize(ws)
    save(wb, "triton_screening_two_tables.xlsx")


# --------------------------------------------------------------------------
# 15. Vertex PK — European CRO export whose values cross the 1000 threshold,
#    formatted with a '.' thousands separator AND a ',' decimal separator
#    (e.g. "1.234,56") -- the classic European vendor pattern 02-RESEARCH.md
#    flagged as absent from the ten-file corpus (Pitfall: distinct from
#    pinnacle_labs_export.csv's bare decimal-comma, which never reaches
#    1000). PK-flavoured (AUC) so it doubles as a plausible target for the
#    pk-parameters preset.
# --------------------------------------------------------------------------
def gen_vertex_eu_thousands() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ergebnisse"
    ws.append(["Verbindung", "Parameter", "Wert (ng*h/mL)", "Zielprotein", "Wdh.", "Datum"])
    for i in range(12):
        auc = round(RNG.uniform(1000.0, 9800.0), 2)
        y, m, d = date_iso(i * 2)
        ws.append([
            compound("VTX", 900 + i),
            "AUC",
            european_thousands_decimal(auc),
            RNG.choice(TARGETS),
            RNG.choice([2, 3]),
            f"{d:02d}.{m:02d}.{y}",  # DD.MM.YYYY, matches helix_genomics_DE's convention
        ])
    autosize(ws)
    save(wb, "vertex_pk_eu_format.xlsx")


# --------------------------------------------------------------------------
# 16. CastleBio — a data sheet whose date column is a genuine Excel-native
#    date-typed cell (ws.cell(...).value = date(y, m, d)), not a formatted
#    string like every other fixture's dates -- 02-RESEARCH.md Pitfall 6:
#    openpyxl returns a real datetime.date back for such a cell, a shape no
#    date_format string (e.g. "%d/%m/%Y") will match via strptime.
# --------------------------------------------------------------------------
def gen_native_date_cell() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    header = ["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Tested On"]
    ws.append(header)
    for i in range(10):
        unit = RNG.choice(["nM", "uM"])
        assay = RNG.choice(ASSAYS_CONC)
        y, m, d = date_iso(i)
        row = i + 2  # header occupies row 1
        ws.cell(row=row, column=1, value=compound("CBI", 500 + i))
        ws.cell(row=row, column=2, value=assay)
        ws.cell(row=row, column=3, value=conc_value(unit))
        ws.cell(row=row, column=4, value=unit)
        ws.cell(row=row, column=5, value=RNG.choice(TARGETS))
        ws.cell(row=row, column=6, value=RNG.choice([2, 3, 4]))
        ws.cell(row=row, column=7, value=date(y, m, d))  # native date, not a string
    autosize(ws)
    save(wb, "castlebio_native_dates.xlsx")


def main() -> None:
    print("Generating messy synthetic PK/assay files ->", OUT)
    gen_zephyr()
    gen_meridian()
    gen_apex()
    gen_helix_eu()
    gen_bionexus()
    gen_orion()
    gen_summit()
    gen_cascade()
    gen_delta()
    gen_pinnacle_csv()
    gen_chart_embedded()
    gen_chartsheet()
    gen_image_only_sheet()
    gen_multiple_tables()
    gen_vertex_eu_thousands()
    gen_native_date_cell()
    print("Done. 16 new files.")


if __name__ == "__main__":
    main()