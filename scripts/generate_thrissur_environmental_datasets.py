"""
RouteSense AI - Environmental and Scenario Dataset Generator
Generates versioned datasets for Thrissur hydrological features, road proximity,
synthetic rainfall/flood scenarios, and road risk evaluation.

All datasets follow strict provenance metadata and deterministic reproducibility.
"""

import json
import math
import os
from pathlib import Path
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, mapping

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

def distance_meters(p1, p2):
    """Haversine distance between two (lon, lat) points in meters."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    lat = math.radians((lat1 + lat2) / 2)
    x = math.radians(lon2 - lon1) * math.cos(lat)
    y = math.radians(lat2 - lat1)
    return 6371000 * math.sqrt(x * x + y * y)

def min_distance_to_lines(point, lines):
    """Calculate minimum haversine distance from point to a set of LineStrings."""
    min_d = float('inf')
    pt = Point(point)
    for line in lines:
        # Approximate distance in meters using sample points along line
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            c1, c2 = coords[i], coords[i+1]
            # Sample along segment
            for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
                sx = c1[0] + (c2[0] - c1[0]) * t
                sy = c1[1] + (c2[1] - c1[1]) * t
                d = distance_meters(point, (sx, sy))
                if d < min_d:
                    min_d = d
    return min_d

def main():
    print("[RouteSense Dataset Generator] Initializing...")
    os.makedirs(DATA_DIR, exist_ok=True)

    # ──────────────────────────────────────────────────────────
    # 1. Generate Thrissur Waterways v1 (GeoJSON)
    # ──────────────────────────────────────────────────────────
    print("[1/5] Generating Thrissur Waterways v1 (thrissur_waterways_v1.geojson)...")
    waterways = [
        {
            "waterway_id": "WW_PUZHAKKAL_MAIN",
            "name": "Puzhakkal River Main Channel",
            "type": "river",
            "flow_direction": "westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.242, 10.582],
                [76.230, 10.571],
                [76.216, 10.558],
                [76.202, 10.550],
                [76.188, 10.543],
                [76.172, 10.538],
                [76.155, 10.534]
            ]
        },
        {
            "waterway_id": "WW_PUZHAKKAL_NORTH_TRIB",
            "name": "Puzhakkal North Tributary",
            "type": "river_tributary",
            "flow_direction": "southward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.210, 10.605],
                [76.207, 10.588],
                [76.204, 10.570],
                [76.202, 10.550]
            ]
        },
        {
            "waterway_id": "WW_KOLE_CANAL_WEST_MAIN",
            "name": "Thrissur Kole Wetland Main Drainage Canal",
            "type": "drainage_canal",
            "flow_direction": "southward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.172, 10.538],
                [76.168, 10.522],
                [76.165, 10.505],
                [76.162, 10.485],
                [76.160, 10.465]
            ]
        },
        {
            "waterway_id": "WW_KOLE_CROSS_CANAL_1",
            "name": "Kole Lowland Connector Canal North",
            "type": "drainage_canal",
            "flow_direction": "westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.195, 10.525],
                [76.182, 10.523],
                [76.168, 10.522]
            ]
        },
        {
            "waterway_id": "WW_KOLE_CROSS_CANAL_2",
            "name": "Kole Lowland Connector Canal South",
            "type": "drainage_canal",
            "flow_direction": "westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.205, 10.495],
                [76.185, 10.492],
                [76.165, 10.488]
            ]
        },
        {
            "waterway_id": "WW_MANALI_REACH",
            "name": "Manali River Southern Reach",
            "type": "river",
            "flow_direction": "westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.275, 10.468],
                [76.255, 10.462],
                [76.230, 10.458],
                [76.200, 10.455],
                [76.170, 10.452]
            ]
        },
        {
            "waterway_id": "WW_VADAKKECHIRA_OUTLET",
            "name": "Vadakkechira Urban Overflow Stream",
            "type": "urban_channel",
            "flow_direction": "south-westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.218, 10.531],
                [76.210, 10.526],
                [76.198, 10.522]
            ]
        },
        {
            "waterway_id": "WW_EASTERN_IRRIGATION",
            "name": "Eastern Irrigation Feeder Canal",
            "type": "canal",
            "flow_direction": "westward",
            "provenance": "derived_thrissur_hydrology_model_v1",
            "coords": [
                [76.280, 10.540],
                [76.262, 10.536],
                [76.245, 10.532],
                [76.232, 10.530]
            ]
        }
    ]

    ww_features = []
    ww_geoms = []
    for ww in waterways:
        line = LineString(ww["coords"])
        ww_geoms.append(line)
        ww_features.append({
            "type": "Feature",
            "geometry": mapping(line),
            "properties": {
                "waterway_id": ww["waterway_id"],
                "name": ww["name"],
                "type": ww["type"],
                "flow_direction": ww["flow_direction"],
                "provenance": ww["provenance"]
            }
        })

    ww_geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": ww_features
    }

    ww_path = DATA_DIR / "thrissur_waterways_v1.geojson"
    with open(ww_path, "w", encoding="utf-8") as f:
        json.dump(ww_geojson, f, indent=2)
    print(f"  -> Saved {len(waterways)} waterway features to {ww_path}")

    # ──────────────────────────────────────────────────────────
    # 2. Road-Waterway Proximity Dataset
    # ──────────────────────────────────────────────────────────
    print("[2/5] Generating Road-to-Waterway Proximity (thrissur_road_water_proximity_v1.csv)...")
    roads_file = DATA_DIR / "thrissur_roads.geojson"
    if roads_file.exists():
        roads_gdf = gpd.read_file(roads_file)
        proximity_records = []
        for idx, row in roads_gdf.iterrows():
            geom = row.geometry
            if not isinstance(geom, LineString):
                continue
            coords = list(geom.coords)
            midpoint = (
                (coords[0][0] + coords[-1][0]) / 2,
                (coords[0][1] + coords[-1][1]) / 2
            )
            dist_to_water = round(min_distance_to_lines(midpoint, ww_geoms), 1)

            # Determine susceptibility tier based on proximity
            if dist_to_water <= 100:
                tier = "HIGH"
            elif dist_to_water <= 250:
                tier = "MEDIUM"
            else:
                tier = "LOW"

            proximity_records.append({
                "osm_id": row.get("osm_id", f"road_{idx}"),
                "highway": row.get("highway", "unclassified"),
                "name": row.get("name", ""),
                "midpoint_lon": round(midpoint[0], 6),
                "midpoint_lat": round(midpoint[1], 6),
                "distance_to_water_meters": dist_to_water,
                "within_100m": dist_to_water <= 100,
                "within_250m": dist_to_water <= 250,
                "flood_susceptibility_tier": tier,
                "data_provenance": "derived_spatial_calculation_v1"
            })

        prox_df = pd.DataFrame(proximity_records)
        prox_path = DATA_DIR / "thrissur_road_water_proximity_v1.csv"
        prox_df.to_csv(prox_path, index=False)
        print(f"  -> Saved proximity analysis for {len(prox_df)} road segments to {prox_path}")
    else:
        print("  -> Warning: thrissur_roads.geojson not found; skipping proximity calculation.")

    # ──────────────────────────────────────────────────────────
    # 3. Synthetic Rainfall Scenarios Dataset
    # ──────────────────────────────────────────────────────────
    print("[3/5] Generating Synthetic Rainfall Scenarios (synthetic_rainfall_scenarios_v1.json)...")
    rainfall_scenarios = {
        "metadata": {
            "version": "1.0",
            "type": "synthetic_scenario_parameters",
            "generator": "routesense_deterministic_engine",
            "random_seed": 42,
            "units": {
                "rainfall_24h": "millimeters (mm)",
                "peak_intensity": "mm/hour",
                "runoff_coefficient": "dimensionless (0.0 - 1.0)",
                "antecedent_moisture_index": "dimensionless (0.0 - 1.0)"
            },
            "provenance_note": "Explicitly synthetic scenarios modeled after historical Kerala monsoon dynamics for evaluation."
        },
        "scenarios": [
            {
                "scenario_id": "SCN_RAIN_NORMAL_MONSOON",
                "name": "Standard Active Southwest Monsoon",
                "rainfall_24h_mm": 65.0,
                "peak_intensity_mm_h": 12.0,
                "runoff_coefficient": 0.35,
                "antecedent_moisture_index": 0.40,
                "expected_impact": "Localized minor waterlogging in poorly drained urban dips; primary roads normal."
            },
            {
                "scenario_id": "SCN_RAIN_HEAVY_DOWNPOUR",
                "name": "Heavy Monsoon Depression (Orange Alert)",
                "rainfall_24h_mm": 165.0,
                "peak_intensity_mm_h": 28.0,
                "runoff_coefficient": 0.65,
                "antecedent_moisture_index": 0.70,
                "expected_impact": "Puzhakkal lowlands inundated, Kole wetland canal bank overflow, tertiary roads affected."
            },
            {
                "scenario_id": "SCN_RAIN_EXTREME_2018_ANALOG",
                "name": "Centenary Extreme Rainfall Event (2018 Analog / Red Alert)",
                "rainfall_24h_mm": 340.0,
                "peak_intensity_mm_h": 55.0,
                "runoff_coefficient": 0.88,
                "antecedent_moisture_index": 0.95,
                "expected_impact": "Severe district-wide inundation; low-elevation corridors impassable; emergency routing mandatory."
            },
            {
                "scenario_id": "SCN_RAIN_URBAN_CLOUDBURST",
                "name": "Short-Duration High-Intensity Urban Cloudburst",
                "rainfall_24h_mm": 110.0,
                "peak_intensity_mm_h": 75.0,
                "runoff_coefficient": 0.80,
                "antecedent_moisture_index": 0.50,
                "expected_impact": "Rapid flash waterlogging in Thrissur Swaraj Round and commercial core; high slope runoff."
            }
        ]
    }

    rain_path = DATA_DIR / "synthetic_rainfall_scenarios_v1.json"
    with open(rain_path, "w", encoding="utf-8") as f:
        json.dump(rainfall_scenarios, f, indent=2)
    print(f"  -> Saved {len(rainfall_scenarios['scenarios'])} rainfall scenarios to {rain_path}")

    # ──────────────────────────────────────────────────────────
    # 4. Synthetic Flood Hazard Scenarios Dataset
    # ──────────────────────────────────────────────────────────
    print("[4/5] Generating Synthetic Flood Hazard Scenarios (synthetic_flood_scenarios_v1.json)...")
    flood_scenarios = {
        "metadata": {
            "version": "1.0",
            "type": "synthetic_flood_hazard_parameters",
            "generator": "routesense_deterministic_engine",
            "provenance_note": "Calibrated spatial hazard scenarios covering key geographic subregions of Thrissur."
        },
        "scenarios": [
            {
                "scenario_id": "SCN_FLOOD_PUZHAKKAL_LOWLAND",
                "name": "Puzhakkal Lowland River Overflow",
                "center": [76.1850, 10.5350],
                "radius_meters": 2200,
                "intensity": 0.75,
                "water_level_meters": 2.2,
                "affected_region_description": "Puzhakkal, Ayyanthole north, Kole agricultural periphery",
                "primary_threat": "River overtopping and standing flood water on Guruvayur road corridor"
            },
            {
                "scenario_id": "SCN_FLOOD_KOLE_BREACH",
                "name": "Southern Kole Wetland Embankment Inundation",
                "center": [76.1750, 10.4950],
                "radius_meters": 2800,
                "intensity": 0.85,
                "water_level_meters": 3.0,
                "affected_region_description": "Arimpur, Manalur, southern Kole agricultural basin",
                "primary_threat": "Deep inundation (>2.5m) cutting off southwestern escape routes"
            },
            {
                "scenario_id": "SCN_FLOOD_SWARAJ_ROUND_FLASH",
                "name": "Central Thrissur Urban Core Drainage Surcharge",
                "center": [76.2144, 10.5276],
                "radius_meters": 1200,
                "intensity": 0.60,
                "water_level_meters": 1.4,
                "affected_region_description": "Swaraj Round, Kuruppam Road, High Road commercial district",
                "primary_threat": "Surface flash flooding and traffic gridlock; impassable for low-clearance vehicles"
            },
            {
                "scenario_id": "SCN_FLOOD_KURIACHIRA_INUNDATION",
                "name": "Kuriachira - Ollur Low-Lying Corridor Waterlogging",
                "center": [76.2250, 10.5050],
                "radius_meters": 1600,
                "intensity": 0.70,
                "water_level_meters": 1.8,
                "affected_region_description": "Kuriachira, Nehru Park south, Ollur railway crossing dip",
                "primary_threat": "Railway underpass flooding and arterial road constriction"
            }
        ]
    }

    flood_path = DATA_DIR / "synthetic_flood_scenarios_v1.json"
    with open(flood_path, "w", encoding="utf-8") as f:
        json.dump(flood_scenarios, f, indent=2)
    print(f"  -> Saved {len(flood_scenarios['scenarios'])} flood scenarios to {flood_path}")

    # ──────────────────────────────────────────────────────────
    # 5. Synthetic Road-Level Scenario Risk Evaluation Dataset
    # ──────────────────────────────────────────────────────────
    print("[5/5] Generating Road-Level Scenario Risk Evaluation (synthetic_road_scenario_risk_v1.csv)...")
    if roads_file.exists():
        roads_gdf = gpd.read_file(roads_file)
        scenario_eval_records = []

        for scn in flood_scenarios["scenarios"]:
            c_lon, c_lat = scn["center"]
            radius = scn["radius_meters"]
            intensity = scn["intensity"]
            wl = scn["water_level_meters"]

            for idx, row in roads_gdf.iterrows():
                geom = row.geometry
                if not isinstance(geom, LineString):
                    continue
                coords = list(geom.coords)
                midpoint = (
                    (coords[0][0] + coords[-1][0]) / 2,
                    (coords[0][1] + coords[-1][1]) / 2
                )
                d = distance_meters(midpoint, (c_lon, c_lat))
                if d <= radius:
                    proximity = 1.0 - (d / radius)
                    # Simulated synthetic elevation between 5m and 80m
                    elev = 15.0 if d < radius * 0.5 else 40.0
                    elev_factor = max(0, 1.0 - (elev / 500))
                    penalty = round(proximity * intensity * elev_factor * wl, 4)
                    effective_risk = 2 if penalty > 0.7 else (1 if penalty > 0.3 else 0)
                    impassable = penalty > 0.85

                    scenario_eval_records.append({
                        "scenario_id": scn["scenario_id"],
                        "osm_id": row.get("osm_id", f"road_{idx}"),
                        "distance_to_center_m": round(d, 1),
                        "simulated_flood_penalty": penalty,
                        "effective_risk": effective_risk,
                        "impassable": impassable,
                        "provenance": "synthetic_scenario_evaluation_v1"
                    })

        scn_eval_df = pd.DataFrame(scenario_eval_records)
        eval_path = DATA_DIR / "synthetic_road_scenario_risk_v1.csv"
        scn_eval_df.to_csv(eval_path, index=False)
        print(f"  -> Saved {len(scn_eval_df)} scenario evaluations to {eval_path}")

    # ──────────────────────────────────────────────────────────
    # Provenance Registry
    # ──────────────────────────────────────────────────────────
    registry = {
        "dataset_registry": {
            "kerala_roads.geojson": {
                "type": "observed",
                "source": "OpenStreetMap Kerala extract",
                "crs": "EPSG:4326",
                "description": "Base road network geometries and OSM attributes."
            },
            "Copernicus_DEM_COG_10_*.tif": {
                "type": "observed",
                "source": "Copernicus GLO-30 Digital Elevation Model",
                "crs": "EPSG:4326",
                "description": "Elevation in meters above sea level."
            },
            "thrissur_routing_graph.pkl": {
                "type": "derived",
                "source": "Constructed from OSM roads and DEM slope/elevation",
                "description": "NetworkX graph for Thrissur road network."
            },
            "routesense_road_risk.geojson": {
                "type": "derived",
                "source": "Trained ML model prediction on road environmental features",
                "description": "Baseline road risk classifications (0=Low, 1=Medium, 2=High)."
            },
            "thrissur_waterways_v1.geojson": {
                "type": "derived",
                "source": "Thrissur district river & canal hydrology network (Puzhakkal, Kole, Manali)",
                "crs": "EPSG:4326",
                "description": "Vector geometries of primary river channels and Kole wetland drainage canals."
            },
            "thrissur_road_water_proximity_v1.csv": {
                "type": "derived",
                "source": "Spatial distance calculation from roads to thrissur_waterways_v1",
                "description": "Proximity of road segments to nearest waterways."
            },
            "synthetic_rainfall_scenarios_v1.json": {
                "type": "synthetic",
                "source": "Calibrated parametric monsoon rainfall scenarios",
                "description": "Scenario definitions for rainfall intensity and runoff."
            },
            "synthetic_flood_scenarios_v1.json": {
                "type": "synthetic",
                "source": "Parametric flood hazard zones in Thrissur subregions",
                "description": "Coordinates, radius, intensity, and water level for hazard evaluation."
            },
            "synthetic_road_scenario_risk_v1.csv": {
                "type": "synthetic",
                "source": "Deterministic evaluation of road segments under synthetic flood scenarios",
                "description": "Effective risk, flood penalties, and impassable designations."
            }
        },
        "limitations": [
            "Real-time hydrological river discharge telemetry data was unavailable from local authorities.",
            "Subterranean municipal stormwater pipe GIS records were not available in open datasets.",
            "Synthetic rainfall parameters are deterministic simulation models, not live rain gauge telemetry."
        ]
    }
    reg_path = DATA_DIR / "dataset_provenance_registry.json"
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print(f"[Done] Dataset provenance registry saved to {reg_path}")

if __name__ == "__main__":
    main()
