import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, Point
import math
import os
import json
import pandas as pd
import argparse

def distance_meters(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    lat = math.radians((lat1 + lat2) / 2)
    x = math.radians(lon2 - lon1) * math.cos(lat)
    y = math.radians(lat2 - lat1)
    earth_radius = 6371000
    return earth_radius * math.sqrt(x * x + y * y)

def get_nearest_node(G, point):
    # point is (lon, lat)
    min_dist = float('inf')
    nearest = None
    for node in G.nodes():
        dist = distance_meters(point, node)
        if dist < min_dist:
            min_dist = dist
            nearest = node
    return nearest

def main():
    parser = argparse.ArgumentParser(description="RouteSense AI Risk-Aware Routing")
    parser.add_argument("--low", type=float, default=1.0, help="LOW risk multiplier")
    parser.add_argument("--medium", type=float, default=1.5, help="MEDIUM risk multiplier")
    parser.add_argument("--high", type=float, default=3.0, help="HIGH risk multiplier")
    parser.add_argument("--origin", type=str, default="76.18,10.49", help="Origin lon,lat")
    parser.add_argument("--dest", type=str, default="76.25,10.57", help="Destination lon,lat")
    args = parser.parse_args()

    risk_mults = {0: args.low, 1: args.medium, 2: args.high}
    origin_pt = tuple(map(float, args.origin.split(',')))
    dest_pt = tuple(map(float, args.dest.split(',')))

    print("================================================================")
    print("ROUTE SENSE AI - RISK-AWARE ROUTING PROTOTYPE")
    print("================================================================")

    # 1. Load GeoJSON
    geojson_path = 'outputs/routesense_road_risk.geojson'
    print(f"Loading {geojson_path}...")
    try:
        roads = gpd.read_file(geojson_path)
    except Exception as e:
        print(f"Failed to load GeoJSON: {e}")
        return

    # 2. Subset to Study Area (Thrissur test area)
    min_lon, max_lon = 76.17, 76.26
    min_lat, max_lat = 10.48, 10.58
    
    print(f"Subsetting to Study Area (Thrissur): lon {min_lon}-{max_lon}, lat {min_lat}-{max_lat}")
    study_roads = roads.cx[min_lon:max_lon, min_lat:max_lat].copy()
    print(f"Study area road segments: {len(study_roads)}")

    # 3. Build Graph
    print("Building routing graph...")
    G = nx.Graph()

    for idx, road in study_roads.iterrows():
        geometry = road.geometry
        if not isinstance(geometry, LineString):
            continue
            
        coords = list(geometry.coords)
        risk = int(road.get("predicted_risk", 0))
        mult = risk_mults.get(risk, 1.0)
        
        for i in range(len(coords) - 1):
            start = coords[i]
            end = coords[i + 1]
            dist = distance_meters(start, end)
            
            rs_cost = dist * mult
            
            G.add_edge(
                start, end,
                distance=dist,
                routesense_cost=rs_cost,
                osm_id=road.get("osm_id"),
                highway=road.get("highway"),
                name=road.get("name"),
                predicted_risk=risk,
                risk_label=road.get("risk_label"),
                low_prob=road.get("low_prob"),
                medium_prob=road.get("medium_prob"),
                high_prob=road.get("high_prob"),
                elevation=road.get("elevation"),
                slope=road.get("slope"),
                rainfall=road.get("rainfall"),
                dist_water=road.get("dist_water")
            )

    print(f"Graph created: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    if G.number_of_nodes() == 0:
        print("Error: Graph is empty. Exiting.")
        return

    # 4. Find nearest nodes to origin/dest
    print(f"Mapping Origin {origin_pt} and Dest {dest_pt} to graph nodes...")
    start_node = get_nearest_node(G, origin_pt)
    end_node = get_nearest_node(G, dest_pt)
    print(f"Origin Node: {start_node}")
    print(f"Dest Node: {end_node}")

    if not nx.has_path(G, start_node, end_node):
        print("Error: No path exists between origin and destination in this graph component.")
        return

    # 5. Routing
    print("Calculating Normal Route (minimizing distance)...")
    normal_path = nx.shortest_path(G, source=start_node, target=end_node, weight="distance")
    
    print("Calculating RouteSense Route (minimizing risk-weighted distance)...")
    rs_path = nx.shortest_path(G, source=start_node, target=end_node, weight="routesense_cost")

    # 6. Extraction & Comparison
    def extract_route_metrics(path, G):
        total_dist = 0
        risk_counts = {0: 0, 1: 0, 2: 0}
        features = []
        for i in range(len(path)-1):
            u, v = path[i], path[i+1]
            data = G.get_edge_data(u, v)
            dist = data['distance']
            risk = data['predicted_risk']
            total_dist += dist
            risk_counts[risk] += 1
            
            # create geojson feature
            feat = {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [u, v]},
                "properties": {k: v for k, v in data.items()}
            }
            features.append(feat)
            
        return total_dist, risk_counts, features

    norm_dist, norm_risk, norm_feats = extract_route_metrics(normal_path, G)
    rs_dist, rs_risk, rs_feats = extract_route_metrics(rs_path, G)

    norm_segments = sum(norm_risk.values())
    rs_segments = sum(rs_risk.values())

    print("\n--- NORMAL ROUTE ---")
    print(f"Distance: {norm_dist:.2f} m | Segments: {norm_segments}")
    print(f"Risk: LOW={norm_risk[0]}, MED={norm_risk[1]}, HIGH={norm_risk[2]}")
    
    print("\n--- ROUTESENSE ROUTE ---")
    print(f"Distance: {rs_dist:.2f} m | Segments: {rs_segments}")
    print(f"Risk: LOW={rs_risk[0]}, MED={rs_risk[1]}, HIGH={rs_risk[2]}")

    dist_diff = rs_dist - norm_dist
    dist_pct = (dist_diff / norm_dist) * 100 if norm_dist > 0 else 0
    high_risk_avoided = norm_risk[2] - rs_risk[2]
    
    print("\n--- COMPARISON ---")
    print(f"Distance diff: {dist_diff:.2f} m ({dist_pct:+.2f}%)")
    print(f"High risk segments avoided: {high_risk_avoided}")

    # 7. Outputs
    out_dir = 'outputs/routing'
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, 'normal_route.geojson'), 'w') as f:
        json.dump({"type": "FeatureCollection", "features": norm_feats}, f)
        
    with open(os.path.join(out_dir, 'routesense_route.geojson'), 'w') as f:
        json.dump({"type": "FeatureCollection", "features": rs_feats}, f)

    df_comp = pd.DataFrame([{
        "Route": "Normal",
        "Distance_m": norm_dist,
        "Segments": norm_segments,
        "Low_Risk": norm_risk[0],
        "Medium_Risk": norm_risk[1],
        "High_Risk": norm_risk[2]
    }, {
        "Route": "RouteSense",
        "Distance_m": rs_dist,
        "Segments": rs_segments,
        "Low_Risk": rs_risk[0],
        "Medium_Risk": rs_risk[1],
        "High_Risk": rs_risk[2]
    }])
    df_comp.to_csv(os.path.join(out_dir, 'route_comparison.csv'), index=False)

    summary = f"""ROUTE SENSE AI - ROUTING SUMMARY
Config: LOW={args.low}, MEDIUM={args.medium}, HIGH={args.high}
Origin: {origin_pt}
Destination: {dest_pt}

--- NORMAL ROUTE ---
Distance: {norm_dist:.2f} m
Segments: {norm_segments}
Risk Distribution: LOW={norm_risk[0]}, MEDIUM={norm_risk[1]}, HIGH={norm_risk[2]}
% High Risk: {(norm_risk[2]/norm_segments)*100 if norm_segments>0 else 0:.1f}%

--- ROUTESENSE ROUTE ---
Distance: {rs_dist:.2f} m
Segments: {rs_segments}
Risk Distribution: LOW={rs_risk[0]}, MEDIUM={rs_risk[1]}, HIGH={rs_risk[2]}
% High Risk: {(rs_risk[2]/rs_segments)*100 if rs_segments>0 else 0:.1f}%

--- COMPARISON ---
Distance penalty: {dist_diff:.2f} m ({dist_pct:+.2f}%)
High risk segments avoided: {high_risk_avoided}
"""
    with open(os.path.join(out_dir, 'route_summary.txt'), 'w') as f:
        f.write(summary)
        
    print(f"\nOutputs successfully saved to {out_dir}/")

if __name__ == "__main__":
    main()
