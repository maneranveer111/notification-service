"""
One-time script: verify notification_test_db tables and seed the default workspace.
Run from backend/ directory with the venv activated.
"""
import psycopg2

conn = psycopg2.connect(
    dbname="notification_test_db",
    user="postgres",
    password="postgre123",
    host="localhost",
    port=5432,
)
cur = conn.cursor()

# List tables
cur.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema='public' ORDER BY table_name"
)
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# Seed default workspace if missing
cur.execute("SELECT count(*) FROM workspaces WHERE slug='default'")
count = cur.fetchone()[0]
if count == 0:
    cur.execute(
        "INSERT INTO workspaces (id, name, slug, webhook_token, plan, created_at) "
        "VALUES (gen_random_uuid(), 'Default', 'default', gen_random_uuid()::text, 'unlimited', now())"
    )
    conn.commit()
    print("Default workspace seeded.")
else:
    print(f"Default workspace already exists (count={count}).")

conn.close()
print("Done.")

