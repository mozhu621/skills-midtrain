"""Download skill sources per configs/sources.yaml -> data/raw/."""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import requests
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import ROOT, DATA

RAW = DATA / "raw"
UA = {"User-Agent": "ssm-research/0.1"}


def clone(repo: str, dest_root: Path, kind: str, manifest: dict):
    owner_repo = repo.strip("/")
    dest = dest_root / owner_repo.replace("/", "__")
    if dest.exists():
        manifest[owner_repo] = {"status": "exists", "kind": kind, "path": str(dest)}
        return True
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", f"https://github.com/{owner_repo}.git", str(dest)],
            check=True, timeout=300, capture_output=True,
        )
        manifest[owner_repo] = {"status": "cloned", "kind": kind, "path": str(dest)}
        print(f"[clone] ok  {owner_repo}")
        return True
    except Exception as e:
        manifest[owner_repo] = {"status": f"failed: {e}", "kind": kind}
        print(f"[clone] FAIL {owner_repo}: {e}")
        return False


def github_discovery(cfg: dict) -> list[str]:
    repos: dict[str, int] = {}
    for q in cfg.get("queries", []):
        url = "https://api.github.com/search/repositories"
        try:
            r = requests.get(url, params={"q": q, "sort": "stars", "order": "desc",
                                          "per_page": cfg.get("max_repos_per_query", 25)},
                             headers=UA, timeout=30)
            if r.status_code == 403:
                print(f"[discover] rate limited on {q!r}, sleeping 70s")
                time.sleep(70)
                r = requests.get(url, params={"q": q, "per_page": cfg.get("max_repos_per_query", 25)},
                                 headers=UA, timeout=30)
            r.raise_for_status()
            for item in r.json().get("items", []):
                if item.get("fork"):
                    continue
                if item.get("stargazers_count", 0) >= cfg.get("min_stars", 3):
                    repos[item["full_name"]] = item["stargazers_count"]
            print(f"[discover] {q!r}: total {len(repos)} repos so far")
        except Exception as e:
            print(f"[discover] FAIL {q!r}: {e}")
        time.sleep(7)  # unauthenticated search: 10 req/min
    excluded = {x.lower() for x in cfg.get("exclude_repos", [])}
    return [r for r in sorted(repos, key=repos.get, reverse=True) if r.lower() not in excluded]


GH_LINK = re.compile(r"github\.com/([\w.-]+/[\w.-]+)")


def harvest_website(site: dict) -> list[str]:
    """Marketplace pages link out to GitHub repos; harvest those links."""
    base = site["base"].rstrip("/")
    pages, found = [base], set()
    try:
        sm = requests.get(base + "/sitemap.xml", headers=UA, timeout=20)
        if sm.ok and "<loc>" in sm.text:
            locs = re.findall(r"<loc>([^<]+)</loc>", sm.text)
            pages += locs[:400]
    except Exception as e:
        print(f"[site {site['name']}] sitemap failed: {e}")
    for url in pages:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if not r.ok:
                continue
            for m in GH_LINK.finditer(r.text):
                full = m.group(1)
                full = re.sub(r"\.git$", "", full)
                if full.count("/") == 1 and not full.endswith((".md", ".html")):
                    found.add(full)
        except Exception:
            pass
        time.sleep(0.3)
    print(f"[site {site['name']}] harvested {len(found)} github repos from {len(pages)} pages")
    return sorted(found)


def fetch_hf_dataset(entry: dict):
    out = RAW / "hf" / f"{entry['name']}.jsonl"
    if out.exists():
        print(f"[hf] {entry['name']} exists, skip")
        return
    try:
        from datasets import load_dataset
        ds = load_dataset(entry["dataset"], split="train")
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            for row in ds:
                f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        print(f"[hf] {entry['name']}: {len(ds)} rows -> {out}")
    except Exception as e:
        print(f"[hf] FAIL {entry['name']}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(ROOT / "configs/sources.yaml"))
    ap.add_argument("--skip-discovery", action="store_true")
    ap.add_argument("--skip-websites", action="store_true")
    ap.add_argument("--skip-hf", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.sources))
    manifest: dict = {}
    gh_root = RAW / "github"
    gh_root.mkdir(parents=True, exist_ok=True)

    for entry in cfg.get("github_repos", []):
        clone(entry["repo"], gh_root, entry.get("kind", "skill_md"), manifest)

    disc = cfg.get("github_discovery", {})
    if disc.get("enabled") and not args.skip_discovery:
        for repo in github_discovery(disc):
            clone(repo, gh_root, "skill_md", manifest)

    if not args.skip_websites:
        curated = {e["repo"].lower() for e in cfg.get("github_repos", [])}
        for site in cfg.get("websites", []):
            if not site.get("enabled"):
                continue
            for repo in harvest_website(site):
                if repo.lower() not in curated and repo not in manifest:
                    clone(repo, gh_root, "skill_md", manifest)

    for entry in cfg.get("git_tool_repos", []):
        if entry.get("enabled", True):
            clone(entry["repo"], RAW / "tools", entry.get("kind", "api_tool"), manifest)

    if not args.skip_hf:
        for entry in cfg.get("hf_datasets", []):
            if entry.get("enabled") and entry.get("dataset"):
                fetch_hf_dataset(entry)

    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))
    ok = sum(1 for v in manifest.values() if v["status"] in ("cloned", "exists"))
    print(f"\n[done] {ok}/{len(manifest)} repos available; manifest -> {RAW/'manifest.json'}")


if __name__ == "__main__":
    main()
