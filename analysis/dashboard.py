"""Render the release dashboard: one HTML page plus a small JSON of gaps per dataset.

The page embeds only `completeness_summary.tsv`. When a viewer drills into a
dataset it fetches `release_dashboard_data/<dataset>.json`, which lists just the
(run, asset) pairs that are missing or absent from some release remote — so
the page stays light however many runs there are.
"""
from pathlib import Path
import json

import pandas as pd

NA = "NA"
GAP_COLUMNS = ["subject", "session", "run_key", "task", "duration_h", "asset", "present", "detail", "remotes"]


def gap_records(table: pd.DataFrame, labels: list[str]) -> list[list]:
    """Rows of one run table that are absent, or present but missing from a release remote.

    `remotes` is the list of labels *holding* the asset; compact arrays keep the JSON small.
    """
    judged = table[table["present"].astype(str) != NA]
    recs = []
    for _, r in judged.iterrows():
        present = str(r["present"]) == "True"
        held = [l for l in labels if str(r[l]) == "True"]
        if present and len(held) == len(labels):
            continue
        recs.append([
            r["run_key"].split("_")[0], "" if pd.isna(r["session"]) else str(r["session"]),
            r["run_key"], r["task"], None if pd.isna(r["duration_h"]) else float(r["duration_h"]),
            r["asset"], int(present), "" if pd.isna(r["detail"]) else str(r["detail"]), held,
        ])
    return recs


def render_dashboard(output_dir: Path, template: Path, labels: list[str], out_html: Path) -> None:
    summary = pd.read_csv(output_dir / "completeness_summary.tsv", sep="\t")
    data_dir = out_html.with_name(out_html.stem + "_data")
    data_dir.mkdir(parents=True, exist_ok=True)

    for dataset_dir in sorted((output_dir / "run_tables").glob("*/")):
        if not dataset_dir.is_dir():
            continue
        frames = [pd.read_csv(p, sep="\t", keep_default_na=False, dtype=str)
                  for p in sorted(dataset_dir.glob("*_runs.tsv"))]
        if not frames:
            continue
        table = pd.concat(frames, ignore_index=True)
        table["duration_h"] = pd.to_numeric(table["duration_h"], errors="coerce")
        payload = {"columns": GAP_COLUMNS, "rows": gap_records(table, labels)}
        with open(data_dir / f"{dataset_dir.name}.json", "w") as f:
            json.dump(payload, f, separators=(",", ":"))

    state = {
        "labels": labels,
        "summary": json.loads(summary.to_json(orient="records")),
        "dataDir": data_dir.name,
    }
    html = template.read_text().replace("__DASHBOARD_STATE__", json.dumps(state, separators=(",", ":")))
    out_html.write_text(html)
