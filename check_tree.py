import sys, json
d = json.loads(sys.stdin.read())
if d.get('truncated'):
    print('WARNING: tree truncated')
leaves = [i for i in d.get('tree', []) if i['type'] == 'blob']
print(f'Total files: {len(leaves)}')
SENSITIVE = ['毕业论文', '本科毕业论文', '答辩', '论文_', 'AI全流程', 'catboost_info', 'benchmark-results', 'build_report', 'coverage.json', '.coverage']
problems = []
for l in leaves:
    for k in SENSITIVE:
        if k in l['path']:
            problems.append((k, l['path'], l.get('size', 0)))
            break
print(f'Sensitive files: {len(problems)}')
for k, p, s in problems[:30]:
    print(f'  [{k}] {s/1024:.1f} KB  {p}')
leaves.sort(key=lambda x: x.get('size', 0), reverse=True)
print('\nTop 5 largest:')
for l in leaves[:5]:
    print(f'  {l.get("size", 0)/1024/1024:.2f} MB  {l["path"]}')
