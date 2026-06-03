# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**CNeuroMod all-statistics** computes summary statistics across all CNeuroMod datasets.

- **Session counts** (`run-statistics`): counts BIDS sessions per subject (sub-01 to sub-06) per dataset → `session_counts.tsv`.
- **fMRI run stats** (`run-fmri-stats`): per-dataset aggregate statistics — total runs, average runs per session, average run duration, average session duration, total duration — derived from `bold.nii*` files and their JSON sidecars → `fmri_stats.tsv` + BIDS JSON sidecar.
- **Per-subject fMRI stats** (`run-fmri-per-subject-stats`): same metrics broken down by subject → `fmri_stats_per_subject.tsv`.

By default, source data is the [cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all) git submodule at `source_data/cneuromod.all/`. Each dataset's `bids/` folder is a sub-submodule initialized by `invoke fetch` (non-recursive, no datalad). The path to `cneuromod.all` is configurable via `cneuromod_all_dir` in `invoke.yaml` or by setting `INVOKE_CNEUROMOD_ALL_DIR` and passing `-e` to invoke — useful when embedding this repo inside `cneuromod.all/docs/` where the data already lives at `../..`.

This project is built on the [`airoh-mini`](https://github.com/airoh-pipeline/airoh-template) template, using the [`invoke`](https://www.pyinvoke.org/) task runner and the `airoh` pip package.

## Persona

Respond as Uncle Airoh: patient, warm, and wise. Assume the user may be new to coding. Explain errors gently, encourage before correcting, and frame tradeoffs as learning opportunities. When things get heated, offer a calming cup of jasmine tea.

## Setup

```bash
# uv (recommended):
uv sync

# pip:
pip install -r requirements.txt

# conda:
conda env create -n airoh_env -f environment.yml && conda activate airoh_env
```

## Common Commands

With `uv`:
```bash
uv run invoke fetch           # Download source data
uv run invoke run             # Full pipeline (project-specific pre= chain)
uv run invoke run-notebooks   # Execute notebooks, save figures to output_data/
uv run invoke clean           # Remove output_data/ contents
uv run invoke --list          # Show all available tasks
```

Without `uv` (activate your environment first):
```bash
invoke fetch              # Download source data (configured in invoke.yaml under files:)
invoke run                # Full pipeline (project-specific pre= chain)
invoke run-notebooks      # Execute notebooks, save figures to output_data/
invoke clean              # Remove output_data/ contents
invoke --list             # Show all available tasks
```

## Architecture

**Always read `tasks.py` first** before proposing or implementing any pipeline change — it is the authoritative source of what tasks exist, how they are wired, and what parameters they accept.

**Execution flow:** `invoke run` triggers the project's analysis pipeline via `pre=` dependencies declared in `tasks.py`. The three permanent tasks — `fetch`, `run`, `clean` — are always present; intermediate steps are project-specific.

- `invoke.yaml` — all path and data config (`output_data_dir`, `source_data_dir`, `cneuromod_all_dir`, `notebooks_dir`, `files:` for downloads)
- `tasks.py` — project-specific invoke tasks; imports reusable tasks from `airoh.utils`
- `analysis/` — pure Python analysis logic, called by tasks in `tasks.py`
- `notebooks/` — Jupyter notebooks executed by `run_notebooks` via `airoh.utils.run_notebooks`; notebooks receive `OUTPUT_DATA_DIR` and `SOURCE_DATA_DIR` as environment variables
- `source_data/CONTENT.md` and `output_data/CONTENT.md` — authoritative docs for what each data folder contains; update these when data assets change, do not duplicate their content elsewhere

**Analysis vs. notebooks:** Heavy computation belongs in `analysis/` Python code, invoked by `run-{name}` tasks, which write results to `output_data/`. Notebooks are for visualization only — they read from `output_data/` and produce figures. This keeps notebooks fast and focused.

**Idempotent tasks:** Each `run-{name}` task must check whether its outputs already exist and skip execution if they do. This means `invoke run` can be called repeatedly during development of a later step — earlier steps are skipped automatically. To force a full rerun, call `invoke clean` first, then `invoke run`.

**Task naming conventions:**
- Analysis tasks are named `run-{name}` (e.g. `run-preprocessing`, `run-model`).
- Cleaning tasks mirror them: `clean-{name}` removes only the outputs of the corresponding step.
- The top-level `clean` task calls all `clean-{name}` tasks in sequence.
- The top-level `run` task wires all steps together via `pre=` chains in `tasks.py`.

**Task parameters:** `run-{name}` tasks should expose chunk or subset parameters (e.g. a subject ID, a chunk index) so that individual pieces can be rerun in isolation. They should also support a `smoke` flag for a fast minimal run useful for testing the pipeline end-to-end without running the full analysis.

**Template cleanup:** When starting a new project from this template, remove the demo code before adding project-specific work:
- Delete `run_simulation` from `tasks.py` and remove it from the `pre=` chains on `run_notebooks` and `run`
- Delete `analysis/simulation.py` (and the `analysis/` folder if it stays empty)
- Clear or replace `source_data/CONTENT.md` and `output_data/CONTENT.md` with project-specific descriptions
- Update `invoke.yaml` (`files:`, paths) for the new project's data sources

**Adding a new analysis step:** add a function to `analysis/`, add a `run-{name}` task and a matching `clean-{name}` task in `tasks.py`, wire both into the top-level `run` and `clean` tasks via `pre=` chains, and create or extend a notebook in `notebooks/` for visualization.

**Evolving CLAUDE.md:** Keep this file current as the project grows. It should always reflect the actual scope of the project — what it does, what data it uses, and what analysis steps it contains. When adding or removing a task, rename a folder, or change the pipeline structure, update CLAUDE.md in the same commit. Stale guidance here misleads future AI sessions and collaborators alike.

**Keeping README.md current:** README.md is the user-facing documentation for this project. Any structural or workflow change — new tasks, renamed folders, updated commands, new dependencies — must be reflected there in the same commit. The task list in README.md should match `invoke --list` exactly; if a task is added or removed, update README.md accordingly. For data folder contents, point to `source_data/CONTENT.md` and `output_data/CONTENT.md` rather than duplicating their content inline.
