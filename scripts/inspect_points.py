import sqlite3
conn = sqlite3.connect('data/processed/kerala_road_points.gpkg')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in c.fetchall()]
print('Tables in kerala_road_points:', tables)
c.execute("PRAGMA table_info(kerala_road_points);")
columns = [row[1] for row in c.fetchall()]
print('Columns in kerala_road_points:', columns)
c.execute("SELECT SAMPLE_1 FROM kerala_road_points LIMIT 1;")
print('SAMPLE_1 in points:', c.fetchone())
conn.close()
