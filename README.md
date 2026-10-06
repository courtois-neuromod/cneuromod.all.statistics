# CNeuroMod all-statistics

Statistics across all CNeuroMod datasets.

This repository computes summary statistics (session counts and fMRI run statistics per subject per dataset) from the BIDS metadata of the [Courtois-NeuroMod](https://www.cneuromod.ca/) data collection, compares CNeuroMod datasets by data volume using each dataset's curated `dataset_info.yaml`, and produces visualizations.

---

## Setup

```bash
uv sync
```

---

## Running the pipeline

```bash
uv run invoke fetch           # Make cneuromod.all and each dataset's bids tree available
uv run invoke run             # Full pipeline (statistics + figures)
uv run invoke run-smoke       # Fast end-to-end check
```

To force a full rerun from scratch:

```bash
uv run invoke clean
uv run invoke run
```

Or in one step: `uv run invoke run --force`.

---

## Task overview

| Task                           | Description                                                         |
|--------------------------------|---------------------------------------------------------------------|
| `fetch`                        | Retrieve all source data: `cneuromod.all` and every dataset's `bids` tree |
| `fetch-cneuromod`              | Make the `cneuromod.all` superdataset available under `source_data/` |
| `fetch-bids`                   | Install each dataset's `bids/` subdataset (tree only, no annexed content) |
| `run-statistics`               | Count sessions per subject per dataset; write `output_data/session_counts.tsv` |
| `run-fmri-stats`               | Compute per-dataset fMRI aggregate stats; write `output_data/fmri_stats.tsv` |
| `run-fmri-per-subject-stats`   | Compute per-subject fMRI stats per dataset; write `output_data/fmri_stats_per_subject.tsv` |
| `run-cneuromod-tables`         | Validate each `dataset_info.yaml` and build the per-dataset comparison tables `output_data/cneuromod_*.csv` |
| `run-cneuromod-summary`        | Sum every `dataset_info.yaml` into one CNeuroMod entry, `output_data/cneuromod_summary.yaml` |
| `run-notebooks`                | Execute notebooks and save figures to `output_data/`               |
| `run`                          | Full pipeline in order                                              |
| `run-smoke`                    | Minimal end-to-end pass                                             |
| `verify`                       | Check that code, config, data and docs still agree (not part of `run`) |
| `clean-statistics`             | Remove `session_counts.tsv`                                         |
| `clean-fmri-stats`             | Remove `fmri_stats.tsv` and its JSON sidecar                       |
| `clean-fmri-per-subject-stats` | Remove `fmri_stats_per_subject.tsv`                                |
| `clean-cneuromod-tables`       | Remove the `cneuromod_*.csv` comparison tables                     |
| `clean-cneuromod-summary`      | Remove `cneuromod_summary.yaml`                                     |
| `clean-figures`                | Remove generated figures                                            |
| `clean`                        | Remove all computed outputs                                         |
| `clean-cneuromod`              | Remove the `cneuromod.all` checkout                                 |
| `clean-source`                 | Remove the `cneuromod.all` checkout                                 |

Use `uv run invoke --list` for the full task list.

---

## Data

- Source data: see [`source_data/CONTENT.md`](source_data/CONTENT.md)
- Output data: see [`output_data/CONTENT.md`](output_data/CONTENT.md)

`invoke fetch` symlinks an existing local checkout of `cneuromod.all` (the
`source:` key in `invoke.yaml`, default `../cneuromod.all`), or clones it from
GitHub when none is found — the dataset *tree* only, no annexed content, since
this project only reads directory structure, `*_bold.json` sidecars, each
dataset's `dataset_info.yaml` and the cneuromod.all JSON schema. What
was actually consumed is recorded in `source_data/MANIFEST.json` (by `fetch`)
and `output_data/PROVENANCE.json` (by `run`).

---

## Embedded use (inside `cneuromod.all/docs/`)

When this repo is a submodule inside `cneuromod.all/docs/`, the source data already lives at `../..`:

```bash
uv run invoke fetch --source ../..
```
