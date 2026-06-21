import sqlite3
conn = sqlite3.connect('test_migration_v19.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cur.fetchall()
print('Tables:', sorted([t[0] for t in tables]))

cur.execute('PRAGMA table_info(review_tasks)')
cols = cur.fetchall()
print('\nreview_tasks columns:')
for c in cols:
    print(f'  {c[1]} ({c[2]})')

cur.execute('PRAGMA table_info(crisis_events)')
cols = cur.fetchall()
print('\ncrisis_events columns:')
for c in cols:
    print(f'  {c[1]} ({c[2]})')

cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%crisis%'")
idxs = cur.fetchall()
print('\ncrisis_events indexes:', [i[0] for i in idxs])

conn.close()
