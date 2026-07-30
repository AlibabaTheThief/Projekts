# DXF prep for Onshape

Cleans a bulge-heavy traced DXF so it imports cleanly into an Onshape sketch.

## The two problems this fixes

1. **Runaway arc centers.** The source polylines store curves as *bulge*
   segments. Nearly-straight bulges imply arcs of huge radius whose **center**
   lands far off the sheet — in the source file, 693 centers (11%) fell outside
   the 1500×900 mm sheet, the worst at Y ≈ −27,000,000 mm. Onshape reconstructs
   those centers and overflows the sketch region, so the import fails/distorts.
2. **Vertex bloat.** 6,328 vertices across 123 closed loops.

## How it fixes them

Flatten every polyline to points (removes all bulges → no arc centers survive),
simplify the point stream with Ramer–Douglas–Peucker, then emit clean
straight-segment `LWPOLYLINE`s (or fitted `SPLINE`s). Output is R2018, single
layer, units = mm.

## Usage

```bash
python3 dxf_prep.py INPUT.dxf OUTPUT.dxf [--tol MM] [--flatten MM] [--mode poly|spline]
```

- `--tol`      Douglas–Peucker tolerance = max deviation from the original curve (default 0.1 mm).
- `--flatten`  Arc-flattening sagitta used before simplifying (default 0.05 mm).
- `--mode`     `poly` (default, most robust in Onshape) or `spline`.

## Results on the source file (`--tol 0.25`)

| Metric | Original | Cleaned |
|---|---|---|
| Vertices | 6,328 | 3,684 (−42%) |
| Off-sheet arc centers | 693 | 0 |
| Largest arc radius | 27,329,632 | none (no arcs) |

`out/tree_onshape_ready.dxf` is the recommended import file. Total worst-case
geometric deviation is ~0.3 mm on a 1500 mm sheet (visually indistinguishable).
