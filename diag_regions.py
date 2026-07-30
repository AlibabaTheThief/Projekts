#!/usr/bin/env python3
"""Diagnose why Onshape won't form sketch regions: explode all curves into
segments, build an endpoint graph, and find open ends / micro-gaps / overlaps
at several tolerances."""
import sys, math, ezdxf
from collections import defaultdict


def arc_end_points(cx, cy, r, a0, a1):
    a0r, a1r = math.radians(a0), math.radians(a1)
    return (cx + r * math.cos(a0r), cy + r * math.sin(a0r)), \
           (cx + r * math.cos(a1r), cy + r * math.sin(a1r))


def explode(msp):
    """Return list of segments: dict(kind, p0, p1, mid, ent)."""
    segs = []
    def add_line(p0, p1):
        segs.append(dict(kind="line", p0=p0, p1=p1,
                         mid=((p0[0]+p1[0])/2, (p0[1]+p1[1])/2)))
    def add_arc(cx, cy, r, a0, a1):
        p0, p1 = arc_end_points(cx, cy, r, a0, a1)
        am = math.radians(a0 + ((a1 - a0) % 360) / 2)
        segs.append(dict(kind="arc", p0=p0, p1=p1, c=(cx, cy), r=r,
                         mid=(cx + r*math.cos(am), cy + r*math.sin(am))))
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            add_line((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
        elif t == "ARC":
            add_arc(e.dxf.center.x, e.dxf.center.y, e.dxf.radius,
                    e.dxf.start_angle, e.dxf.end_angle)
        elif t == "CIRCLE":
            pass  # self-closed
        elif t == "LWPOLYLINE":
            pts = list(e.get_points())            # x,y,swidth,ewidth,bulge
            n = len(pts)
            rng = range(n) if e.closed else range(n - 1)
            for i in rng:
                x0, y0 = pts[i][0], pts[i][1]
                x1, y1 = pts[(i+1) % n][0], pts[(i+1) % n][1]
                b = pts[i][4] if len(pts[i]) > 4 else 0
                if abs(b) < 1e-9:
                    add_line((x0, y0), (x1, y1))
                else:
                    # bulge -> arc
                    chord = math.dist((x0, y0), (x1, y1))
                    r = chord * (1 + b*b) / (4 * abs(b))
                    add_line((x0, y0), (x1, y1))  # approximate for endpoint graph
    return segs


def dist(a, b): return math.hypot(a[0]-b[0], a[1]-b[1])

def dist_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
    if L2 == 0: return dist(p, a)
    t = max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L2))
    return dist(p, (ax+t*dx, ay+t*dy))


def analyse(path):
    msp = ezdxf.readfile(path).modelspace()
    segs = explode(msp)
    print(f"segments (exploded): {len(segs)}")
    endpoints = []
    for i, s in enumerate(segs):
        endpoints.append((s["p0"], i)); endpoints.append((s["p1"], i))

    for tol in (1e-6, 1e-4, 1e-3, 1e-2, 5e-2, 1e-1):
        # cluster endpoints greedily
        clusters = []  # list of [sum_x,sum_y,count, members]
        grid = defaultdict(list)
        cell = max(tol, 1e-9)
        def key(p): return (round(p[0]/cell), round(p[1]/cell))
        assigned = {}
        cl = []
        for idx, (p, si) in enumerate(endpoints):
            found = -1
            for dxk in (-1, 0, 1):
                for dyk in (-1, 0, 1):
                    for j in grid[(key(p)[0]+dxk, key(p)[1]+dyk)]:
                        if dist(cl[j]["ctr"], p) <= tol:
                            found = j; break
                    if found >= 0: break
                if found >= 0: break
            if found < 0:
                cl.append(dict(ctr=p, n=1)); grid[key(p)].append(len(cl)-1)
            else:
                c = cl[found]; c["n"] += 1
        deg1 = sum(1 for c in cl if c["n"] == 1)
        print(f"  tol={tol:<7}: {len(cl)} vertices, degree-1 (open) = {deg1}")

    # for the tightest useful tol, list open ends and whether they sit on another seg
    tol = 1e-3
    cl = []
    for p, si in endpoints:
        m = min((dist(p, c["ctr"]) for c in cl), default=1e9)
        if m > tol:
            cl.append(dict(ctr=p, n=1, si=si))
        else:
            for c in cl:
                if dist(p, c["ctr"]) <= tol: c["n"] += 1; break
    opens = [c for c in cl if c["n"] == 1]
    tjunc = 0; realopen = []
    for c in opens:
        p = c["ctr"]
        onbody = 1e9
        for j, s in enumerate(segs):
            if j == c["si"]: continue
            if s["kind"] == "line":
                dd = dist_seg(p, s["p0"], s["p1"])
            else:
                dd = abs(dist(p, s["c"]) - s["r"])
            onbody = min(onbody, dd)
        if onbody <= 0.05: tjunc += 1
        else: realopen.append((p, onbody))
    print(f"\nAt tol=1e-3: open ends={len(opens)}  (on another curve/T-junction: {tjunc}, "
          f"truly isolated: {len(realopen)})")
    for p, ob in sorted(realopen, key=lambda z: -z[1])[:15]:
        print(f"   isolated end ({p[0]:.3f},{p[1]:.3f})  nearest curve {ob:.3f}")

    # overlaps: near-duplicate segments
    dup = 0
    for i in range(len(segs)):
        for j in range(i+1, len(segs)):
            a, b = segs[i], segs[j]
            if a["kind"] != b["kind"]: continue
            if (dist(a["p0"], b["p0"]) < 0.02 and dist(a["p1"], b["p1"]) < 0.02) or \
               (dist(a["p0"], b["p1"]) < 0.02 and dist(a["p1"], b["p0"]) < 0.02):
                dup += 1
    print(f"exact-duplicate segments: {dup}")


if __name__ == "__main__":
    analyse(sys.argv[1])
