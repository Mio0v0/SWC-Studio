# Docs Structure

This folder stores Sphinx **source** documentation only.

## Source files

- `index.rst`: table of contents root
- `conf.py`: Sphinx configuration
- `requirements.txt` (top-level): full project dependencies (core + GUI + docs)
- `Makefile`: local build helper
- `*.md` and `*.rst`: guide/reference source pages
- `MACOS_PACKAGING.md`: reproducible macOS executable build guide

## Generated output

Generated HTML (`docs/_build/`) is not tracked in git.

Build locally when needed:

```bash
sphinx-build -b html docs docs/_build/html
```

Packaging inputs live in the repo-level `packaging/` folder and are tracked in git.
