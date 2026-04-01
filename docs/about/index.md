# About

`SWC-Studio` is a shared desktop, CLI, and Python toolkit for working with SWC morphology data.

## Overview

`SWC-Studio` is designed for researchers and developers who need to inspect neuron reconstructions, identify structural or annotation problems, repair those problems, and run repeatable morphology-processing workflows from one shared backend.

The project combines a desktop application, a command-line interface, and a Python package so the same core logic can support interactive review, scripted workflows, and larger integration work.

## What the Project Includes

`SWC-Studio` is organized around three connected interfaces:

- a shared Python backend for parsing, validation, reporting, and processing
- a CLI for repeatable batch jobs and single-file operations
- a desktop GUI for issue-driven inspection and repair

These interfaces use the same feature backend, which keeps behavior consistent across the app, terminal workflows, and library usage.

## Core Capabilities

At a high level, the project supports five major tool areas:

1. Batch Processing
2. Validation
3. Visualization
4. Morphology Editing
5. Geometry Editing

Current workflows include:

- splitting SWC files into soma-root trees
- single-file and batch validation
- rule-based auto typing
- radii cleaning and outlier repair
- index cleaning
- simplification and geometry editing
- manual editing for labels, radii, and topology-related fixes

## Intended Workflow

The main application flow is issue-driven.

A typical session starts by opening one SWC file, running validation, reviewing the issue list, applying repairs in the relevant tool, and rerunning validation until the morphology is ready for export or downstream processing.

This makes the GUI useful for focused repair work, while the CLI and Python interface support the same underlying operations in repeatable scripts and larger pipelines.

## Who This Documentation Is For

The documentation is written for three main audiences:

- users running GUI or CLI workflows
- developers extending features or understanding project structure
- labs integrating the toolkit into broader Python or plugin-based workflows

## Documentation Map

The main documentation section is organized to help readers move from setup into practical use:

- `Setup` for installation and first run
- `Workflows` for GUI and CLI usage
- `Validation and Repair` for issue definitions and repair context
- `Reports and Outputs` for generated artifacts and logs
- `Tutorials and Guides` for focused walkthroughs
- `Integration and Extension` and `Reference` for architecture, plugins, and API details
