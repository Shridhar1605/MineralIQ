"""Nightly job (Stage 6): harvest check + evaluate + graph dump + backup.

Idempotent and unattended-safe: exits nonzero on any step failure, appends a
timestamped line to nightly.log. Schedule: `0 2 * * * /path/to/venv/bin/python
/path/to/mineraliq/scripts/nightly.py` (cron) or the GitHub Actions schedule
in .github/workflows/nightly.yml. Live PG backup (pg_dump) plugs in where
marked once the cloud deploy exists — file-level backup below covers data/.
Use: python3 scripts/nightly.py [--data-dir data]
"""
import argparse
import datetime
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(cmd, log):
    log.append(f"$ {' '.join(cmd)}")
    p = subprocess.run(cmd, capture_output=True, text=True)
    log.append(p.stdout.strip())
    if p.returncode != 0:
        log.append("STDERR: " + p.stderr.strip()[-2000:])
        raise RuntimeError(f"nightly step failed: {cmd[1]}")
    return p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args()
    data = ROOT / args.data_dir
    data.mkdir(parents=True, exist_ok=True)
    log = [f"nightly {datetime.datetime.now().isoformat(timespec='seconds')}"]
    try:
        run([sys.executable, "scripts/harvest.py", "--check"], log)
        run([sys.executable, "scripts/evaluate.py", "--out",
             str(data / "metrics_s3.json")], log)
        run([sys.executable, "scripts/dump_graph.py", "--out",
             str(data / "graph.json")], log)
        # TODO(live-deploy): pg_dump -Fc mineraliq > data/pg.dump (needs cloud DB)
        run([sys.executable, "scripts/backup.py", "--backup",
             "--out", str(data / "backup.tgz")], log)
        log.append("NIGHTLY OK")
        rc = 0
    except RuntimeError as e:
        log.append(f"NIGHTLY FAIL: {e}")
        rc = 1
    (data / "nightly.log").write_text("\n".join(log) + "\n")
    print("\n".join(log[-3:]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
