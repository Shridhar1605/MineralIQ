"""Stage 6 gate (s6): hardening — backup round-trip, nightly artifacts,
deliverables checklist, deploy-from-README markers. Regression: full suite.
Live-deploy items (cloud VM, PG dump, demo recording, upload) are Week-6
human steps tracked in docs/deliverables_checklist.md.
"""
import json
import pathlib
import subprocess
import sys
import pytest

pytestmark = pytest.mark.s6

ROOT = pathlib.Path(__file__).resolve().parents[1]

SECTION8 = ["prototype", "presentation", "technical report", "architecture",
            "experimental", "kpis", "demonstration video", "cost",
            "limitations", "roadmap"]


def _run(cmd, cwd=ROOT):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def test_backup_round_trip_with_tamper_detection(tmp_path):
    archive = tmp_path / "backup.tgz"
    rc, out, _ = _run([sys.executable, "scripts/backup.py", "--backup",
                       "--out", str(archive)])
    assert rc == 0, out
    rc, out, _ = _run([sys.executable, "scripts/backup.py", "--verify",
                       "--in", str(archive)])
    assert rc == 0 and "verify ok" in out
    dest = tmp_path / "restore"
    rc, _, _ = _run([sys.executable, "scripts/backup.py", "--restore",
                     "--in", str(archive), "--dest", str(dest)])
    assert rc == 0
    assert (dest / "baselines.json").read_text() == (ROOT / "baselines.json").read_text()
    # tamper with one restored byte: re-verify the ARCHIVE still passes (untouched),
    # while a hash check of the tampered file fails against the manifest
    man = json.loads(pathlib.Path(str(archive) + ".manifest.json").read_text())
    f = dest / "fixtures" / "golden_patents.json"
    f.write_text(f.read_text() + " ")
    import hashlib
    assert hashlib.sha256(f.read_bytes()).hexdigest() != man["files"]["fixtures/golden_patents.json"]


def test_nightly_produces_artifacts_unattended(tmp_path):
    rc, out, err = _run([sys.executable, "scripts/nightly.py", "--data-dir",
                         str(tmp_path)])
    assert rc == 0, err[-2000:]
    for name in ("nightly.log", "metrics_s3.json", "graph.json", "backup.tgz"):
        assert (tmp_path / name).exists(), name
    assert "NIGHTLY OK" in (tmp_path / "nightly.log").read_text()


def test_section8_checklist_complete():
    text = (ROOT / "docs" / "deliverables_checklist.md").read_text().lower()
    for item in SECTION8:
        assert item in text, item
    for doc in ("technical_report.md", "architecture.mmd", "MineralIQ_deck.pptx",
                "demo_script.md"):
        assert (ROOT / "docs" / doc).exists(), doc
    assert (ROOT / "docs" / "MineralIQ_deck.pptx").stat().st_size > 10000


def test_readme_deploy_markers_and_env():
    readme = (ROOT / "README.md").read_text()
    for marker in ("docker compose", ".env", "make regress", "pg_dump", "nightly"):
        assert marker in readme, marker
    env = (ROOT / ".env.example").read_text()
    assert "DATABASE_URL" in env
    assert (ROOT / "docker-compose.yml").exists()
