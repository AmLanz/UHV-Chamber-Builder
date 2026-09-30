# Usage

## Three tables

1. **Reference points:** XYZ coordinates from the chamber origin. Names may change without breaking references. Deleting a referenced point marks affected rows red.
2. **Main chamber:** combine spheres, tubes, cuboids or selected solid snapshots. Tube ends may be open, plated or flanged.
3. **Flanges:** select a point, orientation, face distance and flange size. Use **Deviate** or **Custom** for your own dimensions.

Flange distance starts at the referenced point and ends at the outer mating face. Tube-end flange positions come from their tube endpoints.

## Azimuth, elevation and roll

The same convention applies to flanges and manually oriented body shapes:

- **Azimuth:** angle from +X, from −180° to +180°. Its absolute value gives the inclination; a negative value selects the opposite Y half.
- **Elevation:** sweep around X. On either signed half, positive elevation moves toward +Z from its zero-elevation position. A full sweep is allowed.
- **Roll:** rotation around the outward axis, including bolt-hole orientation.

| Azimuth | Elevation | Direction |
| ---: | ---: | --- |
| 0° | 0° or any elevation | +X |
| 90° | 0° | +Y |
| −90° | 0° | −Y |
| 90° | 90° | +Z |
| 90° | −90° | −Z |
| 180° | 0° or any elevation | −X |

For a ring about X, use the same reference point, distance, absolute azimuth, roll and flange dimensions. `examples/X_axis_ring.json` demonstrates ±75° azimuth with elevations ±15°, ±45° and ±75°. Alternatively, use positive azimuth and sweep elevation through 0–360°. An optional **Aim toward point** overrides the two direction angles.

## Useful controls

| Control | Use |
| --- | --- |
| **+** beside a row | Extra dimensions, roll, tube and connection settings. |
| **Preview** / **Build** on a row | Inspect or build that row in chamber context, including required parent necks. |
| **Build / update all** | Apply every edit and removal. |
| **Clear preview** | Restore the built model and remove recognized preview leftovers. Saving also clears previews. |
| **Defaults & appearance** | Shared dimensions, preferred tube stock, and the light/dark switch. |
| **Deviate / Custom** | Per-row dimensions; other rows continue to inherit defaults. |
| **Port axes / Points** | Helper visibility, applied with Preview or Build. |
| **Geometry outside this recipe** | Highlight and review additional geometry before deleting it. |

Automatic necks can connect to another neck regardless of table order. For ambiguous connections, choose an attachment target or manual length. Existing solids are snapshots and require manual neck lengths.

**Gasket offset** measures outer flange face to outer gasket face. Zero is flush; the gasket extends one thickness inward. Overlap and negative offsets are allowed because the gasket stays in a separate component.

## Save and exchange

Save the Fusion document to retain the recipe. A recipe ZIP includes JSON, CSV tables, Markdown documentation and selected-solid snapshots. Import accepts the JSON recipe or the recipe ZIP; CSV is for documentation. Export an unbuilt draft before replacing it with New or Load example.

Rebuilds can replace faces and edges. Keep manual finishing features in a separate copy.

## Troubleshooting

- **Add-in missing:** register the folder containing the manifest, not the ZIP or its parent folder. Use the Add-Ins tab.
- **Old version shown:** stop the add-in, replace its entire folder, restart Fusion and check the version again.
- **Build blocked:** finish active Fusion commands, fix the reported red rows and confirm the Hybrid change when prompted.
- **Neck does not connect:** check the point, orientation and distance; select a target or a suitable manual length.
- **Unwanted blue preview lines:** use Clear preview, then rebuild. Points and port axes have separate visibility controls.
- **Section view:** clear preview and use Fusion’s Inspect → Section Analysis.
- **Citation copy unavailable:** the text is selected for Ctrl+C / Command+C.

Errors include the path to `UHVChamberBuilder.log` in the operating system’s temporary directory. For a bug report, include the version, minimal recipe and relevant log entries; see [Contributing](../CONTRIBUTING.md).
