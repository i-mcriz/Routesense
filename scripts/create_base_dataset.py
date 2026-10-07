import json
import csv
import os

input_file = "data/raw/kerala_roads.geojson"
output_file = "data/processed/kerala_roads_base.csv"

os.makedirs("data/processed", exist_ok=True)

with open(input_file, "r", encoding="utf-8") as f:
    roads = json.load(f)

features = roads["features"]

rows = []

for index, feature in enumerate(features, start=1):

    properties = feature.get("properties", {})
    geometry = feature.get("geometry", {})

    rows.append({
        "road_id": index,
        "osm_id": properties.get("osm_id"),
        "name": properties.get("name"),
        "highway": properties.get("highway"),
        "geometry_type": geometry.get("type"),
        "geometry": json.dumps(geometry.get("coordinates"))
    })

fieldnames = [
    "road_id",
    "osm_id",
    "name",
    "highway",
    "geometry_type",
    "geometry"
]

with open(output_file, "w", newline="", encoding="utf-8") as f:

    writer = csv.DictWriter(f, fieldnames=fieldnames)

    writer.writeheader()
    writer.writerows(rows)

print("====================================")
print("RouteSense Base Dataset Created")
print("====================================")
print(f"Road features: {len(rows):,}")
print(f"Output: {output_file}")