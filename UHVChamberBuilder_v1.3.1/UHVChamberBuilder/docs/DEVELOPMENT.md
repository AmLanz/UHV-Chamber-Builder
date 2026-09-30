# Implementation and verification

V1.3.1 · 30 September 2026

| File | Responsibility |
| --- | --- |
| `core.py` | One X-axis coordinate frame for bodies and flanges, recipe checks and neck planning. |
| `fusion_backend.py` | Temporary solids, components, preview and graphics cleanup. |
| `UHVChamberBuilder.py` | Fusion commands, document events and HTML bridge. |
| `exchange.py` | JSON, recipe ZIP, CSV and Markdown export. |
| `ui/` | Local high-contrast palette. |

## Publication update

V1.3.1 adds the logo, About / Cite, native clipboard copying, Apache-2.0 files and repository documentation. The geometry implementation is unchanged from V1.3.0. The clipboard helper is shared with LaserOpticsRouter; its platform calls need a live Windows/macOS check.

## Coordinate model

The earlier spherical formula changed X while stepping the second angle. At azimuth 75°, face distance 160 mm and elevation 15°/45°/75°, the old X offsets were **40.000 / 29.282 / 10.718 mm**. Rotating the 15° flange centre 30° about X missed the 45° centre by **11.059 mm**. The present frame keeps the X offset at **41.411 mm** for those three ports.

For azimuth `a` and elevation `e`, let `theta = abs(a)` and `phi = e` if `a ≥ 0`, otherwise `180° − e`. The outward unit normal and zero-roll in-plane axes are:

```
n  = ( cos(theta), sin(theta) cos(phi), sin(theta) sin(phi))
u0 = (-sin(theta), cos(theta) cos(phi), cos(theta) sin(phi))
v0 = (0, -sin(phi), cos(phi))
u  = cos(roll) u0 + sin(roll) v0
v  = n × u
```

The frame defines body axes and entire flange geometry, including bolt centres. Tube-end flanges inherit their parent tube axis. An aim-toward point supplies the normal, after which the same frame determines bolt clocking. The former flange-angle mode and spherical branch have been removed. Old mode metadata is ignored on import; all angles are interpreted using this X-axis convention.

## Checks

```sh
python -m unittest discover -s UHVChamberBuilder/tests -v
node UHVChamberBuilder/tests/test_ui.cjs
```

Release checks: **65 Python tests** and **71 browser checks** passed. The citation file validates against the CFF 1.2.0 schema. Version metadata, local documentation links and packaged assets were checked; text contrast passes 4.5:1 in both themes.

The Python checks cover the exact twelve-port ring, 30° rotations including bolt holes and odd bolt counts, orientation of base tubes and their end flanges, signed azimuth, export/import, examples and the document-independent citation handler. Browser checks cover the explanatory lines, entered angle retention, build payloads, document switching, table controls, light/dark contrast, logo loading and citation-copy success/fallback. Browser checks require Node.js/Playwright; `UHV_CHROMIUM_BIN` selects an existing Chromium binary.

These tests use Fusion API fakes and a browser. They cannot verify Fusion’s solid kernel, renderer or native transactions.

## Short live check

1. Stop the old add-in, replace the folder and run V1.3.1. Open About / Cite, check the logo and both copy buttons in light and dark mode.
2. Import `examples/X_axis_ring.json` and build. Inspect the twelve DN40 ports along X. In a disposable copy, rotate one side flange 30° about the X-parallel line through point B; its complete flange and bolt pattern should coincide with the next port.
3. Add a tube with azimuth 90° and elevation 90°: its axis and its end flanges should point along ±Z.

Retain a recipe ZIP, affected F3D and diagnostic log if the result differs.

## API references

- [Occurrence assembly contexts](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence_createForAssemblyContext.htm)
- [Cylinder endpoints](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_TemporaryBRepManager_createCylinderOrCone.htm)
- [Graphics ownership IDs](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_CustomGraphicsGroup_id.htm)
- [Document-saving event](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_documentSaving.htm)
