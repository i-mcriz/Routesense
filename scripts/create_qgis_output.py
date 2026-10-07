import pandas as pd
import json
import os

print("Loading predictions...")
df_preds = pd.read_csv('data/processed/ml_dataset_predictions.csv')

print("Loading base CSV with geometries...")
df_base = pd.read_csv('data/processed/kerala_roads_base.csv')

# The prediction dataframe has 'osm_id' and 'name' which match. However, the order is identical to kerala_road_elevation which was derived from kerala_roads_base!
# Let's merge on road index if we can, or just assume they align if length is exactly the same and we didn't sort.
# Actually, the prepare_dataset script selected from gpkg. 
# It's safer to merge on osm_id or just assume alignment if row counts match.
# Wait, osm_id might not be unique if there are multiple segments.
# Since prepare_dataset.py extracted directly without sorting, and both gpkg and csv were created from the same source geojson in the same order, they align perfectly.
# But let's verify lengths.

if len(df_preds) == len(df_base):
    print("Row counts match perfectly.")
    # Add predicted risk and probabilities
    df_base['predicted_risk'] = df_preds['predicted_risk']
    df_base['risk_label'] = df_base['predicted_risk'].map({0: 'Low', 1: 'Medium', 2: 'High'})
    df_base['low_probability'] = df_preds['low_probability']
    df_base['medium_probability'] = df_preds['medium_probability']
    df_base['high_probability'] = df_preds['high_probability']
    
    # Add environmental features
    df_base['elevation'] = df_preds['elevation']
    df_base['slope'] = df_preds['slope']
    df_base['rainfall'] = df_preds['rainfall']
    df_base['distance_to_water'] = df_preds['distance_to_water']
else:
    print("Row counts do not match, please investigate!")

print("Creating GeoJSON output...")
features = []
for i, row in df_base.iterrows():
    # Only process a small sample if needed, but we process all.
    coords = json.loads(row['geometry'])
    geom_type = row['geometry_type']
    
    properties = {
        "osm_id": row['osm_id'],
        "name": row['name'],
        "highway": row['highway'],
        "predicted_risk": int(row['predicted_risk']),
        "risk_label": row['risk_label'],
        "low_prob": round(row['low_probability'], 3),
        "medium_prob": round(row['medium_probability'], 3),
        "high_prob": round(row['high_probability'], 3),
        "elevation": round(row['elevation'], 2),
        "slope": round(row['slope'], 2),
        "rainfall": round(row['rainfall'], 2),
        "dist_water": round(row['distance_to_water'], 2)
    }
    
    feature = {
        "type": "Feature",
        "geometry": {
            "type": geom_type,
            "coordinates": coords
        },
        "properties": properties
    }
    features.append(feature)

geojson_dict = {
    "type": "FeatureCollection",
    "features": features
}

os.makedirs('outputs', exist_ok=True)
output_path = 'outputs/routesense_road_risk.geojson'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(geojson_dict, f)

print(f"QGIS-ready GeoJSON saved to {output_path}")
