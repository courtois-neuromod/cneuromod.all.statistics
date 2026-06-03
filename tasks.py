from pathlib import Path
from invoke import task


@task
def fetch(c):
    """Init cneuromod.all submodule and each dataset's bids sub-submodule."""
    cneuromod_all_dir = Path(c.config.get("cneuromod_all_dir"))
    repo_root = Path(".").resolve()

    is_external = not cneuromod_all_dir.resolve().is_relative_to(repo_root)

    if not is_external:
        print("Updating cneuromod.all submodule...")
        c.run(f"git submodule update --init {cneuromod_all_dir}")
    else:
        print(f"Using external cneuromod.all at {cneuromod_all_dir}, skipping top-level submodule init.")

    for bids_dir in sorted(cneuromod_all_dir.glob("*/bids")):
        rel = bids_dir.relative_to(cneuromod_all_dir)
        dataset = bids_dir.parent.name
        print(f"Initializing {dataset}/bids...")
        c.run(f"git -C {cneuromod_all_dir} submodule update --init {rel}")


@task
def run_statistics(c):
    """Count sessions per subject per dataset; save to output_data/session_counts.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import count_sessions

    cneuromod_all_dir = Path(c.config.get("cneuromod_all_dir"))
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

    cneuromod_all_dir = Path(c.config.get("cneuromod_all_dir"))
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

    cneuromod_all_dir = Path(c.config.get("cneuromod_all_dir"))
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "fmri_stats_per_subject.tsv"

    if out_file.exists():
        print(f"Skipping run-fmri-per-subject-stats (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    compute_fmri_stats_per_subject(cneuromod_all_dir, out_file)


@task
def run_notebooks(c):
    """Execute notebooks and save figures to output_data/."""
    from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])


@task(pre=[fetch, run_statistics, run_fmri_stats, run_fmri_per_subject_stats, run_notebooks])
def run(c):
    """Full pipeline."""
    print("Pipeline complete.")


@task
def run_smoke(c):
    """Smoke test: minimal end-to-end pass."""
    fetch(c)
    run_statistics(c)
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
def clean_figures(c):
    """Remove generated figures."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "*.png")


@task(pre=[clean_statistics, clean_fmri_stats, clean_fmri_per_subject_stats, clean_figures])
def clean(c):
    """Remove all computed outputs."""
    pass


@task
def clean_source(c):
    """Deinitialize the cneuromod.all submodule and all bids sub-submodules."""
    cneuromod_all_dir = Path(c.config.get("cneuromod_all_dir"))
    c.run(f"git submodule deinit -f {cneuromod_all_dir}")
