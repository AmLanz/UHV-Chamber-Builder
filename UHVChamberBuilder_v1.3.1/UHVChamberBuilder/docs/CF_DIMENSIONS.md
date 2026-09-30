# Implemented CF dimensions

All dimensions are in **mm**. Values are the MBE reference catalog, not a claim of independently verified ISO compliance.

Source: [MBE flange / gasket / tube tables](https://www.mbe-komponenten.de/service/flange-gasket/), retrieved 29 September 2026.

## Flanges

| CF size | OD | Thickness | Bolt circle | Bolts | Hole Ø | Knife Ø | Recess Ø |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DN10CF | 25 | 6 | 17.5 | 6 | 3.3 | 10.5 | 13.5 |
| DN16CF | 33.8 | 7 | 27 | 6 | 4.4 | 18.3 | 21.4 |
| DN25CF | 54 | 11.5 | 41.3 | 4 | 6.8 | 27.7 | 33 |
| DN40CF | 69.9 | 12.5 | 58.7 | 6 | 6.8 | 41.9 | 48.3 |
| DN50CF | 85.7 | 16 | 72.4 | 8 | 8.4 | 55.9 | 61.8 |
| DN63CF | 114.3 | 17 | 92.2 | 8 | 8.4 | 77.2 | 82.5 |
| DN75CF | 117.4 | 17.5 | 102.3 | 10 | 8.4 | 85.2 | 91.6 |
| DN100CF | 152.4 | 19.5 | 130.3 | 16 | 8.4 | 115.3 | 120.6 |
| DN125CF | 171.5 | 21 | 151.6 | 18 | 8.4 | 136.3 | 141.8 |
| DN160CF | 203.2 | 21 | 181 | 20 | 8.4 | 166.1 | 171.4 |
| DN200CF | 254 | 24 | 231.8 | 24 | 8.4 | 216.9 | 222.2 |
| DN250CF | 304.8 | 24 | 284 | 32 | 8.4 | 267.5 | 273.1 |
| DN275CF | 336.6 | 28 | 306.3 | 30 | 10.8 | 288.2 | 294.4 |
| DN300CF | 368.3 | 28 | 338.1 | 32 | 10.8 | 320 | 326.4 |
| DN350CF | 419.1 | 28 | 388.9 | 36 | 10.8 | 373 | 376.7 |
| DN400CF | 469.9 | 28 | 437.9 | 40 | 10.8 | 419 | 424.4 |

## Nominal gaskets

| CF size | OD | ID | Thickness |
| --- | ---: | ---: | ---: |
| DN10CF | 13.3 | 8.4 | 2 |
| DN16CF | 21.3 | 16.2 | 2 |
| DN25CF | 32.9 | 25.2 | 2 |
| DN40CF | 48.2 | 39.2 | 2 |
| DN50CF | 61.7 | 51.1 | 2 |
| DN63CF | 82.4 | 72 | 2 |
| DN75CF | 91.5 | 76.4 | 2 |
| DN100CF | 120.5 | 101.7 | 2 |
| DN125CF | 141.7 | 127.3 | 2 |
| DN160CF | 171.3 | 152.5 | 2 |
| DN200CF | 222.1 | 203.3 | 2 |
| DN250CF | 272.9 | 254.2 | 2 |
| DN275CF | 294.3 | 276 | 2 |
| DN300CF | 326.2 | 302 | 2 |
| DN350CF | 376.5 | 356.5 | 2 |
| DN400CF | 423.9 | 405 | 2 |

## Tube stock

| Flange | Tube OD | Wall | Calculated ID |
| --- | ---: | ---: | ---: |
| DN16CF | 19 | 2 | 15 |
| DN40CF | 38 | 1.5 | 35 |
| DN40CF | 41 | 1.5 | 38 |
| DN40CF | 42.4 | 1.6 | 39.2 |
| DN50CF | 54 | 2 | 50 |
| DN63CF | 63.5 | 1.8 | 59.9 |
| DN63CF | 70 | 2 | 66 |
| DN63CF | 76 | 2 | 72 |
| DN100CF | 104 | 2 | 100 |
| DN160CF | 154 | 2 | 150 |
| DN200CF | 204 | 2 | 200 |
| DN250CF | 254 | 2 | 250 |

## Interpretation

- **DN150CF** maps to **DN160CF**.
- **DN250CF OD = 304.8 mm**: the flange table gives 304.8; the tube table gives 308.4. The add-in uses the flange-table value.
- Tube sizes are independent of flange OD. The first listed stock size is the initial preferred tube; change it in Defaults. Sizes without a listed tube require user-entered tube dimensions.
- Catalog dimensions remain editable in Defaults. Explicit row overrides take precedence. Export embeds the defaults, so recipes do not silently adopt later catalog changes.
- Gasket/knife features are off by default. When enabled, recess depth 1.30 and knife-tip depth 0.60 are editable **schematic** inputs, not a complete specified seal profile. The nominal gasket is uncompressed and positioned by its outer-face offset; it may overlap the flange while remaining a separate component.
- Fixed inline/straddled patterns differ by half a bolt pitch. Rotatable flanges have two schematic bodies; manufacturer-specific retaining details are omitted.

## Standards note

MBE cites ISO 3669:2020. ISO 3669:2026 supersedes it; the complete dimensional changes have not been compared. This release therefore retains the traceable MBE dataset and does not label it as verified against the newer edition.

[ISO 3669 search at ISO](https://www.iso.org/search.html?q=ISO%203669) · [DIN Media standard search](https://www.dinmedia.de/en/search-results?query=ISO%203669)
