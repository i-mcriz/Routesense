import pickle
import networkx as nx
import geopandas as gpd
from shapely.geometry import LineString
from pathlib import Path

# Project folder
BASE_DIR = Path(__file__).resolve().parent.parent

GRAPH_FILE = BASE_DIR / "data" / "thrissur_routing_graph.pkl"
ROUTE_FILE = BASE_DIR / "data" / "test_route.geojson"

# ------------------------------------------------
# Load graph
# ------------------------------------------------

print("Loading routing graph...")

with open(GRAPH_FILE, "rb") as f:
    G = pickle.load(f)

print("Graph loaded!")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())


# ------------------------------------------------
# Start and destination
# ------------------------------------------------

START = (76.2144, 10.5276)
DESTINATION = (76.2200, 10.5400)


# ------------------------------------------------
# Find nearest road node
# ------------------------------------------------

def nearest_node(point):

    lon, lat = point

    nearest = None
    min_distance = float("inf")

    for node in G.nodes:

        node_lon, node_lat = node

        distance = (
            (node_lon - lon) ** 2 +
            (node_lat - lat) ** 2
        )

        if distance < min_distance:
            min_distance = distance
            nearest = node

    return nearest


print("\nFinding nearest road nodes...")

start_node = nearest_node(START)
destination_node = nearest_node(DESTINATION)

print("Start node:", start_node)
print("Destination node:", destination_node)


# ------------------------------------------------
# Calculate route
# ------------------------------------------------

print("\nCalculating route...")

route = nx.shortest_path(
    G,
    start_node,
    destination_node,
    weight="weight"
)

distance = nx.shortest_path_length(
    G,
    start_node,
    destination_node,
    weight="weight"
)

print("\n========== ROUTE FOUND ==========")
print("Route points:", len(route))
print("Distance:", round(distance, 2), "meters")


# ------------------------------------------------
# Convert route to GeoJSON
# ------------------------------------------------

route_line = LineString(route)

route_gdf = gpd.GeoDataFrame(
    {
        "route": ["RouteSense Test Route"],
        "distance_m": [distance]
    },
    geometry=[route_line],
    crs="EPSG:4326"
)

route_gdf.to_file(
    ROUTE_FILE,
    driver="GeoJSON"
)

print("\nRoute saved successfully!")
print("File:", ROUTE_FILE)