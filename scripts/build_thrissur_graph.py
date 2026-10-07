import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString
import pickle
import math
from pathlib import Path

# Find the Routesense project folder
BASE_DIR = Path(__file__).resolve().parent.parent

ROADS_FILE = BASE_DIR / "data" / "thrissur_roads.geojson"
GRAPH_FILE = BASE_DIR / "data" / "thrissur_routing_graph.pkl"

print("Loading:", ROADS_FILE)

if not ROADS_FILE.exists():
    print("ERROR: Thrissur road file was not found!")
    print("Expected location:")
    print(ROADS_FILE)
    exit()

roads = gpd.read_file(ROADS_FILE)

print("Thrissur roads loaded.")
print("Total road segments:", len(roads))


# Roads suitable for vehicle evacuation
allowed_roads = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "unclassified",
    "living_street",
    "service"
]

roads = roads[
    roads["highway"].isin(allowed_roads)
].copy()

print("Usable road segments:", len(roads))


# Create graph
G = nx.Graph()


def distance_meters(a, b):

    lon1, lat1 = a
    lon2, lat2 = b

    lat = math.radians((lat1 + lat2) / 2)

    x = math.radians(lon2 - lon1) * math.cos(lat)
    y = math.radians(lat2 - lat1)

    earth_radius = 6371000

    return earth_radius * math.sqrt(x * x + y * y)


print("Building routing graph...")


for _, road in roads.iterrows():

    geometry = road.geometry

    if not isinstance(geometry, LineString):
        continue

    coords = list(geometry.coords)

    # Connect every point in the road geometry
    for i in range(len(coords) - 1):

        start = coords[i]
        end = coords[i + 1]

        distance = distance_meters(start, end)

        G.add_edge(
            start,
            end,
            weight=distance,
            highway=road["highway"],
            name=road["name"]
        )


print()
print("========== GRAPH COMPLETE ==========")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())


# Save graph
with open(GRAPH_FILE, "wb") as f:
    pickle.dump(
        G,
        f,
        protocol=pickle.HIGHEST_PROTOCOL
    )

print()
print("Routing graph saved successfully!")
print("Saved to:")
print(GRAPH_FILE)