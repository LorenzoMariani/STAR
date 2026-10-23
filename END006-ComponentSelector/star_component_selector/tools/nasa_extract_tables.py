"""Extract the on-board product tables of the NASA Small Spacecraft Technology
State of the Art report into audit/nasa_tables/<table>.csv (one row per product
row, with the source page). Run with the `star` env (pymupdf). Idempotent.

Only raw transcription: no mapping to the catalog and no invented values.
Cells merged vertically in the PDF (empty company) inherit the value above.
"""
import csv
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "NASA" / "NASA platform soa-2026.pdf"
OUT = ROOT / "audit" / "nasa_tables"

# table id -> (caption substring, subsystem tag). Ground segment, services,
# software, materials and surveys are not on-board components and are left out.
TABLES = {
    "3-2": ("Solar Array/Panel", "solar_panel"),
    "3-5": ("Battery (Pack)", "battery"),
    "3-7": ("Solid-State Batteries", "battery"),
    "3-8": ("Power Management and Distribution", "eps"),
    "4-2": ("Hydrazine", "propulsion"),
    "4-3": ("Monopropellant and Bipropellant", "propulsion"),
    "4-4": ("Hybrid Chemical", "propulsion"),
    "4-5": ("Cold Gas", "propulsion"),
    "4-6": ("Solid Motor", "propulsion"),
    "4-7": ("Electrothermal", "propulsion"),
    "4-8": ("Electrospray", "propulsion"),
    "4-9": ("Gridded-Ion", "propulsion"),
    "4-10": ("Hall-Effect", "propulsion"),
    "4-11": ("Pulsed Plasma", "propulsion"),
    "4-12": ("Ambipolar", "propulsion"),
    "4-13": ("Propellant-less", "propulsion"),
    "5-3": ("Reaction Wheels", "adcs"),
    "5-4": ("Magnetic Torquers", "adcs"),
    "5-5": ("Star Trackers", "adcs"),
    "5-6": ("Magnetometers", "adcs"),
    "5-7": ("sun sensors", "adcs"),
    "5-8": ("Horizon Sensors", "adcs"),
    "5-9": ("Gyros", "adcs"),
    "5-10": ("GPS Receivers", "gnss"),
    "5-12": ("Atomic Clocks", "clock"),
    "6-2": ("Commercial Primary CubeSat Structures", "structure"),
    "6-5": ("Actuator Mechanisms", "mechanism"),
    "6-6": ("Deployable Booms", "mechanism"),
    "6-7": ("Robotic Arms", "mechanism"),
    "7-3": ("Sprayable Thermal", "thermal_passive"),
    "7-4": ("Films, Tapes and MLI", "thermal_passive"),
    "7-5": ("Thermal Straps", "thermal_passive"),
    "7-7": ("Thermal Interface Materials", "thermal_passive"),
    "7-8": ("Phase Change Materials", "thermal_passive"),
    "7-9": ("Thermal Switches", "thermal_passive"),
    "7-11": ("Electrical Heaters", "heater"),
    "7-12": ("Cryocoolers", "thermal_active"),
    "7-13": ("Thermoelectric Coolers", "thermal_active"),
    "7-14": ("Fluid Loops", "thermal_active"),
    "8-4": ("Highly Integrated Onboard Computing", "obc"),
    "9-2": ("Antennas", "antenna"),
    "9-3": ("Radios", "comms"),
    "10-2": ("Dispensers", "dispenser"),
    "10-3": ("Separation Devices", "dispenser"),
    "13-2": ("Drag", "deorbit"),
}
# pages that follow a table under the same caption id but belong to another one
SKIP_PAGES = {"6-7": {207}}
CAP = re.compile(r"Table\s*(\d+)\s*-\s*(\d+)\s*[:.]")


def cell_text(page, bbox):
    """Cell text from characters, so spaces and decimal points are kept."""
    raw = page.get_text("rawdict", clip=pymupdf.Rect(bbox))
    lines = []
    for blk in raw["blocks"]:
        for ln in blk.get("lines", []):
            s, prev = "", None
            for sp in ln["spans"]:
                for ch in sp["chars"]:
                    x0, x1 = ch["bbox"][0], ch["bbox"][2]
                    if prev is not None and x0 - prev > 0.22 * sp["size"] and ch["c"] != " ":
                        s += " "
                    s += ch["c"]
                    prev = x1
            lines.append((round(ln["bbox"][1]), s.strip()))
    lines.sort()
    text = " ".join(t for _, t in lines if t)
    return re.sub(r"\s+", " ", text).strip()


def captions(page):
    out = []
    for m in CAP.finditer(page.get_text()):
        tid = f"{m.group(1)}-{m.group(2)}"
        if tid not in TABLES:
            continue
        hits = page.search_for(m.group(0).split(":")[0].replace(".", "")) or page.search_for(f"Table {tid}")
        for r in hits:
            line = page.get_text("text", clip=pymupdf.Rect(0, r.y0 - 2, page.rect.width, r.y1 + 2))
            if TABLES[tid][0].lower() in re.sub(r"\s+", " ", line).lower() or True:
                out.append((r.y0, tid))
    return sorted(set(out))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    acc = {}  # tid -> list of (page, header_or_None, rows)
    for pno in range(len(doc)):
        page = doc[pno]
        txt = page.get_text()
        if not any(f"{a}" in txt for a in ("Table ",)):
            continue
        caps = captions(page)
        if not caps:
            continue
        for tab in page.find_tables().tables:
            above = [c for c in caps if c[0] <= tab.bbox[1] + 6]
            if not above:
                continue
            tid = above[-1][1]
            if pno + 1 in SKIP_PAGES.get(tid, ()):
                continue
            rows = []
            for r in tab.rows:
                cells = []
                for c in r.cells:
                    cells.append(cell_text(page, c) if c else "")
                rows.append(cells)
            rows = [r for r in rows if any(r)]
            ncol = max((len(r) for r in rows), default=0)
            keep = [i for i in range(ncol) if any(i < len(r) and r[i] for r in rows)]
            rows = [[r[i] if i < len(r) else "" for i in keep] for r in rows]
            acc.setdefault(tid, []).append((pno + 1, rows))
    summary = []
    for tid in sorted(acc, key=lambda t: tuple(map(int, t.split("-")))):
        header, out = None, []
        for pno, rows in acc[tid]:
            for cells in rows:
                # drop merged-cell duplicates and empty columns later
                if not any(cells):
                    continue
                if cells[0].startswith("Table") and len([c for c in cells if c]) == 1:
                    continue
                if header is None:
                    header = cells
                    continue
                if cells == header or cells[0] == header[0]:
                    continue
                out.append((pno, cells))
        # keep only columns that carry something
        ncol = max(len(c) for _, c in out) if out else 0
        keep = [i for i in range(ncol)
                if any(i < len(c) and c[i] for _, c in out) or (header and i < len(header) and header[i])]
        last = ""
        path = OUT / f"table_{tid}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["table", "subsystem", "page"] + [(header[i] if header and i < len(header) else f"col{i}") for i in keep])
            for pno, cells in out:
                row = [cells[i] if i < len(cells) else "" for i in keep]
                if row and row[0]:
                    last = row[0]
                elif row:
                    row[0] = last
                w.writerow([tid, TABLES[tid][1], pno] + row)
        summary.append((tid, len(out), sorted({p for p, _ in acc[tid]})))
    missing = [t for t in TABLES if t not in acc]
    print("table  rows  pages")
    for tid, n, pages in summary:
        print(f"{tid:6} {n:4}  {pages[0]}-{pages[-1]}")
    print("no table found:", missing)


if __name__ == "__main__":
    sys.exit(main())
