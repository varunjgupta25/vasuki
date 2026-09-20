import sqlite3
conn = sqlite3.connect('var/data/vasuki.db')
# Show first 20 store apps to see what names got indexed
rows = conn.execute(
    "SELECT name, path FROM app_index WHERE source='store' LIMIT 20"
).fetchall()
for r in rows:
    print(r)
print('---')
# Total count
count = conn.execute("SELECT COUNT(*) FROM app_index WHERE source='store'").fetchone()
print('Total store apps:', count[0])
conn.close()