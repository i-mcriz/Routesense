import sqlite3
import pandas as pd
import numpy as np

print("Connecting to gpkg...")
conn = sqlite3.connect('data/processed/kerala_road_elevation.gpkg')
query = """
SELECT osm_id, name, highway, SAMPLE_1 as elevation
FROM kerala_road_elevation
"""
df = pd.read_sql_query(query, conn)
conn.close()

print("Initial data shape:", df.shape)

# Create a clean ML dataset
# 1. road_type
# 2. elevation
# 3. slope (prototype since not found in files)
# 4. rainfall (prototype)
# 5. distance_to_water (prototype)
# 6. flood_history / risk_label (prototype)

np.random.seed(42)

# Handle missing elevation
df['elevation'] = df['elevation'].fillna(df['elevation'].median())

print("Generating prototype features...")
# 3. Slope
# Prototype: assume higher elevation regions generally have higher slope variance, and random factor
df['slope'] = np.abs(np.random.normal(0, 5, len(df)) + (df['elevation'] / 100))

# 4. Rainfall
# Prototype: assume higher rainfall in certain elevation bands (e.g. Western Ghats)
df['rainfall'] = 2000 + np.random.normal(0, 300, len(df)) + (df['elevation'] * 0.5)

# 5. Distance to water
# Prototype: Random but biased by elevation (lower elevation might be closer to water)
df['distance_to_water'] = np.abs(np.random.normal(500, 1000, len(df)) + df['elevation'] * 2)

# 6. Risk Score & Label
# Combine factors to create a realistic-looking risk score
# Higher risk if: low elevation, low distance to water, high rainfall, high slope
risk_score = (
    (3000 - df['elevation']) * 0.01 + 
    (df['slope'] * 2) + 
    (df['rainfall'] * 0.005) - 
    (df['distance_to_water'] * 0.002)
)

# Convert to 0, 1, 2
threshold_low = risk_score.quantile(0.4)
threshold_high = risk_score.quantile(0.8)

def categorize_risk(score):
    if score < threshold_low:
        return 0 # Low
    elif score < threshold_high:
        return 1 # Medium
    else:
        return 2 # High

df['risk_level'] = risk_score.apply(categorize_risk)

df.to_csv('data/processed/ml_dataset_clean.csv', index=False)
print("ML Dataset saved to data/processed/ml_dataset_clean.csv")
