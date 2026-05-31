from pathlib import Path
import pandas as pd

SUBJECTS = [f"sub-{i:02d}" for i in range(1, 7)]


def count_sessions(source_dir: Path, out_file: Path) -> None:
    """Count BIDS sessions per subject per dataset and write a TSV."""
    records = []
    cneuromod_dir = source_dir / "cneuromod.all"

    for bids_dir in sorted(cneuromod_dir.glob("*/bids")):
        dataset = bids_dir.parent.name
        for subject in SUBJECTS:
            sub_dir = bids_dir / subject
            if not sub_dir.exists():
                n_sessions = 0
            else:
                sessions = list(sub_dir.glob("ses-*"))
                if sessions:
                    n_sessions = len(sessions)
                else:
                    # No session level: count as 1 if the subject folder has content
                    n_sessions = 1 if any(sub_dir.iterdir()) else 0
            records.append({"dataset": dataset, "subject": subject, "n_sessions": n_sessions})

    df = pd.DataFrame(records)
    df.to_csv(out_file, sep="\t", index=False)
    print(f"Session counts saved to {out_file}")
