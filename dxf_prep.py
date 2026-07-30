#!/usr/bin/env python3
"""
dxf_prep.py — Prepare a bulge-heavy DXF for import into Onshape.

Fixes two problems common in traced/tessellated DXF outlines:

  1. Runaway arc centers.  Polyline "bulge" segments that are nearly
     straight imply arcs of enormous radius whose *center* lands far
     outside the drawing (millions of units away).  Onshape reconstructs
     the arc and its center, and those far-flung centers overflow the
     sketch region, so the import fails or distorts.

  2. Vertex bloat.  Thousands of short segments make the sketch heavy
     and slow.

The pipeline: flatten every polyline to points (removing all bulges, so
no arc centers survive), simplify the point stream with Douglas-Peucker,
then emit either clean straight-segment polylines or fitted splines.

Usage:
    python3 dxf_prep.py INPUT.dxf OUTPUT.dxf [--tol MM] [--flatten MM] [--mode poly|spline]
"""
import argparse
import math
import ezdxf
from ezdxf import path as ezpath


def flatten_polyline(entity, sagitta):
    """Return list of (x, y) points approximating the polyline (arcs included)
    with max deviation ~= sagitta.  Bulges are turned into real points here."""
    p = ezpath.make_path(entity)
    pts = [(v.x, v.y) for v in p.flattening(distance=sagitta)]
    # de-duplicate consecutive identical points
    out = []
    for pt in pts:
        if not out or math.dist(out[-1], pt) > 1e-9:
            out.append(pt)
    return out


def douglas_peucker(points, tol):
    """Iterative Ramer-Douglas-Peucker. Keeps endpoints."""
    if len(points) < 3:
        return points[:]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        ax, ay = points[lo]
        bx, by = points[hi]
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        dmax, idx = -1.0, -1
        for i in range(lo + 1, hi):
            px, py = points[i]
            if seg == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / seg
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol and idx != -1:
            keep[idx] = True
            stack.append((lo, idx))
            stack.append((idx, hi))
    return [pt for i, pt in enumerate(points) if keep[i]]


def clean(in_path, out_path, tol=0.1, sagitta=0.05, mode="poly"):
    src = ezdxf.readfile(in_path)
    smsp = src.modelspace()

    out = ezdxf.new("R2018", setup=True)
    out.header["$INSUNITS"] = 4  # millimeters — makes Onshape's unit guess unambiguous
    omsp = out.modelspace()

    stats = {"in_verts": 0, "out_verts": 0, "loops": 0, "splines": 0}

    for e in smsp:
        if e.dxftype() not in ("POLYLINE", "LWPOLYLINE"):
            # pass through anything else unchanged
            try:
                omsp.add_foreign_entity(e.copy())
            except Exception:
                pass
            continue

        raw = flatten_polyline(e, sagitta)
        stats["in_verts"] += len(raw)
        if len(raw) < 2:
            continue

        closed = bool(getattr(e, "is_closed", False) or getattr(e.dxf, "flags", 0) & 1)

        pts = douglas_peucker(raw, tol)
        # For a closed loop keep it closed but drop a duplicated closing point
        if closed and len(pts) > 2 and math.dist(pts[0], pts[-1]) < tol:
            pts = pts[:-1]
        stats["out_verts"] += len(pts)
        stats["loops"] += 1

        if mode == "spline" and len(pts) >= 4:
            fit = pts + [pts[0]] if closed else pts
            try:
                omsp.add_spline(fit_points=fit, dxfattribs={"layer": "0"})
                stats["splines"] += 1
                continue
            except Exception:
                pass  # fall back to polyline

        omsp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": "0"})

    out.saveas(out_path)
    return stats


def _iter_bulge_segments(msp):
    """Yield (p1, p2, bulge) for every curved segment in POLYLINE and
    LWPOLYLINE entities, regardless of DXF vintage."""
    for e in msp:
        t = e.dxftype()
        if t == "POLYLINE":
            verts = list(e.vertices)
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in verts]
            bulges = [getattr(v.dxf, "bulge", 0) or 0 for v in verts]
            closed = e.is_closed
        elif t == "LWPOLYLINE":
            raw = list(e.get_points("xyb"))
            pts = [(p[0], p[1]) for p in raw]
            bulges = [p[2] for p in raw]
            closed = e.closed
        else:
            continue
        n = len(pts)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            if bulges[i]:
                yield pts[i], pts[(i + 1) % n], bulges[i]


def audit_far_centers(dxf_path, sheet=(0, 0, 1500, 900), margin=100):
    """Count reconstructed arc centers that land outside the sheet."""
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    minx, miny, maxx, maxy = sheet
    far = 0
    worst = 0.0
    for p1, p2, b in _iter_bulge_segments(msp):
        chord = math.dist(p1, p2)
        if chord == 0:
            continue
        r = chord * (1 + b * b) / (4 * abs(b))
        worst = max(worst, r)
        mx, my = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        d = math.hypot(dx, dy)
        a = math.sqrt(max(r * r - (chord / 2) ** 2, 0))
        ux, uy = -dy / d, dx / d
        s = 1 if b > 0 else -1
        cx, cy = mx - s * ux * a, my - s * uy * a
        if cx < minx - margin or cx > maxx + margin or cy < miny - margin or cy > maxy + margin:
            far += 1
    return far, worst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("outp")
    ap.add_argument("--tol", type=float, default=0.1, help="Douglas-Peucker tolerance (mm)")
    ap.add_argument("--flatten", type=float, default=0.05, help="arc flattening sagitta (mm)")
    ap.add_argument("--mode", choices=["poly", "spline"], default="poly")
    a = ap.parse_args()
    s = clean(a.inp, a.outp, tol=a.tol, sagitta=a.flatten, mode=a.mode)
    far, worst = audit_far_centers(a.outp)
    print(f"loops={s['loops']}  in_verts={s['in_verts']}  out_verts={s['out_verts']}  "
          f"reduction={100*(1-s['out_verts']/max(s['in_verts'],1)):.1f}%  splines={s['splines']}")
    print(f"far-flung arc centers remaining: {far}  (largest radius: {worst:.1f})")
