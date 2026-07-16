import psycopg
import sys

sys.stdout.reconfigure(encoding='utf-8')

DATABASE_URL = "postgresql://amad:development-only-password@localhost:55432/amad"

try:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = cur.fetchall()
            for t in tables:
                table_name = t[0]
                # exclude checkpoint tables to save output space
                if table_name.startswith("checkpoint"):
                    continue
                print(f"\nTable: {table_name}")
                cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description]
                print("Columns:", cols)
                for r in rows:
                    print(r)
except Exception as e:
    print("Error:", e)
