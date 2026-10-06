"""Per-dataset comparison of CNeuroMod datasets, read from each `cneuromod.all/<dataset>/dataset_info.yaml`."""

import yaml
import pandas as pd
from pathlib import Path


COLUMN_GROUPS_PER_SUBJECT = [
    ("Brain", "#4472C4", [
        ("fMRI",  "neuroimaging.fmri.per_subject_h",  "h"),
    ]),
    ("Task content", "#538135", [
        ("Images",     "tasks.images.per_subject_unique",           "#img"),
        ("Video",      "tasks.video.per_subject_unique",            "h"),
        ("Audio",      "tasks.audio.per_subject_unique",            "h"),
        ("Speech",     "tasks.speech_listening.per_subject_unique", "h"),
        ("Text",       "tasks.text_reading.per_subject_unique",     "h"),
        ("Rest",       "tasks.resting_state.per_subject_h",        "h"),
        ("Controlled", "tasks.controlled.per_subject_h",           "h"),
        ("Games",      "tasks.game.per_subject_h",                 "h"),
        ("Contrasts",  "tasks.contrasts.per_subject",              "#"),
    ]),
    ("Physiology", "#7030A0", [
        ("ECG",   "physiology.ecg.per_subject_h",            "h"),
        ("Resp.", "physiology.respiration.per_subject_h",    "h"),
        ("PPG",   "physiology.plethysmograph.per_subject_h", "h"),
        ("EDA",   "physiology.eda.per_subject_h",            "h"),
        ("Eye",   "physiology.eye_tracking.per_subject_h",   "h"),
    ]),
]

COLUMN_GROUPS_TOTAL = [
    ("Brain recordings", "#4472C4", [
        ("fMRI",  "neuroimaging.fmri.total_h",  "h"),
        ("EEG",   "neuroimaging.eeg.total_h",   "h"),
        ("MEG",   "neuroimaging.meg.total_h",   "h"),
        ("iEEG",  "neuroimaging.ieeg.total_h",  "h"),
        ("Ca²⁺",  "neuroimaging.calcium_imaging.total_h", "h"),
    ]),
    ("Task content", "#538135", [
        ("Images", "tasks.images.total_unique",           "#img"),
        ("Video",  "tasks.video.total_unique",            "h"),
        ("Audio",  "tasks.audio.total_unique",            "h"),
        ("Speech", "tasks.speech_listening.total_unique", "h"),
        ("Text",   "tasks.text_reading.total_unique",     "h"),
        ("Rest",   "tasks.resting_state.total_h",         "h"),
        ("Controlled", "tasks.controlled.total_h",        "h"),
        ("Games",      "tasks.game.total_h",              "h"),
        ("Contrasts",  "tasks.contrasts.total",               "#"),
    ]),
    ("Physiology", "#7030A0", [
        ("ECG",   "physiology.ecg.total_h",            "h"),
        ("Resp.", "physiology.respiration.total_h",    "h"),
        ("PPG",   "physiology.plethysmograph.total_h", "h"),
        ("EDA",   "physiology.eda.total_h",            "h"),
        ("Eye",   "physiology.eye_tracking.total_h",   "h"),
    ]),
]


# Cognitive categories used to group and color rows of the bubble charts.
# Mirrors CATEGORIES in cneuromod.paper .claude/skills/update-data-overview/scripts/build_overview.py
# (table tab-cognitive-categories in the paper intro); keep in sync.
# Colors: categorical slots 1-5 of the dataviz reference palette (validated for CVD
# separation), plus a neutral gray so "Others" recedes.
CATEGORIES = [
    ("Movies",                "🍿", "#2a78d6", ["movie10", "friends", "ood"]),
    ("Stories",               "💬", "#eb6834", ["harrypotter", "petit-prince", "narratives"]),
    ("Videogames",            "👾", "#1baf7a", ["shinobi", "mario", "mariostars", "mario3", "mario_eeg"]),
    ("Taskscapes",            "🔬", "#eda100", ["triplets", "things", "emotion-videos", "multfs", "mutemusic"]),
    ("Functional localizers", "🧭", "#4a3aa7", ["langlocalizer", "floc", "retinotopy", "hcptrt"]),
    ("Others",                "🧰", "#898781", ["hearing", "anat", "gamepad"]),
]


def check_categories(datasets, categories=CATEGORIES):
    """Raise ValueError if any dataset is missing from `categories`."""
    known = {ds for _, _, _, members in categories for ds in members}
    missing = sorted(set(datasets) - known)
    if missing:
        raise ValueError(f"Datasets without a category in CATEGORIES: {', '.join(missing)}")


def _get_nested(d, path):
    parts = path.split(".")
    for i, key in enumerate(parts):
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
        if not isinstance(d, dict) and i < len(parts) - 1:
            # Scalar where sub-key expected: treat it as both total and per_subject
            if parts[i + 1] in ("total", "per_subject") and isinstance(d, (int, float)):
                return d
            return None
    return d


def _build_rows(datasets: list, column_groups: list) -> list:
    rows = []
    for ds in datasets:
        for group_name, group_color, fields in column_groups:
            for label, dotpath, unit in fields:
                value = _get_nested(ds, dotpath)
                rows.append({
                    "dataset": ds.get("short_name", ds.get("name", "?")),
                    "group": group_name,
                    "group_color": group_color,
                    "modality": label,
                    "dotpath": dotpath,
                    "unit": unit,
                    "value": value,
                })
    return rows




def load_cneuromod_datasets(cneuromod_dir: Path) -> list:
    """Load datasets from cneuromod.all dataset_info.yaml files.

    Each file's `stats` block is used as the dataset dict; the folder name
    becomes the `name` field.
    """
    datasets = []
    for info_file in sorted(Path(cneuromod_dir).glob("*/dataset_info.yaml")):
        with open(info_file) as f:
            data = yaml.safe_load(f)
        stats = data.get("stats", {})
        stats["name"] = info_file.parent.name
        datasets.append(stats)
    return datasets


def build_cneuromod_tidy_table(cneuromod_dir: Path, column_groups: list) -> pd.DataFrame:
    """Load cneuromod datasets and return a tidy long-format DataFrame."""
    return pd.DataFrame(_build_rows(load_cneuromod_datasets(cneuromod_dir), column_groups))


def build_cneuromod_subjects_table(cneuromod_dir: Path) -> pd.DataFrame:
    """Tidy table of per-dataset subject availability from cneuromod.all.

    Columns: dataset, subject, status, note. `status` is the value recorded in
    dataset_info.yaml (e.g. `available`, `partial`, `not_collected`); `note`
    carries the free-text qualifier when there is one.
    """
    rows = []
    for info_file in sorted(Path(cneuromod_dir).glob("*/dataset_info.yaml")):
        with open(info_file) as f:
            data = yaml.safe_load(f)
        for subject in data.get("subjects", []) or []:
            rows.append({
                "dataset": info_file.parent.name,
                "subject": subject.get("id", ""),
                "status": subject.get("status", ""),
                "note": subject.get("note", "") or "",
            })
    return pd.DataFrame(rows)


def validate_dataset_info(cneuromod_dir: Path, schema_file: Path) -> None:
    """Validate each dataset_info.yaml `stats` block against cneuromod.all's JSON schema.

    Raises SystemExit listing every file that fails validation.
    """
    import json
    import jsonschema

    with open(schema_file) as f:
        schema = json.load(f)

    errors = []
    for info_file in sorted(Path(cneuromod_dir).glob("*/dataset_info.yaml")):
        with open(info_file) as f:
            data = yaml.safe_load(f)
        stats = data.get("stats", {})
        stats.setdefault("name", info_file.parent.name)
        try:
            jsonschema.validate(stats, schema)
        except jsonschema.ValidationError as e:
            print(f"  ERR {info_file.parent.name}/dataset_info.yaml: {e.message}")
            errors.append(info_file.parent.name)
    if errors:
        raise SystemExit(f"dataset_info.yaml validation failed: {', '.join(errors)}")
