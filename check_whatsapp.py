import sqlite3
conn = sqlite3.connect('var/data/vasuki.db')
rows = conn.execute(
    "SELECT name, path FROM app_index WHERE path LIKE '%WhatsApp%' LIMIT 10"
).fetchall()
for r in rows:
    print(r)
conn.close()