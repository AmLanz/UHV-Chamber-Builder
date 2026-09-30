<img src="assets/vogel-orange.svg" width="64" alt="Amon P. Lanz’s bird logo">

# UHV Chamber Builder

Plan, visualize and document vacuum chambers in **Autodesk Fusion** using three tables: **reference points → main chamber → flanges**.

**Version 1.3.1 · Apache-2.0 · Amon P. Lanz**

[Download a release](https://github.com/AmLanz/UHV-Chamber-Builder/releases) · [Report an issue](https://github.com/AmLanz/UHV-Chamber-Builder/issues)

## What it does

- Combine spheres, tubes, cuboids and selected solids into a main chamber.
- Add CF flanges as individual components; connect and merge their port necks.
- Preview and build individual rows or the whole chamber. Keep flange numbers stable for documentation.
- Export recipes with tables and documentation; share defaults and custom dimensions.

Optional gasket features, fasteners and tool-clearance envelopes help visualize the layout. Dimensions are in **mm**, angles in **degrees**. The interface has high-contrast light and dark themes.

## Installation

Requires desktop Autodesk Fusion on Windows or macOS. Fusion supplies Python; no separate packages are needed.

1. Download **UHVChamberBuilder_v1.3.1.zip** from Releases and extract it to a permanent location.
2. Keep the whole inner **UHVChamberBuilder** folder together. It must directly contain `UHVChamberBuilder.py`, `UHVChamberBuilder.manifest` and the `ui`, `assets` and `data` folders.
3. In Fusion’s **Design** workspace, open **Utilities → Add-Ins → Scripts and Add-Ins** (or press **Shift+S**).
4. On **Add-Ins**, click **+**, choose **Script or add-in from device** if prompted, and select that folder.
5. Select **UHV Chamber Builder → Run**. Check that the window shows **1.3.1**. **Run on Startup** is optional.

**Updating:** save your Fusion document, stop the add-in and replace the complete contents of its registered folder. Restart Fusion, run the add-in and check the version.

## Your first chamber

1. Open a design and choose **Load example → Preview all**.
2. Edit the points, main-chamber shapes and flange rows. **+** beside a row reveals its extra settings.
3. Choose **Build / update all**. If needed, the add-in asks before switching the current design to **Hybrid**.
4. Save the Fusion document. Use **Export → Recipe + tables + assets (.zip)** for a portable copy.

All body shapes and port necks form **Main chamber**. Each flange is a separate component; optional gaskets remain separate inside their flanges.

**Flange numbers:** enter unique positive whole numbers before Build; skipped numbers are allowed. Copy inserts below its source with a blank number. ↑/↓ move rows and Sort never renumbers.

**Angles:** azimuth is the signed angle from +X; elevation rotates around X toward +Z on either signed half. These definitions are shown above the table. See [Usage](docs/USAGE.md) for examples, roll and the complete convention.

## Documentation and limits

[Usage & troubleshooting](docs/USAGE.md) · [CF dimensions and sources](docs/CF_DIMENSIONS.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

This is a layout and reference tool. Seal details, rotatable retaining geometry and fasteners are schematic. It does not verify structural strength, sealing performance or manufacturing suitability. Independently check the generated model before fabrication.

## License and citation

Copyright © 2026 **Amon P. Lanz**. Distributed under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE). This independent project is not affiliated with, endorsed by or sponsored by Autodesk. The software is provided “AS IS” under the license, subject to applicable law.

Citation is appreciated and optional:

> Amon P. Lanz (2026). *UHV Chamber Builder* (version 1.3.1). Computer software.  
> https://github.com/AmLanz/UHV-Chamber-Builder

Use **About / Cite** in the add-in to copy a citation or BibTeX entry. [CITATION.cff](CITATION.cff) and [CITATION.bib](CITATION.bib) are included for reference managers and GitHub.
