# Docs Overview

Use these pages first:

- [GETTING_STARTED.md](GETTING_STARTED.md)
  - install, run, first steps
- [GUI_WORKFLOW.md](GUI_WORKFLOW.md)
  - current GUI layout and issue-driven workflow
- [CLI_REFERENCE.md](CLI_REFERENCE.md)
  - command reference
- [CHECKS_AND_ISSUES_REFERENCE.md](CHECKS_AND_ISSUES_REFERENCE.md)
  - canonical check, issue, parameter, and algorithm reference
- [RADII_CLEANING_TUTORIAL.md](RADII_CLEANING_TUTORIAL.md)
  - focused radii-cleaning guide

Supporting pages:

- [VALIDATION_RULES.md](VALIDATION_RULES.md)
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [LOGS_AND_REPORTS.md](LOGS_AND_REPORTS.md)
- [MACOS_PACKAGING.md](MACOS_PACKAGING.md)
- [TOOL_TUTORIALS.md](TOOL_TUTORIALS.md)

Sphinx HTML output is generated locally and is not tracked in git:

```bash
sphinx-build -b html docs docs/_build/html
```
