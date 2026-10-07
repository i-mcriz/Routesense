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

# Handle missing elevation
df['elevation'] = df['elevation'].fillna(df['elevation'].median())

print("Generating prototype features...")
np.random.seed(42)

# 3. Slope (Prototype)
df['slope'] = np.abs(np.random.normal(0, 5, len(df)) + (df['elevation'] / 100))

# 4. Rainfall (Prototype)
df['rainfall'] = 2000 + np.random.normal(0, 300, len(df)) + (df['elevation'] * 0.5)

# 5. Distance to water (Prototype)
df['distance_to_water'] = np.abs(np.random.normal(500, 1000, len(df)) + df['elevation'] * 2)

# ---------------------------------------------------------
# IMPORTANT: PROTOTYPE TARGET GENERATION
# ---------------------------------------------------------
# The risk score is currently an engineered synthetic label based on 
# environmental features, as real-world flood history data is unavailable.
# We introduce some gaussian noise here to simulate unobserved real-world variance,
# so the ML model learns a generalized relationship rather than a flawless algebraic formula.

print("Generating engineered prototype risk labels with simulated noise...")

base_risk_score = (
    (3000 - df['elevation']) * 0.01 + 
    (df['slope'] * 2) + 
    (df['rainfall'] * 0.005) - 
    (df['distance_to_water'] * 0.002)
)

# Inject noise to simulate unobserved variance (e.g. soil type, local drainage)
noise = np.random.normal(0, 5, len(df))
risk_score = base_risk_score + noise

# Convert to 0 (Low), 1 (Medium), 2 (High)
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
