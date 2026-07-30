#!/usr/bin/env python3
"""
fix_baz.py — correct Baznicas_logs.dxf:
  1. close the 1.8u gap (extend the line to the arc endpoint),
  2. delete the redundant overlapping (double) line,
  3. enforce exact bilateral symmetry by mirroring the LEFT half onto the
     right (this also fixes the asymmetric inner border and the ~0.4u
     quatrefoil-cusp drift).
The gap/double fixes are done on the left half first, so mirroring carries
the corrections to both sides. Writes out/baz_fixed.dxf.
"""
import math, ezdxf

AX = 522.26
SELF_TOL = 0.30
SRC = "/root/.claude/uploads/9968892c-70e9-52f8-ba7b-ffc825fcd643/1c04b752-Baznicas_logs.dxf"


def arc_pts(e, n=8):
    c = e.dxf.center; r = e.dxf.radius
    a0 = math.radians(e.dxf.start_angle); a1 = math.radians(e.dxf.end_angle)
    if a1 < a0: a1 += 2 * math.pi
    return [(c.x + r * math.cos(a0 + (a1 - a0) * i / n),
             c.y + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

def geo_pts(e):
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t == "ARC":
        return arc_pts(e)
    if t == "CIRCLE":
        c = e.dxf.center; r = e.dxf.radius
        return [(c.x + r * math.cos(a), c.y + r * math.sin(a)) for a in
                [i * math.pi / 6 for i in range(12)]]
    if t == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points()]
    return []

def sig_pts(e):
    """few points used to test self-symmetry (unordered match)."""
    t = e.dxftype()
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        return [(s.x, s.y), (en.x, en.y)]
    if t == "ARC":
        p = arc_pts(e, 4); return [p[0], p[2], p[len(p)//2]]
    if t == "CIRCLE":
        c = e.dxf.center; r = e.dxf.radius
        return [(c.x + r, c.y), (c.x - r, c.y), (c.x, c.y + r)]
    if t == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points()]
    return []

def dd(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])

def mirror_pts(pts): return [(2 * AX - x, y) for x, y in pts]

def is_self_symmetric(e):
    s = sig_pts(e); ms = mirror_pts(s)
    used = [False] * len(s)
    for p in ms:
        f = -1
        for k, q in enumerate(s):
            if not used[k] and dd(p, q) <= SELF_TOL:
                f = k; break
        if f < 0: return False
        used[f] = True
    return True


def add_entity(msp, e, mirror):
    t = e.dxftype(); a = {"layer": e.dxf.layer}
    mx = (lambda x: 2 * AX - x) if mirror else (lambda x: x)
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        msp.add_line((mx(s.x), s.y), (mx(en.x), en.y), dxfattribs=a)
    elif t == "CIRCLE":
        c = e.dxf.center
        msp.add_circle((mx(c.x), c.y), e.dxf.radius, dxfattribs=a)
    elif t == "ARC":
        c = e.dxf.center
        if mirror:
            msp.add_arc((mx(c.x), c.y), e.dxf.radius,
                        180 - e.dxf.end_angle, 180 - e.dxf.start_angle, dxfattribs=a)
        else:
            msp.add_arc((c.x, c.y), e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle, dxfattribs=a)
    elif t == "LWPOLYLINE":
        pts = [(mx(p[0]), p[1], (-p[4] if mirror else p[4]) if len(p) > 4 else 0)
               for p in e.get_points()]
        msp.add_lwpolyline(pts, format="xyb", close=e.closed, dxfattribs=a)


def main():
    doc = ezdxf.readfile(SRC)
    msp = doc.modelspace()

    # ---- 1. close the gap: extend the line end to the arc endpoint ----
    fixed_gap = 0
    for e in msp:
        if e.dxftype() == "LINE" and dd((e.dxf.end.x, e.dxf.end.y), (151.75, 1175.90)) < 0.2:
            e.dxf.end = (150.236, 1176.882, 0)
            fixed_gap += 1
    print("gap lines closed:", fixed_gap)

    # ---- 2. delete the redundant double line ----
    deleted = 0
    for e in list(msp):
        if e.dxftype() == "LINE":
            s, en = e.dxf.start, e.dxf.end
            if dd((s.x, s.y), (358.23, 1415.87)) < 0.2 and dd((en.x, en.y), (349.64, 1421.56)) < 0.2:
                msp.delete_entity(e); deleted += 1
    print("redundant double lines deleted:", deleted)

    # ---- 2b. fix the lopsided inner-border polyline (left leg short) ----
    fixed_border = 0
    for e in msp:
        if e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points())
            changed = False
            new = []
            for p in pts:
                if dd((p[0], p[1]), (52.3, 878.2)) < 1.0:      # left leg top -> match right (1167)
                    new.append((p[0], 1167.0) + tuple(p[2:])); changed = True
                else:
                    new.append(p)
            if changed:
                e.set_points(new); fixed_border += 1
    print("border polylines squared up:", fixed_border)

    # ---- 3. mirror the left half onto the right ----
    ents = [e for e in msp if e.dxftype() in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")]
    out = ezdxf.new("R2018", setup=True)
    out.header["$INSUNITS"] = doc.header.get("$INSUNITS", 1)
    omsp = out.modelspace()

    kept = mirrored = dropped = spanning = 0
    for e in ents:
        if is_self_symmetric(e):
            add_entity(omsp, e, False); kept += 1
            continue
        xs = [p[0] for p in geo_pts(e)]
        minx, maxx = min(xs), max(xs)
        if minx < AX - 0.5 and maxx > AX + 0.5:
            add_entity(omsp, e, False); spanning += 1        # asymmetric spanner: keep, warn
            continue
        if maxx <= AX + 0.5:                                  # left -> keep + mirror
            add_entity(omsp, e, False); add_entity(omsp, e, True); mirrored += 1
        else:                                                 # right -> drop (regenerated)
            dropped += 1
    print(f"self-symmetric kept: {kept}, left mirrored: {mirrored}, "
          f"right dropped: {dropped}, asymmetric spanners kept: {spanning}")
    print("output entities:", len(list(omsp)))
    out.saveas("out/baz_fixed.dxf")
    print("saved out/baz_fixed.dxf")


if __name__ == "__main__":
    main()
