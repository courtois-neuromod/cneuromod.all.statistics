from pathlib import Path
from invoke import task


def _cneuromod_dir(c) -> Path:
    """Where the cneuromod.all superdataset is made available under source_data/."""
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink "
              "instead of cloning (defaults to the `source:` key in "
              "invoke.yaml, i.e. ../cneuromod.all).",
})
def fetch_cneuromod(c, source=None):
    """Make the cneuromod.all superdataset available under source_data/ (symlink or clone, tree only)."""
    from airoh.datalad import install_dataset
    install_dataset(c, "cneuromod_all", source=source)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `bids/` subfolder).",
    "strict": "Raise if a bids subdataset fails to install.",
})
def fetch_bids(c, dataset=None, strict=False):
    """Install each dataset's `bids/` subdataset (tree only, no annexed content)."""
    from airoh.datalad import install_subdataset

    root = _cneuromod_dir(c)
    if not root.is_dir():
        print(f"⚠️  {root} not found — run `invoke fetch-cneuromod` first.")
        return

    names = {n.strip() for n in dataset.split(",")} if dataset else None
    for bids_dir in sorted(root.glob("*/bids")):
        name = bids_dir.parent.name
        if names is not None and name not in names:
            continue
        print(f"Installing {name}/bids...")
        install_subdataset(f"{name}/bids", root, strict=strict)


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink instead of cloning.",
    "dataset": "Comma-separated dataset names to restrict the bids fetch to.",
    "strict": "Raise if a bids subdataset fails to install.",
})
def fetch(c, source=None, dataset=None, strict=False):
    """Retrieve all source data: the cneuromod.all superdataset and every dataset's bids tree."""
    from airoh.provenance import record_sources

    fetch_cneuromod(c, source=source)
    fetch_bids(c, dataset=dataset, strict=strict)
    record_sources(c)
    print("✅ fetch complete.")


@task
def run_statistics(c):
    """Count sessions per subject per dataset; save to output_data/session_counts.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import count_sessions

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "session_counts.tsv"

    if out_file.exists():
        print(f"Skipping run-statistics (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    count_sessions(cneuromod_all_dir, out_file)


@task
def run_fmri_stats(c):
    """Compute fMRI run stats per dataset; save to output_data/fmri_stats.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import compute_fmri_stats

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "fmri_stats.tsv"

    if out_file.exists():
        print(f"Skipping run-fmri-stats (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    compute_fmri_stats(cneuromod_all_dir, out_file)


@task
def run_fmri_per_subject_stats(c):
    """Compute per-subject fMRI run stats per dataset; save to output_data/fmri_stats_per_subject.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import compute_fmri_stats_per_subject

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "fmri_stats_per_subject.tsv"

    if out_file.exists():
        print(f"Skipping run-fmri-per-subject-stats (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    compute_fmri_stats_per_subject(cneuromod_all_dir, out_file)


@task
def run_cneuromod_tables(c):
    """Build tidy per-dataset comparison tables from cneuromod.all dataset_info.yaml files."""
    from airoh.utils import ensure_dir_exist
    from analysis.dataset_info import (
        build_cneuromod_subjects_table,
        build_cneuromod_tidy_table,
        validate_dataset_info,
        COLUMN_GROUPS_PER_SUBJECT,
        COLUMN_GROUPS_TOTAL,
    )

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_files = {
        "per_subject": output_dir / "cneuromod_tidy_per_subject.csv",
        "total": output_dir / "cneuromod_tidy_total.csv",
        "subjects": output_dir / "cneuromod_subjects.csv",
    }

    if all(f.exists() for f in out_files.values()):
        print(f"Skipping run-cneuromod-tables (outputs exist in {output_dir})")
        return

    ensure_dir_exist(c, "output_data_dir")
    validate_dataset_info(cneuromod_all_dir, cneuromod_all_dir / "docs" / "schema.json")

    for scope, groups in [
        ("per_subject", COLUMN_GROUPS_PER_SUBJECT),
        ("total", COLUMN_GROUPS_TOTAL),
    ]:
        df = build_cneuromod_tidy_table(cneuromod_all_dir, groups)
        df.to_csv(out_files[scope], index=False)
        print(f"Saved {len(df)} rows to {out_files[scope].name}")

    df = build_cneuromod_subjects_table(cneuromod_all_dir)
    df.to_csv(out_files["subjects"], index=False)
    print(f"Saved {len(df)} rows to {out_files['subjects'].name}")


@task
def run_notebooks(c):
    """Execute notebooks and save figures to output_data/."""
    from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])


@task(help={"force": "Run `clean` first, forcing every step to recompute."})
def run(c, force=False):
    """Full pipeline."""
    from airoh.provenance import record_run

    if force:
        clean(c)

    run_statistics(c)
    run_fmri_stats(c)
    run_fmri_per_subject_stats(c)
    run_cneuromod_tables(c)
    run_notebooks(c)

    record_run(c, tasks="run-statistics,run-fmri-stats,run-fmri-per-subject-stats,"
                        "run-cneuromod-tables,run-notebooks")
    print("Pipeline complete.")


@task(help={
    "skip": "Comma-separated check names to skip (also settable under "
            "`verify: skip_checks:` in invoke.yaml).",
    "strict": "Treat warnings as failures.",
})
def verify(c, skip=None, strict=False):
    """Check that code, config, data and docs still agree. Not part of `run`."""
    from airoh.verify import verify as airoh_verify
    airoh_verify(c, skip=skip, strict=strict)


@task
def run_smoke(c):
    """Smoke test: minimal end-to-end pass."""
    fetch_cneuromod(c)
    fetch_bids(c, strict=True)
    run_statistics(c)
    run_fmri_per_subject_stats(c)
    run_cneuromod_tables(c)
    run_notebooks(c)


@task
def clean_fmri_stats(c):
    """Remove fmri_stats.tsv and its JSON sidecar."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "fmri_stats.tsv")
    clean_folder(c, "output_data_dir", "fmri_stats.json")


@task
def clean_fmri_per_subject_stats(c):
    """Remove fmri_stats_per_subject.tsv."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "fmri_stats_per_subject.tsv")


@task
def clean_statistics(c):
    """Remove session_counts.tsv."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "session_counts.tsv")


@task
def clean_cneuromod_tables(c):
    """Remove the cneuromod_*.csv comparison tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "cneuromod_*.csv")


@task
def clean_figures(c):
    """Remove generated figures."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "*.png")


@task
def clean(c):
    """Remove all computed outputs."""
    clean_statistics(c)
    clean_fmri_stats(c)
    clean_fmri_per_subject_stats(c)
    clean_cneuromod_tables(c)
    clean_figures(c)


@task
def clean_cneuromod(c):
    """Remove the cneuromod.all checkout (unlink the symlink, or delete a clone)."""
    root = _cneuromod_dir(c)
    if root.is_symlink():
        root.unlink()
        print(f"🧹 Unlinked {root}")
    elif root.is_dir():
        import shutil
        shutil.rmtree(root)
        print(f"🧹 Removed {root}")
    else:
        print(f"🫧 {root} does not exist — nothing to clean")


@task
def clean_source(c):
    """Remove the cneuromod.all checkout."""
    clean_cneuromod(c)
