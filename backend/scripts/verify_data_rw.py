import sqlite3

conn = sqlite3.connect('test_migration_v19.db')
cur = conn.cursor()

cur.execute("INSERT INTO review_tasks (user_id, risk_level, risk_score, crisis_override, status, priority) VALUES (1, 3, 85.5, 0, 'pending', 'crisis_review')")
conn.commit()
cur.execute('SELECT COUNT(*) FROM review_tasks')
print('review_tasks rows:', cur.fetchone()[0])

cur.execute("INSERT INTO crisis_events (user_id, trigger_source, status) VALUES (1, 'text', 'detected')")
conn.commit()
cur.execute('SELECT COUNT(*) FROM crisis_events')
print('crisis_events rows:', cur.fetchone()[0])

conn.close()
print('Data read/write: PASS')
