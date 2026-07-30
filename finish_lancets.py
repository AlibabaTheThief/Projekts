#!/usr/bin/env python3
"""
finish_lancets.py — complete the lower half of the symmetric Gothic window:
centre mullion, four cusped lancet heads, sill and base; and strip the top
construction circle plus the tiny r=5/r=10 centre-mark circles.

Reads the symmetric sketch, writes:
  out/skices_finished.dxf   (full drawing)
  out/skices_finished_clean.dxf (line-only main window near origin)
"""
import math, ezdxf

AX = 5620.65
# structural levels / positions read from the sketch
FRAME_L, FRAME_R = 5150.6, 6090.6      # inner frame sides
FRAME_BOT = 413.6                       # inner frame bottom
SILL = 644.2                            # light bottoms (existing mullion feet)
IMP = 917.8                             # impost / head springing (existing transom)
SUBFOOT = 1070.22                       # where the two sub-arches meet on the axis
MULL = [5150.6, 5385.6, 5620.65, 5855.7, 6090.6]   # light divisions
APEX = 1090.0                           # lancet-head apex height
CUSPS = True

TAU = 2 * math.pi


def add_pointed_head(msp, xl, xr, ys, ya):
    xc = (xl + xr) / 2; w = (xr - xl) / 2; h = ya - ys
    c = (h * h - w * w) / (2 * w); R = c + w
    aL = math.degrees(math.atan2(h, -c))
    msp.add_arc((xc + c, ys), R, aL, 180.0)          # left sweep -> spring at xl
    aR = math.degrees(math.atan2(h, c))
    msp.add_arc((xc - c, ys), R, 0.0, aR)            # right sweep -> spring at xr


def foil_pts(O, R, n, phase=0.0, samp=16):
    s = math.sin(math.pi / n); r = R * s / (1 + s); a = R - r
    C = [(O[0] + a * math.cos(phase + TAU * k / n),
          O[1] + a * math.sin(phase + TAU * k / n)) for k in range(n)]

    def cusp(k):
        A, B = C[k], C[(k + 1) % n]
        mx, my = (A[0] + B[0]) / 2, (A[1] + B[1]) / 2
        D = math.dist(A, B); hh = math.sqrt(max(r * r - (D / 2) ** 2, 0))
        dx, dy = B[0] - A[0], B[1] - A[1]; L = math.hypot(dx, dy)
        px, py = -dy / L, dx / L
        p, q = (mx + px * hh, my + py * hh), (mx - px * hh, my - py * hh)
        return p if math.dist(p, O) < math.dist(q, O) else q

    def norm(x):
        while x < 0: x += TAU
        while x >= TAU: x -= TAU
        return x

    pts = []
    for k in range(n):
        cen = C[k]; ci = cusp((k - 1) % n); co = cusp(k)
        ai = math.atan2(ci[1] - cen[1], ci[0] - cen[0])
        ao = math.atan2(co[1] - cen[1], co[0] - cen[0])
        amid = phase + TAU * k / n
        dccw = norm(ao - ai); midccw = norm(amid - ai)
        a1 = ai + dccw if midccw <= dccw else ai - norm(ai - ao)
        pts += [(cen[0] + r * math.cos(ai + (a1 - ai) * i / samp),
                 cen[1] + r * math.sin(ai + (a1 - ai) * i / samp)) for i in range(samp + 1)]
    return pts


def build():
    doc = ezdxf.readfile("out/skices_symmetric.dxf")
    msp = doc.modelspace()

    # --- strip unnecessary circles ---
    removed = 0
    for e in list(msp):
        if e.dxftype() != "CIRCLE":
            continue
        c = e.dxf.center; r = e.dxf.radius
        if c.x < 5000:                       # leave the side detail-studies alone
            continue
        if (abs(r - 240) < 1 and c.y > 1900) or r < 12:   # top circle + tiny centre marks
            msp.delete_entity(e); removed += 1
    print("removed circles:", removed)

    # --- centre mullion + complete impost + sill ---
    msp.add_line((AX, SILL), (AX, SUBFOOT))
    msp.add_line((MULL[1], IMP), (MULL[3], IMP))      # middle impost segment
    msp.add_line((FRAME_L, SILL), (FRAME_R, SILL))    # sill

    # --- base plinth (simple stepped moldings) ---
    for yy in (SILL - 40, FRAME_BOT + 55):
        msp.add_line((FRAME_L, yy), (FRAME_R, yy))

    # --- four lancet heads (+ cusping) ---
    for xl, xr in zip(MULL[:-1], MULL[1:]):
        add_pointed_head(msp, xl, xr, IMP, APEX)
        if CUSPS:
            xc = (xl + xr) / 2
            Rf = (xr - xl) * 0.33
            Of = (xc, IMP + 0.50 * (APEX - IMP))
            msp.add_lwpolyline(foil_pts(Of, Rf, 3, phase=math.pi / 2), close=True)

    doc.saveas("out/skices_finished.dxf")
    print("saved out/skices_finished.dxf ; entities:", len(list(msp)))

    # --- clean line-only extract of just the main window near origin ---
    out = ezdxf.new("R2018", setup=True)
    out.header["$INSUNITS"] = 1
    omsp = out.modelspace()
    ox, oy = 5120.6, 383.6
    xmin, xmax, ymin, ymax = 5100, 6140, 350, 2260
    kept = 0
    for e in msp:
        t = e.dxftype()
        if t not in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE"):
            continue
        if t == "LINE":
            s, en = e.dxf.start, e.dxf.end
            rx = (s.x + en.x) / 2
            if not (xmin <= rx <= xmax and ymin <= (s.y + en.y) / 2 <= ymax):
                continue
            if min(s.x, en.x) < 5115 or max(s.x, en.x) > 6125:   # drop construction overshoot
                continue
            omsp.add_line((s.x - ox, s.y - oy), (en.x - ox, en.y - oy))
        elif t in ("ARC", "CIRCLE"):
            c = e.dxf.center
            if not (xmin <= c.x <= xmax and ymin <= c.y <= ymax):
                continue
            if t == "CIRCLE":
                omsp.add_circle((c.x - ox, c.y - oy), e.dxf.radius)
            else:
                omsp.add_arc((c.x - ox, c.y - oy), e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle)
        else:
            pts = [(p[0], p[1]) for p in e.get_points()]
            rx = sum(a for a, _ in pts) / len(pts); ry = sum(b for _, b in pts) / len(pts)
            if not (xmin <= rx <= xmax and ymin <= ry <= ymax):
                continue
            omsp.add_lwpolyline([(p[0] - ox, p[1] - oy, p[4] if len(p) > 4 else 0)
                                 for p in e.get_points()], format="xyb", close=e.closed)
        kept += 1
    out.saveas("out/skices_finished_clean.dxf")
    print("clean extract:", kept, "entities -> out/skices_finished_clean.dxf")
    return doc


if __name__ == "__main__":
    build()
