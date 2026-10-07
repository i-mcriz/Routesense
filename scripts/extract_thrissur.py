import geopandas as gpd

# Load Kerala roads
roads = gpd.read_file("data/kerala_roads.geojson")

# Approximate Thrissur area
min_lon = 76.17
max_lon = 76.26
min_lat = 10.48
max_lat = 10.58

# Extract roads inside the bounding box
thrissur_roads = roads.cx[
    min_lon:max_lon,
    min_lat:max_lat
].copy()

print("Thrissur road segments:", len(thrissur_roads))

# Save
thrissur_roads.to_file(
    "data/thrissur_roads.geojson",
    driver="GeoJSON"
)

print("Saved successfully!")