import json

file_path = "data/raw/kerala_roads.geojson"

with open(file_path, "r", encoding="utf-8") as f:
    roads = json.load(f)

features = roads["features"]

min_lon = float("inf")
max_lon = float("-inf")
min_lat = float("inf")
max_lat = float("-inf")


def process_coordinates(coords):
    global min_lon, max_lon, min_lat, max_lat

    if isinstance(coords[0], (int, float)):
        lon, lat = coords[:2]

        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)

    else:
        for item in coords:
            process_coordinates(item)


for feature in features:
    geometry = feature.get("geometry")

    if geometry and geometry.get("coordinates"):
        process_coordinates(geometry["coordinates"])


print("\n===== KERALA ROAD NETWORK EXTENT =====")
print(f"Minimum longitude: {min_lon}")
print(f"Maximum longitude: {max_lon}")
print(f"Minimum latitude : {min_lat}")
print(f"Maximum latitude : {max_lat}")

print("\nUse these values to determine DEM coverage.")