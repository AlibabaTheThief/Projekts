#!/usr/bin/env python3
"""QA for Baznicas_logs.dxf — symmetry, open/near-miss line-ends, duplicates."""
import sys, math, ezdxf

COINC = 0.05      # endpoints treated as joined
GAP_MAX = 4.0     # near-miss gap window (COINC < d <= GAP_MAX)
TOL_ON = 0.15     # point lies on another entity's body (valid T-junction)
DUP_TOL = 0.15    # duplicate geometry tolerance
SYM_TOL = 0.30    # symmetry match tolerance


def rad(d): return math.radians(d)

def arc_pts(e):
    c = e.dxf.center; r = e.dxf.radius
    a0 = rad(e.dxf.start_angle); a1 = rad(e.dxf.end_angle)
    if a1 < a0: a1 += 2 * math.pi
    am = (a0 + a1) / 2
    return [(c.x + r * math.cos(a), c.y + r * math.sin(a)) for a in (a0, am, a1)]

def samples(e):
    t = e.dxftype()
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        return [(s.x, s.y), ((s.x + en.x) / 2, (s.y + en.y) / 2), (en.x, en.y)]
    if t == "ARC":
        return arc_pts(e)
    if t == "CIRCLE":
        c = e.dxf.center; r = e.dxf.radius
        return [(c.x + r, c.y), (c.x, c.y + r), (c.x - r, c.y), (c.x, c.y - r)]
    if t == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points()]
    return []

def endpoints(e):
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t == "ARC":
        p = arc_pts(e); return [p[0], p[2]]
    if t == "LWPOLYLINE" and not e.closed:
        pts = [(p[0], p[1]) for p in e.get_points()]
        return [pts[0], pts[-1]] if pts else []
    return []

def d(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])

def dist_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0: return d(p, a)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return d(p, (ax + t * dx, ay + t * dy))

def dist_point_entity(p, e):
    t = e.dxftype()
    if t == "LINE":
        return dist_seg(p, (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
    if t == "ARC":
        c = e.dxf.center; r = e.dxf.radius
        a0 = e.dxf.start_angle % 360; a1 = e.dxf.end_angle % 360
        ang = math.degrees(math.atan2(p[1] - c.y, p[0] - c.x)) % 360
        inside = (a0 <= ang <= a1) if a0 <= a1 else (ang >= a0 or ang <= a1)
        if inside:
            return abs(d(p, (c.x, c.y)) - r)
        pp = arc_pts(e); return min(d(p, pp[0]), d(p, pp[2]))
    if t == "CIRCLE":
        c = e.dxf.center; return abs(d(p, (c.x, c.y)) - e.dxf.radius)
    if t == "LWPOLYLINE":
        pts = [(q[0], q[1]) for q in e.get_points()]
        rng = list(zip(pts, pts[1:] + ([pts[0]] if e.closed else [])))
        return min((dist_seg(p, a, b) for a, b in rng), default=1e9)
    return 1e9


def main(path):
    doc = ezdxf.readfile(path); msp = doc.modelspace()
    ents = [e for e in msp if e.dxftype() in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")]
    print(f"entities analysed: {len(ents)}")

    # ---------- 1. axis detection ----------
    xs = []
    for e in ents:
        for s in samples(e): xs.append(s[0])
    best = (None, -1)
    for k in range(-40, 41):
        ax = 522.26 + k * 0.05
        # quick score: reflect all sample x, see how symmetric the x-multiset is
        # (use entity mirror matching below for the real check; here approximate)
        break
    AX = (855.06 + 189.46) / 2  # from the two main-arch centres
    # refine AX from all arc centre pairs symmetric in y
    print(f"symmetry axis AX = {AX:.3f}")

    # ---------- 2. dangling / near-miss ends ----------
    EP = []
    for i, e in enumerate(ents):
        for p in endpoints(e): EP.append((p, i))
    dangling, gaps = [], []
    for idx, (p, ei) in enumerate(EP):
        dmin = min((d(p, q) for j, (q, ej) in enumerate(EP) if j != idx), default=1e9)
        if dmin <= COINC:
            continue
        on_body = min((dist_point_entity(p, ents[j]) for j in range(len(ents)) if j != ei), default=1e9)
        if on_body <= TOL_ON:
            continue
        # nearest OTHER endpoint distance for near-miss classification
        if dmin <= GAP_MAX:
            gaps.append((p, dmin))
        else:
            dangling.append((p, dmin, on_body))
    # dedupe gap pairs (each reported from both ends)
    print(f"\n--- LINE-ENDS ---")
    print(f"near-miss gaps (endpoints {COINC}<d<={GAP_MAX} apart, not joined): {len(gaps)}")
    for p, dm in sorted(gaps, key=lambda z: -z[1])[:20]:
        print(f"   gap  at ({p[0]:.2f},{p[1]:.2f})  nearest end {dm:.3f}")
    print(f"truly dangling free ends (isolated, not on any entity): {len(dangling)}")
    for p, dm, ob in sorted(dangling, key=lambda z: z[1])[:20]:
        print(f"   free end ({p[0]:.2f},{p[1]:.2f})  nearest end {dm:.2f}  nearest body {ob:.2f}")

    # ---------- 3. duplicates ----------
    dups = []
    L = [e for e in ents if e.dxftype() == "LINE"]
    for i in range(len(L)):
        si = samples(L[i])
        for j in range(i + 1, len(L)):
            sj = samples(L[j])
            if (d(si[0], sj[0]) < DUP_TOL and d(si[2], sj[2]) < DUP_TOL) or \
               (d(si[0], sj[2]) < DUP_TOL and d(si[2], sj[0]) < DUP_TOL):
                dups.append(("LINE", L[i], L[j]))
    A = [e for e in ents if e.dxftype() == "ARC"]
    for i in range(len(A)):
        ci = A[i].dxf.center; ri = A[i].dxf.radius; pi = arc_pts(A[i])
        for j in range(i + 1, len(A)):
            cj = A[j].dxf.center; rj = A[j].dxf.radius; pj = arc_pts(A[j])
            if abs(ri - rj) < DUP_TOL and d((ci.x, ci.y), (cj.x, cj.y)) < DUP_TOL:
                # overlapping angular span?
                if (d(pi[0], pj[0]) < DUP_TOL and d(pi[2], pj[2]) < DUP_TOL) or \
                   (d(pi[0], pj[2]) < DUP_TOL and d(pi[2], pj[0]) < DUP_TOL) or \
                   d(pi[1], pj[1]) < DUP_TOL:
                    dups.append(("ARC", A[i], A[j]))
    print(f"\n--- DUPLICATES / DOUBLE LINES ---")
    print(f"coincident duplicate entities: {len(dups)}")
    for kind, a, b in dups[:25]:
        s = samples(a)[0]
        print(f"   {kind} duplicate near ({s[0]:.1f},{s[1]:.1f})")

    # ---------- 4. symmetry ----------
    def mirror_samples(e):
        return [(2 * AX - x, y) for x, y in samples(e)]
    def match(ms, cand_list):
        for c in cand_list:
            sc = samples(c)
            if len(sc) != len(ms): continue
            # unordered compare
            used = [False] * len(sc); ok = True
            for pt in ms:
                f = -1
                for k, q in enumerate(sc):
                    if not used[k] and d(pt, q) <= SYM_TOL:
                        f = k; break
                if f < 0: ok = False; break
                used[f] = True
            if ok: return True
        return False
    by_type = {}
    for e in ents: by_type.setdefault(e.dxftype(), []).append(e)
    asym = []
    for e in ents:
        ms = mirror_samples(e)
        if not match(ms, by_type[e.dxftype()]):
            asym.append(e)
    print(f"\n--- SYMMETRY (axis x={AX:.3f}) ---")
    print(f"entities with NO mirror partner: {len(asym)} of {len(ents)}")
    for e in asym[:25]:
        s = samples(e)[0]
        print(f"   {e.dxftype()} unmatched near ({s[0]:.1f},{s[1]:.1f})")

    return dict(AX=AX, gaps=gaps, dangling=dangling, dups=dups, asym=asym, ents=ents)


if __name__ == "__main__":
    main(sys.argv[1])
