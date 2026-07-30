#!/usr/bin/env python3
"""
symmetrize_skices.py — enforce bilateral symmetry on the Gothic-window WIP
sketch and emit a clean line-only extract.

The source sketch has the tracery head fully detailed on the LEFT half only;
the right half carries bare placeholder circles.  This mirrors the left-half
detail features across the window axis, removes the placeholders, and writes:

  * <out>_symmetric.dxf  — the full sketch with the right half completed
  * <out>_clean.dxf      — just the main-window linework (no OLE image, no
                           dimensions, no side studies, no construction lines),
                           translated near the origin, for import into Onshape.

Usage: python3 symmetrize_skices.py INPUT.dxf OUT_PREFIX
"""
import sys, math, ezdxf

AX = 5620.65                       # window axis (x)
Uc = (5267.82, 1736.39)            # upper-left trefoil centre
Lc = (5385.65, 1275.59)            # lower-left trefoil-in-triangle centre
FRAME = (5100, 6140, 350, 2260)    # main-assembly bbox (xmin,xmax,ymin,ymax)


def rep(e):
    t = e.dxftype()
    if t == "LINE":
        return ((e.dxf.start.x + e.dxf.end.x) / 2, (e.dxf.start.y + e.dxf.end.y) / 2)
    if t in ("ARC", "CIRCLE"):
        return (e.dxf.center.x, e.dxf.center.y)
    if t == "LWPOLYLINE":
        p = [(q[0], q[1]) for q in e.get_points()]
        return (sum(a for a, _ in p) / len(p), sum(b for _, b in p) / len(p))
    return None


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_left_mullion(e):
    return e.dxftype() == "LINE" and abs(e.dxf.start.x - 5385.6) < 1 and abs(e.dxf.end.x - 5385.6) < 1


def is_left_transom(e):
    if e.dxftype() != "LINE":
        return False
    s, en = e.dxf.start, e.dxf.end
    return abs(s.y - 917.8) < 1 and abs(en.y - 917.8) < 1 and max(s.x, en.x) <= 5386.5


def mx(x):
    return 2 * AX - x


def add_mirror(msp, e):
    t = e.dxftype(); a = {"layer": e.dxf.layer}
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        msp.add_line((mx(s.x), s.y), (mx(en.x), en.y), dxfattribs=a)
    elif t == "CIRCLE":
        c = e.dxf.center
        msp.add_circle((mx(c.x), c.y), e.dxf.radius, dxfattribs=a)
    elif t == "ARC":
        c = e.dxf.center
        msp.add_arc((mx(c.x), c.y), e.dxf.radius,
                    180 - e.dxf.end_angle, 180 - e.dxf.start_angle, dxfattribs=a)
    elif t == "LWPOLYLINE":
        pts = [(mx(q[0]), q[1], -q[4] if len(q) > 4 else 0) for q in e.get_points()]
        msp.add_lwpolyline(pts, format="xyb", close=e.closed, dxfattribs=a)


def symmetrize(inp, prefix):
    doc = ezdxf.readfile(inp)
    msp = doc.modelspace()

    sel = []
    for e in list(msp):
        r = rep(e)
        if r is None:
            continue
        left_feature = is_left_mullion(e) or is_left_transom(e)
        if r[0] >= AX - 0.2 and not left_feature:
            continue
        if dist(r, Uc) < 145 or dist(r, Lc) < 170 or left_feature:
            sel.append(e)
    for e in sel:
        add_mirror(msp, e)

    # drop bare placeholder circles on the right
    for e in list(msp):
        if e.dxftype() == "CIRCLE" and abs(e.dxf.radius - 117.171) < 0.5:
            c = e.dxf.center
            if dist((c.x, c.y), (5973.48, 1736.39)) < 1 or dist((c.x, c.y), (5855.65, 1275.59)) < 1:
                msp.delete_entity(e)

    doc.saveas(f"{prefix}_symmetric.dxf")
    print(f"mirrored {len(sel)} entities -> {prefix}_symmetric.dxf")

    # ---- clean line-only extract of just the main window --------------
    out = ezdxf.new("R2018", setup=True)
    out.header["$INSUNITS"] = 1  # inches
    omsp = out.modelspace()
    xmin, xmax, ymin, ymax = FRAME
    ox, oy = 5120.6, 383.6       # translate outer frame corner toward origin
    kept = 0
    for e in msp:
        t = e.dxftype()
        if t not in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE"):
            continue
        r = rep(e)
        if not (xmin <= r[0] <= xmax and ymin <= r[1] <= ymax):
            continue
        if t == "LINE":  # drop construction lines overshooting the frame
            s, en = e.dxf.start, e.dxf.end
            if min(s.x, en.x) < 5115 or max(s.x, en.x) > 6125:
                continue
            omsp.add_line((s.x - ox, s.y - oy), (en.x - ox, en.y - oy))
        elif t == "CIRCLE":
            c = e.dxf.center
            omsp.add_circle((c.x - ox, c.y - oy), e.dxf.radius)
        elif t == "ARC":
            c = e.dxf.center
            omsp.add_arc((c.x - ox, c.y - oy), e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle)
        elif t == "LWPOLYLINE":
            pts = [(q[0] - ox, q[1] - oy, q[4] if len(q) > 4 else 0) for q in e.get_points()]
            omsp.add_lwpolyline(pts, format="xyb", close=e.closed)
        kept += 1
    out.saveas(f"{prefix}_clean.dxf")
    print(f"clean extract: {kept} entities -> {prefix}_clean.dxf")


if __name__ == "__main__":
    inp = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else "out/skices"
    symmetrize(inp, prefix)
