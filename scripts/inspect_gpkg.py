import sqlite3

def inspect_gpkg(filepath):
    conn = sqlite3.connect(filepath)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in c.fetchall()]
    print(f"Tables in {filepath}:", tables)
    
    for table in tables:
        c.execute(f"PRAGMA table_info({table});")
        columns = [row[1] for row in c.fetchall()]
        print(f"Columns in {table}:", columns)
    conn.close()

inspect_gpkg('data/processed/kerala_road_elevation.gpkg')
