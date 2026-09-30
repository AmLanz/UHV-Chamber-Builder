# Publishing V1.3.1

Target repository: [AmLanz/UHV-Chamber-Builder](https://github.com/AmLanz/UHV-Chamber-Builder).

1. Extract `UHVChamberBuilder_v1.3.1.zip`.
2. Upload the **contents of the inner `UHVChamberBuilder` folder** to the repository root. `README.md`, `LICENSE` and `CITATION.cff` should sit beside `UHVChamberBuilder.py`; keep `ui/`, `assets/`, `data/`, `docs/`, `examples/` and `tests/` as folders. Include `.gitignore` when committing with Git.
3. Confirm the logo, README links and GitHub's **Cite this repository** action work.
4. Under **Releases → Draft a new release**, create tag **v1.3.1** on `main`, use title **V1.3.1**, and attach the original **UHVChamberBuilder_v1.3.1.zip** as the download. Use the 1.3.1 entry from `CHANGELOG.md` as the description.
5. Publish the release after checking installation, About / Cite, preview and build in Fusion. The generated GitHub source ZIP is separate from the attached installation ZIP.

Suggested repository description:

> Autodesk Fusion add-in for planning and documenting UHV chambers with table-defined body shapes, merged port necks and separate CF flanges.

## Future releases

Keep the version consistent in `core.py`, the manifest, `ui/index.html`, `ui/about.js`, `ui/demo-data.js`, example recipes, README and citation files. Update the citation date and changelog. Package the complete `UHVChamberBuilder/` folder without caches, local environments or old ZIPs.

Add an ORCID or DOI to citation metadata only when a real identifier is available. See [GitHub's citation-file guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files).
