"""Bundle the whole project into one JSON file for off-container backup
(Google Drive / git). Everything needed to resurrect the test on a blank
container: code, config, runbook, market data, state, journal, secrets.

    python make_backup.py            # writes /tmp/strategy-test-backup.json
    python make_backup.py restore /path/to/bundle.json   # rebuilds project
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INCLUDE = [
    "RUNBOOK.md", "config.json",  # secrets.json deliberately EXCLUDED from backups
    "indicators.py", "datastore.py", "strategies.py", "engine.py",
    "dashboard.py", "publish.py", "make_backup.py", "test_offline.py",
    "docs/manifest.webmanifest", "docs/sw.js",
]
INCLUDE_DIRS = [("data", ".csv"), ("data", ".json"),
                ("state", ".json"), ("state", ".jsonl"), ("state", ".md")]


def collect():
    files = {}
    for rel in INCLUDE:
        p = os.path.join(HERE, rel)
        if os.path.exists(p):
            files[rel] = open(p).read()
    for d, ext in INCLUDE_DIRS:
        dp = os.path.join(HERE, d)
        if os.path.isdir(dp):
            for fn in os.listdir(dp):
                if fn.endswith(ext):
                    files[f"{d}/{fn}"] = open(os.path.join(dp, fn)).read()
    return files


def backup(out="/tmp/strategy-test-backup.json"):
    files = collect()
    bundle = {"_project": "strategy-test", "_root": "/home/claude/work/trading",
              "files": files}
    json.dump(bundle, open(out, "w"))
    print(f"{out}: {len(files)} files, {os.path.getsize(out)/1024:.0f} KB")
    return out


def restore(src):
    bundle = json.load(open(src))
    root = bundle["_root"]
    for rel, content in bundle["files"].items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
    print(f"restored {len(bundle['files'])} files to {root}")
    print("NOTE: regenerate icons/dashboard with dashboard.build; then resume RUNBOOK.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore(sys.argv[2])
    else:
        backup()
