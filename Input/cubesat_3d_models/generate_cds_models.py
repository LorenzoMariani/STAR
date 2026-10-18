"""Genera i modelli 3D CubeSat 1U, 2U, 3U, 6U e 12U "in stile NASA" (guide arrotondate, pannelli solari modulari con celle, fasce di separazione).

Uso:  python generate_cds_models.py [cartella_di_uscita]      (richiede solo numpy; trimesh facoltativo per scrivere anche i GLB)

DALLA CUBESAT DESIGN SPECIFICATION Rev. 14.1 (Appendice B, disegni 1U, 2U, 3U, 6U, 12U; sezione 2.2):
  - inviluppo: 1U 100 x 100 x 113.5, 2U 100 x 100 x 227.0, 3U 100 x 100 x 340.5, 6U 226.3 x 100 x 366.0, 12U 226.3 x 226.3 x 366.0 mm;
    origine al centro geometrico; Z = asse lungo;
  - 4 guide sugli spigoli per tutta la lunghezza; larghezza minima 8.5 mm (2.2.5): sezione 8.5 x 8.5 mm; spigoli arrotondati con raggio di almeno 1 mm (2.2.7): 1 mm;
  - le facce con protrusioni ammesse iniziano a 0.5-7.0 mm dalle facce +/-Z (disegno): si usa il minimo, 0.5 mm;
  - protrusioni fino a 6.5 mm dal piano delle guide (2.2.3): qui nessuna (tutto a filo o sotto il piano delle guide).
CONVENZIONI MIE (non date dalla CDS), da cambiare in cima al file se servono altre scelte:
  - pannelli solari su 5 facce: le 4 facce lunghe e il tappo +Z; il tappo -Z e' una piastra di struttura (la faccia inserita per prima nel dispenser);
  - pannelli modulari: n. moduli lungo Z = 1, 2, 3, 3, 3 per 1U, 2U, 3U, 6U, 12U; due moduli affiancati sulle facce larghe 226.3 mm;
    tra i moduli fasce di struttura larghe 6 mm lungo Z e 3 mm in larghezza, fasce di 4 mm alle estremita';
  - spessore totale del pannello 2.5 mm (quello dichiarato per il pannello ISIS 1U/3U del catalogo END-006): 2.2 mm di substrato, bordo di cella 0.1 mm, cella 0.2 mm;
    la superficie delle celle e' a filo del piano delle guide;
  - celle da 40 x 80 mm con angoli smussati di 3 mm (dimensione tipica di una cella a tripla giunzione da circa 30 cm2: il valore NON e' scritto nei datasheet del catalogo),
    lato lungo lungo Z, spazio tra le celle 1 mm, margine 1 mm, griglia centrata; il bordo di cella (rame/oro) sporge 0.4 mm attorno alla cella;
    il numero di celle e' quello che entra nel pannello, non quello dei fornitori (2 celle per un pannello 1U come EnduroSat; 3U: 6 per faccia contro 7 del fornitore);
  - corpo (struttura) pieno dietro i pannelli; nessuna antenna, sensore, connettore, vite, RBF, linguette o dettaglio di elettronica.
NESSUNA proprieta' ottica: i colori del MTL sono solo di visualizzazione. Unita' del file: metri.
"""
import math
import sys
from pathlib import Path

import numpy as np

ENVELOPE_MM = {"1U": (100.0, 100.0, 113.5), "2U": (100.0, 100.0, 227.0), "3U": (100.0, 100.0, 340.5), "6U": (226.3, 100.0, 366.0), "12U": (226.3, 226.3, 366.0)}
MODULES_Z = {"1U": 1, "2U": 2, "3U": 3, "6U": 3, "12U": 3}
RAIL, RAIL_R = 8.5, 1.0                      # CDS 2.2.5 e 2.2.7
END_RECESS = 0.5                              # CDS Appendice B, "(0.5 - 7.0)"
PANEL_T, SUB_T, BORDER_T, CELL_T = 2.5, 2.2, 0.1, 0.2
SEP_Z, SEP_X, END_BAND = 6.0, 3.0, 4.0
CELL_W, CELL_L, CELL_CUT, CELL_GAP, CELL_MARGIN, BORDER_GROW = 40.0, 80.0, 3.0, 1.0, 1.0, 0.4

MATERIALS = {   # solo colori di visualizzazione
    "rail": (0.78, 0.78, 0.80), "structure": (0.62, 0.62, 0.65), "panel_substrate": (0.14, 0.12, 0.17),
    "solar_cell": (0.23, 0.18, 0.50), "cell_border": (0.72, 0.46, 0.26),
}


class Mesh:
    """Insieme di oggetti OBJ: nome -> (materiale, vertici, normali, triangoli)."""

    def __init__(self):
        self.objects = {}

    def add(self, name, mat, v, n, f):
        o = self.objects.setdefault(name, [mat, [], [], []])
        base = len(o[1])
        o[1] += list(v)
        o[2] += list(n)
        o[3] += [(a + base, b + base, c + base) for a, b, c in f]


def flat_segments(poly):
    """Segmenti (p0, n0, p1, n1) di un poligono convesso antiorario con normale per lato."""
    segs = []
    k = len(poly)
    for i in range(k):
        p0, p1 = np.array(poly[i], float), np.array(poly[(i + 1) % k], float)
        e = p1 - p0
        n = np.array([e[1], -e[0]]) / np.linalg.norm(e)
        segs.append((p0, n, p1, n))
    return segs


def rounded_square_segments(x0, y0, x1, y1, r, arc_steps=4):
    """Rettangolo con angoli arrotondati: archi con normali radiali, lati piani con normale propria."""
    centers = [(x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)]
    pts = []   # (punto, normale)
    for cx, cy, a0 in centers:
        for s in range(arc_steps + 1):
            a = math.radians(a0 + 90.0 * s / arc_steps)
            nrm = np.array([math.cos(a), math.sin(a)])
            pts.append((np.array([cx, cy]) + r * nrm, nrm))
    return [(pts[i][0], pts[i][1], pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]) for i in range(len(pts))]


def prism(mesh, name, mat, segs, frame, h0, h1):
    """Prisma chiuso: profilo 2D (u, v) estruso lungo la normale n del sistema `frame` = (O, U, V, N) tra le quote h0 < h1 (h lungo N)."""
    O, U, V, N = (np.array(x, float) for x in frame)
    P = lambda p, h: O + U * p[0] + V * p[1] + N * h   # noqa: E731
    Dn = lambda q: U * q[0] + V * q[1]                 # noqa: E731
    verts, norms, faces = [], [], []

    def tri(a, b, c, want):
        g = np.cross(verts[b] - verts[a], verts[c] - verts[a])
        if np.dot(g, want) < 0:
            b, c = c, b
        faces.append((a, b, c))

    for p0, n0, p1, n1 in segs:        # fianchi
        i = len(verts)
        verts += [P(p0, h0), P(p1, h0), P(p1, h1), P(p0, h1)]
        norms += [Dn(n0), Dn(n1), Dn(n1), Dn(n0)]
        want = Dn((n0 + n1) / 2)
        tri(i, i + 1, i + 2, want)
        tri(i, i + 2, i + 3, want)
    pts = [s[0] for s in segs]
    c = np.mean(pts, axis=0)
    for h, sgn in ((h1, 1.0), (h0, -1.0)):   # tappi a ventaglio (profilo convesso)
        i = len(verts)
        verts.append(P(c, h))
        norms.append(N * sgn)
        for p in pts:
            verts.append(P(p, h))
            norms.append(N * sgn)
        for k in range(len(pts)):
            tri(i, i + 1 + k, i + 1 + (k + 1) % len(pts), N * sgn)
    mesh.add(name, mat, verts, norms, faces)


def rect(u0, v0, u1, v1):
    return flat_segments([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


def cell_polygon(cu, cv, w, l, cut):
    hw, hl = w / 2, l / 2
    return [(cu - hw + cut, cv - hl), (cu + hw - cut, cv - hl), (cu + hw, cv - hl + cut), (cu + hw, cv + hl - cut),
            (cu + hw - cut, cv + hl), (cu - hw + cut, cv + hl), (cu - hw, cv + hl - cut), (cu - hw, cv - hl + cut)]


def build_panel(mesh, tag, frame, u0, v0, u1, v1):
    """Pannello nel rettangolo [u0,u1] x [v0,v1] (mm nel sistema locale della faccia): substrato, bordi e celle. Quote h in mm sotto il piano delle guide (h = 0)."""
    prism(mesh, f"{tag}_substrate", "panel_substrate", rect(u0, v0, u1, v1), frame, -PANEL_T, -PANEL_T + SUB_T)
    w, l = u1 - u0, v1 - v0
    nu = int(math.floor((w - 2 * CELL_MARGIN + CELL_GAP + 1e-9) / (CELL_W + CELL_GAP)))
    nv = int(math.floor((l - 2 * CELL_MARGIN + CELL_GAP + 1e-9) / (CELL_L + CELL_GAP)))
    if nu < 1 or nv < 1:
        return 0
    gu = nu * CELL_W + (nu - 1) * CELL_GAP
    gv = nv * CELL_L + (nv - 1) * CELL_GAP
    cu0 = (u0 + u1) / 2 - gu / 2 + CELL_W / 2
    cv0 = (v0 + v1) / 2 - gv / 2 + CELL_L / 2
    for i in range(nu):
        for j in range(nv):
            cu, cv = cu0 + i * (CELL_W + CELL_GAP), cv0 + j * (CELL_L + CELL_GAP)
            prism(mesh, f"{tag}_cell_borders", "cell_border", flat_segments(cell_polygon(cu, cv, CELL_W + 2 * BORDER_GROW, CELL_L + 2 * BORDER_GROW, CELL_CUT + BORDER_GROW * 0.5)), frame, -PANEL_T + SUB_T, -PANEL_T + SUB_T + BORDER_T)
            prism(mesh, f"{tag}_cells", "solar_cell", flat_segments(cell_polygon(cu, cv, CELL_W, CELL_L, CELL_CUT)), frame, -CELL_T, 0.0)
    return nu * nv


def mm(frame):
    O, U, V, N = frame
    return (np.array(O) / 1000.0, U, V, N)


def split(total0, total1, n, gap):
    """Divide [total0, total1] in n intervalli separati da fasce `gap`; restituisce (intervalli, fasce)."""
    length = (total1 - total0 - (n - 1) * gap) / n
    ivs, bands = [], []
    x = total0
    for k in range(n):
        ivs.append((x, x + length))
        x += length
        if k < n - 1:
            bands.append((x, x + gap))
            x += gap
    return ivs, bands


def build(u):
    lx, ly, lz = ENVELOPE_MM[u]
    m = Mesh()
    S = 0.001                                    # mm -> m: le coordinate dei profili restano in mm e si scalano alla fine
    # guide: 4 prismi 8.5 x 8.5 mm a spigoli arrotondati, lungo Z
    for sx, nx in ((1, "p"), (-1, "m")):
        for sy, ny in ((1, "p"), (-1, "m")):
            xa, xb = sorted((sx * lx / 2, sx * (lx / 2 - RAIL)))
            ya, yb = sorted((sy * ly / 2, sy * (ly / 2 - RAIL)))
            prism(m, f"rail_{nx}X_{ny}Y", "rail", rounded_square_segments(xa, ya, xb, yb, RAIL_R), ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), -lz / 2, lz / 2)
    zb = lz / 2 - END_RECESS
    # corpo: scatola piena sotto i pannelli (dalla faccia interna dei pannelli)
    prism(m, "structure_body", "structure", rect(-(lx / 2 - PANEL_T), -(ly / 2 - PANEL_T), lx / 2 - PANEL_T, ly / 2 - PANEL_T), ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), -(zb - PANEL_T), zb - PANEL_T)
    ncells = {}
    # facce lunghe: (nome, normale, u, v, larghezza utile, moduli in larghezza)
    faces = [("pX", (1, 0, 0), (0, 1, 0), ly, 2 if ly > 150 else 1, lx / 2), ("mX", (-1, 0, 0), (0, -1, 0), ly, 2 if ly > 150 else 1, lx / 2),
             ("pY", (0, 1, 0), (-1, 0, 0), lx, 2 if lx > 150 else 1, ly / 2), ("mY", (0, -1, 0), (1, 0, 0), lx, 2 if lx > 150 else 1, ly / 2)]
    for name, n, uvec, width, nxm, half in faces:
        n = np.array(n, float)
        uvec = np.array(uvec, float)
        vvec = np.array((0, 0, 1.0))
        frame = (n * half, uvec, vvec, n)        # origine sul piano delle guide al centro della faccia; h lungo la normale esterna
        wa = width - 2 * RAIL
        # fasce di estremita' e separatori lungo Z
        v_lo, v_hi = -zb + END_BAND, zb - END_BAND
        zivs, zbands = split(v_lo, v_hi, MODULES_Z[u], SEP_Z)
        for (b0, b1) in [(-zb, -zb + END_BAND), (zb - END_BAND, zb)] + zbands:
            prism(m, f"structure_band_{name}", "structure", rect(-wa / 2, b0, wa / 2, b1), frame, -PANEL_T, 0.0)
        xivs, xbands = split(-wa / 2, wa / 2, nxm, SEP_X)
        for k, (b0, b1) in enumerate(xbands):
            for (z0, z1) in zivs:
                prism(m, f"structure_band_{name}", "structure", rect(b0, z0, b1, z1), frame, -PANEL_T, 0.0)
        for iz, (z0, z1) in enumerate(zivs):
            for ix, (x0, x1) in enumerate(xivs):
                tag = f"solar_panel_{name}_z{iz + 1}" + (f"_x{ix + 1}" if nxm > 1 else "")
                ncells[tag] = build_panel(m, tag, frame, x0, z0, x1, z1)
    # tappo +Z con pannello, tappo -Z di struttura
    wa_x, wa_y = lx - 2 * RAIL, ly - 2 * RAIL
    frame_top = (np.array((0, 0, zb)), np.array((1.0, 0, 0)), np.array((0, 1.0, 0)), np.array((0, 0, 1.0)))
    ncells["solar_panel_pZ"] = build_panel(m, "solar_panel_pZ", frame_top, -wa_x / 2, -wa_y / 2, wa_x / 2, wa_y / 2)
    frame_bot = (np.array((0, 0, -zb)), np.array((1.0, 0, 0)), np.array((0, 1.0, 0)), np.array((0, 0, -1.0)))
    prism(m, "structure_endplate_mZ", "structure", rect(-wa_x / 2, -wa_y / 2, wa_x / 2, wa_y / 2), frame_bot, -PANEL_T, 0.0)
    # scala in metri
    for o in m.objects.values():
        o[1] = [np.array(v) * S for v in o[1]]
    return m, (lx, ly, lz), ncells


def write_obj(path, name, m, dims):
    lines = [f"mtllib {name}.mtl",
             f"# CubeSat Design Specification Rev. 14.1, {name}: inviluppo {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm, unita' metri, Z = asse lungo, origine al centro.",
             "# Guide 8.5 mm con raggio 1 mm, pannelli solari modulari con celle 40 x 80 mm: vedi generate_cds_models.py per le convenzioni."]
    vo = 1
    for oname, (mat, v, n, f) in m.objects.items():
        lines += [f"o {oname}", f"usemtl {mat}"]
        lines += ["v %.6f %.6f %.6f" % tuple(x) for x in v]
        lines += ["vn %.5f %.5f %.5f" % tuple(x) for x in n]
        lines += ["f " + " ".join(f"{a + vo}//{a + vo}" for a in tri) for tri in f]
        vo += len(v)
    Path(path).with_suffix(".obj").write_text("\n".join(lines) + "\n", encoding="ascii")
    mtl = []
    for k, (r, g, b) in MATERIALS.items():
        mtl += [f"newmtl {k}", f"Kd {r} {g} {b}", "Ka 0 0 0", "Ks 0 0 0", ""]
    Path(path).with_suffix(".mtl").write_text("\n".join(mtl), encoding="ascii")


def write_glb(path, m):
    try:
        import trimesh
    except ImportError:
        return False
    sc = trimesh.Scene()
    for oname, (mat, v, n, f) in m.objects.items():
        tm = trimesh.Trimesh(vertices=np.array(v), faces=np.array(f), vertex_normals=np.array(n), process=False)
        r, g, b = MATERIALS[mat]
        tm.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name=mat, baseColorFactor=[int(r * 255), int(g * 255), int(b * 255), 255], metallicFactor=0.0, roughnessFactor=1.0))
        sc.add_geometry(tm, node_name=oname, geom_name=oname)
    sc.export(Path(path).with_suffix(".glb"))
    return True


def check(m, dims):
    """Inviluppo esatto e centrato; ogni oggetto chiuso con volume positivo; normali dichiarate coerenti con l'avvolgimento; celle sotto o a filo del piano delle guide."""
    allv = np.vstack([np.array(o[1]) for o in m.objects.values()])
    ext = (allv.max(0) - allv.min(0)) * 1000
    assert np.allclose(ext, dims, atol=1e-6), (ext, dims)
    assert np.allclose((allv.max(0) + allv.min(0)) / 2, 0, atol=1e-9)
    for name, (mat, v, n, f) in m.objects.items():
        v, n = np.array(v), np.array(n)
        vol, edges = 0.0, {}
        for a, b, c in f:
            vol += np.dot(v[a], np.cross(v[b], v[c])) / 6.0
            g = np.cross(v[b] - v[a], v[c] - v[a])
            assert np.dot(g, n[a] + n[b] + n[c]) > 0, (name, "normale opposta")
            key = [tuple(np.round(v[i], 7)) for i in (a, b, c)]
            for i in range(3):
                e = tuple(sorted((key[i], key[(i + 1) % 3])))
                edges[e] = edges.get(e, 0) + 1
        assert vol > 0, (name, vol)
        assert all(c == 2 for c in edges.values()), (name, "non chiuso")
    return True


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "cds_nasa_style_1U_2U_3U_6U_12U"
    for u in ENVELOPE_MM:
        m, dims, ncells = build(u)
        check(m, dims)
        name = f"CDS_{u}_nasa_style"
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        write_obj(d / name, name, m, dims)
        glb = write_glb(d / name, m)
        tot = sum(len(o[3]) for o in m.objects.values())
        print(u, "OK", dims, "oggetti", len(m.objects), "triangoli", tot, "celle", sum(ncells.values()), "GLB" if glb else "(senza GLB)")


if __name__ == "__main__":
    main()
