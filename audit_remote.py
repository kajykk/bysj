"""Comprehensive check: recursively scan GitHub repo tree for any sensitive content."""
import urllib.request
import json
import sys

TOKEN = None  # public repo, no auth needed
OWNER = "kajykk"
REPO = "bysj"
BRANCH = "main"

# Files/paths that should NOT appear
SENSITIVE_KEYWORDS = [
    "毕业论文", "本科毕业论文", "答辩", "论文_", "AI全流程",
    "catboost_info", "benchmark-results", "build_report",
    "coverage.json", ".coverage",
]

# Use the git trees API with recursion
url = f"https://api.github.com/repos/{OWNER}/{REPO}/git/trees/{BRANCH}?recursive=1"
print(f"Fetching: {url}\n")
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read())

if data.get("truncated"):
    print("WARNING: tree was truncated, results may be incomplete")

leaves = [i for i in data.get("tree", []) if i["type"] == "blob"]
print(f"Total files in tree: {len(leaves)}")

# Find any sensitive files
problems = []
for leaf in leaves:
    path = leaf["path"]
    for kw in SENSITIVE_KEYWORDS:
        if kw in path:
            problems.append((kw, path, leaf.get("size", 0)))
            break

if problems:
    print(f"\nSENSITIVE FILES FOUND: {len(problems)}\n")
    for kw, path, sz in problems:
        print(f"  [{kw:15s}] {sz/1024:>8.1f} KB  {path}")
else:
    print("\nNo sensitive files found in repo tree!")

# Top 10 largest files
leaves.sort(key=lambda x: x.get("size", 0), reverse=True)
print(f"\nTop 10 largest files:")
for leaf in leaves[:10]:
    print(f"  {leaf.get('size', 0)/1024:>10.1f} KB  {leaf['path']}")
