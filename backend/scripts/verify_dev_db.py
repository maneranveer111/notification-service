"""
Verify notification_db (dev database) is unmodified after tests ran.
Counts rows in key tables — does NOT print passwords or hashes.
"""
import psycopg2

conn = psycopg2.connect(
    dbname="notification_db",
    user="postgres",
    password="postgre123",
    host="localhost",
    port=5432,
)
cur = conn.cursor()

tables = ["users", "workspaces", "memberships", "invitations"]
for t in tables:
    cur.execute(f"SELECT count(*) FROM {t}")
    count = cur.fetchone()[0]
    print(f"  {t}: {count} rows")

# Confirm admin account exists (email only, no hash)
cur.execute(
    "SELECT email, is_active, email_verified_at IS NOT NULL as verified "
    "FROM users WHERE role = 'admin' LIMIT 1"
)
row = cur.fetchone()
if row:
    print(f"\nAdmin account found: email={row[0]}, is_active={row[1]}, verified={row[2]}")
else:
    print("\nNo admin account found in notification_db — may need to run first-time setup.")

conn.close()

