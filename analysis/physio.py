"""Physiological recording statistics (duration and physprep QC) per dataset.

Neither the raw BIDS `*_physio.json` sidecars nor the physprep derivatives store
a recording duration in a plain git file, and the signals themselves are
annexed. Physio is segmented around each fMRI run, so a physio run's duration
is taken to be the duration of its paired BOLD run (n_volumes × TR).

Basic QC comes from physprep's `*_desc-quality.json` (plain git): for each
modality, `PercentageValid` is the fraction of 1-minute windows passing a
modality-specific criterion, and `QualityAssessment` is `Pass` when it exceeds
80%. Usable hours = duration × PercentageValid.
"""
from pathlib import Path
import json
import re
import warnings
import pandas as pd

from analysis.statistics import SUBJECTS, _collect_run_map, _load_run_data, _run_key
from analysis.dataset_info import load_cneuromod_datasets, _get_nested

MODALITIES = ["PPG", "ECG", "EDA", "RSP"]
# physprep modality -> dataset_info.yaml `physiology.<name>` field
SCHEMA_NAMES = {"ECG": "ecg", "RSP": "respiration", "PPG": "plethysmograph", "EDA": "eda"}


def _strip_suffix(name: str, suffix: str) -> str:
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _glob_func(root: Path, pattern: str) -> list[Path]:
    """Glob func/ files in both session and session-less (e.g. harrypotter) layouts."""
    return sorted(root.glob(f"sub-*/ses-*/func/{pattern}")) + sorted(root.glob(f"sub-*/func/{pattern}"))


def _physio_runs(bids_dir: Path) -> list[str]:
    """Return run keys (BIDS name without `_physio.json`) for every raw physio run.

    Only file existence is used: some sidecars are not valid JSON upstream
    (pickled dicts in movie10), and they carry no duration anyway.
    """
    return [_strip_suffix(p.name, "_physio.json") for p in _glob_func(bids_dir, "*_physio.json")]


def _quality_map(physprep_dir: Path) -> dict[str, dict]:
    """Return {run_key: quality_dict} from physprep `*_desc-quality.json` files."""
    qmap = {}
    for p in _glob_func(physprep_dir, "*_desc-quality.json"):
        with open(p) as f:
            qmap[_strip_suffix(p.name, "_desc-quality.json")] = json.load(f)
    return qmap


def _strip_run(key: str) -> str:
    return re.sub(r"_run-[^_]+", "", key)


def _lookup_quality(
    key: str, qmap: dict[str, dict], ambiguous: set[str]
) -> tuple[str | None, dict | None]:
    """Match a raw physio key to its QC entry.

    Physprep naming drifts from raw BIDS: movie10 drops the `run-` entity
    (tried only when the run-less key is not in `ambiguous`, i.e. unique among
    the dataset's physio runs), harrypotter keeps a stray `_physio`.
    """
    candidates = [key, f"{key}_physio"]
    if _strip_run(key) not in ambiguous:
        candidates.append(_strip_run(key))
    for candidate in candidates:
        if candidate in qmap:
            return candidate, qmap[candidate]
    return None, None


def _parse_key(key: str) -> tuple[str, str]:
    m = re.match(r"(sub-[^_]+)_(ses-[^_]+)_", key)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"(sub-[^_]+)_", key)
    return (m.group(1) if m else "unknown"), "ses-01"


def build_physio_run_table(cneuromod_all_dir: Path) -> pd.DataFrame:
    """One row per raw physio run: duration from the paired BOLD run, plus physprep QC."""
    rows = []
    for bids_dir in sorted(cneuromod_all_dir.glob("*/bids")):
        dataset = bids_dir.parent.name
        physio_keys = _physio_runs(bids_dir)
        if not physio_keys:
            continue

        run_map = _collect_run_map(bids_dir)
        # BOLD run keys end in `_bold`; physio keys do not
        bold_map = {_strip_suffix(k, "_bold"): v for k, v in run_map.items()}
        paired = {k: bold_map[k] for k in physio_keys if k in bold_map}
        _, run_durations = _load_run_data(
            {_run_key(nii): nii for nii in paired.values()}, dataset
        )
        durations = {k: run_durations[_run_key(nii)] for k, nii in paired.items()}

        unpaired = sorted(set(physio_keys) - set(paired))
        if unpaired:
            warnings.warn(
                f"[{dataset}] {len(unpaired)} physio run(s) without a matching BOLD run "
                f"(duration unknown), e.g. {unpaired[0]}",
                stacklevel=2,
            )

        qmap = _quality_map(cneuromod_all_dir / dataset / "physprep")
        runless = pd.Series([_strip_run(k) for k in physio_keys]).value_counts()
        ambiguous = set(runless[runless > 1].index)
        matched_q = set()
        for key in physio_keys:
            sub, ses = _parse_key(key)
            dur = durations.get(key)
            qkey, quality = _lookup_quality(key, qmap, ambiguous)
            if qkey is not None:
                matched_q.add(qkey)
            row = {
                "dataset": dataset,
                "subject": sub,
                "session": ses,
                "run": key,
                "duration_h": dur if dur is not None else float("nan"),
                "has_qc": quality is not None,
            }
            for mod in MODALITIES:
                q = (quality or {}).get(mod)
                row[f"{mod}_pct_valid"] = q["PercentageValid"] if q else float("nan")
                row[f"{mod}_pass"] = (q["QualityAssessment"] == "Pass") if q else pd.NA
            rows.append(row)

        orphan_q = sorted(set(qmap) - matched_q)
        if orphan_q:
            warnings.warn(
                f"[{dataset}] {len(orphan_q)} physprep QC file(s) without a raw physio run, "
                f"e.g. {orphan_q[0]}",
                stacklevel=2,
            )

    return pd.DataFrame(rows)


def _aggregate(g: pd.DataFrame) -> dict:
    qc = g[g["has_qc"]]
    rec = {
        "n_runs": len(g),
        "recorded_h": round(g["duration_h"].sum(skipna=True), 4),
        "n_runs_qc": len(qc),
        "recorded_qc_h": round(qc["duration_h"].sum(skipna=True), 4),
    }
    for mod in MODALITIES:
        has_qc = len(qc) > 0
        usable = (qc["duration_h"] * qc[f"{mod}_pct_valid"]).sum(skipna=True)
        passed = qc.loc[qc[f"{mod}_pass"] == True, "duration_h"].sum(skipna=True)  # noqa: E712
        rec[f"{mod}_usable_h"] = round(usable, 4) if has_qc else float("nan")
        rec[f"{mod}_pass_h"] = round(passed, 4) if has_qc else float("nan")
        rec[f"{mod}_n_pass"] = int((qc[f"{mod}_pass"] == True).sum()) if has_qc else float("nan")  # noqa: E712
    return rec


def compute_physio_stats(run_df: pd.DataFrame) -> pd.DataFrame:
    """Per-dataset physio stats, with a final `all` row."""
    records = [{"dataset": ds, **_aggregate(g)} for ds, g in run_df.groupby("dataset")]
    records.append({"dataset": "all", **_aggregate(run_df)})
    return pd.DataFrame(records)


def compute_physio_stats_per_subject(run_df: pd.DataFrame) -> pd.DataFrame:
    """Per-(dataset, subject) physio stats, covering every subject in SUBJECTS."""
    empty = run_df.iloc[0:0]
    records = []
    for ds, g in run_df.groupby("dataset"):
        for subject in SUBJECTS:
            sg = g[g["subject"] == subject]
            records.append({"dataset": ds, "subject": subject, **_aggregate(sg if len(sg) else empty)})
    return pd.DataFrame(records)


def crosscheck_declared(stats_df: pd.DataFrame, cneuromod_all_dir: Path) -> pd.DataFrame:
    """Compare computed physio hours with `physiology.*.total_h` declared in dataset_info.yaml."""
    computed = stats_df.set_index("dataset")
    records = []
    for ds in load_cneuromod_datasets(cneuromod_all_dir):
        name = ds["name"]
        declared = {
            mod: _get_nested(ds, f"physiology.{SCHEMA_NAMES[mod]}.total_h") for mod in MODALITIES
        }
        if name not in computed.index and not any(v for v in declared.values()):
            continue
        rec = {"dataset": name}
        rec["recorded_h"] = computed.at[name, "recorded_h"] if name in computed.index else float("nan")
        for mod in MODALITIES:
            rec[f"{mod}_declared_h"] = declared[mod] if declared[mod] is not None else float("nan")
            rec[f"{mod}_usable_h"] = (
                computed.at[name, f"{mod}_usable_h"] if name in computed.index else float("nan")
            )
        records.append(rec)
    return pd.DataFrame(records)
