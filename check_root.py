import sys, json
d = json.load(sys.stdin)
print(f'Total items at root: {len(d)}')
sensitive = ['毕业论文', '本科毕业论文', '答辩', '论文', 'catboost_info', 'benchmark', 'coverage.json', 'build_report', '.coverage', 'AI全流程']
for i in sorted(d, key=lambda x: x['name']):
    flag = ' [SENSITIVE!]' if any(s in i['name'] for s in sensitive) else ''
    print(f'  {i["type"]:5s} {i["size"]:>10} {i["name"]}{flag}')
