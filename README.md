# CNeuroMod all-statistics

Statistics across all CNeuroMod datasets.

This repository computes summary statistics (session counts per subject per dataset) from the BIDS metadata of the [Courtois-NeuroMod](https://www.cneuromod.ca/) data collection and produces visualizations.

---

## Setup

```bash
uv sync
```

---

## Running the pipeline

```bash
uv run invoke fetch           # Init the cneuromod.all submodule and bids sub-submodules
uv run invoke run             # Full pipeline (statistics + figures)
uv run invoke run-smoke       # Fast end-to-end check
```

To force a full rerun from scratch:

```bash
uv run invoke clean
uv run invoke run
```

---

## Task overview

| Task                           | Description                                                         |
|--------------------------------|---------------------------------------------------------------------|
| `fetch`                        | Init `cneuromod.all` submodule and each dataset's `bids` sub-submodule |
| `run-statistics`               | Count sessions per subject per dataset; write `output_data/session_counts.tsv` |
| `run-fmri-stats`               | Compute per-dataset fMRI aggregate stats; write `output_data/fmri_stats.tsv` |
| `run-fmri-per-subject-stats`   | Compute per-subject fMRI stats per dataset; write `output_data/fmri_stats_per_subject.tsv` |
| `run-notebooks`                | Execute notebooks and save figures to `output_data/`               |
| `run`                          | Full pipeline in order                                              |
| `run-smoke`                    | Minimal end-to-end pass                                             |
| `clean-statistics`             | Remove `session_counts.tsv`                                         |
| `clean-fmri-stats`             | Remove `fmri_stats.tsv` and its JSON sidecar                       |
| `clean-fmri-per-subject-stats` | Remove `fmri_stats_per_subject.tsv`                                |
| `clean-figures`                | Remove generated figures                                            |
| `clean`                        | Remove all computed outputs                                         |
| `clean-source`                 | Deinitialize the `cneuromod.all` submodule                         |

Use `uv run invoke --list` for the full task list.

---

## Data

- Source data: see [`source_data/CONTENT.md`](source_data/CONTENT.md)
- Output data: see [`output_data/CONTENT.md`](output_data/CONTENT.md)

---

## Embedded use (inside `cneuromod.all/docs/`)

When this repo is a submodule inside `cneuromod.all/docs/`, the source data already lives at `../..` — no submodule init is needed. Override the data path via the `INVOKE_CNEUROMOD_ALL_DIR` environment variable and pass `-e` to invoke:

```makefile
INVOKE_CNEUROMOD_ALL_DIR=../.. invoke -e run
```

`fetch` detects that the path is external and skips the git submodule step automatically.
