# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**CNeuroMod all-statistics** computes summary statistics across all CNeuroMod datasets.

- **Session counts** (`run-statistics`): counts BIDS sessions per subject (sub-01 to sub-06) per dataset → `session_counts.tsv`.
- **fMRI run stats** (`run-fmri-stats`): per-dataset aggregate statistics — total runs, average runs per session, average run duration, average session duration, total duration — derived from `bold.nii*` files and their JSON sidecars → `fmri_stats.tsv` + BIDS JSON sidecar.
- **Per-subject fMRI stats** (`run-fmri-per-subject-stats`): same metrics broken down by subject → `fmri_stats_per_subject.tsv`.
- **CNeuroMod dataset comparison** (`run-cneuromod-tables`): validates the `stats` block of each dataset's `dataset_info.yaml` against `source_data/cneuromod.all/docs/schema.json`, then builds tidy per-dataset tables of data volume (brain, task, physiology) → `cneuromod_tidy_per_subject.csv`, `cneuromod_tidy_total.csv`, plus subject availability → `cneuromod_subjects.csv`. Plotted as bubble charts by `notebooks/figure_cneuromod_comparison.ipynb`, rows grouped and colored by the paper's six cognitive categories (`CATEGORIES` in `analysis/dataset_info.py`, mirrored from cneuromod.paper — keep in sync). Moved here from `dataset_comparison`, which keeps only the cross-dataset comparison (CNeuroMod as a single row).
- **CNeuroMod summary** (`run-cneuromod-summary`): sums every dataset's `stats` block into one schema-compatible entry → `cneuromod_summary.yaml` (git-tracked). This is the single CNeuroMod row read by `dataset_comparison`, via `cneuromod.all/analysis/cneuromod.all.statistics/output_data/` — keep the file name and format stable.

Source data is [cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all), declared under `datasets:` in `invoke.yaml` and made available under `source_data/cneuromod.all/` — **not** a git submodule. `invoke fetch-cneuromod` symlinks an existing local checkout (the `source:` key, default `../cneuromod.all`, overridable with `--source`) or `datalad clone`s it when none is found; `invoke fetch-bids` then installs each dataset's `bids/` subdataset (tree only, via `datalad get -n`, since it is nested inside the superdataset and plain `git submodule` cannot reach it). The analysis only reads directory structure, `*_bold.json` sidecars, each dataset's `dataset_info.yaml` and the cneuromod.all JSON schema — plain git files, never annexed — so no annexed content retrieval is ever needed. `source_data/cneuromod.all` is gitignored; `invoke fetch --source ../..` is the embedded case, when this repo lives inside `cneuromod.all/docs/`.

**Never run `git submodule update --init --recursive` or `datalad install -r`** inside `cneuromod.all` — submodules re-expose their own sub-submodules at differing versions, and recursive cloning triggers a massive, redundant retrieval. Use `airoh.datalad.install_subdataset` (`datalad get -n`) instead.

What each source asset actually resolved to is recorded in `source_data/MANIFEST.json` (written by `fetch`); what produced the outputs is recorded in `output_data/PROVENANCE.json` (written by `run`). Both are git-tracked and expected to churn on every run.

This project is built on the [`airoh-mini`](https://github.com/airoh-pipeline/airoh-template) template, using the [`invoke`](https://www.pyinvoke.org/) task runner and the `airoh[datalad]` pip package.

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
uv run invoke fetch           # Make cneuromod.all and every dataset's bids tree available
uv run invoke run             # Full pipeline (project-specific step chain)
uv run invoke run-notebooks   # Execute notebooks, save figures to output_data/
uv run invoke verify          # Check code, config, data and docs still agree
uv run invoke clean           # Remove output_data/ contents
uv run invoke --list          # Show all available tasks
```

Without `uv` (activate your environment first):
```bash
invoke fetch              # Make cneuromod.all and every dataset's bids tree available
invoke run                # Full pipeline (project-specific step chain)
invoke run-notebooks      # Execute notebooks, save figures to output_data/
invoke verify             # Check code, config, data and docs still agree
invoke clean              # Remove output_data/ contents
invoke --list             # Show all available tasks
```

## Architecture

**Always read `tasks.py` first** before proposing or implementing any pipeline change — it is the authoritative source of what tasks exist, how they are wired, and what parameters they accept.

**Execution flow:** `invoke run` triggers the project's analysis pipeline by calling each step in its body, in order. The permanent tasks — `fetch`, `run`, `verify`, `clean` — are always present; intermediate steps are project-specific.

**`pre=` chains do not fire when a task is called as a function.** A `pre=` list only runs when invoke executes that task from the command line; calling `run(c)` or `clean(c)` from Python runs the body alone. Umbrella tasks that other tasks call (`run`, `clean`, `fetch`) therefore do their work in the body, not via `pre=` — this is why `run --force` (which calls `clean(c)` directly) actually deletes something. No task in this project uses `pre=`: `run` sequences `run-statistics`, `run-fmri-stats`, `run-fmri-per-subject-stats`, `run-cneuromod-tables`, `run-cneuromod-summary` and `run-notebooks` as direct body calls instead.

**Fetch retrieves, run never pulls.** `invoke fetch` is the only place that touches the network or `datalad`/`git`. Every `run-*` task reads whatever is already on disk under `source_data/`. `invoke verify` is deliberately **not** part of `run` — reproducing results must not depend on documentation hygiene; run `verify` before committing instead.

**Caching is by existence.** Every `run-{name}` task checks whether its output file already exists and skips if so — this is what makes repeated `invoke run` calls during development cheap. `invoke fetch-cneuromod` and `invoke fetch-bids` are no-ops once the checkout/subdataset is already present, except `fetch-bids`, which still runs a lightweight `datalad update --merge` on an already-installed subdataset so new upstream commits surface on every fetch.

- `invoke.yaml` — all path and data config (`output_data_dir`, `source_data_dir`, `notebooks_dir`, `datasets:` for `cneuromod_all`, `manifest_file`/`provenance_file` for provenance, `verify:` for verify settings)
- `tasks.py` — project-specific invoke tasks; imports reusable tasks from `airoh.utils`, `airoh.datalad`, `airoh.provenance`, `airoh.verify`
- `analysis/` — pure Python analysis logic, called by tasks in `tasks.py`
- `notebooks/` — Jupyter notebooks executed by `run_notebooks` via `airoh.utils.run_notebooks`; notebooks receive `OUTPUT_DATA_DIR` and `SOURCE_DATA_DIR` as environment variables
- `source_data/CONTENT.md` and `output_data/CONTENT.md` — authoritative docs for what each data folder contains; update these when data assets change, do not duplicate their content elsewhere

**Analysis vs. notebooks:** Heavy computation belongs in `analysis/` Python code, invoked by `run-{name}` tasks, which write results to `output_data/`. Notebooks are for visualization only — they read from `output_data/` and produce figures. This keeps notebooks fast and focused.

**Idempotent tasks:** Each `run-{name}` task must check whether its outputs already exist and skip execution if they do. This means `invoke run` can be called repeatedly during development of a later step — earlier steps are skipped automatically. To force a full rerun, call `invoke clean` first, then `invoke run`.

**Task naming conventions:**
- Analysis tasks are named `run-{name}` (e.g. `run-preprocessing`, `run-model`).
- Cleaning tasks mirror them: `clean-{name}` removes only the outputs of the corresponding step.
- The top-level `clean` task calls all `clean-{name}` tasks in sequence, in its body (see the `pre=` warning above).
- The top-level `run` task calls all steps in sequence, in its body.

**Task parameters:** `run-{name}` tasks should expose chunk or subset parameters (e.g. a subject ID, a chunk index) so that individual pieces can be rerun in isolation. They should also support a `smoke` flag for a fast minimal run useful for testing the pipeline end-to-end without running the full analysis.

**Template cleanup:** When starting a new project from this template, remove the demo code before adding project-specific work:
- Delete `run_simulation` from `tasks.py` and remove it from the `pre=` chains on `run_notebooks` and `run`
- Delete `analysis/simulation.py` (and the `analysis/` folder if it stays empty)
- Clear or replace `source_data/CONTENT.md` and `output_data/CONTENT.md` with project-specific descriptions
- Update `invoke.yaml` (`files:`, paths) for the new project's data sources

**Adding a new analysis step:** add a function to `analysis/`, add a `run-{name}` task and a matching `clean-{name}` task in `tasks.py`, call both from the bodies of the top-level `run` and `clean` tasks (see the `pre=` warning above — a body call, not `pre=`), and create or extend a notebook in `notebooks/` for visualization.

**Verification:** `invoke verify` (see `airoh.verify`) checks that the code, config, data and docs still agree — the task list in README/CLAUDE.md matches `tasks.py`, `pyproject.toml`/`requirements.txt` agree, paths named in the docs exist, `source_data/CONTENT.md`/`output_data/CONTENT.md` describe everything in their folders, config keys declared in `invoke.yaml` are actually read, no oversized or risky file is tracked in git, and the provenance records are present and current. Run it before committing; it is not part of `run`.

**Evolving CLAUDE.md:** Run `invoke verify` after any structural change — it catches the mechanical half of this instruction (renamed tasks, moved paths, undocumented outputs) that is otherwise left to memory. Keep this file current as the project grows. It should always reflect the actual scope of the project — what it does, what data it uses, and what analysis steps it contains. When adding or removing a task, rename a folder, or change the pipeline structure, update CLAUDE.md in the same commit. Stale guidance here misleads future AI sessions and collaborators alike.

**Keeping README.md current:** README.md is the user-facing documentation for this project. Any structural or workflow change — new tasks, renamed folders, updated commands, new dependencies — must be reflected there in the same commit. The task list in README.md should match `invoke --list` exactly; if a task is added or removed, update README.md accordingly. For data folder contents, point to `source_data/CONTENT.md` and `output_data/CONTENT.md` rather than duplicating their content inline.
