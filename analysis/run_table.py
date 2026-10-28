"""Run-wise completeness: for every fMRI run, which assets exist and where they are stored.

The spine is the BIDS `*_bold.nii*` runs of each dataset. Each run gets one row per
asset (long format): raw `bold`, raw `physio`, `fmriprep`, `physprep` and one
`ts_<atlas>` per timeseries atlas. `present` is True / False, or NA when the
asset cannot be judged for that run (the dataset has no such derivative, or the
timeseries h5 is missing or was not indexed). One boolean column per release
remote says whether the asset is held there (from `fetch-annex-locations`).

Everything is read from files already on disk — directory trees, plain-git
sidecars, and the indexes written by `fetch` (`source_data/annex_locations/`,
`source_data/timeseries_index.tsv`).
"""
from pathlib import Path
import re

import pandas as pd

from analysis.physio import (
    MODALITIES, _glob_func, _lookup_quality, _physio_runs, _quality_map, _strip_run, _strip_suffix,
)
from analysis.statistics import _collect_run_map, _load_run_data, _run_key
from analysis.timeseries_index import h5_files

NA = "NA"
ASSETS_FIXED = ["bold", "physio", "fmriprep", "physprep"]
INDEX_COLUMNS = ["dataset", "subject", "file", "n_rows"]


def _read_locations(annex_dir: Path, dataset: str, kind: str) -> pd.DataFrame | None:
    path = annex_dir / f"{dataset}_{kind}.tsv"
    if not path.exists():
        return None
    return pd.read_csv(path, sep="\t", keep_default_na=False)


def _remote_sets(df: pd.DataFrame | None, base_of) -> dict[str, set[str]]:
    """{run base: labels held by *every* file of the run} (all echoes / spaces must be there)."""
    sets: dict[str, set[str]] = {}
    if df is None:
        return sets
    for path, remotes in zip(df["path"], df["remotes"]):
        base = _canon(base_of(Path(path).name))
        held = set(filter(None, str(remotes).split(";")))
        sets[base] = sets[base] & held if base in sets else held
    return sets


def _canon(key: str) -> str:
    """Canonical run key for matching across datasets whose derivative naming drifts from BIDS.

    fmriprep unpads `run-01` to `run-1` and places `part-mag` differently, and some
    BIDS runs carry a `__dup-01` suffix; none of that identifies a different run.
    """
    key = re.sub(r"__dup-\d+", "", key)
    key = re.sub(r"_(part|echo)-[^_]+", "", key)
    key = re.sub(r"_bold$", "", key)
    return re.sub(r"(run-)0+(\d)", r"\1\2", key)


def _bold_base(name: str) -> str:
    return _strip_suffix(_run_key(Path(name)), "_bold")


def _physio_base(name: str) -> str:
    return _strip_suffix(name, "_physio.tsv.gz")


def _physprep_base(name: str) -> str:
    return _strip_suffix(name, "_desc-preproc_physio.tsv.gz")


def _fmriprep_base(name: str) -> str:
    return re.split(r"_space-", name)[0]


def _fmriprep_runs(fmriprep_dir: Path) -> dict[str, list[str]]:
    """{run base: [spaces]} from the fmriprep `desc-preproc_bold.nii.gz` tree."""
    runs: dict[str, list[str]] = {}
    for p in _glob_func(fmriprep_dir, "*_desc-preproc*_bold.nii.gz"):
        m = re.search(r"_space-([^_]+)", p.name)
        runs.setdefault(_canon(_fmriprep_base(p.name)), []).append(m.group(1) if m else "native")
    return runs


def _ts_run_set(run_keys) -> set[str]:
    """Canonical timeseries run keys, also without their session.

    Session-less datasets (harrypotter) are stored under a single `ses-001` in the h5
    while their BIDS runs have no session; run numbers are unique, so dropping it is safe.
    """
    canon = {_canon(r) for r in run_keys}
    return canon | {re.sub(r"_ses-[^_]+", "", k) for k in canon}


def _parse(key: str) -> tuple[str, str, str]:
    """Return (subject, session, task) from a BIDS run key; session is '' when absent."""
    sub = re.match(r"(sub-[^_]+)", key)
    ses = re.search(r"_(ses-[^_]+)", key)
    task = re.search(r"_task-([^_]+)", key)
    return (sub.group(1) if sub else "unknown", ses.group(1) if ses else "",
            task.group(1) if task else "")


def run_subjects(bids_dir: Path) -> list[str]:
    """Subjects of a dataset that have at least one bold run."""
    return sorted({_parse(k)[0] for k in _collect_run_map(bids_dir)})


class DatasetAssets:
    """All the per-dataset lookups needed to fill the rows of any of its subjects."""

    def __init__(self, cneuromod_all_dir: Path, dataset: str, annex_dir: Path,
                 ts_index: pd.DataFrame, atlases: list[str], labels: list[str]):
        self.dataset, self.labels, self.atlases = dataset, labels, atlases
        root = cneuromod_all_dir / dataset
        bids = root / "bids"

        run_map = _collect_run_map(bids)
        _, durations = _load_run_data(run_map, dataset)
        self.runs = {_strip_suffix(k, "_bold"): durations[k] for k in run_map}

        bids_loc = _read_locations(annex_dir, dataset, "bids")
        is_bold = bids_loc is not None and bids_loc["path"].str.contains(r"_bold\.nii")
        self.bold_rem = _remote_sets(bids_loc[is_bold] if bids_loc is not None else None, _bold_base)
        is_physio = bids_loc is not None and bids_loc["path"].str.endswith("_physio.tsv.gz")
        self.bids_physio_rem = _remote_sets(bids_loc[is_physio] if bids_loc is not None else None, _physio_base)

        # raw physio
        self.physio_keys = set(_physio_runs(bids))

        # physprep QC
        self.qmap = _quality_map(root / "physprep") if (root / "physprep").is_dir() else {}
        runless = pd.Series([_strip_run(k) for k in self.physio_keys]).value_counts()
        self.ambiguous = set(runless[runless > 1].index) if len(runless) else set()
        self.physprep_rem = _remote_sets(_read_locations(annex_dir, dataset, "physprep"), _physprep_base)

        # fmriprep
        self.fmriprep = _fmriprep_runs(root / "fmriprep") if (root / "fmriprep").is_dir() else {}
        self.fmriprep_rem = _remote_sets(_read_locations(annex_dir, dataset, "fmriprep"), _fmriprep_base)

        # timeseries: per atlas, subject -> (h5 path or None, indexed run keys or None, remotes)
        ts_repo = root / "timeseries"
        ts_loc = _read_locations(annex_dir, dataset, "timeseries")
        self.ts_has_repo = ts_repo.is_dir() and any(ts_repo.glob("timeseries/*/sub-*"))
        self.ts = {}
        for atlas in atlases:
            files = h5_files(ts_repo, atlas) if self.ts_has_repo else {}
            rows = ts_index[(ts_index["dataset"] == dataset) & (ts_index["atlas"] == atlas)]
            for sub, path in files.items():
                rel = path.relative_to(ts_repo).as_posix()
                held = set()
                if ts_loc is not None:
                    hit = ts_loc[ts_loc["path"] == rel]
                    held = set(filter(None, str(hit["remotes"].iloc[0]).split(";"))) if len(hit) else set()
                runs = rows[rows["subject"] == sub]["run_key"]
                self.ts[(atlas, sub)] = (_ts_run_set(runs) if len(runs) else None, held)

    def _remote_cols(self, present, held: set[str] | None) -> dict:
        if present is NA:
            return {label: NA for label in self.labels}
        return {label: bool(present and held is not None and label in held) for label in self.labels}

    def rows_for_run(self, base: str, sub: str) -> list[dict]:
        out = []

        def add(asset, present, detail, held):
            out.append({"asset": asset, "present": present, "detail": detail,
                        **self._remote_cols(present, held)})

        canon = _canon(base)
        add("bold", True, "", self.bold_rem.get(canon))

        # raw physio
        if not self.physio_keys:
            add("physio", NA, "", None)
        else:
            has = base in self.physio_keys
            qkey, quality = _lookup_quality(base, self.qmap, self.ambiguous)
            streams = ";".join(m for m in MODALITIES if quality and m in quality)
            add("physio", has, streams if has else "", self.bids_physio_rem.get(canon))

        # fmriprep
        if not self.fmriprep:
            add("fmriprep", NA, "", None)
        else:
            spaces = sorted(self.fmriprep.get(canon, []))
            add("fmriprep", bool(spaces), ";".join(spaces), self.fmriprep_rem.get(canon))

        # physprep
        if not self.qmap:
            add("physprep", NA, "", None)
        else:
            qkey, quality = _lookup_quality(base, self.qmap, self.ambiguous)
            if quality is None:
                add("physprep", False, "", None)
            else:
                verdicts = ";".join(f"{m}={quality[m]['QualityAssessment']}"
                                    for m in MODALITIES if m in quality)
                add("physprep", True, verdicts, self.physprep_rem.get(_canon(qkey)))

        # timeseries
        for atlas in self.atlases:
            entry = self.ts.get((atlas, sub))
            if entry is None:
                add(f"ts_{atlas}", NA, "no h5" if self.ts_has_repo else "", None)
                continue
            runs, held = entry
            if runs is None:
                add(f"ts_{atlas}", NA, "h5 not indexed", None)
            else:
                add(f"ts_{atlas}", canon in runs, "", held)
        return out


def build_run_table(assets: DatasetAssets, subject: str) -> pd.DataFrame:
    """The long run x asset table of one dataset x subject."""
    rows = []
    for base in sorted(b for b in assets.runs if _parse(b)[0] == subject):
        _, session, task = _parse(base)
        dur = assets.runs[base]
        for rec in assets.rows_for_run(base, subject):
            rows.append({"session": session, "run_key": base, "task": task,
                         "duration_h": round(dur, 5) if dur is not None else float("nan"), **rec})
    return pd.DataFrame(rows)


def table_path(out_dir: Path, dataset: str, subject: str) -> Path:
    return out_dir / "run_tables" / dataset / f"{dataset}_{subject}_runs.tsv"


def _summary_row(dataset: str, subject: str, asset: str, g: pd.DataFrame, labels: list[str]) -> dict:
    """Completeness counts of one asset (or the pseudo-asset `complete`) for a dataset x subject."""
    judged = g[g["present"].astype(str) != NA]
    present = judged["present"].astype(str) == "True"
    rec = {"dataset": dataset, "subject": subject, "asset": asset, "n_runs": len(g),
           "n_judged": len(judged), "hours": round(g["duration_h"].sum(), 4),
           "n_present": int(present.sum()),
           "pct_present": round(100 * present.mean(), 2) if len(judged) else float("nan"),
           "hours_missing": round(judged.loc[~present, "duration_h"].sum(), 4) if len(judged) else float("nan")}
    for label in labels:
        held = judged[label].astype(str) == "True"
        rec[f"n_on_{label}"] = int(held.sum())
        rec[f"pct_on_{label}"] = round(100 * held.mean(), 2) if len(judged) else float("nan")
    return rec


def summarize_tables(out_dir: Path, labels: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Concatenate the per-subject tables into the completeness summary and the table index."""
    summary_rows, index_rows = [], []
    for path in sorted((out_dir / "run_tables").glob("*/*_runs.tsv")):
        dataset = path.parent.name
        subject = path.name.split("_")[1]
        df = pd.read_csv(path, sep="\t", keep_default_na=False, na_values=[""],
                         dtype={"session": str, "detail": str})
        index_rows.append({"dataset": dataset, "subject": subject,
                           "file": path.relative_to(out_dir).as_posix(), "n_rows": len(df)})
        for asset, g in df.groupby("asset", sort=False):
            summary_rows.append(_summary_row(dataset, subject, asset, g, labels))
        # a run is complete when every asset that can be judged for it is present
        judged_rows = df[df["present"].astype(str) != NA]
        if len(judged_rows):
            runs = judged_rows.groupby("run_key").agg(
                present=("present", lambda p: (p.astype(str) == "True").all()),
                duration_h=("duration_h", "first"),
                **{label: (label, lambda p: (p.astype(str) == "True").all()) for label in labels})
            runs["asset"] = "complete"
            runs["run_key"] = runs.index
            summary_rows.append(_summary_row(dataset, subject, "complete", runs.assign(
                present=runs["present"].astype(str)), labels))
    return pd.DataFrame(summary_rows), pd.DataFrame(index_rows, columns=INDEX_COLUMNS)
