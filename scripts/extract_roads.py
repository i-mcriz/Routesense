import geopandas as gpd

pbf_file = "data/kerala-latest.osm.pbf"

roads = gpd.read_file(
    pbf_file,
    layer="lines"
)

roads = roads[
    roads["highway"].notna()
]

print(roads.head())
print("Number of road features:", len(roads))

roads.to_file(
    "data/kerala_roads.geojson",
    driver="GeoJSON"
)

print("Done! Kerala roads saved.")