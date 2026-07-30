#!/usr/bin/env python3
"""
gothic_window.py — parametric, perfectly-symmetric line reconstruction of the
Gothic traceried window in the reference plate ("Fig. 1").

Everything is built from real Gothic compass geometry (two-centred arches,
multifoil cusping).  Non-axial elements are constructed on the RIGHT half and
mirrored across x=0, so bilateral symmetry is mathematically exact.  Output is
line-only: LINE / CIRCLE entities plus lightly-sampled polylines for the arcs
and foils.  Units = inches.
"""
import math
import ezdxf

TAU = 2 * math.pi
prims = []  # list of primitive dicts


# ---------- primitive builders ----------
def line(p1, p2):
    prims.append({"t": "line", "p1": p1, "p2": p2})

def circle(c, r):
    prims.append({"t": "circle", "c": c, "r": r})

def poly(pts, closed=False):
    prims.append({"t": "poly", "pts": [(float(x), float(y)) for x, y in pts], "closed": closed})


def sample_arc(c, r, a0, a1, n=48):
    """Points along a circular arc, a0->a1 in radians."""
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n),
             c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def pointed_arch(xc, w, ys, ya, n=40):
    """Two-centred (pointed) arch: half-span w about xc, springing y=ys,
    apex (xc, ya).  Adds the left and right sweeps as two open polylines."""
    h = ya - ys
    # c can be negative (drop arch) -> centres cross the axis, still valid
    c = (h * h - w * w) / (2 * w)
    R = c + w
    # left sweep: struck from right centre (xc+c, ys), from left spring to apex
    cr = (xc + c, ys)
    a_spring = math.atan2(ys - cr[1], (xc - w) - cr[0])   # to (xc-w, ys)
    a_apex = math.atan2(ya - cr[1], xc - cr[0])           # to (xc, ya)
    poly(sample_arc(cr, R, a_spring, a_apex, n))
    # right sweep: mirror of the left about x=xc
    cl = (xc - c, ys)
    a_spring2 = math.atan2(ys - cl[1], (xc + w) - cl[0])
    a_apex2 = math.atan2(ya - cl[1], xc - cl[0])
    poly(sample_arc(cl, R, a_spring2, a_apex2, n))


def foil(O, R, n, phase=0.0, samp=14):
    """Closed multifoil outline (n lobes) inscribed in circle radius R about O.
    Classic construction: lobe radius r = R*sin(pi/n)/(1+sin(pi/n))."""
    s = math.sin(math.pi / n)
    r = R * s / (1 + s)
    a = R - r                                   # lobe-centre distance
    centres = [(O[0] + a * math.cos(phase + TAU * k / n),
                O[1] + a * math.sin(phase + TAU * k / n)) for k in range(n)]

    def cusp(k):
        C0, C1 = centres[k], centres[(k + 1) % n]
        mx, my = (C0[0] + C1[0]) / 2, (C0[1] + C1[1]) / 2
        D = math.dist(C0, C1)
        hh = math.sqrt(max(r * r - (D / 2) ** 2, 0))
        # perpendicular to C0->C1
        dx, dy = C1[0] - C0[0], C1[1] - C0[1]
        L = math.hypot(dx, dy)
        px, py = -dy / L, dx / L
        p_a = (mx + px * hh, my + py * hh)
        p_b = (mx - px * hh, my - py * hh)
        # inner cusp = the one nearer O
        return p_a if math.dist(p_a, O) < math.dist(p_b, O) else p_b

    pts = []
    for k in range(n):
        C = centres[k]
        c_in = cusp((k - 1) % n)                 # cusp before this lobe
        c_out = cusp(k)                          # cusp after this lobe
        a_in = math.atan2(c_in[1] - C[1], c_in[0] - C[0])
        a_out = math.atan2(c_out[1] - C[1], c_out[0] - C[0])
        a_mid = phase + TAU * k / n              # outward direction (on lobe circle)
        # choose sweep a_in -> a_out that passes through a_mid
        def norm(x):
            while x < 0: x += TAU
            while x >= TAU: x -= TAU
            return x
        d_ccw = norm(a_out - a_in)
        mid_ccw = norm(a_mid - a_in)
        if mid_ccw <= d_ccw:
            a1 = a_in + d_ccw
        else:
            a1 = a_in - norm(a_in - a_out)
        pts += sample_arc(C, r, a_in, a1, samp)
    poly(pts, closed=True)


def mirror_new(from_index):
    """Mirror every primitive added since `from_index` across x=0 (appends copies)."""
    for p in prims[from_index:]:
        if p["t"] == "line":
            line((-p["p1"][0], p["p1"][1]), (-p["p2"][0], p["p2"][1]))
        elif p["t"] == "circle":
            circle((-p["c"][0], p["c"][1]), p["r"])
        elif p["t"] == "poly":
            poly([(-x, y) for x, y in p["pts"]], p["closed"])


# =====================================================================
#  PARAMETERS (inches, proportions matched to the plate)
# =====================================================================
IWh = 65.0                     # inner opening half-width  (130 total)
JT = 15.0                      # jamb / frame thickness
OWh = IWh + JT                 # outer half-width
CORN_OH, CORN_H = 10.0, 15.0   # cornice overhang / height
BASE_OH, BASE_H = 9.0, 6.0     # base overhang / cap

SILL = 30.0                    # top of base / bottom of lights
FRAME_TOP = 250.0              # top of rectangular frame opening
CORN_TOP = FRAME_TOP + CORN_H

# lancet lights
N_LIGHTS = 4
mullions_x = [-32.5, 0.0, 32.5]          # 3 internal mullions -> 4 lights
LANCET_SPRING = 116.0
LANCET_APEX = 145.0

# secondary (sub-arch) tracery grouping the lights in two pairs
SUB_SPRING = 145.0
SUB_APEX = 190.0

# main arch (drop-pointed), springs at the inner jambs
MAIN_SPRING = 150.0
MAIN_APEX = 236.0

# rose
ROSE_C = (0.0, 200.0)
ROSE_R = 33.0
# side circles (trefoil in triangle)
SIDE_C = (32.5, 168.0)
SIDE_R = 21.0
# corner spandrel foils
CORN_C = (49.0, 214.0)
CORN_R = 10.5


def build():
    # ---- outer frame (rectangle) + cornice + base --------------------
    line((-OWh, SILL), (-OWh, FRAME_TOP))
    line((OWh, SILL), (OWh, FRAME_TOP))
    line((-OWh, FRAME_TOP), (OWh, FRAME_TOP))
    # inner opening rectangle
    line((-IWh, SILL), (-IWh, FRAME_TOP))
    line((IWh, SILL), (IWh, FRAME_TOP))
    # cornice cap
    line((-OWh - CORN_OH, FRAME_TOP), (OWh + CORN_OH, FRAME_TOP))
    line((-OWh - CORN_OH, FRAME_TOP), (-OWh - CORN_OH, CORN_TOP))
    line((OWh + CORN_OH, FRAME_TOP), (OWh + CORN_OH, CORN_TOP))
    line((-OWh - CORN_OH, CORN_TOP), (OWh + CORN_OH, CORN_TOP))
    # base plinth
    for yy in (SILL, SILL - BASE_H):
        line((-OWh - BASE_OH, yy), (OWh + BASE_OH, yy))
    line((-OWh - BASE_OH, SILL - BASE_H), (-OWh - BASE_OH, SILL))
    line((OWh + BASE_OH, SILL - BASE_H), (OWh + BASE_OH, SILL))
    line((-OWh, SILL), (-OWh, SILL - BASE_H))
    line((OWh, SILL), (OWh, SILL - BASE_H))

    # ---- main pointed arch (bar tracery head) ------------------------
    pointed_arch(0.0, IWh, MAIN_SPRING, MAIN_APEX, n=60)

    # ---- rose : quatrefoil + inscribed diamond -----------------------
    circle(ROSE_C, ROSE_R)
    foil(ROSE_C, ROSE_R * 0.90, 4, phase=0.0)          # quatrefoil, lobes N/E/S/W
    rd = ROSE_R * 0.62                                   # inscribed square (diamond)
    dv = [(ROSE_C[0] + rd * math.cos(math.pi/4 + TAU*k/4),
           ROSE_C[1] + rd * math.sin(math.pi/4 + TAU*k/4)) for k in range(4)]
    poly(dv, closed=True)

    # ================= RIGHT-HALF ELEMENTS (mirrored) =================
    start = len(prims)

    # right jamb-to-first-mullion lights + mullions
    for mx in [m for m in mullions_x if m > 0] + [IWh]:
        line((mx, SILL), (mx, LANCET_SPRING))
    # central mullion at x=0 rises full height of light zone
    # (added once, symmetric)  -> handle after mirror

    # right two lancet heads (lights 3 and 4 : x 0..32.5 and 32.5..65)
    for (xl, xr) in [(0.0, 32.5), (32.5, 65.0)]:
        xc = (xl + xr) / 2
        w = (xr - xl) / 2
        pointed_arch(xc, w, LANCET_SPRING, LANCET_APEX, n=22)
        # trefoil cusping inside the head
        foil((xc, LANCET_SPRING + 0.55 * (LANCET_APEX - LANCET_SPRING)),
             w * 0.72, 3, phase=math.pi / 2, samp=10)

    # right sub-arch grouping lights 3-4  (spans x 0..65)
    pointed_arch(IWh / 2, IWh / 2, SUB_SPRING, SUB_APEX, n=40)

    # right side circle : trefoil set in a triangle
    circle(SIDE_C, SIDE_R)
    tri = [(SIDE_C[0] + SIDE_R * math.cos(math.pi/2 + TAU*k/3),
            SIDE_C[1] + SIDE_R * math.sin(math.pi/2 + TAU*k/3)) for k in range(3)]
    poly(tri, closed=True)
    foil(SIDE_C, SIDE_R * 0.78, 3, phase=math.pi / 2)

    # right corner spandrel foil (trefoil in small circle)
    circle(CORN_C, CORN_R)
    foil(CORN_C, CORN_R * 0.82, 3, phase=-math.pi / 2)

    mirror_new(start)

    # ---- axial (self-symmetric) members ------------------------------
    line((0.0, SILL), (0.0, LANCET_SPRING))            # central mullion
    # central mullion continues up as a shaft to the rose
    line((0.0, LANCET_APEX), (0.0, ROSE_C[1] - ROSE_R))


# =====================================================================
#  writers
# =====================================================================
def write_dxf(path):
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 1        # inches
    msp = doc.modelspace()
    for p in prims:
        if p["t"] == "line":
            msp.add_line(p["p1"], p["p2"], dxfattribs={"layer": "0"})
        elif p["t"] == "circle":
            msp.add_circle(p["c"], p["r"], dxfattribs={"layer": "0"})
        elif p["t"] == "poly":
            msp.add_lwpolyline(p["pts"], close=p["closed"], dxfattribs={"layer": "0"})
    doc.saveas(path)


def render_png(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 11))
    for p in prims:
        if p["t"] == "line":
            ax.plot([p["p1"][0], p["p2"][0]], [p["p1"][1], p["p2"][1]], "k", lw=0.9)
        elif p["t"] == "circle":
            ax.add_patch(plt.Circle(p["c"], p["r"], fill=False, lw=0.9, ec="k"))
        elif p["t"] == "poly":
            xs = [q[0] for q in p["pts"]]; ys = [q[1] for q in p["pts"]]
            if p["closed"]:
                xs += [xs[0]]; ys += [ys[0]]
            ax.plot(xs, ys, "k", lw=0.9)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_xlim(-OWh - 25, OWh + 25); ax.set_ylim(SILL - BASE_H - 10, CORN_TOP + 10)
    plt.tight_layout(); plt.savefig(path, dpi=120, bbox_inches="tight")


if __name__ == "__main__":
    build()
    write_dxf("out/gothic_window.dxf")
    render_png("out/gothic_window.png")
    print("primitives:", len(prims))
    print("wrote out/gothic_window.dxf and out/gothic_window.png")
