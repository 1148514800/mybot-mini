"""Integration tests in disposable repositories; run with uv run python -m scripts.test_phase_archives."""
import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.environ["COPYFILE_DISABLE"] = "1"
with tempfile.TemporaryDirectory(prefix="mybot-phase-tests-") as folder:
    base = Path(folder)
    repo = base / "repo"
    repo.mkdir()
    data = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=root)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(repo)
    for name in ("mybot", "scripts", "docs", "skills", "evals"):
        shutil.copytree(root / name, repo / name, dirs_exist_ok=True, copy_function=shutil.copyfile, ignore=shutil.ignore_patterns("__pycache__", "._*"))
    for name in ("pyproject.toml", "uv.lock", "config/config.example.json"):
        shutil.copyfile(root / name, repo / name)
    def run(args, ok=True):
        result = subprocess.run(args, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == ok, result.stdout
        print("PASS:", " ".join(args), "success" if ok else "refused", flush=True)
        return result
    run(["git", "init", "-q"])
    run(["git", "config", "user.name", "Archive Test"])
    run(["git", "config", "user.email", "archive-test@example.invalid"])
    run(["git", "add", "."])
    run(["git", "commit", "-qm", "feat: phase 01 observability archive"])
    run(["bash", "scripts/save_phase.sh", "../1", "bad"], False)
    (repo / "dirty.txt").write_text("uncommitted")
    run(["bash", "scripts/save_phase.sh", "1", "observability"], False)
    (repo / "dirty.txt").unlink()
    run(["bash", "scripts/save_phase.sh", "1", "observability"])
    run(["bash", "scripts/save_phase.sh", "1", "again"], False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo)
    run(["bash", "scripts/restore_phase.sh", "1"])
    assert head == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo)
    run(["bash", "scripts/restore_phase.sh", "1"], False)
    run(["git", "tag", "-d", "phase-01"])
    shutil.rmtree(base / "mybot-mini-learning" / "phase-01")
    run(["bash", "scripts/restore_phase.sh", "1"])
    run(["bash", "scripts/save_phase.sh", "1", "existing zip"], False)
    run(["bash", "scripts/restore_phase.sh", "2"], False)
    malicious = base / "bad.zip"
    with zipfile.ZipFile(base / "mybot-mini-snapshots" / "phase-01.zip") as src, zipfile.ZipFile(malicious, "w") as dst:
        for entry in src.infolist():
            dst.writestr(entry, src.read(entry))
        dst.writestr("../escape", "bad")
    run(["uv", "run", "--no-project", "python", "scripts/phase_zip.py", str(malicious), "phase-01", str(base / "bad-output")], False)
    assert not (base / "escape").exists()
    for name, payload in (("config/config.json", b'{"api_key":"secret"}'), (".venv/private.txt", b"cache"), (".mybot_state/session.json", b'{"version":1,"turns":[]}'), ("private-history.dat", b'{"version":1,"turns":[]}')):
        with zipfile.ZipFile(base / "mybot-mini-snapshots" / "phase-01.zip") as src, zipfile.ZipFile(malicious, "w") as dst:
            for entry in src.infolist():
                dst.writestr(entry, src.read(entry))
            dst.writestr(name, payload)
        run(["uv", "run", "--no-project", "python", "scripts/phase_zip.py", str(malicious), "phase-01", str(base / "bad-output")], False)
    malicious.write_bytes(b"not a zip")
    run(["uv", "run", "--no-project", "python", "scripts/phase_zip.py", str(malicious), "phase-01", str(base / "bad-output")], False)

print("Archive integration checks passed.")
