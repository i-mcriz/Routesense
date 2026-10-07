"""
RouteSense AI - Flask Backend
Prototype Disaster Evacuation Routing System

IMPORTANT: This system uses ML-based prototype road-risk classification
and a simulated flood-risk layer. It is intended for academic demonstration
and is NOT a certified emergency navigation system.
"""

import os
import sys
import json
import math
import time
import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ── Configuration ──────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GEOJSON_PATH = os.path.join(BASE_DIR, 'outputs', 'routesense_road_risk.geojson')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# Thrissur study area bounding box
STUDY_BBOX = {
    'min_lon': 76.17, 'max_lon': 76.26,
    'min_lat': 10.48, 'max_lat': 10.58
}

# Default routing profiles
PROFILES = {
    'general': {
        'low': 1.0, 'medium': 2.0, 'high': 5.0,
        'slope_penalty': 0.0,
        'avoid_steps': False,
        'avoid_footway': False
    },
    'elderly': {
        'low': 1.0, 'medium': 3.0, 'high': 8.0,
        'slope_penalty': 0.5,
        'avoid_steps': True,
        'avoid_footway': True
    },
    'emergency': {
        'low': 1.0, 'medium': 4.0, 'high': 12.0,
        'slope_penalty': 0.0,
        'avoid_steps': False,
        'avoid_footway': False
    }
}

# Default origin/destination (Thrissur demo)
DEFAULT_ORIGIN = [76.1798295, 10.4900642]
DEFAULT_DEST = [76.2500925, 10.5696931]

# ── Utilities ──────────────────────────────────────────────────

def haversine(a, b):
    """Compute distance in meters between two (lon, lat) points."""
    lon1, lat1 = a
    lon2, lat2 = b
    lat = math.radians((lat1 + lat2) / 2)
    x = math.radians(lon2 - lon1) * math.cos(lat)
    y = math.radians(lat2 - lat1)
    return 6371000 * math.sqrt(x * x + y * y)


def nearest_node(G, point, node_index=None):
    """Find the nearest graph node to a (lon, lat) point."""
    if node_index is not None:
        min_dist = float('inf')
        nearest = None
        for node in node_index:
            dist = haversine(point, node)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest, min_dist

    min_dist = float('inf')
    nearest = None
    for node in G.nodes():
        dist = haversine(point, node)
        if dist < min_dist:
            min_dist = dist
            nearest = node
    return nearest, min_dist


# ── Data Loading ───────────────────────────────────────────────

print("[RouteSense] Loading road risk GeoJSON…")
t0 = time.time()
full_roads = gpd.read_file(GEOJSON_PATH)
print(f"[RouteSense] Loaded {len(full_roads)} features in {time.time()-t0:.1f}s")

# Subset to study area
study_roads = full_roads.cx[
    STUDY_BBOX['min_lon']:STUDY_BBOX['max_lon'],
    STUDY_BBOX['min_lat']:STUDY_BBOX['max_lat']
].copy()
print(f"[RouteSense] Study area (Thrissur): {len(study_roads)} road segments")

# Prepare a lightweight GeoJSON for the frontend risk map (sampled for performance)
print("[RouteSense] Preparing risk-map payload…")
risk_features = []
for _, road in study_roads.iterrows():
    geom = road.geometry
    if not isinstance(geom, LineString):
        continue
    coords = [list(c[:2]) for c in geom.coords]
    risk_features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "osm_id": str(road.get("osm_id", "")),
            "highway": road.get("highway", ""),
            "predicted_risk": int(road.get("predicted_risk", 0)),
            "risk_label": road.get("risk_label", "Low"),
            "elevation": float(road.get("elevation", 0) or 0),
            "slope": float(road.get("slope", 0) or 0),
            "rainfall": float(road.get("rainfall", 0) or 0),
            "dist_water": float(road.get("dist_water", 0) or 0),
        }
    })
RISK_MAP_GEOJSON = {"type": "FeatureCollection", "features": risk_features}
print(f"[RouteSense] Risk map: {len(risk_features)} renderable features")

# ── Graph Building ─────────────────────────────────────────────

print("[RouteSense] Building NetworkX routing graph…")
G_BASE = nx.Graph()
EDGE_DATA_STORE = {}   # (u,v) -> dict of original attributes

for _, road in study_roads.iterrows():
    geom = road.geometry
    if not isinstance(geom, LineString):
        continue
    coords = list(geom.coords)
    risk = int(road.get("predicted_risk", 0))
    highway = road.get("highway", "")
    elev = float(road.get("elevation", 0) or 0)
    slope = float(road.get("slope", 0) or 0)
    rainfall = float(road.get("rainfall", 0) or 0)
    dist_water = float(road.get("dist_water", 0) or 0)

    for i in range(len(coords) - 1):
        u = (round(coords[i][0], 7), round(coords[i][1], 7))
        v = (round(coords[i+1][0], 7), round(coords[i+1][1], 7))
        dist = haversine(u, v)
        if dist < 0.1:
            continue  # skip degenerate edges
        attrs = {
            'distance': dist,
            'osm_id': str(road.get("osm_id", "")),
            'highway': highway,
            'predicted_risk': risk,
            'risk_label': road.get("risk_label", "Low"),
            'elevation': elev,
            'slope': slope,
            'rainfall': rainfall,
            'dist_water': dist_water,
        }
        G_BASE.add_edge(u, v, **attrs)
        EDGE_DATA_STORE[(u, v)] = attrs
        EDGE_DATA_STORE[(v, u)] = attrs

NODE_LIST = list(G_BASE.nodes())
print(f"[RouteSense] Graph: {G_BASE.number_of_nodes()} nodes, {G_BASE.number_of_edges()} edges")


# ── Routing Engine ─────────────────────────────────────────────

def compute_edge_weights(G, profile_name, flood_center=None, flood_radius=2000, flood_intensity=0.5, water_level=1.0):
    """
    Recompute edge weights on the graph considering profile and optional flood simulation.
    Returns a new graph with updated weights.
    """
    profile = PROFILES.get(profile_name, PROFILES['general'])
    risk_mults = {0: profile['low'], 1: profile['medium'], 2: profile['high']}
    slope_pen = profile['slope_penalty']
    avoid_steps = profile['avoid_steps']
    avoid_footway = profile['avoid_footway']

    G_weighted = G.copy()

    for u, v, data in G_weighted.edges(data=True):
        dist = data['distance']
        original_risk = data['predicted_risk']
        highway = data.get('highway', '')
        slope_val = data.get('slope', 0)

        effective_risk = original_risk

        # ── Flood simulation penalty ──
        if flood_center is not None:
            mid = ((u[0]+v[0])/2, (u[1]+v[1])/2)
            d_to_flood = haversine(mid, tuple(flood_center))
            if d_to_flood < flood_radius:
                # Proximity factor: 1.0 at center, 0.0 at boundary
                proximity = 1.0 - (d_to_flood / flood_radius)
                # Elevation factor: lower elevation = more vulnerable
                elev = data.get('elevation', 50)
                elev_factor = max(0, 1.0 - (elev / 500))  # normalized
                # Combined flood penalty pushes risk up
                flood_penalty = proximity * flood_intensity * elev_factor * water_level
                if flood_penalty > 0.7:
                    effective_risk = 2  # HIGH
                elif flood_penalty > 0.3:
                    effective_risk = max(effective_risk, 1)  # at least MEDIUM
                # else keep original

        mult = risk_mults.get(effective_risk, 1.0)
        cost = dist * mult

        # ── Slope penalty for elderly ──
        if slope_pen > 0 and slope_val > 5:
            cost += dist * slope_pen * (slope_val / 10)

        # ── Avoid steps/footway for elderly ──
        if avoid_steps and highway == 'steps':
            cost += dist * 50  # huge penalty
        if avoid_footway and highway in ('footway', 'path'):
            cost += dist * 10

        G_weighted[u][v]['routesense_cost'] = cost
        G_weighted[u][v]['effective_risk'] = effective_risk

    return G_weighted


def run_routing(origin, destination, profile_name, flood_center=None, flood_radius=2000, flood_intensity=0.5, water_level=1.0):
    """
    Full routing pipeline: find nearest nodes, compute both routes, extract metrics.
    """
    origin_node, origin_dist = nearest_node(G_BASE, tuple(origin), NODE_LIST)
    dest_node, dest_dist = nearest_node(G_BASE, tuple(destination), NODE_LIST)

    if origin_node is None or dest_node is None:
        return {"error": "Could not map origin/destination to graph"}

    if not nx.has_path(G_BASE, origin_node, dest_node):
        return {"error": "No path exists between origin and destination"}

    # Weighted graph
    G_w = compute_edge_weights(G_BASE, profile_name, flood_center, flood_radius, flood_intensity, water_level)

    # Normal route (distance only)
    normal_path = nx.shortest_path(G_BASE, source=origin_node, target=dest_node, weight='distance')
    # RouteSense route (risk-weighted)
    rs_path = nx.shortest_path(G_w, source=origin_node, target=dest_node, weight='routesense_cost')

    def extract_metrics(path, graph, use_effective=False):
        total_dist = 0
        risk_counts = {0: 0, 1: 0, 2: 0}
        coordinates = [list(path[0])]
        segments = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            data = graph.get_edge_data(u, v)
            d = data['distance']
            r = data.get('effective_risk', data['predicted_risk']) if use_effective else data['predicted_risk']
            total_dist += d
            risk_counts[r] = risk_counts.get(r, 0) + 1
            coordinates.append(list(v))
            segments.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [list(u), list(v)]},
                "properties": {
                    "distance": round(d, 2),
                    "predicted_risk": r,
                    "risk_label": ["Low", "Medium", "High"][r],
                    "highway": data.get('highway', ''),
                    "elevation": round(data.get('elevation', 0), 1),
                    "slope": round(data.get('slope', 0), 1),
                }
            })
        n_seg = sum(risk_counts.values())
        return {
            "distance": round(total_dist, 2),
            "segments": n_seg,
            "risk_counts": risk_counts,
            "high_pct": round((risk_counts.get(2, 0) / n_seg * 100) if n_seg > 0 else 0, 1),
            "coordinates": coordinates,
            "geojson": {"type": "FeatureCollection", "features": segments}
        }

    normal_metrics = extract_metrics(normal_path, G_w, use_effective=False)
    rs_metrics = extract_metrics(rs_path, G_w, use_effective=True)

    # Affected roads (for flood viz)
    affected_roads = []
    if flood_center is not None:
        for u, v, data in G_w.edges(data=True):
            if data.get('effective_risk', data['predicted_risk']) != data['predicted_risk']:
                affected_roads.append({
                    "coordinates": [list(u), list(v)],
                    "original_risk": data['predicted_risk'],
                    "effective_risk": data['effective_risk']
                })

    dist_diff = rs_metrics['distance'] - normal_metrics['distance']
    dist_pct = round((dist_diff / normal_metrics['distance']) * 100, 1) if normal_metrics['distance'] > 0 else 0
    high_avoided = normal_metrics['risk_counts'].get(2, 0) - rs_metrics['risk_counts'].get(2, 0)
    high_normal = normal_metrics['risk_counts'].get(2, 0)
    reduction_pct = round((high_avoided / high_normal * 100) if high_normal > 0 else 0, 1)

    return {
        "origin": list(origin_node),
        "destination": list(dest_node),
        "profile": profile_name,
        "normal": normal_metrics,
        "routesense": rs_metrics,
        "comparison": {
            "distance_diff": round(dist_diff, 2),
            "distance_pct": dist_pct,
            "high_risk_avoided": high_avoided,
            "risk_reduction_pct": reduction_pct,
            "routes_differ": normal_path != rs_path
        },
        "affected_roads_count": len(affected_roads),
        "flood_active": flood_center is not None
    }


# ── Flask App ──────────────────────────────────────────────────

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)


@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "nodes": G_BASE.number_of_nodes(),
        "edges": G_BASE.number_of_edges(),
        "study_area": "Thrissur, Kerala",
        "road_segments": len(study_roads),
        "prototype": True
    })


@app.route('/api/risk-map')
def risk_map():
    return jsonify(RISK_MAP_GEOJSON)


@app.route('/api/route', methods=['POST'])
def route():
    data = request.get_json(force=True)
    origin = data.get('origin', DEFAULT_ORIGIN)
    destination = data.get('destination', DEFAULT_DEST)
    profile = data.get('profile', 'general')

    flood = data.get('flood', None)
    flood_center = None
    flood_radius = 2000
    flood_intensity = 0.5
    water_level = 1.0

    if flood and flood.get('active'):
        flood_center = flood.get('center')
        flood_radius = flood.get('radius', 2000)
        flood_intensity = flood.get('intensity', 0.5)
        water_level = flood.get('water_level', 1.0)

    result = run_routing(
        origin, destination, profile,
        flood_center=flood_center,
        flood_radius=flood_radius,
        flood_intensity=flood_intensity,
        water_level=water_level
    )
    return jsonify(result)


@app.route('/api/simulate-flood', methods=['POST'])
def simulate_flood():
    """Return affected road segments for a given flood configuration."""
    data = request.get_json(force=True)
    center = data.get('center')
    radius = data.get('radius', 2000)
    intensity = data.get('intensity', 0.5)
    water_level = data.get('water_level', 1.0)

    if not center:
        return jsonify({"error": "Flood center required"}), 400

    affected = []
    for u, v, attr in G_BASE.edges(data=True):
        mid = ((u[0]+v[0])/2, (u[1]+v[1])/2)
        d = haversine(mid, tuple(center))
        if d < radius:
            proximity = 1.0 - (d / radius)
            elev = attr.get('elevation', 50)
            elev_factor = max(0, 1.0 - (elev / 500))
            penalty = proximity * intensity * elev_factor * water_level
            original = attr['predicted_risk']
            effective = original
            if penalty > 0.7:
                effective = 2
            elif penalty > 0.3:
                effective = max(effective, 1)
            if effective != original:
                affected.append({
                    "coordinates": [list(u), list(v)],
                    "original_risk": original,
                    "effective_risk": effective
                })

    return jsonify({
        "affected_count": len(affected),
        "affected_roads": affected[:3000],  # cap for performance
        "center": center,
        "radius": radius
    })


if __name__ == '__main__':
    print("\n[RouteSense] Starting web application…")
    print(f"[RouteSense] Frontend: {FRONTEND_DIR}")
    print(f"[RouteSense] Open http://localhost:5000 in your browser\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
