# Contributing

Report bugs or suggest changes in the [issue tracker](https://github.com/AmLanz/UHV-Chamber-Builder/issues). Support is best effort.

For a reproducible geometry issue, include:

- Add-in version, Fusion version and Windows/macOS version.
- A minimal exported recipe, steps to reproduce, and expected versus actual result.
- A screenshot and relevant entries from `UHVChamberBuilder.log` when available.

Remove private paths, project details and proprietary geometry before sharing.

## Development

Clone into a folder named `UHVChamberBuilder` so the Python package and Fusion entry files have matching names:

```sh
git clone https://github.com/AmLanz/UHV-Chamber-Builder.git UHVChamberBuilder
python -m unittest discover -s UHVChamberBuilder/tests -v
```

The portable Python suite uses Fusion API fakes. UI checks use Node.js and Playwright; see [DEVELOPMENT.md](docs/DEVELOPMENT.md). Geometry changes also need a live Fusion check. Keep the three-table workflow compact and preserve the high-contrast themes.

Contributions are submitted under the project's Apache-2.0 license. Release preparation is described in [PUBLISHING.md](docs/PUBLISHING.md).
