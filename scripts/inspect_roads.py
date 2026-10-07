import json
from collections import Counter

file_path = "data/kerala_roads.geojson"

with open(file_path, "r", encoding="utf-8") as f:
    roads = json.load(f)

features = roads["features"]

highway_counts = Counter()

for feature in features:
    highway = feature.get("properties", {}).get("highway")

    if highway:
        highway_counts[highway] += 1

print("\n===== KERALA ROUTESENSE ROAD NETWORK =====")
print(f"Total road/path features: {len(features):,}")

print("\n===== HIGHWAY TYPES =====")

for highway, count in highway_counts.most_common():
    percentage = (count / len(features)) * 100
    print(f"{highway:25} {count:>10,} ({percentage:5.2f}%)")