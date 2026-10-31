import subprocess

from analysis import freshness as fr

H = lambda c: {"head": c * 40, "annex": None}


def test_parse_ls_remote():
    text = f"{'a' * 40}\tHEAD\n{'b' * 40}\trefs/heads/git-annex\n"
    assert fr.parse_ls_remote(text) == {"head": "a" * 40, "annex": "b" * 40}
    assert fr.parse_ls_remote(f"{'a' * 40}\tHEAD\n")["annex"] is None


def test_no_state_all_stale():
    cur = {"floc": {"bids": H("a")}, "hcptrt": {"bids": H("b")}}
    stale = fr.stale_datasets(cur, {}, "x", None)
    assert set(stale) == {"floc", "hcptrt"}


def test_only_changed_dataset_stale():
    rec = {"floc": {"bids": H("a")}, "hcptrt": {"bids": H("b")}}
    cur = {"floc": {"bids": H("a")}, "hcptrt": {"bids": H("c")}}
    stale = fr.stale_datasets(cur, rec, "x", "x")
    assert list(stale) == ["hcptrt"] and "bids head" in stale["hcptrt"][0]


def test_code_change_marks_all():
    cur = {"floc": {"bids": H("a")}}
    assert "floc" in fr.stale_datasets(cur, cur, "new", "old")


def test_new_kind_and_annex_change():
    rec = {"floc": {"bids": H("a")}}
    cur = {"floc": {"bids": {"head": "a" * 40, "annex": "d" * 40}, "fmriprep": H("e")}}
    reasons = fr.stale_datasets(cur, rec, "x", "x")["floc"]
    assert any(r.startswith("bids annex") for r in reasons)
    assert any(r.startswith("fmriprep head") for r in reasons)


def test_state_roundtrip(tmp_path):
    fr.write_state(tmp_path, "c", {"floc": {"bids": H("a")}})
    st = fr.read_state(tmp_path)
    assert st["code_hash"] == "c" and st["datasets"]["floc"]["bids"] == H("a")
    assert fr.read_state(tmp_path / "none")["datasets"] == {}


def test_code_hash(tmp_path):
    for p in fr.CODE_PATHS:
        (tmp_path / p).parent.mkdir(exist_ok=True)
        if p in ("analysis", "dashboard"):
            (tmp_path / p).mkdir()
            (tmp_path / p / "f").write_text("1")
        else:
            (tmp_path / p).write_text("1")
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    run("init", "-q"); run("add", "."); run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
    h1 = fr.code_hash(tmp_path)
    (tmp_path / "analysis" / "f").write_text("2")
    run("add", "."); run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "y")
    assert fr.code_hash(tmp_path) != h1


def test_regressions():
    import pandas as pd
    cols = ["dataset", "subject", "asset", "n_judged", "n_on_s3unf"]
    before = pd.DataFrame([["floc", "sub-01", "bold", 10, 10], ["floc", "sub-02", "bold", 5, 5],
                           ["hcptrt", "sub-01", "bold", 3, 3]], columns=cols)
    after = pd.DataFrame([["floc", "sub-01", "bold", 10, 8], ["floc", "sub-02", "bold", 6, 5],
                          ["hcptrt", "sub-01", "bold", 0, 0]], columns=cols)
    assert fr.regressions(before, after, ["floc"]) == ["floc/bold n_on_s3unf: 15 -> 13"]
    assert fr.regressions(before, before, ["floc", "hcptrt"]) == []
    assert len(fr.regressions(before, after.iloc[:0], ["floc"])) == 2
