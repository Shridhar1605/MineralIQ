"""Backup drill (Stage 6): manifest + tarball + verify + restore. Stdlib only.

Covers the file-level state (data/, fixtures/, taxonomy/, baselines.json,
GATES.md, db/). Live PG dumps (pg_dump -Fc) slot in as data/pg.dump once the
cloud deploy exists — verify/restore already handle it as just another file.
Use:
  python3 scripts/backup.py --backup [--out data/backup.tgz]
  python3 scripts/backup.py --verify --in data/backup.tgz
  python3 scripts/backup.py --restore --in data/backup.tgz --dest /tmp/restore
"""
import argparse
import hashlib
import json
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
INCLUDE = ["data", "fixtures", "taxonomy", "db", "baselines.json", "GATES.md",
           "DATA_SOURCES.md"]


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def backup(out):
    out = pathlib.Path(out)
    manifest = {}
    skip = {out.resolve(), pathlib.Path(str(out) + ".manifest.json").resolve()}
    with tarfile.open(out, "w:gz") as t:
        for rel in INCLUDE:
            p = ROOT / rel
            if not p.exists():
                continue
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and f.resolve() not in skip:
                        manifest[str(f.relative_to(ROOT))] = _sha(f)
                        t.add(f, arcname=str(f.relative_to(ROOT)))
            else:
                manifest[rel] = _sha(p)
                t.add(p, arcname=rel)
    meta = {"files": manifest}
    with tarfile.open(out, "r:gz") as t:
        names = set(t.getnames())
    assert set(manifest) <= names, "tarball missing manifested files"
    (out.parent / (out.name + ".manifest.json")).write_text(json.dumps(meta, indent=2))
    print(f"backup ok: {len(manifest)} files -> {out}")
    return out


def verify(archive):
    tmp = pathlib.Path(str(archive) + ".verify")
    manifest = json.loads(pathlib.Path(str(archive) + ".manifest.json").read_text())
    with tarfile.open(archive, "r:gz") as t:
        t.extractall(tmp, filter="data")
    ok = all((tmp / rel).exists() and _sha(tmp / rel) == h
             for rel, h in manifest["files"].items())
    print("verify", "ok" if ok else "FAIL")
    return ok


def restore(archive, dest):
    dest = pathlib.Path(dest)
    with tarfile.open(archive, "r:gz") as t:
        t.extractall(dest, filter="data")
    print(f"restored -> {dest}")
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--in", dest="archive", default="data/backup.tgz")
    ap.add_argument("--out", default="data/backup.tgz")
    ap.add_argument("--dest", default="/tmp/mineraliq-restore")
    a = ap.parse_args()
    if a.backup:
        backup(ROOT / a.out)
    elif a.verify:
        raise SystemExit(0 if verify(ROOT / a.archive) else 1)
    elif a.restore:
        restore(ROOT / a.archive, a.dest)
    else:
        ap.error("need --backup, --verify or --restore")
