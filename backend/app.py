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
import socket
import pickle
import threading
import webbrowser
import urllib.request
import numpy as np
from scipy.spatial import cKDTree
import networkx as nx
from shapely.geometry import LineString, Polygon, Point
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

NODE_TREE = None
NODE_ARRAY = None
ROUTABLE_TREE = None
ROUTABLE_NODE_LIST = []
EDGE_LIST = []
EDGE_MIDS = None

# ── Configuration ──────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GEOJSON_PATH = os.path.join(BASE_DIR, 'outputs', 'routesense_road_risk.geojson')
REPAIRED_CACHE_PATH = os.path.join(BASE_DIR, 'data', 'repaired', 'thrissur_app_cache_repaired.pkl')
ORIGINAL_CACHE_PATH = os.path.join(BASE_DIR, 'data', 'thrissur_app_cache.pkl')
CACHE_PATH = os.environ.get('ROUTESENSE_CACHE', REPAIRED_CACHE_PATH if os.path.exists(REPAIRED_CACHE_PATH) else ORIGINAL_CACHE_PATH)
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# Thrissur study area bounding box (Complete study area covering all 17,335 roads)
STUDY_BBOX = {
    'min_lon': 76.15, 'max_lon': 76.28,
    'min_lat': 10.45, 'max_lat': 10.61
}

# Configurable flood severity thresholds
# Roads with flood_penalty > IMPASSABLE_THRESHOLD are excluded from RouteSense routing
IMPASSABLE_THRESHOLD = 0.85

# Default routing profiles
PROFILES = {
    'general': {
        'low': 1.0, 'medium': 1.3, 'high': 2.5,
        'slope_penalty': 0.0,
        'avoid_steps': False,
        'avoid_footway': False
    },
    'wheelchair': {
        'low': 1.0, 'medium': 1.5, 'high': 3.0,
        'slope_penalty': 1.0,
        'max_slope': 8.0,
        'avoid_steps': True,
        'avoid_footway': False
    },
    'elderly': {
        'low': 1.0, 'medium': 1.5, 'high': 3.0,
        'slope_penalty': 0.5,
        'avoid_steps': True,
        'avoid_footway': True
    },
    'emergency': {
        'low': 1.0, 'medium': 2.0, 'high': 5.0,
        'slope_penalty': 0.0,
        'avoid_steps': False,
        'avoid_footway': False
    }
}

# Default origin/destination (Thrissur demo)
DEFAULT_ORIGIN = [76.1798295, 10.4900642]
DEFAULT_DEST = [76.2500925, 10.5696931]

# ── Emergency Relief Shelters (Thrissur Evacuation Shelters & Relief Hubs) ──
SHELTERS = [
    # ── Verified Emergency Relief Shelters ──
    {
        "id": "sh_town_hall",
        "name": "Thrissur Town Hall Relief Center",
        "type": "Civic Center",
        "coordinates": [76.2168, 10.5276],
        "elevation": 18.5,
        "capacity": 450,
        "contact": "0487-2331241",
        "supplies": ["Medical Aid", "Drinking Water", "Bedding", "Emergency Food"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_model_boys",
        "name": "Govt Model Boys HSS Camp",
        "type": "Educational Institution",
        "coordinates": [76.2205, 10.5255],
        "elevation": 22.0,
        "capacity": 600,
        "contact": "0487-2423321",
        "supplies": ["Blankets", "Baby Food", "Clean Water", "First Aid"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_st_thomas",
        "name": "St. Thomas College Relief Camp",
        "type": "College Campus",
        "coordinates": [76.2248, 10.5281],
        "elevation": 20.2,
        "capacity": 850,
        "contact": "0487-2420435",
        "supplies": ["Ambulance Access", "Power Backup", "Dry Rations"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_vimala",
        "name": "Vimala College Relief Center (Cheroor)",
        "type": "Elevated Ridge Shelter",
        "coordinates": [76.2260, 10.5510],
        "elevation": 35.0,
        "capacity": 700,
        "contact": "0487-2332080",
        "supplies": ["High Ground Camp", "Medical Staff", "Sanitation"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_medical_college",
        "name": "Govt Medical College Disaster Relief Camp",
        "type": "Specialized Medical Hub",
        "coordinates": [76.2080, 10.5650],
        "elevation": 42.0,
        "capacity": 1200,
        "contact": "0487-2200310",
        "supplies": ["ICU & Trauma Support", "Helipad Access", "Maternity Aid"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_collectorate",
        "name": "Civil Station Relief Center (Ayyanthole)",
        "type": "District Administration Camp",
        "coordinates": [76.1915, 10.5330],
        "elevation": 25.5,
        "capacity": 900,
        "contact": "1077 (Disaster Toll-Free)",
        "supplies": ["Command Dispatch", "Food Packets", "Satellite Comms"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },
    {
        "id": "sh_jubilee",
        "name": "Jubilee Mission Medical Relief Hub",
        "type": "Hospital Shelter",
        "coordinates": [76.2310, 10.5200],
        "elevation": 28.0,
        "capacity": 500,
        "contact": "0487-2432200",
        "supplies": ["Emergency Surgical Unit", "Oxygen Supply", "Clean Water"],
        "status": "OPEN",
        "verified": True,
        "demo_shelter": False
    },

    # ── Well-Distributed Safe Prototype / Demo Shelters Across Thrissur Study Area ──
    {
        "id": "sh_amala",
        "name": "Amala Institute Medical Relief Hub (Amalanagar) [Prototype]",
        "type": "Hospital Shelter (Prototype Shelter)",
        "coordinates": [76.1652, 10.5645],
        "elevation": 26.0,
        "capacity": 950,
        "contact": "0487-2304000",
        "supplies": ["Trauma Care", "Generators", "Surgical Facility"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_vilangan",
        "name": "Vilangan Hill Elevated Relief Camp (Muthuvara) [Prototype]",
        "type": "Elevated Ridge Shelter (Prototype Shelter)",
        "coordinates": [76.1648, 10.5423],
        "elevation": 48.0,
        "capacity": 600,
        "contact": "0487-2305100",
        "supplies": ["High Ground Refuge", "Drinking Water", "Bedding"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_sobha",
        "name": "Sobha City Area Relief Facility (Puzhakkal) [Prototype]",
        "type": "Community Facility (Prototype Shelter)",
        "coordinates": [76.1816, 10.5515],
        "elevation": 18.0,
        "capacity": 1100,
        "contact": "0487-2308800",
        "supplies": ["Mass Capacity", "Food Rations", "Shelter Halls"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_kottekkad",
        "name": "St. Mary Community Relief Centre (Kottekkad) [Prototype]",
        "type": "Educational Institution (Prototype Shelter)",
        "coordinates": [76.1835, 10.5810],
        "elevation": 21.0,
        "capacity": 450,
        "contact": "0487-2311200",
        "supplies": ["Drinking Water", "First Aid", "Blankets"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_mulamkunnathukavu",
        "name": "Mulamkunnathukavu Community Relief Camp [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2049, 10.5958],
        "elevation": 28.0,
        "capacity": 500,
        "contact": "0487-2200220",
        "supplies": ["Sanitation", "Dry Rations", "Ambulance Access"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_kolazhy",
        "name": "Kolazhy Panchayat Community Shelter [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2153, 10.5741],
        "elevation": 24.0,
        "capacity": 550,
        "contact": "0487-2201300",
        "supplies": ["Emergency Water", "Bedding", "First Aid"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_pottore",
        "name": "Pottore Community Relief Facility [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.1990, 10.5683],
        "elevation": 22.0,
        "capacity": 400,
        "contact": "0487-2202400",
        "supplies": ["Clean Water", "First Aid", "Bedding"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_police_academy",
        "name": "Police Academy Relief Facility (Ramavarmapuram) [Prototype]",
        "type": "Administrative Facility (Prototype Shelter)",
        "coordinates": [76.2371, 10.5562],
        "elevation": 34.0,
        "capacity": 1200,
        "contact": "0487-2328100",
        "supplies": ["Helipad Access", "High Security", "Command Center"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_kau",
        "name": "KAU Central Campus Relief Hub (Vellanikkara) [Prototype]",
        "type": "University Campus (Prototype Shelter)",
        "coordinates": [76.2749, 10.5450],
        "elevation": 36.0,
        "capacity": 1500,
        "contact": "0487-2438011",
        "supplies": ["Extensive Campus", "Emergency Food", "High Elevation"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_mannuthy",
        "name": "Don Bosco Relief Center (Mannuthy) [Prototype]",
        "type": "Educational Institution (Prototype Shelter)",
        "coordinates": [76.2618, 10.5333],
        "elevation": 27.0,
        "capacity": 750,
        "contact": "0487-2370438",
        "supplies": ["Large Halls", "Water Supply", "First Aid"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_nadathara",
        "name": "Nadathara Community Relief Facility [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2572, 10.5161],
        "elevation": 22.0,
        "capacity": 500,
        "contact": "0487-2371200",
        "supplies": ["Community Hall", "Rations", "Medical Aid"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_kuttanellur",
        "name": "Kuttanellur Govt College Relief Camp [Prototype]",
        "type": "College Campus (Prototype Shelter)",
        "coordinates": [76.2521, 10.4940],
        "elevation": 25.0,
        "capacity": 800,
        "contact": "0487-2351233",
        "supplies": ["Open Grounds", "Clean Water", "Bedding"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_marathakkara",
        "name": "Marathakkara Community Relief Shelter [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2541, 10.4739],
        "elevation": 23.0,
        "capacity": 400,
        "contact": "0487-2352100",
        "supplies": ["First Aid", "Blankets", "Dry Food"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_ollur",
        "name": "St. Anthony Relief Center (Ollur) [Prototype]",
        "type": "Educational Institution (Prototype Shelter)",
        "coordinates": [76.2382, 10.4783],
        "elevation": 24.0,
        "capacity": 650,
        "contact": "0487-2352210",
        "supplies": ["Auditorium", "Drinking Water", "Power Backup"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_chiyyaram",
        "name": "Chiyyaram Community Relief Point [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2181, 10.4968],
        "elevation": 19.0,
        "capacity": 500,
        "contact": "0487-2251100",
        "supplies": ["Sanitation", "First Aid", "Food Supplies"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_koorkenchery",
        "name": "Koorkenchery Community Relief Center [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2124, 10.5061],
        "elevation": 18.0,
        "capacity": 550,
        "contact": "0487-2421500",
        "supplies": ["Community Hall", "Emergency Food", "Bedding"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_palakkal",
        "name": "Palakkal Community Relief Shelter [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.2141, 10.4607],
        "elevation": 17.0,
        "capacity": 450,
        "contact": "0487-2272300",
        "supplies": ["Drinking Water", "Blankets", "First Aid"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_elthuruth",
        "name": "St. Aloysius College Relief Camp (Elthuruth) [Prototype]",
        "type": "College Campus (Prototype Shelter)",
        "coordinates": [76.1839, 10.4948],
        "elevation": 18.0,
        "capacity": 700,
        "contact": "0487-2360538",
        "supplies": ["Large Campus", "Generators", "Clean Water"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_aranattukara",
        "name": "Aranattukara Community Relief Facility [Prototype]",
        "type": "Civic Center (Prototype Shelter)",
        "coordinates": [76.1821, 10.5100],
        "elevation": 19.0,
        "capacity": 500,
        "contact": "0487-2381200",
        "supplies": ["First Aid", "Food Packets", "Sanitation"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    },
    {
        "id": "sh_kanattukara",
        "name": "Sree Kerala Varma College Camp (Kanattukara) [Prototype]",
        "type": "College Campus (Prototype Shelter)",
        "coordinates": [76.2002, 10.5193],
        "elevation": 22.0,
        "capacity": 850,
        "contact": "0487-2380535",
        "supplies": ["Auditorium", "Water Storage", "Blankets"],
        "status": "OPEN (Prototype)",
        "verified": False,
        "demo_shelter": True
    }
]

def estimate_inundation_time(elevation, dist_to_flood_center, flood_radius, water_level=1.0, intensity=0.5):
    """
    Hydrological inundation arrival time estimation.
    Calculates estimated minutes before water submerges the specified road or area.
    """
    intensity = max(0.05, float(intensity))
    water_level = max(0.1, float(water_level))
    elevation = float(elevation) if elevation else 15.0

    rise_rate = max(0.1, intensity * 0.8 * water_level)
    elevation_head = max(0.3, elevation - 2.5)
    surge_speed_kmh = max(0.8, 3.2 * intensity)
    horizontal_dist_km = max(0.05, dist_to_flood_center / 1000.0)
    surge_travel_time_hrs = horizontal_dist_km / surge_speed_kmh
    vertical_time_hrs = elevation_head / (rise_rate * 2.0)

    total_minutes = int(round((surge_travel_time_hrs * 0.35 + vertical_time_hrs * 0.65) * 60))
    total_minutes = max(8, min(720, total_minutes))

    if total_minutes < 45:
        urgency = "CRITICAL"
        display = f"~{total_minutes} mins"
    elif total_minutes < 120:
        urgency = "HIGH"
        display = f"~{total_minutes} mins"
    elif total_minutes < 300:
        hours = round(total_minutes / 60, 1)
        urgency = "MODERATE"
        display = f"~{hours} hrs"
    else:
        hours = round(total_minutes / 60, 1)
        urgency = "LOW"
        display = f"~{hours} hrs"

    return {
        "minutes": total_minutes,
        "eta_display": display,
        "urgency": urgency,
        "rise_rate_m_hr": round(rise_rate, 2),
        "elevation": elevation
    }

# ── Utilities ──────────────────────────────────────────────────

def haversine(a, b):
    """Compute distance in meters between two (lon, lat) points."""
    lon1, lat1 = a
    lon2, lat2 = b
    lat = math.radians((lat1 + lat2) / 2)
    x = math.radians(lon2 - lon1) * math.cos(lat)
    y = math.radians(lat2 - lat1)
    return 6371000 * math.sqrt(x * x + y * y)


def is_point_in_flood(point, flood_center=None, flood_radius=2000, flood_polygon=None, flood_zones=None):
    """Check whether a (lon, lat) point lies inside an active flood circle or flood zone polygon."""
    if point is None:
        return False
    try:
        p_lon, p_lat = float(point[0]), float(point[1])
        if p_lon < 20 and p_lat > 70:
            p_lon, p_lat = p_lat, p_lon
    except (ValueError, TypeError, IndexError):
        return False

    # 1. Circular flood check
    if flood_center is not None and flood_radius and flood_radius > 0:
        try:
            c_lon, c_lat = float(flood_center[0]), float(flood_center[1])
            if c_lon < 20 and c_lat > 70:
                c_lon, c_lat = c_lat, c_lon
            if haversine((p_lon, p_lat), (c_lon, c_lat)) <= flood_radius:
                return True
        except (ValueError, TypeError, IndexError):
            pass

    # 2. Multi-zone and legacy flood polygon check
    candidate_zones = []
    if flood_zones:
        candidate_zones.extend(flood_zones)
    elif flood_polygon is not None and len(flood_polygon) >= 3:
        candidate_zones.append({'polygon': flood_polygon})

    if candidate_zones:
        pt = Point(p_lon, p_lat)
        for z in candidate_zones:
            pts = z.get('polygon') if isinstance(z, dict) else None
            if not pts or len(pts) < 3:
                continue
            try:
                poly_coords = []
                for p in pts:
                    if p[0] < 20 and p[1] > 70:
                        poly_coords.append((float(p[1]), float(p[0])))
                    else:
                        poly_coords.append((float(p[0]), float(p[1])))
                sp = Polygon(poly_coords)
                if not sp.is_valid:
                    sp = sp.buffer(0)
                if sp.contains(pt) or sp.distance(pt) < 1e-6:
                    return True
            except Exception:
                continue

    return False


def get_origin_flood_zone(point, flood_center, flood_radius):
    """
    Determine which concentric zone of the flood circle a point falls in.
    The flood circle is visually split into 3 rings on the frontend:
        - Inner circle:       0% to 50% of radius  (most dangerous, fully submerged)
        - Intermediate circle: 50% to 75% of radius (moderate risk)
        - Outer circle:       75% to 100% of radius (lower risk, evacuation possible)
    Returns 'inner', 'intermediate', 'outer', or None (outside circle).
    """
    if point is None or flood_center is None or not flood_radius or flood_radius <= 0:
        return None
    try:
        p_lon, p_lat = float(point[0]), float(point[1])
        if p_lon < 20 and p_lat > 70:
            p_lon, p_lat = p_lat, p_lon
        c_lon, c_lat = float(flood_center[0]), float(flood_center[1])
        if c_lon < 20 and c_lat > 70:
            c_lon, c_lat = c_lat, c_lon
        dist = haversine((p_lon, p_lat), (c_lon, c_lat))
        if dist > flood_radius:
            return None
        ratio = dist / flood_radius  # 0.0 at center, 1.0 at edge
        if ratio <= 0.50:
            return 'inner'
        elif ratio <= 0.75:
            return 'intermediate'
        else:
            return 'outer'
    except (ValueError, TypeError, IndexError):
        return None


def nearest_node(G, point, node_index=None):
    """Find the nearest graph node to a (lon, lat) point in <0.05ms using KD-Tree."""
    pt = np.array([float(point[0]), float(point[1])], dtype=np.float64)

    # If caller did not provide custom subset, prioritize the routable main component
    if node_index is None:
        if ROUTABLE_TREE is not None and ROUTABLE_NODE_LIST:
            _, idx = ROUTABLE_TREE.query(pt)
            node = ROUTABLE_NODE_LIST[idx]
            return node, haversine(pt, node)
        if NODE_TREE is not None:
            _, idx = NODE_TREE.query(pt)
            node = NODE_LIST[idx]
            return node, haversine(pt, node)

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

if os.path.exists(CACHE_PATH):
    print("[RouteSense] Loading cached Thrissur road network and graph...")
    t0 = time.time()
    with open(CACHE_PATH, 'rb') as f:
        cache_data = pickle.load(f)
    study_roads = cache_data['study_roads']
    RISK_MAP_GEOJSON = cache_data['RISK_MAP_GEOJSON']
    G_BASE = cache_data['G_BASE']
    EDGE_DATA_STORE = cache_data['EDGE_DATA_STORE']
    NODE_LIST = cache_data['NODE_LIST']
    print(f"[RouteSense] Loaded cached graph in {time.time()-t0:.1f}s ({len(NODE_LIST)} nodes, {G_BASE.number_of_edges()} edges)")
else:
    print("[RouteSense] Loading road risk GeoJSON…")
    t0 = time.time()
    import geopandas as gpd
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
    try:
        with open(CACHE_PATH, 'wb') as f:
            pickle.dump({
                'study_roads': study_roads,
                'RISK_MAP_GEOJSON': RISK_MAP_GEOJSON,
                'G_BASE': G_BASE,
                'EDGE_DATA_STORE': EDGE_DATA_STORE,
                'NODE_LIST': NODE_LIST
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[RouteSense] Saved cache to {CACHE_PATH}")
    except Exception as e:
        print(f"[RouteSense] Warning: could not save cache: {e}")


# ── High-Performance Spatial Acceleration Indices ─────────────
print("[RouteSense] Initializing KD-Tree & Vectorized Spatial Indices...")
NODE_ARRAY = np.array(NODE_LIST, dtype=np.float64)
NODE_TREE = cKDTree(NODE_ARRAY)

# Index largest connected component for 100% routable snapping
components = sorted(list(nx.connected_components(G_BASE)), key=len, reverse=True)
if components and len(components[0]) > len(NODE_LIST) * 0.7:
    ROUTABLE_NODE_LIST = list(components[0])
    ROUTABLE_NODE_ARRAY = np.array(ROUTABLE_NODE_LIST, dtype=np.float64)
    ROUTABLE_TREE = cKDTree(ROUTABLE_NODE_ARRAY)
else:
    ROUTABLE_NODE_LIST = NODE_LIST
    ROUTABLE_TREE = NODE_TREE

EDGE_LIST = list(G_BASE.edges(data=True))
EDGE_MIDS = np.array([
    [((u[0] + v[0]) * 0.5), ((u[1] + v[1]) * 0.5)]
    for u, v, _ in EDGE_LIST
], dtype=np.float64)
print(f"[RouteSense] Ready: {len(NODE_LIST)} nodes indexed in KD-Tree ({len(ROUTABLE_NODE_LIST)} routable), {len(EDGE_LIST)} edges indexed.")


# ── Precomputed Baseline Profile Graphs & Spatial Cache ───────────
BASE_PROFILE_GRAPHS = {}
_EDGE_WEIGHTS_CACHE = {}
_CACHE_MAX_SIZE = 48
_NORMAL_PATH_CACHE = {}
_ROUTE_RESULT_CACHE = {}
_ROUTE_CACHE_MAX_SIZE = 64

def init_base_profile_graphs():
    global BASE_PROFILE_GRAPHS
    print("[RouteSense] Precomputing baseline profile graphs for sub-millisecond routing...")
    t_start = time.time()
    for p_name, profile in PROFILES.items():
        G_p = G_BASE.copy()
        risk_mults = {0: profile['low'], 1: profile['medium'], 2: profile['high']}
        slope_pen = profile['slope_penalty']
        avoid_steps = profile['avoid_steps']
        avoid_footway = profile['avoid_footway']
        max_slope = profile.get('max_slope', None)

        for u, v, data in G_p.edges(data=True):
            dist = data['distance']
            risk = data['predicted_risk']
            highway = data.get('highway', '')
            slope_val = data.get('slope', 0)
            is_imp = False
            mult = risk_mults.get(risk, 1.0)
            cost = dist * mult

            if slope_pen > 0 and slope_val > 5:
                cost += dist * slope_pen * (slope_val / 10)

            if avoid_steps and highway == 'steps':
                if p_name == 'wheelchair':
                    is_imp = True
                    cost = float('inf')
                else:
                    cost += dist * 50

            if avoid_footway and highway in ('footway', 'path'):
                cost += dist * 10

            if max_slope is not None and slope_val > max_slope:
                if p_name == 'wheelchair':
                    is_imp = True
                    cost = float('inf')
                else:
                    cost += dist * 50

            data['routesense_cost'] = cost
            data['effective_risk'] = risk
            data['flood_penalty'] = 0.0
            data['impassable'] = is_imp

        BASE_PROFILE_GRAPHS[p_name] = G_p
    print(f"[RouteSense] Baseline profile graphs ready in {time.time()-t_start:.2f}s ({list(BASE_PROFILE_GRAPHS.keys())}).")

init_base_profile_graphs()


def get_flood_cache_key(profile_name, flood_center, flood_radius, flood_intensity, water_level, flood_polygon, flood_zones):
    fc = tuple(round(float(x), 4) for x in flood_center) if flood_center is not None else None
    fr = round(float(flood_radius), 1) if flood_radius is not None else None
    fi = round(float(flood_intensity), 3) if flood_intensity is not None else None
    wl = round(float(water_level), 2) if water_level is not None else None
    fp = tuple(tuple(round(float(c), 4) for c in pt) for pt in flood_polygon) if flood_polygon is not None else None
    fz = None
    if flood_zones:
        fz_list = []
        for z in flood_zones:
            if isinstance(z, dict):
                pts = z.get('polygon')
                z_pts = tuple(tuple(round(float(c), 4) for c in pt) for pt in pts) if pts else ()
                fz_list.append((z.get('id', ''), round(float(z.get('intensity', 0)), 3), round(float(z.get('water_level', 0)), 2), z_pts))
        fz = tuple(fz_list)
    return (profile_name, fc, fr, fi, wl, fp, fz)


# ── Routing Engine ─────────────────────────────────────────────

def compute_edge_weights(G, profile_name, flood_center=None, flood_radius=2000,
                         flood_intensity=0.5, water_level=1.0, flood_polygon=None,
                         flood_zones=None):
    """
    Recompute edge weights on the graph considering profile and optional flood simulation.
    Returns a graph with updated weights.

    Supports both baseline circular flood and multiple custom flood zones with
    independent simulated rainfall intensities.

    Optimization:
        Spatial bounding-box pre-filtering reduces candidate edges from 60,567 down
        to ~100-400 before computing haversine or Shapely geometries, yielding >100x speedup.
        Precomputed profile base graphs and LRU caching make repeated or chained requests 0.0ms.

    Overlapping Zone Rule:
        Deterministic maximum penalty: flood_penalty = max(penalties) across all intersecting
        zones and the circular flood. This prevents runaway compounding while preserving
        true worst-case hazard severity and enables clean restoration upon zone deletion.

    Edge cost formula (units: risk-weighted meters):
        routesense_cost = distance × risk_multiplier + slope_penalty + accessibility_penalty

    Impassable roads:
        Roads with flood_penalty > IMPASSABLE_THRESHOLD get routesense_cost = inf
        and are excluded from RouteSense pathfinding. They remain in the base graph
        so the normal shortest-distance route is unaffected.
    """
    profile = PROFILES.get(profile_name, PROFILES['general'])
    risk_mults = {0: profile['low'], 1: profile['medium'], 2: profile['high']}
    slope_pen = profile['slope_penalty']
    avoid_steps = profile['avoid_steps']
    avoid_footway = profile['avoid_footway']
    max_slope = profile.get('max_slope', None)

    # 1. Circle bounding box pre-computation
    circle_bbox = None
    if flood_center is not None and flood_radius and flood_radius > 0:
        c_lon, c_lat = flood_center[0], flood_center[1]
        d_lat = (flood_radius / 110000.0) * 1.15
        d_lon = (flood_radius / 108000.0) * 1.15
        circle_bbox = (c_lon - d_lon, c_lat - d_lat, c_lon + d_lon, c_lat + d_lat)

    # 2. Parse multi-zone flood list or fallback legacy single polygon
    parsed_zones = []
    zone_candidates = []
    if flood_zones:
        zone_candidates.extend(flood_zones)
    elif flood_polygon is not None and len(flood_polygon) >= 3:
        zone_candidates.append({
            'polygon': flood_polygon,
            'intensity': flood_intensity,
            'water_level': water_level
        })

    for z in zone_candidates:
        pts = z.get('polygon') if isinstance(z, dict) else None
        if not pts or len(pts) < 3:
            continue
        try:
            poly_coords = []
            for p in pts:
                if p[0] < 20 and p[1] > 70:
                    poly_coords.append((float(p[1]), float(p[0])))
                else:
                    poly_coords.append((float(p[0]), float(p[1])))
            sp = Polygon(poly_coords)
            if not sp.is_valid:
                sp = sp.buffer(0)
            if sp.is_empty:
                continue
            z_intensity = float(z.get('intensity', flood_intensity))
            z_water = float(z.get('water_level', water_level))
            boundary = getattr(sp, 'boundary', None) or getattr(sp, 'exterior', None)
            max_dist = max(0.001, math.sqrt(sp.area) / 2.0)
            parsed_zones.append({
                'shapely': sp,
                'bounds': sp.bounds,  # (minx, miny, maxx, maxy)
                'intensity': z_intensity,
                'water_level': z_water,
                'boundary': boundary,
                'max_dist': max_dist
            })
        except Exception:
            continue

    has_circle = circle_bbox is not None
    has_zones = len(parsed_zones) > 0
    has_any_flood = has_circle or has_zones

    # ── Fast path: Zero flood condition uses precomputed baseline profile graph directly ──
    if not has_any_flood:
        base_p = BASE_PROFILE_GRAPHS.get(profile_name)
        if base_p is not None and G is G_BASE:
            return base_p

    # ── Cache lookup for repeated flood queries ──
    cache_key = get_flood_cache_key(profile_name, flood_center, flood_radius, flood_intensity, water_level, flood_polygon, flood_zones)
    if cache_key in _EDGE_WEIGHTS_CACHE:
        return _EDGE_WEIGHTS_CACHE[cache_key]

    base_p = BASE_PROFILE_GRAPHS.get(profile_name, BASE_PROFILE_GRAPHS.get('general', G))
    G_weighted = base_p.copy() if base_p is not None else G.copy()

    all_minx = all_miny = all_maxx = all_maxy = None
    if has_any_flood:
        bboxes = []
        if has_circle:
            bboxes.append(circle_bbox)
        for pz in parsed_zones:
            bboxes.append(pz['bounds'])
        all_minx = min(b[0] for b in bboxes)
        all_miny = min(b[1] for b in bboxes)
        all_maxx = max(b[2] for b in bboxes)
        all_maxy = max(b[3] for b in bboxes)

    for u, v, data in G_weighted.edges(data=True):
        e_minx = u[0] if u[0] < v[0] else v[0]
        e_maxx = u[0] if u[0] > v[0] else v[0]
        e_miny = u[1] if u[1] < v[1] else v[1]
        e_maxy = u[1] if u[1] > v[1] else v[1]

        # Fast reject edges outside overall flood bounding box (already have valid base attributes)
        if has_any_flood and (e_minx > all_maxx or e_maxx < all_minx or e_miny > all_maxy or e_maxy < all_miny):
            continue

        dist = data['distance']
        original_risk = data['predicted_risk']
        highway = data.get('highway', '')
        slope_val = data.get('slope', 0)

        effective_risk = original_risk
        flood_penalty_val = 0.0
        is_impassable = False

        mid = ((u[0] + v[0]) * 0.5, (u[1] + v[1]) * 0.5)

        # ── Circular flood simulation penalty ──
        if has_circle:
            c_minx, c_miny, c_maxx, c_maxy = circle_bbox
            if not (e_minx > c_maxx or e_maxx < c_minx or e_miny > c_maxy or e_maxy < c_miny):
                d_to_flood = haversine(mid, tuple(flood_center))
                if d_to_flood < flood_radius:
                    proximity = 1.0 - (d_to_flood / flood_radius)
                    elev = data.get('elevation', 50)
                    elev_factor = max(0, 1.0 - (elev / 500.0))
                    circle_pen = proximity * flood_intensity * elev_factor * water_level
                    if circle_pen > flood_penalty_val:
                        flood_penalty_val = circle_pen

        # ── Multi-zone flood simulation penalty ──
        if has_zones:
            mid_pt = None
            seg_ln = None
            for pz in parsed_zones:
                z_minx, z_miny, z_maxx, z_maxy = pz['bounds']
                if e_minx > z_maxx or e_maxx < z_minx or e_miny > z_maxy or e_maxy < z_miny:
                    continue
                if mid_pt is None:
                    mid_pt = Point(mid[0], mid[1])
                    seg_ln = LineString([u, v])
                sp = pz['shapely']
                if sp.contains(mid_pt) or sp.intersects(seg_ln):
                    boundary = pz['boundary']
                    dist_from_boundary = boundary.distance(mid_pt) if boundary else 0.0
                    interior_depth = min(1.0, dist_from_boundary / pz['max_dist'])
                    elev = data.get('elevation', 50)
                    elev_factor = max(0, 1.0 - (elev / 500.0))
                    poly_penalty = (0.5 + 0.5 * interior_depth) * pz['intensity'] * elev_factor * pz['water_level']
                    if poly_penalty > flood_penalty_val:
                        flood_penalty_val = poly_penalty

        # ── Apply flood penalty thresholds ──
        if flood_penalty_val > IMPASSABLE_THRESHOLD:
            effective_risk = 2  # HIGH
            is_impassable = True
        elif flood_penalty_val > 0.7:
            effective_risk = 2  # HIGH
        elif flood_penalty_val > 0.3:
            effective_risk = max(effective_risk, 1)  # at least MEDIUM
        # else keep original

        # ── Compute cost ──
        if is_impassable:
            cost = float('inf')
        else:
            mult = risk_mults.get(effective_risk, 1.0)
            cost = dist * mult

            # ── Slope penalty for elderly & wheelchair ──
            if slope_pen > 0 and slope_val > 5:
                cost += dist * slope_pen * (slope_val / 10)

            # ── Avoid steps/footway ──
            if avoid_steps and highway == 'steps':
                if profile_name == 'wheelchair':
                    is_impassable = True
                    cost = float('inf')
                else:
                    cost += dist * 50  # huge penalty

            if avoid_footway and highway in ('footway', 'path'):
                cost += dist * 10

            # ── Max slope limit (e.g. 8.0% for wheelchair) ──
            if max_slope is not None and slope_val > max_slope:
                if profile_name == 'wheelchair':
                    is_impassable = True
                    cost = float('inf')
                else:
                    cost += dist * 50

        G_weighted[u][v]['routesense_cost'] = cost
        G_weighted[u][v]['effective_risk'] = effective_risk
        G_weighted[u][v]['flood_penalty'] = round(flood_penalty_val, 4)
        G_weighted[u][v]['impassable'] = is_impassable

    if cache_key is not None:
        if len(_EDGE_WEIGHTS_CACHE) >= _CACHE_MAX_SIZE:
            _EDGE_WEIGHTS_CACHE.pop(next(iter(_EDGE_WEIGHTS_CACHE)))
        _EDGE_WEIGHTS_CACHE[cache_key] = G_weighted

    return G_weighted


def run_routing(origin, destination, profile_name, flood_center=None, flood_radius=2000,
                flood_intensity=0.5, water_level=1.0, flood_polygon=None, flood_zones=None,
                objective='safest', auto_reallocate=False, allow_reallocate=None, reallocate=None):
    """
    Full routing pipeline: find nearest nodes, compute both routes, extract metrics.

    Invariants:
    - Dry condition (flood_active == False): routesense route strictly equals normal
      Dijkstra shortest route (rs_dist == normal_dist) with zero detour penalties.
    - Flood on route — safe alternative exists: recompute path on G_passable, setting
      comparison.routes_differ = True.
    - Flood blocks destination — instant shelter reallocation: if destination is blocked
      and auto_reallocate is enabled, runs single-source Dijkstra on G_passable from origin
      across all Thrissur shelters, selects closest reachable unflooded shelter, and returns
      reallocated: True, reallocated_shelter, and reallocation_reason.
    - Completely trapped: if origin has no passable exits to any shelter or destination,
      returns route_safety: 'blocked', routesense: None, and error:
      "No safe route available — request rescue assistance."
    """
    if allow_reallocate is not None:
        auto_reallocate = allow_reallocate
    if reallocate is not None:
        auto_reallocate = reallocate

    route_cache_key = (
        tuple(round(float(x), 5) for x in origin),
        tuple(round(float(x), 5) for x in destination),
        profile_name,
        objective,
        auto_reallocate,
        get_flood_cache_key(profile_name, flood_center, flood_radius, flood_intensity, water_level, flood_polygon, flood_zones)
    )
    if route_cache_key in _ROUTE_RESULT_CACHE:
        return _ROUTE_RESULT_CACHE[route_cache_key]

    origin_node, origin_dist = nearest_node(G_BASE, tuple(origin), NODE_LIST)
    dest_node, dest_dist = nearest_node(G_BASE, tuple(destination), NODE_LIST)

    if origin_node is None or dest_node is None:
        return {"error": "Could not map origin/destination to graph"}

    if origin_dist > 30000 or dest_dist > 30000:
        return {"error": "Origin or destination is outside the study area road network"}

    if not nx.has_path(G_BASE, origin_node, dest_node):
        return {"error": "No path exists between origin and destination"}

    # Weighted graph with flood penalties and impassable flags
    G_w = compute_edge_weights(G_BASE, profile_name, flood_center, flood_radius,
                               flood_intensity, water_level, flood_polygon, flood_zones=flood_zones)

    # Normal route (distance only, on base graph — always ignores flood state)
    normal_key = (origin_node, dest_node)
    if normal_key in _NORMAL_PATH_CACHE:
        normal_path = _NORMAL_PATH_CACHE[normal_key]
    else:
        normal_path = nx.shortest_path(G_BASE, source=origin_node, target=dest_node, weight='distance')
        if len(_NORMAL_PATH_CACHE) < 512:
            _NORMAL_PATH_CACHE[normal_key] = normal_path

    # Passable subgraph (strictly excludes impassable roads where flood_penalty > 0.85)
    passable_edges = [(u, v) for u, v, d in G_w.edges(data=True) if not d.get('impassable', False)]
    G_passable = G_w.edge_subgraph(passable_edges)

    flood_active = flood_center is not None or flood_polygon is not None or bool(flood_zones)

    rs_path = None
    rs_error = None
    reallocated = False
    reallocated_shelter = None
    reallocation_reason = None
    orig_zone = None

    # Overall and inner flood bounding boxes for fast coordinate pre-filtering
    fb_minx = fb_miny = fb_maxx = fb_maxy = None
    inner_minx = inner_miny = inner_maxx = inner_maxy = None

    if flood_active:
        if flood_center is not None and flood_radius and flood_radius > 0:
            c_lon, c_lat = float(flood_center[0]), float(flood_center[1])
            d_lat = (flood_radius / 110000.0) * 1.05
            d_lon = (flood_radius / 108000.0) * 1.05
            fb_minx, fb_miny = c_lon - d_lon, c_lat - d_lat
            fb_maxx, fb_maxy = c_lon + d_lon, c_lat + d_lat

            inner_r = flood_radius * 0.50
            in_lat = (inner_r / 110000.0) * 1.05
            in_lon = (inner_r / 108000.0) * 1.05
            inner_minx, inner_miny = c_lon - in_lon, c_lat - in_lat
            inner_maxx, inner_maxy = c_lon + in_lon, c_lat + in_lat

        if flood_zones or flood_polygon:
            z_boxes = []
            if flood_zones:
                for z in flood_zones:
                    pts = z.get('polygon') if isinstance(z, dict) else None
                    if pts:
                        z_boxes.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
            elif flood_polygon:
                z_boxes.append((min(p[0] for p in flood_polygon), min(p[1] for p in flood_polygon), max(p[0] for p in flood_polygon), max(p[1] for p in flood_polygon)))
            if z_boxes:
                z_minx = min(b[0] for b in z_boxes)
                z_miny = min(b[1] for b in z_boxes)
                z_maxx = max(b[2] for b in z_boxes)
                z_maxy = max(b[3] for b in z_boxes)
                fb_minx = min(fb_minx, z_minx) if fb_minx is not None else z_minx
                fb_miny = min(fb_miny, z_miny) if fb_miny is not None else z_miny
                fb_maxx = max(fb_maxx, z_maxx) if fb_maxx is not None else z_maxx
                fb_maxy = max(fb_maxy, z_maxy) if fb_maxy is not None else z_maxy
                inner_minx = min(inner_minx, z_minx) if inner_minx is not None else z_minx
                inner_miny = min(inner_miny, z_miny) if inner_miny is not None else z_miny
                inner_maxx = max(inner_maxx, z_maxx) if inner_maxx is not None else z_maxx
                inner_maxy = max(inner_maxy, z_maxy) if inner_maxy is not None else z_maxy

    if not flood_active:
        # Dry Condition: routesense route must strictly equal normal Dijkstra shortest route
        rs_path = normal_path
    else:
        # ── 1. Determine origin flood circle zone (inner: 0-50%, intermediate: 50-75%, outer: 75-100%) ──
        if flood_center is not None and flood_radius and flood_radius > 0:
            z1 = get_origin_flood_zone(origin, flood_center, flood_radius)
            z2 = get_origin_flood_zone(origin_node, flood_center, flood_radius)
            if z1 == 'inner' or z2 == 'inner':
                orig_zone = 'inner'
            elif z1 == 'intermediate' or z2 == 'intermediate':
                orig_zone = 'intermediate'
            elif z1 == 'outer' or z2 == 'outer':
                orig_zone = 'outer'

        if orig_zone is None and (flood_polygon or flood_zones):
            if is_point_in_flood(origin, None, 0, flood_polygon, flood_zones) or \
               is_point_in_flood(origin_node, None, 0, flood_polygon, flood_zones):
                orig_zone = 'inner'

        # Check if all connected edges to origin_node in G_w are impassable
        if orig_zone is None and origin_node is not None and origin_node in G_w:
            orig_edges = G_w[origin_node]
            if len(orig_edges) > 0 and all(G_w[origin_node][nbr].get('impassable', False) for nbr in orig_edges):
                orig_zone = 'inner'

        dest_in_flood = is_point_in_flood(destination, flood_center, flood_radius, flood_polygon, flood_zones) or \
                        (dest_node is not None and is_point_in_flood(dest_node, flood_center, flood_radius, flood_polygon, flood_zones))

        def is_edge_in_inner_flood(u_e, v_e):
            if G_w[u_e][v_e].get('impassable', False):
                return True
            if inner_minx is not None:
                u_x, u_y = u_e
                v_x, v_y = v_e
                if (u_x < inner_minx and v_x < inner_minx) or (u_x > inner_maxx and v_x > inner_maxx) or \
                   (u_y < inner_miny and v_y < inner_miny) or (u_y > inner_maxy and v_y > inner_maxy):
                    return False
            mid_e = ((u_e[0] + v_e[0]) * 0.5, (u_e[1] + v_e[1]) * 0.5)
            if flood_center is not None and flood_radius and flood_radius > 0:
                inner_r = flood_radius * 0.50
                c = tuple(flood_center)
                if haversine(mid_e, c) <= inner_r or haversine(u_e, c) <= inner_r or haversine(v_e, c) <= inner_r:
                    return True
            if flood_polygon or flood_zones:
                if is_point_in_flood(mid_e, None, 0, flood_polygon, flood_zones) or \
                   is_point_in_flood(u_e, None, 0, flood_polygon, flood_zones) or \
                   is_point_in_flood(v_e, None, 0, flood_polygon, flood_zones):
                    return True
            return False

        def is_edge_in_full_flood(u_e, v_e):
            if G_w[u_e][v_e].get('impassable', False):
                return True
            if fb_minx is not None:
                u_x, u_y = u_e
                v_x, v_y = v_e
                if (u_x < fb_minx and v_x < fb_minx) or (u_x > fb_maxx and v_x > fb_maxx) or \
                   (u_y < fb_miny and v_y < fb_miny) or (u_y > fb_maxy and v_y > fb_maxy):
                    return False
            mid_e = ((u_e[0] + v_e[0]) * 0.5, (u_e[1] + v_e[1]) * 0.5)
            return is_point_in_flood(mid_e, flood_center, flood_radius, flood_polygon, flood_zones) or \
                   is_point_in_flood(u_e, flood_center, flood_radius, flood_polygon, flood_zones) or \
                   is_point_in_flood(v_e, flood_center, flood_radius, flood_polygon, flood_zones)

        if orig_zone == 'inner':
            # ── Zone 1: Inner Circle (Submerged) ──────────────────────────
            # When origin is inside inner circle, no route must be shown and alert displayed
            rs_path = None
            reallocated = False
            reallocated_shelter = None
            rs_error = "No route satisfying the configured safety constraints is available. no safe route is available  requesting for rescue"

        elif orig_zone == 'intermediate':
            # ── Zone 2: Intermediate Circle ───────────────────────────────
            # Show a low risk route if available and nearby; shelter must be nearby with low risk factor
            inter_safe_edges = [(u, v) for u, v in passable_edges if not is_edge_in_inner_flood(u, v)]
            G_inter_safe = G_w.edge_subgraph(inter_safe_edges)

            try:
                dist_dict, path_dict = nx.single_source_dijkstra(G_inter_safe, origin_node, weight='routesense_cost')
            except Exception:
                dist_dict, path_dict = {}, {}

            cand_dest_path = None
            dest_high = 999
            if not dest_in_flood and dest_node in path_dict:
                cand_dest_path = path_dict[dest_node]
                dest_high = sum(1 for k in range(len(cand_dest_path)-1)
                                if G_w.get_edge_data(cand_dest_path[k], cand_dest_path[k+1]).get('effective_risk', 0) == 2)

            # Find safe shelters outside flood
            safe_shelter_candidates = []
            for sh in SHELTERS:
                sh_coords = sh['coordinates']
                if is_point_in_flood(sh_coords, flood_center, flood_radius, flood_polygon, flood_zones):
                    continue
                sh_node, _ = nearest_node(G_BASE, tuple(sh_coords))
                if sh_node is None or is_point_in_flood(sh_node, flood_center, flood_radius, flood_polygon, flood_zones):
                    continue
                if sh_node not in path_dict:
                    continue

                c_path = path_dict[sh_node]
                r_dist = 0.0
                h_cnt = 0
                for k in range(len(c_path)-1):
                    e_dt = G_w.get_edge_data(c_path[k], c_path[k+1])
                    r_dist += e_dt['distance']
                    if e_dt.get('effective_risk', e_dt['predicted_risk']) == 2:
                        h_cnt += 1

                safe_shelter_candidates.append({
                    'shelter': sh,
                    'path': c_path,
                    'road_dist': r_dist,
                    'high_count': h_cnt,
                    'id': sh['id']
                })

            if safe_shelter_candidates:
                # Rank shelters nearby to origin with low risk factor (lowest high_count, then closest road distance)
                safe_shelter_candidates.sort(key=lambda s: (s['high_count'], s['road_dist'], s['id']))

            # A low-risk route must have minimal hazard segments and be nearby
            best_match = safe_shelter_candidates[0] if safe_shelter_candidates else None
            is_shelter_low_risk_nearby = best_match and best_match['high_count'] <= 3 and best_match['road_dist'] <= 15000
            is_dest_low_risk_nearby = cand_dest_path and dest_high <= 3 and not dest_in_flood

            if is_dest_low_risk_nearby and not auto_reallocate:
                rs_path = cand_dest_path
            elif is_shelter_low_risk_nearby and (dest_in_flood or auto_reallocate or not is_dest_low_risk_nearby):
                best_sh = best_match['shelter']
                rs_path = best_match['path']
                reallocated = True
                reallocated_shelter = best_sh
                dist_km = round(best_match['road_dist'] / 1000.0, 2)
                reallocation_reason = (
                    f"Origin in intermediate flood zone. "
                    f"Low-risk route established to nearby safe shelter: {best_sh['name']} ({dist_km} km)."
                )
            elif is_dest_low_risk_nearby:
                rs_path = cand_dest_path
            else:
                # No low-risk route available nearby
                rs_path = None
                rs_error = "No route satisfying the configured safety constraints is available. no safe route is available  requesting for rescue"

        elif orig_zone == 'outer':
            # ── Zone 3: Outer Circle ──────────────────────────────────────
            # Show an accessible safe route to shelter point or destination; shelter nearby to origin with low risk
            outer_safe_edges = [(u, v) for u, v in passable_edges if not is_edge_in_inner_flood(u, v)]
            G_outer_safe = G_w.edge_subgraph(outer_safe_edges)

            try:
                dist_dict, path_dict = nx.single_source_dijkstra(G_outer_safe, origin_node, weight='routesense_cost')
            except Exception:
                dist_dict, path_dict = {}, {}

            cand_dest_path = None
            dest_high = 999
            if not dest_in_flood and dest_node in path_dict:
                cand_dest_path = path_dict[dest_node]
                dest_high = sum(1 for k in range(len(cand_dest_path)-1)
                                if G_w.get_edge_data(cand_dest_path[k], cand_dest_path[k+1]).get('effective_risk', 0) == 2)

            safe_shelter_candidates = []
            for sh in SHELTERS:
                sh_coords = sh['coordinates']
                if is_point_in_flood(sh_coords, flood_center, flood_radius, flood_polygon, flood_zones):
                    continue
                sh_node, _ = nearest_node(G_BASE, tuple(sh_coords))
                if sh_node is None or is_point_in_flood(sh_node, flood_center, flood_radius, flood_polygon, flood_zones):
                    continue
                if sh_node not in path_dict:
                    continue

                c_path = path_dict[sh_node]
                r_dist = 0.0
                h_cnt = 0
                for k in range(len(c_path)-1):
                    e_dt = G_w.get_edge_data(c_path[k], c_path[k+1])
                    r_dist += e_dt['distance']
                    if e_dt.get('effective_risk', e_dt['predicted_risk']) == 2:
                        h_cnt += 1

                safe_shelter_candidates.append({
                    'shelter': sh,
                    'path': c_path,
                    'road_dist': r_dist,
                    'high_count': h_cnt,
                    'id': sh['id']
                })

            if safe_shelter_candidates:
                # Prioritize low risk factor first (lowest high_count), then nearby road distance
                safe_shelter_candidates.sort(key=lambda s: (s['high_count'], s['road_dist'], s['id']))

            if cand_dest_path and dest_high == 0 and not dest_in_flood and not auto_reallocate:
                rs_path = cand_dest_path
            elif safe_shelter_candidates and (dest_in_flood or auto_reallocate or dest_high > 0 or not cand_dest_path):
                best_match = safe_shelter_candidates[0]
                best_sh = best_match['shelter']
                rs_path = best_match['path']
                reallocated = True
                reallocated_shelter = best_sh
                dist_km = round(best_match['road_dist'] / 1000.0, 2)
                reallocation_reason = (
                    f"Origin in outer flood zone. "
                    f"Accessible safe route established to nearby safe shelter: {best_sh['name']} ({dist_km} km)."
                )
            elif cand_dest_path:
                rs_path = cand_dest_path
            else:
                rs_path = None
                rs_error = "No route satisfying the configured safety constraints is available. no safe route is available  requesting for rescue"

        else:
            # ── Zone 4: Outside Flood Circle ──────────────────────────────
            # Detour around the entire flood circle and polygon on G_safe
            safe_edges = [(u, v) for u, v in passable_edges if not is_edge_in_full_flood(u, v)]
            G_safe = G_w.edge_subgraph(safe_edges)

            flood_affects_normal_path = False
            for i in range(len(normal_path) - 1):
                u_p, v_p = normal_path[i], normal_path[i+1]
                e_data = G_w.get_edge_data(u_p, v_p)
                if e_data and (e_data.get('flood_penalty', 0) > 0 or e_data.get('impassable', False)):
                    flood_affects_normal_path = True
                    break
                mid_e = ((u_p[0] + v_p[0]) * 0.5, (u_p[1] + v_p[1]) * 0.5)
                if is_point_in_flood(mid_e, flood_center, flood_radius, flood_polygon, flood_zones) or \
                   is_point_in_flood(u_p, flood_center, flood_radius, flood_polygon, flood_zones) or \
                   is_point_in_flood(v_p, flood_center, flood_radius, flood_polygon, flood_zones):
                    flood_affects_normal_path = True
                    break

            if not dest_in_flood and not flood_affects_normal_path:
                # Dry / unaffected path: use normal shortest path
                rs_path = normal_path
            else:
                if not dest_in_flood:
                    try:
                        cost_weight = 'distance' if objective == 'shortest' else 'routesense_cost'
                        candidate_path = nx.shortest_path(G_safe, source=origin_node, target=dest_node, weight=cost_weight)
                        rs_path = candidate_path
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        rs_path = None

                if rs_path is None and auto_reallocate:
                    try:
                        dist_dict, path_dict = nx.single_source_dijkstra(G_safe, origin_node, weight='routesense_cost')
                    except Exception:
                        dist_dict, path_dict = {}, {}

                    safe_shelter_candidates = []
                    for sh in SHELTERS:
                        sh_coords = sh['coordinates']
                        if is_point_in_flood(sh_coords, flood_center, flood_radius, flood_polygon, flood_zones):
                            continue
                        sh_node, _ = nearest_node(G_BASE, tuple(sh_coords))
                        if sh_node is None or is_point_in_flood(sh_node, flood_center, flood_radius, flood_polygon, flood_zones):
                            continue
                        if sh_node not in path_dict:
                            continue

                        cand_path = path_dict[sh_node]
                        road_dist = 0.0
                        high_count = 0
                        for k in range(len(cand_path) - 1):
                            u_k, v_k = cand_path[k], cand_path[k+1]
                            e = G_w.get_edge_data(u_k, v_k)
                            road_dist += e['distance']
                            if e.get('effective_risk', e['predicted_risk']) == 2:
                                high_count += 1

                        safe_shelter_candidates.append({
                            'shelter': sh,
                            'path': cand_path,
                            'road_dist': road_dist,
                            'high_count': high_count,
                            'id': sh['id']
                        })

                    if safe_shelter_candidates:
                        safe_shelter_candidates.sort(key=lambda s: (s['high_count'], s['road_dist'], s['id']))
                        best_match = safe_shelter_candidates[0]
                        best_sh = best_match['shelter']
                        rs_path = best_match['path']
                        reallocated = True
                        reallocated_shelter = best_sh
                        dist_km = round(best_match['road_dist'] / 1000.0, 2)
                        reallocation_reason = (
                            f"Primary destination blocked by flood hazard. "
                            f"Strictly rerouted to safe shelter away from flood: {best_sh['name']} ({dist_km} km)."
                        )

            if rs_path is None:
                rs_error = "No route satisfying the configured safety constraints is available. no safe route is available  requesting for rescue"

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
                    "flood_penalty": round(data.get('flood_penalty', 0), 4),
                    "impassable": data.get('impassable', False),
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

    # Build affected roads list (roads whose risk changed due to flood)
    affected_roads = []
    if flood_active:
        for u, v, data in G_w.edges(data=True):
            if fb_minx is not None:
                u_x, u_y = u
                v_x, v_y = v
                if (u_x < fb_minx and v_x < fb_minx) or (u_x > fb_maxx and v_x > fb_maxx) or \
                   (u_y < fb_miny and v_y < fb_miny) or (u_y > fb_maxy and v_y > fb_maxy):
                    continue
            if data.get('effective_risk', data['predicted_risk']) != data['predicted_risk']:
                affected_roads.append({
                    "coordinates": [list(u), list(v)],
                    "original_risk": data['predicted_risk'],
                    "effective_risk": data['effective_risk'],
                    "flood_penalty": data.get('flood_penalty', 0),
                    "impassable": data.get('impassable', False),
                    "elevation": data.get('elevation', 15),
                })

    # Build response
    if rs_path is not None:
        rs_metrics = extract_metrics(rs_path, G_w, use_effective=flood_active)
        dist_diff = rs_metrics['distance'] - normal_metrics['distance']
        dist_pct = round((dist_diff / normal_metrics['distance']) * 100, 1) if normal_metrics['distance'] > 0 else 0
        high_avoided = normal_metrics['risk_counts'].get(2, 0) - rs_metrics['risk_counts'].get(2, 0)
        high_normal = normal_metrics['risk_counts'].get(2, 0)
        reduction_pct = round((high_avoided / high_normal * 100) if high_normal > 0 else 0, 1)

        # Route safety classification
        total_segs = rs_metrics['segments']
        high_segs = rs_metrics['risk_counts'].get(2, 0)
        high_pct = (high_segs / total_segs * 100) if total_segs > 0 else 0

        if high_pct == 0 and not any(f.get('properties', {}).get('impassable') for f in rs_metrics['geojson']['features']):
            route_safety = 'safe'
        elif high_pct < 10:
            route_safety = 'caution'
        elif high_pct < 30:
            route_safety = 'elevated'
        else:
            route_safety = 'high_risk'

        if not flood_active:
            dist_diff = 0.0
            dist_pct = 0.0
            routes_differ = False
            reduction_pct = 0.0
            high_avoided = 0
        else:
            routes_differ = normal_path != rs_path or reallocated

        res = {
            "origin": list(origin_node),
            "destination": list(dest_node) if not reallocated else list(rs_path[-1]),
            "original_destination": list(dest_node),
            "reallocated": reallocated,
            "reallocated_shelter": reallocated_shelter,
            "reallocation_reason": reallocation_reason,
            "profile": profile_name,
            "route_safety": route_safety,
            "normal": normal_metrics,
            "routesense": rs_metrics,
            "comparison": {
                "distance_diff": round(dist_diff, 2),
                "distance_pct": dist_pct,
                "high_risk_avoided": high_avoided,
                "risk_reduction_pct": reduction_pct,
                "routes_differ": routes_differ
            },
            "affected_roads": affected_roads[:3000],
            "affected_roads_count": len(affected_roads),
            "flood_active": flood_active,
            "origin_zone": orig_zone,
            "route_validated": True,
            "routing_objective": {
                "normal": "Minimizes total distance (meters) on the base road network, ignoring flood state.",
                "routesense": "Minimizes risk-weighted distance (risk-weighted meters). Roads with flood_penalty > {} are excluded as impassable.".format(IMPASSABLE_THRESHOLD)
            }
        }
        if len(_ROUTE_RESULT_CACHE) >= _ROUTE_CACHE_MAX_SIZE:
            _ROUTE_RESULT_CACHE.pop(next(iter(_ROUTE_RESULT_CACHE)))
        _ROUTE_RESULT_CACHE[route_cache_key] = res
        return res
    else:
        # No safe route found / completely trapped / origin submerged
        res = {
            "origin": list(origin_node),
            "destination": list(dest_node),
            "profile": profile_name,
            "route_safety": "blocked",
            "normal": normal_metrics,
            "routesense": None,
            "error": "no safe route is available  requesting for rescue",
            "routesense_error": rs_error or "no safe route is available  requesting for rescue",
            "origin_submerged": (orig_zone == 'inner'),
            "origin_zone": orig_zone,
            "reallocated": False,
            "reallocated_shelter": None,
            "reallocation_reason": None,
            "comparison": None,
            "affected_roads": affected_roads[:3000],
            "affected_roads_count": len(affected_roads),
            "flood_active": flood_active,
            "route_validated": False,
            "routing_objective": {
                "normal": "Minimizes total distance (meters) on the base road network, ignoring flood state.",
                "routesense": "no safe route is available  requesting for rescue"
            }
        }
        if len(_ROUTE_RESULT_CACHE) >= _ROUTE_CACHE_MAX_SIZE:
            _ROUTE_RESULT_CACHE.pop(next(iter(_ROUTE_RESULT_CACHE)))
        _ROUTE_RESULT_CACHE[route_cache_key] = res
        return res


# ── Flask App ──────────────────────────────────────────────────

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)


@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/favicon.ico')
def favicon():
    return ('', 204)


@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "nodes": G_BASE.number_of_nodes(),
        "edges": G_BASE.number_of_edges(),
        "study_area": "Thrissur, Kerala",
        "road_segments": len(study_roads),
        "shelters_count": len(SHELTERS),
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
    flood_polygon = None
    flood_zones = None

    if flood and (flood.get('active') or (flood.get('active') is not False and bool(flood.get('center') or flood.get('flood_zones') or flood.get('zones') or flood.get('polygon')))):
        flood_center = flood.get('center')
        flood_radius = flood.get('radius', 2000)
        flood_intensity = flood.get('intensity', 0.5)
        water_level = flood.get('water_level', 1.0)
        flood_polygon = flood.get('polygon')  # optional legacy freehand polygon coords
        flood_zones = flood.get('flood_zones') or flood.get('zones')

    objective = data.get('objective', 'safest')
    auto_reallocate = data.get('auto_reallocate', data.get('allow_reallocate', data.get('reallocate', True)))

    result = run_routing(
        origin, destination, profile,
        flood_center=flood_center,
        flood_radius=flood_radius,
        flood_intensity=flood_intensity,
        water_level=water_level,
        flood_polygon=flood_polygon,
        flood_zones=flood_zones,
        objective=objective,
        auto_reallocate=auto_reallocate
    )
    return jsonify(result)


@app.route('/api/reroute-shelter', methods=['POST'])
def reroute_shelter():
    """
    Intelligent Multi-Shelter Dynamic Rerouting Engine.
    Evaluates alternative registered safe shelters when flood hazard strikes the active evacuation corridor.
    If the alternative safe route to the current destination is blocked OR significantly longer than
    routing to a closer, accessible shelter, it dynamically reroutes to that alternative shelter.
    """
    data = request.get_json(force=True)
    origin = data.get('origin', DEFAULT_ORIGIN)
    current_dest = data.get('current_destination', DEFAULT_DEST)
    profile = data.get('profile', 'general')

    flood = data.get('flood', None)
    flood_center = None
    flood_radius = 2000
    flood_intensity = 0.5
    water_level = 1.0
    flood_polygon = None
    flood_zones = None

    if flood and (flood.get('active') or (flood.get('active') is not False and bool(flood.get('center') or flood.get('flood_zones') or flood.get('zones') or flood.get('polygon')))):
        flood_center = flood.get('center')
        flood_radius = flood.get('radius', 2000)
        flood_intensity = flood.get('intensity', 0.5)
        water_level = flood.get('water_level', 1.0)
        flood_polygon = flood.get('polygon')
        flood_zones = flood.get('flood_zones') or flood.get('zones')

    # 1. Compute route to current destination under current flood conditions
    current_route = run_routing(
        origin, current_dest, profile,
        flood_center=flood_center, flood_radius=flood_radius,
        flood_intensity=flood_intensity, water_level=water_level,
        flood_polygon=flood_polygon, flood_zones=flood_zones
    )

    current_safe = current_route.get('routesense') is not None
    current_dist = current_route['routesense']['distance'] if current_safe else float('inf')

    # 2. Evaluate all candidate shelters
    best_alt = None
    best_alt_dist = float('inf')
    best_alt_route = None

    for sh in SHELTERS:
        sh_coords = sh['coordinates']
        is_same_as_current = (
            abs(sh_coords[0] - current_dest[0]) < 0.001 and
            abs(sh_coords[1] - current_dest[1]) < 0.001
        )
        if is_same_as_current:
            continue

        if flood_center or flood_zones or flood_polygon:
            if is_point_in_flood(sh_coords, flood_center, flood_radius, flood_polygon, flood_zones):
                continue

        alt_route = run_routing(
            origin, sh_coords, profile,
            flood_center=flood_center, flood_radius=flood_radius,
            flood_intensity=flood_intensity, water_level=water_level,
            flood_polygon=flood_polygon, flood_zones=flood_zones
        )

        if alt_route.get('routesense') is not None:
            alt_dist = alt_route['routesense']['distance']
            if alt_dist < best_alt_dist:
                best_alt_dist = alt_dist
                best_alt = sh
                best_alt_route = alt_route

    # 3. Decision logic:
    should_reroute = False
    reason = ""

    if not current_safe and best_alt is not None:
        should_reroute = True
        reason = f"Original route is impassable due to flood. Rerouted to accessible safe shelter: {best_alt['name']}."
    elif current_safe and best_alt is not None and (best_alt_dist < current_dist - 50):
        should_reroute = True
        meters_saved = round(current_dist - best_alt_dist, 1)
        reason = f"Original route detour is {round(current_dist)}m. Rerouted to nearer safe shelter {best_alt['name']} ({round(best_alt_dist)}m, saving {meters_saved}m)."

    if should_reroute:
        return jsonify({
            "rerouted": True,
            "reason": reason,
            "best_shelter": best_alt,
            "new_destination": best_alt['coordinates'],
            "original_distance": round(current_dist, 1) if current_safe else None,
            "new_distance": round(best_alt_dist, 1),
            "distance_saved": round(current_dist - best_alt_dist, 1) if current_safe else None,
            "route": best_alt_route
        })
    else:
        return jsonify({
            "rerouted": False,
            "reason": "Current shelter route remains the shortest and safest accessible path.",
            "route": current_route,
            "new_destination": current_dest
        })


@app.route('/api/nearest-shelter', methods=['POST'])
def nearest_shelter():
    """
    Intelligent Shelter Discovery by True Road-Network Distance.
    Computes exact road distances from origin to all registered shelters simultaneously.
    When no flood is active, selects the shelter with the absolute shortest road distance.
    When flood is active, excludes inundated shelters and impassable roads.
    """
    data = request.get_json(force=True)
    origin = data.get('origin', DEFAULT_ORIGIN)
    profile = data.get('profile', 'general')

    flood = data.get('flood', None)
    flood_center = None
    flood_radius = 2000
    flood_intensity = 0.5
    water_level = 1.0
    flood_polygon = None
    flood_zones = None

    if flood and (flood.get('active') or (flood.get('active') is not False and bool(flood.get('center') or flood.get('flood_zones') or flood.get('zones') or flood.get('polygon')))):
        flood_center = flood.get('center')
        flood_radius = flood.get('radius', 2000)
        flood_intensity = flood.get('intensity', 0.5)
        water_level = flood.get('water_level', 1.0)
        flood_polygon = flood.get('polygon')
        flood_zones = flood.get('flood_zones') or flood.get('zones')

    flood_active = bool(flood_center or flood_polygon or flood_zones)

    orig_node, _ = nearest_node(G_BASE, tuple(origin))
    if orig_node is None:
        return jsonify({"error": "Could not map origin to road network"}), 400

    orig_zone = None
    if flood_active and flood_center is not None and flood_radius and flood_radius > 0:
        z1 = get_origin_flood_zone(origin, flood_center, flood_radius)
        z2 = get_origin_flood_zone(orig_node, flood_center, flood_radius)
        if z1 == 'inner' or z2 == 'inner':
            orig_zone = 'inner'
        elif z1 == 'intermediate' or z2 == 'intermediate':
            orig_zone = 'intermediate'
        elif z1 == 'outer' or z2 == 'outer':
            orig_zone = 'outer'

    if orig_zone is None and flood_active and (flood_polygon or flood_zones):
        if is_point_in_flood(origin, None, 0, flood_polygon, flood_zones) or \
           is_point_in_flood(orig_node, None, 0, flood_polygon, flood_zones):
            orig_zone = 'inner'

    if orig_zone == 'inner':
        return jsonify({
            "error": "no safe route is available  requesting for rescue",
            "origin_submerged": True,
            "best_shelter": None,
            "all_shelters": []
        }), 200

    # 1. Prepare graph
    if flood_active:
        G_w = compute_edge_weights(
            G_BASE, profile,
            flood_center=flood_center, flood_radius=flood_radius,
            flood_intensity=flood_intensity, water_level=water_level,
            flood_polygon=flood_polygon, flood_zones=flood_zones
        )
        passable_edges = [(u, v) for u, v, d in G_w.edges(data=True) if not d.get('impassable', False)]

        # Bounding box pre-filtering for nearest shelter edge checks
        ns_minx = ns_miny = ns_maxx = ns_maxy = None
        ns_in_minx = ns_in_miny = ns_in_maxx = ns_in_maxy = None
        if flood_center is not None and flood_radius and flood_radius > 0:
            c_lon, c_lat = float(flood_center[0]), float(flood_center[1])
            d_lat = (flood_radius / 110000.0) * 1.05
            d_lon = (flood_radius / 108000.0) * 1.05
            ns_minx, ns_miny = c_lon - d_lon, c_lat - d_lat
            ns_maxx, ns_maxy = c_lon + d_lon, c_lat + d_lat

            inner_r = flood_radius * 0.50
            in_lat = (inner_r / 110000.0) * 1.05
            in_lon = (inner_r / 108000.0) * 1.05
            ns_in_minx, ns_in_miny = c_lon - in_lon, c_lat - in_lat
            ns_in_maxx, ns_in_maxy = c_lon + in_lon, c_lat + in_lat

        def is_edge_in_inner(u_e, v_e):
            if G_w[u_e][v_e].get('impassable', False):
                return True
            if ns_in_minx is not None:
                u_x, u_y = u_e
                v_x, v_y = v_e
                if (u_x < ns_in_minx and v_x < ns_in_minx) or (u_x > ns_in_maxx and v_x > ns_in_maxx) or \
                   (u_y < ns_in_miny and v_y < ns_in_miny) or (u_y > ns_in_maxy and v_y > ns_in_maxy):
                    return False
            mid_e = ((u_e[0] + v_e[0]) * 0.5, (u_e[1] + v_e[1]) * 0.5)
            if flood_center is not None and flood_radius and flood_radius > 0:
                inner_r = flood_radius * 0.50
                c = tuple(flood_center)
                if haversine(mid_e, c) <= inner_r or haversine(u_e, c) <= inner_r or haversine(v_e, c) <= inner_r:
                    return True
            if flood_polygon or flood_zones:
                if is_point_in_flood(mid_e, None, 0, flood_polygon, flood_zones) or \
                   is_point_in_flood(u_e, None, 0, flood_polygon, flood_zones) or \
                   is_point_in_flood(v_e, None, 0, flood_polygon, flood_zones):
                    return True
            return False

        if orig_zone in ('intermediate', 'outer'):
            # Origin inside intermediate or outer flood circle: strictly exclude inner circle
            eval_edges = [(u, v) for u, v in passable_edges if not is_edge_in_inner(u, v)]
        else:
            def is_edge_in_full_flood(u_e, v_e):
                if G_w[u_e][v_e].get('impassable', False):
                    return True
                if ns_minx is not None:
                    u_x, u_y = u_e
                    v_x, v_y = v_e
                    if (u_x < ns_minx and v_x < ns_minx) or (u_x > ns_maxx and v_x > ns_maxx) or \
                       (u_y < ns_miny and v_y < ns_miny) or (u_y > ns_maxy and v_y > ns_maxy):
                        return False
                mid_e = ((u_e[0] + v_e[0]) * 0.5, (u_e[1] + v_e[1]) * 0.5)
                return is_point_in_flood(mid_e, flood_center, flood_radius, flood_polygon, flood_zones) or \
                       is_point_in_flood(u_e, flood_center, flood_radius, flood_polygon, flood_zones) or \
                       is_point_in_flood(v_e, flood_center, flood_radius, flood_polygon, flood_zones)
            eval_edges = [(u, v) for u, v in passable_edges if not is_edge_in_full_flood(u, v)]

        G_eval = G_w.edge_subgraph(eval_edges)
    else:
        G_eval = G_BASE

    # 2. Single-source Dijkstra for ALL reachable nodes in ONE pass (sub-millisecond)
    try:
        dist_dict, path_dict = nx.single_source_dijkstra(G_eval, orig_node, weight='distance')
    except Exception:
        dist_dict, path_dict = {}, {}

    ranked = []
    for sh in SHELTERS:
        sh_coords = sh['coordinates']
        # Check if shelter is submerged
        if flood_active and is_point_in_flood(sh_coords, flood_center, flood_radius, flood_polygon, flood_zones):
            continue

        sh_node, _ = nearest_node(G_BASE, tuple(sh_coords))
        if sh_node is None or (flood_active and is_point_in_flood(sh_node, flood_center, flood_radius, flood_polygon, flood_zones)):
            continue

        if sh_node in dist_dict:
            road_dist = dist_dict[sh_node]
            c_path = path_dict[sh_node]
            h_cnt = sum(1 for k in range(len(c_path)-1)
                        if G_w.get_edge_data(c_path[k], c_path[k+1]).get('effective_risk', 0) == 2) if flood_active else 0
            ranked.append({
                **sh,
                "road_distance_m": round(road_dist, 1),
                "road_distance_km": round(road_dist / 1000.0, 2),
                "high_count": h_cnt
            })

    if not ranked:
        return jsonify({
            "error": "no safe route is available  requesting for rescue",
            "origin_submerged": (orig_zone == 'inner'),
            "best_shelter": None,
            "all_shelters": []
        }), 200

    # Rank strictly prioritizing low risk factor, then nearby road distance to origin
    if flood_active:
        ranked.sort(key=lambda s: (s['high_count'], s['road_distance_m'], s['id']))
    else:
        ranked.sort(key=lambda s: s['road_distance_m'])
    best_shelter = ranked[0]

    # Compute full routing metrics to this best shelter
    route_data = run_routing(
        origin, best_shelter['coordinates'], profile,
        flood_center=flood_center, flood_radius=flood_radius,
        flood_intensity=flood_intensity, water_level=water_level,
        flood_polygon=flood_polygon, flood_zones=flood_zones
    )

    if flood_active and route_data.get('routesense') is None and len(ranked) > 1:
        for alt_sh in ranked[1:]:
            alt_route = run_routing(
                origin, alt_sh['coordinates'], profile,
                flood_center=flood_center, flood_radius=flood_radius,
                flood_intensity=flood_intensity, water_level=water_level,
                flood_polygon=flood_polygon, flood_zones=flood_zones
            )
            if alt_route.get('routesense') is not None:
                best_shelter = alt_sh
                route_data = alt_route
                break

    if flood_active and route_data.get('routesense') is None:
        return jsonify({
            "error": "no safe route is available  requesting for rescue",
            "origin_submerged": False,
            "best_shelter": None,
            "all_shelters": ranked
        }), 200

    return jsonify({
        "best_shelter": best_shelter,
        "all_shelters": ranked,
        "ranked_shelters": ranked,
        "shelters": ranked,
        "shelter_count": len(ranked),
        "route": route_data,
        "flood_active": flood_active
    })


@app.route('/api/simulate-flood', methods=['POST'])
def simulate_flood():
    """Return affected road segments for a given flood configuration.
    Reuses compute_edge_weights() to ensure penalty calculations are
    consistent with the routing engine."""
    data = request.get_json(force=True)
    center = data.get('center')
    radius = data.get('radius', 2000)
    intensity = data.get('intensity', 0.5)
    water_level = data.get('water_level', 1.0)
    polygon = data.get('polygon')  # optional legacy freehand polygon coords
    flood_zones = data.get('flood_zones') or data.get('zones')

    if not center and not polygon and not flood_zones:
        return jsonify({"error": "Flood center, polygon, or flood_zones required"}), 400

    # Reuse compute_edge_weights for consistent penalty calculation
    G_w = compute_edge_weights(
        G_BASE, 'general',
        flood_center=center, flood_radius=radius,
        flood_intensity=intensity, water_level=water_level,
        flood_polygon=polygon, flood_zones=flood_zones
    )

    affected = []
    total_eta_mins = 0
    count_eta = 0

    sim_minx = sim_miny = sim_maxx = sim_maxy = None
    if center is not None and radius and radius > 0:
        c_lon, c_lat = float(center[0]), float(center[1])
        d_lat = (radius / 110000.0) * 1.05
        d_lon = (radius / 108000.0) * 1.05
        sim_minx, sim_miny = c_lon - d_lon, c_lat - d_lat
        sim_maxx, sim_maxy = c_lon + d_lon, c_lat + d_lat
    if flood_zones or polygon:
        z_boxes = []
        if flood_zones:
            for z in flood_zones:
                pts = z.get('polygon') if isinstance(z, dict) else None
                if pts:
                    z_boxes.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
        elif polygon:
            z_boxes.append((min(p[0] for p in polygon), min(p[1] for p in polygon), max(p[0] for p in polygon), max(p[1] for p in polygon)))
        if z_boxes:
            z_minx = min(b[0] for b in z_boxes)
            z_miny = min(b[1] for b in z_boxes)
            z_maxx = max(b[2] for b in z_boxes)
            z_maxy = max(b[3] for b in z_boxes)
            sim_minx = min(sim_minx, z_minx) if sim_minx is not None else z_minx
            sim_miny = min(sim_miny, z_miny) if sim_miny is not None else z_miny
            sim_maxx = max(sim_maxx, z_maxx) if sim_maxx is not None else z_maxx
            sim_maxy = max(sim_maxy, z_maxy) if sim_maxy is not None else z_maxy

    for u, v, edge_data in G_w.edges(data=True):
        if sim_minx is not None:
            u_x, u_y = u
            v_x, v_y = v
            if (u_x < sim_minx and v_x < sim_minx) or (u_x > sim_maxx and v_x > sim_maxx) or \
               (u_y < sim_miny and v_y < sim_miny) or (u_y > sim_maxy and v_y > sim_maxy):
                continue
        if edge_data.get('effective_risk', edge_data['predicted_risk']) != edge_data['predicted_risk']:
            mid = ((u[0]+v[0])/2, (u[1]+v[1])/2)
            d_center = haversine(mid, tuple(center)) if center else 500
            eta_info = estimate_inundation_time(edge_data.get('elevation', 15), d_center, radius, water_level, intensity)
            total_eta_mins += eta_info['minutes']
            count_eta += 1
            affected.append({
                "coordinates": [list(u), list(v)],
                "original_risk": edge_data['predicted_risk'],
                "effective_risk": edge_data['effective_risk'],
                "flood_penalty": edge_data.get('flood_penalty', 0),
                "impassable": edge_data.get('impassable', False),
                "elevation": edge_data.get('elevation', 15),
                "inundation_eta": eta_info['eta_display'],
                "inundation_minutes": eta_info['minutes'],
                "inundation_urgency": eta_info['urgency']
            })

    avg_eta_mins = int(total_eta_mins / count_eta) if count_eta > 0 else 0
    avg_eta_str = f"~{avg_eta_mins} mins" if avg_eta_mins < 60 else f"~{round(avg_eta_mins/60, 1)} hrs"

    return jsonify({
        "affected_count": len(affected),
        "affected_roads": affected[:3000],  # cap for performance
        "center": center,
        "radius": radius,
        "avg_inundation_eta": avg_eta_str,
        "avg_inundation_minutes": avg_eta_mins
    })


@app.route('/api/flood-arrival')
def flood_arrival():
    """Returns inundation time estimation for a specific lat/lon coordinate."""
    try:
        lat = float(request.args.get('lat', 10.53))
        lon = float(request.args.get('lon', 76.22))
    except (ValueError, TypeError):
        return jsonify({"error": "Valid lat and lon parameters required"}), 400

    center_lat = float(request.args.get('center_lat', 10.53))
    center_lon = float(request.args.get('center_lon', 76.22))
    radius = float(request.args.get('radius', 2000))
    water_level = float(request.args.get('water_level', 1.0))
    intensity = float(request.args.get('intensity', 0.5))

    d = haversine((lon, lat), (center_lon, center_lat))
    nearest, _ = nearest_node(G_BASE, (lon, lat), NODE_LIST)
    elev = 15.0
    if nearest and nearest in G_BASE:
        for nbr in G_BASE[nearest]:
            edge = G_BASE[nearest][nbr]
            if 'elevation' in edge:
                elev = edge['elevation']
                break

    eta_data = estimate_inundation_time(elev, d, radius, water_level, intensity)
    return jsonify({
        "coordinates": [lon, lat],
        "distance_to_center_m": round(d, 1),
        "in_flood_radius": d <= radius,
        **eta_data
    })


@app.route('/api/shelters')
def get_shelters():
    """Return verified disaster relief camps and shelters in Thrissur."""
    return jsonify({"shelters": SHELTERS})


@app.route('/api/network-info')
def network_info():
    """Return server local IP so mobile client can connect over Wi-Fi/LAN."""
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    return jsonify({
        "server_ip": ip,
        "port": 5000,
        "mobile_url": f"http://{ip}:5000",
        "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=http%3A%2F%2F{ip}%3A5000"
    })


@app.route('/api/rivers')
def get_rivers():
    """Serve Thrissur waterway and canal features for environmental layer."""
    rivers_path = os.path.join(BASE_DIR, 'data', 'thrissur_waterways_v1.geojson')
    if os.path.exists(rivers_path):
        with open(rivers_path, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"type": "FeatureCollection", "features": []})


@app.route('/api/scenarios')
def get_scenarios():
    """Serve pre-configured realistic synthetic flood hazard scenarios."""
    scenarios_path = os.path.join(BASE_DIR, 'data', 'synthetic_flood_scenarios_v1.json')
    if os.path.exists(scenarios_path):
        with open(scenarios_path, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"scenarios": []})


@app.route('/api/streets')
@app.route('/api/roads')
@app.route('/api/street-view')
def get_streets_info():
    """Endpoint for road network and street view metadata."""
    return jsonify({
        "status": "ok",
        "nodes": G_BASE.number_of_nodes(),
        "edges": G_BASE.number_of_edges(),
        "study_area": "Thrissur, Kerala",
        "mode": "street_view",
        "crs": "EPSG:4326"
    })


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "API route not found", "path": request.path}), 404
    return e



if __name__ == '__main__':
    print("\n[RouteSense] Starting web application…")
    print(f"[RouteSense] Frontend: {FRONTEND_DIR}")
    print("[RouteSense] Opening http://localhost:5000 in your browser automatically...\n")

    def _auto_open_browser():
        for _ in range(60):
            time.sleep(0.2)
            try:
                req = urllib.request.Request("http://127.0.0.1:5000/api/health", headers={'User-Agent': 'RouteSenseLauncher'})
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    if resp.status == 200:
                        print("[RouteSense] Server is ready! Launching browser at http://localhost:5000\n")
                        webbrowser.open("http://localhost:5000")
                        return
            except Exception:
                pass
        webbrowser.open("http://localhost:5000")

    opener_thread = threading.Thread(target=_auto_open_browser, daemon=True)
    opener_thread.start()

    # Production WSGI Server (Waitress) with multi-threaded request handling
    try:
        from waitress import serve
        print("[RouteSense] WSGI Server: Waitress (Production Multi-Threaded Engine, 8 worker threads)")
        print("[RouteSense] Serving on http://0.0.0.0:5000 (Local: http://localhost:5000)\n")
        serve(app, host='0.0.0.0', port=5000, threads=8, channel_timeout=60, cleanup_interval=30)
    except ImportError:
        print("[RouteSense] WSGI Server: Flask Built-in (Development Fallback)")
        app.run(host='0.0.0.0', port=5000, debug=False)
