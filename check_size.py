"""Check what's taking up space in the repo."""
import os
ROOT = r"e:\code\bysj"
sizes = []
for dp, dn, fn in os.walk(ROOT):
    if any(skip in dp for skip in ['node_modules', '__pycache__', '.venv', '.git', 'models', 'datasets', '__backup__']):
        continue
    for f in fn:
        p = os.path.join(dp, f)
        try:
            sz = os.path.getsize(p)
            if sz > 100*1024:  # > 100KB
                sizes.append((sz, os.path.relpath(p, ROOT)))
        except OSError:
            pass

sizes.sort(reverse=True)
total = sum(s for s, _ in sizes)
print(f"Total (files >100KB, excluding ignored): {total/1024/1024:.1f} MB across {len(sizes)} files\n")
for sz, p in sizes[:30]:
    print(f"  {sz/1024/1024:>8.2f} MB  {p}")
