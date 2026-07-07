import sys, json
d = json.load(sys.stdin)
print(f'Full name: {d["full_name"]}')
print(f'Default branch: {d["default_branch"]}')
print(f'Size: {d["size"]/1024:.1f} MB')
print(f'Language: {d["language"]}')
print(f'Pushed at: {d["pushed_at"]}')
print(f'Stars: {d["stargazers_count"]}, Forks: {d["forks_count"]}')
