#!/usr/bin/env python3
"""
heal_for_onshape.py — make a DXF form selectable sketch regions in Onshape.

Two defects block region detection in this drawing:

  1. Full CIRCLE entities that other curves *end on*.  A closed circle is a
     single entity, so the sub-arcs between those junctions can't act as
     separate region boundaries.  Each circle is split into ARCs at every
     point where another curve touches it.

  2. Near-miss endpoints (0.001-0.2 units) that look joined but aren't.
     All endpoints are snapped onto a shared cluster centre so coincident
     ends become exactly equal.

Usage: python3 heal_for_onshape.py IN.dxf OUT.dxf [--snap 0.25]
"""
import sys, math, argparse, ezdxf

def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])

def dist_seg(p, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy
    if L2 == 0: return dist(p, a)
    t = max(0, min(1, ((p[0]-ax)*dx + (p[1]-ay)*dy) / L2))
    return dist(p, (ax + t*dx, ay + t*dy))

def arc_ends(cx, cy, r, a0, a1):
    return ((cx + r*math.cos(math.radians(a0)), cy + r*math.sin(math.radians(a0))),
            (cx + r*math.cos(math.radians(a1)), cy + r*math.sin(math.radians(a1))))


def endpoints_of(e):
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t == "ARC":
        p0, p1 = arc_ends(e.dxf.center.x, e.dxf.center.y, e.dxf.radius,
                          e.dxf.start_angle, e.dxf.end_angle)
        return [p0, p1]
    if t == "LWPOLYLINE" and not e.closed:
        pts = [(p[0], p[1]) for p in e.get_points()]
        return [pts[0], pts[-1]] if pts else []
    return []


def heal(inp, outp, snap=0.25):
    doc = ezdxf.readfile(inp)
    msp = doc.modelspace()

    # ---------- pass 1: snap near-coincident endpoints ----------
    pts = []
    for e in msp:
        pts += endpoints_of(e)
    clusters = []
    for p in pts:
        hit = None
        for c in clusters:
            if dist(p, c["ctr"]) <= snap:
                hit = c; break
        if hit:
            hit["pts"].append(p)
            n = len(hit["pts"])
            hit["ctr"] = (sum(q[0] for q in hit["pts"]) / n,
                          sum(q[1] for q in hit["pts"]) / n)
        else:
            clusters.append(dict(ctr=p, pts=[p]))

    def snapped(p):
        for c in clusters:
            if dist(p, c["ctr"]) <= snap:
                return c["ctr"]
        return p

    moved = 0
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            for attr in ("start", "end"):
                v = getattr(e.dxf, attr)
                s = snapped((v.x, v.y))
                if dist((v.x, v.y), s) > 1e-9:
                    setattr(e.dxf, attr, (s[0], s[1], 0)); moved += 1
        elif t == "ARC":
            # Snapping an arc end means re-fitting the arc so the endpoint is
            # EXACTLY the cluster centre: keep the far end + the arc's sweep
            # direction, and solve a new centre/radius through both ends.
            c = e.dxf.center; r = e.dxf.radius
            p0, p1 = arc_ends(c.x, c.y, r, e.dxf.start_angle, e.dxf.end_angle)
            s0, s1 = snapped(p0), snapped(p1)
            if dist(p0, s0) < 1e-12 and dist(p1, s1) < 1e-12:
                continue
            # new centre = intersection of perpendicular bisector of s0..s1 with
            # the original centre direction; simplest stable fix: keep radius,
            # move centre so both snapped ends lie on it (least-squares of 2 pts)
            mxp, myp = (s0[0]+s1[0])/2, (s0[1]+s1[1])/2
            dxp, dyp = s1[0]-s0[0], s1[1]-s0[1]
            chord = math.hypot(dxp, dyp)
            if chord < 1e-9:
                continue
            rr = max(r, chord/2 + 1e-9)
            h = math.sqrt(max(rr*rr - (chord/2)**2, 0))
            ux, uy = -dyp/chord, dxp/chord
            cand = [(mxp + ux*h, myp + uy*h), (mxp - ux*h, myp - uy*h)]
            nc = min(cand, key=lambda q: dist(q, (c.x, c.y)))
            na0 = math.degrees(math.atan2(s0[1]-nc[1], s0[0]-nc[0])) % 360
            na1 = math.degrees(math.atan2(s1[1]-nc[1], s1[0]-nc[0])) % 360
            e.dxf.center = (nc[0], nc[1], 0)
            e.dxf.radius = rr
            e.dxf.start_angle = na0
            e.dxf.end_angle = na1
            moved += 1
    print(f"endpoints snapped: {moved}")

    # ---------- pass 2: split circles at touching points ----------
    all_pts = []
    for e in msp:
        all_pts += endpoints_of(e)

    circles = [e for e in msp if e.dxftype() == "CIRCLE"]
    split_total = 0
    for circ in circles:
        cx, cy, r = circ.dxf.center.x, circ.dxf.center.y, circ.dxf.radius
        angs = []
        for p in all_pts:
            if abs(dist(p, (cx, cy)) - r) <= max(snap, 0.05):
                angs.append(math.degrees(math.atan2(p[1]-cy, p[0]-cx)) % 360)
        # dedupe angles
        angs.sort()
        uniq = []
        for a in angs:
            if not uniq or abs(a - uniq[-1]) > 0.05:
                uniq.append(a)
        if len(uniq) >= 2:
            lay = circ.dxf.layer
            for i in range(len(uniq)):
                a0 = uniq[i]; a1 = uniq[(i + 1) % len(uniq)]
                msp.add_arc((cx, cy), r, a0, a1, dxfattribs={"layer": lay})
                split_total += 1
            msp.delete_entity(circ)
    print(f"circles split into arcs: {split_total} arcs from {len(circles)} circles")

    doc.saveas(outp)
    print("saved", outp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("outp")
    ap.add_argument("--snap", type=float, default=0.25)
    a = ap.parse_args()
    heal(a.inp, a.outp, a.snap)
