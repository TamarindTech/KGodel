# Preparing and publishing a preview

[Product preview](product-preview.md) · [Contributor guide](../CONTRIBUTING.md)

The first product channel is an alpha developer preview. Release tooling requires an alpha version such as `0.13.0a1`; it does not label experimental code stable. This guide describes the process, not a claim that a release is published.

## Build and verify locally

Use a clean checkout of the intended commit. Set `kgodel.__version__`, update the changelog/current instructions, and add `docs/releases/vVERSION.md`. Create a separate build environment with `python -m venv .venv-release`. Activate it, or use its interpreter path for each command below (`.venv-release\Scripts\python` on Windows, `.venv-release/bin/python` on macOS/Linux):

```sh
python -m pip install build twine
python -m unittest discover -s tests -v
python tools/verify_tutorials.py
python tools/prepare_release.py --output dist/release
python tools/verify_release.py dist/release
python tools/verify_install.py dist/release
```

The output directory must not already exist. Choose another directory for a subsequent build; the tool does not delete or mix old releases. `build` creates a source archive and builds the wheel from it, exposing missing source-manifest resources. `twine check --strict` checks metadata. The installation verifier uses a fresh environment outside the checkout and exercises both command entry points, starter projects, all demos, query features, and checkpoint restart.

The release directory contains the wheel, source archive, starter-kit ZIP, `SHA256SUMS.txt`, and `release.json`. The kit includes the same wheel, source documentation and examples, and `START_HERE.md`. `verify_release.py` checks metadata/resources, all three hashes, and byte equality of the kit's wheel and sources. Checksums detect corruption; obtain them and the downloads from the repository's trusted release page.

## GitHub workflow

Every push and pull request runs unit/tutorial checks, builds the complete kit, validates its contents, and tests an isolated installation on Windows, Linux, and macOS with Python 3.10 and 3.13. The Linux/Python-3.13 job retains verified downloads as the `preview-distributions` Actions artifact. These are candidate artifacts, not published releases.

After review and merge to `main`, run **Prepare preview release** from Actions, selecting `main`. It reruns the six verification jobs, downloads the verified artifact, checks it again, and creates an **unpublished draft prerelease** tied to that commit. It requires no PyPI token. An existing release with the same tag fails instead of replacing its files. The workflow must exist on the default branch before dispatch, as described in [GitHub's documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

Review the draft's notes, target commit, and assets. Test its downloaded kit in a fresh environment. Then select **Publish release** when you intend to make it public, keeping the prerelease designation. Publishing a GitHub release does not upload anything to PyPI.

For a manual draft, use the same verified files and an explicit SHA with `gh release create --draft --prerelease --target COMMIT --notes-file NOTES`. See the [GitHub CLI reference](https://cli.github.com/manual/gh_release_create). Do not replace published files; fix problems in a new alpha version.

## Optional PyPI distribution

PyPI is not configured by this change, and the name's availability or ownership has not been established. Before enabling `pip install kgodel`, the owner must confirm the project name, register the package or pending publisher, and configure a dedicated GitHub environment and Trusted Publisher. Test on TestPyPI first. Follow the [Python Packaging guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) for current tokenless publishing and attestations. Publish the verified distributions without rebuilding different files after review.

## Before a stable 1.0

Collect feedback on installation, proofs, and supported use cases. Establish an API/deprecation policy, decide whether to support worlds beyond the route simulator, and measure representative workloads against documented limits. Choose the product surface before adding a desktop interface or hosted service. A passing matrix supports this preview's documented behavior; it is not production certification or complete Prolog compatibility.
