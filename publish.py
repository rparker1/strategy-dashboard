"""Publish the whole project (code + state + data + PWA) to GitHub.

The repo root is the trading directory; GitHub Pages serves /docs.
secrets.json is .gitignored — it never leaves this machine.

Requires in secrets.json: github_token, github_user, github_repo.
First run: creates the repo via REST API and enables Pages.

    python publish.py
"""
import json
import os
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(HERE, "secrets.json")))
TOKEN, USER = S["github_token"], S["github_user"]
REPO = S.get("github_repo", "strategy-dashboard")
API = "https://api.github.com"


def api(path, method="GET", payload=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(payload).encode() if payload else None)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "strategy-dashboard")
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def sh(*cmd):
    return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)


def ensure_repo():
    code, _ = api(f"/repos/{USER}/{REPO}")
    if code == 404:
        code, j = api("/user/repos", "POST", {
            "name": REPO,
            "description": "Paper-trading strategy test (auto-published; simulated money)",
            "private": False, "auto_init": False})
        if code != 201:
            raise RuntimeError(f"repo create failed: {code} {j}")
        print(f"created repo {USER}/{REPO}")


def ensure_pages():
    code, _ = api(f"/repos/{USER}/{REPO}/pages")
    if code == 404:
        code, j = api(f"/repos/{USER}/{REPO}/pages", "POST",
                      {"source": {"branch": "main", "path": "/docs"}})
        print(f"pages enable -> {code}")


def push():
    if not os.path.isdir(os.path.join(HERE, ".git")):
        sh("git", "init", "-b", "main")
        sh("git", "config", "user.email", "bot@strategy-test.local")
        sh("git", "config", "user.name", "Strategy Test Bot")
    remote = f"https://x-access-token:{TOKEN}@github.com/{USER}/{REPO}.git"
    sh("git", "remote", "remove", "origin")
    sh("git", "remote", "add", "origin", remote)
    sh("git", "add", "-A")
    r = sh("git", "commit", "-m", "check-in update")
    if "nothing to commit" in r.stdout + r.stderr:
        print("no changes to commit")
    r = sh("git", "push", "-u", "origin", "main")
    if r.returncode != 0:
        # remote may have history this container lacks (fresh clone divergence)
        sh("git", "fetch", "origin")
        r2 = sh("git", "push", "-u", "origin", "main", "--force-with-lease")
        if r2.returncode != 0:
            raise RuntimeError(f"push failed: {r.stderr[-300:]} / {r2.stderr[-300:]}")
    print(f"pushed -> https://github.com/{USER}/{REPO} ; site https://{USER}.github.io/{REPO}/")


if __name__ == "__main__":
    push()  # repo exists; Pages is enabled manually once (proxy blocks those APIs)
