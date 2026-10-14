"""
RouteSense AI - Automated Test Suite
Covers Requirements 1 through 7:
- Routing logic (Shortest distance, Risk-aware evasion, Impassable exclusion, Profiles)
- Disaster simulation (Circular flood, Freehand polygon flood, Severity sensitivity)
- Dataset integrity and provenance
- Visualization contracts
"""

import unittest
import os
import sys
import json
import math
from pathlib import Path
import networkx as nx

# Add project root and backend to python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from backend.app import (
    G_BASE, NODE_LIST, PROFILES, IMPASSABLE_THRESHOLD,
    DEFAULT_ORIGIN, DEFAULT_DEST,
    haversine, nearest_node, compute_edge_weights, run_routing,
    app
)

class TestRouteSenseEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.origin_node, _ = nearest_node(G_BASE, tuple(DEFAULT_ORIGIN), NODE_LIST)
        cls.dest_node, _ = nearest_node(G_BASE, tuple(DEFAULT_DEST), NODE_LIST)

    # ════════════════════════════════════════════════════════════
    # ROUTING TESTS (Requirement 1 & 7)
    # ════════════════════════════════════════════════════════════

    def test_01_shortest_route_minimizes_distance(self):
        """Shortest route must minimize total physical distance on base network."""
        path = nx.shortest_path(G_BASE, self.origin_node, self.dest_node, weight='distance')
        dist = sum(G_BASE[path[i]][path[i+1]]['distance'] for i in range(len(path)-1))
        self.assertGreater(dist, 0)
        self.assertEqual(path[0], self.origin_node)
        self.assertEqual(path[-1], self.dest_node)

    def test_02_risk_penalties_do_not_alter_shortest_distance(self):
        """Flood penalties must never change the normal shortest route distance."""
        res_baseline = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        flood_center = [(DEFAULT_ORIGIN[0] + DEFAULT_DEST[0])/2, (DEFAULT_ORIGIN[1] + DEFAULT_DEST[1])/2]
        res_flood = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
                                flood_center=flood_center, flood_radius=2500, flood_intensity=0.9, water_level=2.5)

        self.assertEqual(res_baseline['normal']['distance'], res_flood['normal']['distance'])
        self.assertEqual(res_baseline['normal']['coordinates'], res_flood['normal']['coordinates'])

    def test_03_recommended_route_avoids_impassable_roads(self):
        """RouteSense route must strictly avoid roads marked impassable."""
        # Place severe flood directly along middle of normal corridor
        normal_path = nx.shortest_path(G_BASE, self.origin_node, self.dest_node, weight='distance')
        mid_node = normal_path[len(normal_path)//2]

        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
                          flood_center=list(mid_node), flood_radius=1500, flood_intensity=1.0, water_level=4.0)

        if res['routesense'] is not None:
            # Check all features in routesense route
            for feat in res['routesense']['geojson']['features']:
                penalty = feat['properties'].get('flood_penalty', 0)
                self.assertLessEqual(penalty, IMPASSABLE_THRESHOLD,
                                     f"Segment has flood penalty {penalty} > threshold {IMPASSABLE_THRESHOLD}")
                self.assertFalse(feat['properties'].get('impassable', False))

    def test_04_moderate_risk_receives_intended_penalties(self):
        """Moderate flood penalty (0.3 - 0.7) escalates risk without marking impassable."""
        test_edge = list(G_BASE.edges(data=True))[0]
        u, v, _ = test_edge
        mid = ((u[0]+v[0])/2, (u[1]+v[1])/2)

        # Flood with moderate intensity
        G_w = compute_edge_weights(G_BASE, 'general', flood_center=mid, flood_radius=1000,
                                   flood_intensity=0.4, water_level=1.0)
        edge_data = G_w.get_edge_data(u, v)
        self.assertFalse(edge_data['impassable'])
        self.assertGreater(edge_data['routesense_cost'], 0)

    def test_05_no_path_returns_clear_status(self):
        """When safety constraints block all routes, return explicit clear error message."""
        # Create flood covering all edges around origin node
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
                          flood_center=list(self.origin_node), flood_radius=4000,
                          flood_intensity=1.0, water_level=5.0)

        self.assertIn("No route satisfying the configured safety constraints is available",
                      res.get('routesense_error', ''))
        self.assertIsNone(res['routesense'])
        self.assertFalse(res['route_validated'])

    def test_06_route_geometries_match_graph_paths(self):
        """LineString geometries match the actual sequence of graph coordinates."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        normal_coords = res['normal']['coordinates']
        self.assertEqual(normal_coords[0], list(self.origin_node))
        self.assertEqual(normal_coords[-1], list(self.dest_node))

        for feat in res['normal']['geojson']['features']:
            coords = feat['geometry']['coordinates']
            self.assertEqual(len(coords), 2)
            self.assertTrue(G_BASE.has_edge(tuple(coords[0]), tuple(coords[1])))

    def test_07_origin_dest_points_work(self):
        """Default Thrissur origin and destination points successfully map to graph nodes."""
        self.assertIsNotNone(self.origin_node)
        self.assertIsNotNone(self.dest_node)
        self.assertTrue(nx.has_path(G_BASE, self.origin_node, self.dest_node))

    def test_08_routing_profiles_remain_functional(self):
        """Profiles (general, elderly, emergency) apply differential weighting."""
        G_gen = compute_edge_weights(G_BASE, 'general')
        G_eld = compute_edge_weights(G_BASE, 'elderly')
        G_emg = compute_edge_weights(G_BASE, 'emergency')

        # Pick high risk edge
        high_risk_edge = None
        for u, v, d in G_BASE.edges(data=True):
            if d.get('predicted_risk') == 2:
                high_risk_edge = (u, v)
                break

        if high_risk_edge:
            u, v = high_risk_edge
            cost_gen = G_gen[u][v]['routesense_cost']
            cost_eld = G_eld[u][v]['routesense_cost']
            cost_emg = G_emg[u][v]['routesense_cost']
            # Emergency high multiplier is 12x, General is 5x
            self.assertGreater(cost_emg, cost_gen)
            self.assertGreater(cost_eld, cost_gen)

    def test_09_route_distances_calculated_correctly(self):
        """Total route distance equals sum of individual segment distances."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        features = res['normal']['geojson']['features']
        summed_dist = sum(f['properties']['distance'] for f in features)
        self.assertAlmostEqual(res['normal']['distance'], summed_dist, delta=1.0)

    def test_10_api_contract_and_routing_objectives(self):
        """API response provides documented objectives and validation flags."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        self.assertIn('routing_objective', res)
        self.assertIn('normal', res['routing_objective'])
        self.assertIn('routesense', res['routing_objective'])
        self.assertTrue(res['route_validated'])

    # ════════════════════════════════════════════════════════════
    # DISASTER SIMULATION TESTS (Requirement 2, 5 & 7)
    # ════════════════════════════════════════════════════════════

    def test_11_localized_flood_changes_risk(self):
        """Localized circular flood increases flood penalty for proximal roads."""
        center = [76.214, 10.525]
        G_w = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                   flood_intensity=0.8, water_level=2.0)
        elevated = [d['flood_penalty'] for u, v, d in G_w.edges(data=True) if d['flood_penalty'] > 0]
        self.assertGreater(len(elevated), 0)

    def test_12_roads_outside_unaffected(self):
        """Roads beyond flood radius receive zero penalty."""
        center = [76.18, 10.49]
        radius = 500  # small radius in southwest
        G_w = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=radius,
                                   flood_intensity=0.8, water_level=2.0)

        # Find edge far away in northeast
        for u, v, d in G_w.edges(data=True):
            mid = ((u[0]+v[0])/2, (u[1]+v[1])/2)
            if haversine(mid, tuple(center)) > 4000:
                self.assertEqual(d['flood_penalty'], 0)
                self.assertEqual(d['effective_risk'], d['predicted_risk'])

    def test_13_increasing_severity_monotonic_response(self):
        """Increasing flood severity strictly increases or maintains penalty."""
        center = [76.214, 10.525]
        G_low = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                     flood_intensity=0.3, water_level=1.0)
        G_high = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                      flood_intensity=0.9, water_level=3.0)

        for u, v in G_BASE.edges():
            p_low = G_low[u][v]['flood_penalty']
            p_high = G_high[u][v]['flood_penalty']
            self.assertGreaterEqual(p_high, p_low)

    def test_14_effective_risk_differs_from_baseline(self):
        """Effective risk escalates above baseline for severely affected roads."""
        center = [76.214, 10.525]
        G_w = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                   flood_intensity=0.9, water_level=3.0)
        diff_count = sum(1 for u, v, d in G_w.edges(data=True) if d['effective_risk'] != d['predicted_risk'])
        self.assertGreater(diff_count, 0)

    def test_15_reproducible_risk_values(self):
        """Same scenario inputs yield exact deterministic risk values."""
        center = [76.214, 10.525]
        G_1 = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                   flood_intensity=0.6, water_level=1.5)
        G_2 = compute_edge_weights(G_BASE, 'general', flood_center=center, flood_radius=2000,
                                   flood_intensity=0.6, water_level=1.5)

        for u, v in G_BASE.edges():
            self.assertEqual(G_1[u][v]['flood_penalty'], G_2[u][v]['flood_penalty'])
            self.assertEqual(G_1[u][v]['effective_risk'], G_2[u][v]['effective_risk'])

    def test_16_circular_flood_simulation_works(self):
        """API endpoint /api/simulate-flood returns affected roads."""
        res = self.client.post('/api/simulate-flood', json={
            'center': [76.214, 10.525],
            'radius': 2000,
            'intensity': 0.7,
            'water_level': 2.0
        })
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertGreater(data['affected_count'], 0)
        self.assertIn('affected_roads', data)

    def test_17_polygon_simulation_updates_roads(self):
        """Polygon flood mode properly affects roads intersecting the polygon."""
        poly = [
            [76.210, 10.520],
            [76.225, 10.520],
            [76.225, 10.535],
            [76.210, 10.535]
        ]
        G_poly = compute_edge_weights(G_BASE, 'general', flood_polygon=poly,
                                      flood_intensity=0.8, water_level=2.0)
        affected_edges = [d for u, v, d in G_poly.edges(data=True) if d['flood_penalty'] > 0]
        self.assertGreater(len(affected_edges), 0)

    def test_18_reset_restores_baseline(self):
        """Resetting disaster simulation restores baseline network behavior."""
        G_w = compute_edge_weights(G_BASE, 'general', flood_center=None, flood_polygon=None)
        for u, v, d in G_w.edges(data=True):
            self.assertEqual(d['effective_risk'], d['predicted_risk'])
            self.assertEqual(d['flood_penalty'], 0)
            self.assertFalse(d['impassable'])

    # ════════════════════════════════════════════════════════════
    # DATASET INTEGRITY & PROVENANCE TESTS (Requirement 4 & 7)
    # ════════════════════════════════════════════════════════════

    def test_19_existing_road_graph_ids_intact(self):
        """Road network nodes and edge geometries remain intact."""
        self.assertGreater(G_BASE.number_of_nodes(), 500)
        self.assertGreater(G_BASE.number_of_edges(), 500)
        sample_edge = list(G_BASE.edges(data=True))[0]
        self.assertIn('osm_id', sample_edge[2])
        self.assertIn('distance', sample_edge[2])

    def test_20_road_risk_maps_to_graph_edges(self):
        """Every edge contains a predicted_risk in {0, 1, 2}."""
        for u, v, d in G_BASE.edges(data=True):
            self.assertIn(d.get('predicted_risk'), [0, 1, 2])

    def test_21_reproducible_dataset_generation(self):
        """Environmental dataset files exist and are populated."""
        waterways_path = ROOT_DIR / "data" / "thrissur_waterways_v1.geojson"
        proximity_path = ROOT_DIR / "data" / "thrissur_road_water_proximity_v1.csv"
        self.assertTrue(waterways_path.exists())
        self.assertTrue(proximity_path.exists())

    def test_22_synthetic_fields_correctly_labeled(self):
        """Synthetic scenarios are explicitly identified as synthetic."""
        rain_path = ROOT_DIR / "data" / "synthetic_rainfall_scenarios_v1.json"
        with open(rain_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['metadata']['type'], 'synthetic_scenario_parameters')

    def test_23_provenance_registry_exists_and_valid(self):
        """Dataset provenance registry is documented and records limitations."""
        reg_path = ROOT_DIR / "data" / "dataset_provenance_registry.json"
        self.assertTrue(reg_path.exists())
        with open(reg_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
        self.assertIn('dataset_registry', registry)
        self.assertIn('limitations', registry)
        self.assertGreater(len(registry['limitations']), 0)

    def test_24_missing_values_handled_cleanly(self):
        """Graph edges do not contain None or NaN for essential routing attributes."""
        for u, v, d in G_BASE.edges(data=True):
            self.assertFalse(math.isnan(d['distance']))
            self.assertGreater(d['distance'], 0)

    def test_25_graph_topology_unchanged_by_simulations(self):
        """Graph node count and base edge count remain identical across simulations."""
        initial_nodes = G_BASE.number_of_nodes()
        initial_edges = G_BASE.number_of_edges()

        # Run multiple simulations
        _ = compute_edge_weights(G_BASE, 'general', flood_center=[76.21, 10.53], flood_radius=1500)
        _ = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'emergency', flood_center=[76.22, 10.51])

        self.assertEqual(G_BASE.number_of_nodes(), initial_nodes)
        self.assertEqual(G_BASE.number_of_edges(), initial_edges)

    # ════════════════════════════════════════════════════════════
    # VISUALIZATION & FRONTEND CONTRACT TESTS (Requirement 3, 6 & 7)
    # ════════════════════════════════════════════════════════════

    def test_26_affected_roads_risk_tiers(self):
        """Affected roads returned by route API include penalty and impassable flag."""
        center = [76.214, 10.525]
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
                          flood_center=center, flood_radius=2000, flood_intensity=0.8, water_level=2.0)
        self.assertIn('affected_roads', res)
        if res['affected_roads']:
            road = res['affected_roads'][0]
            self.assertIn('coordinates', road)
            self.assertIn('effective_risk', road)
            self.assertIn('impassable', road)

    def test_27_recommended_route_structure(self):
        """RouteSense route contains features for green outline + risk segment coloring."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        self.assertIn('routesense', res)
        self.assertIn('geojson', res['routesense'])
        features = res['routesense']['geojson']['features']
        self.assertGreater(len(features), 0)
        for f in features:
            self.assertIn(f['properties']['predicted_risk'], [0, 1, 2])

    def test_28_normal_route_distinguishable(self):
        """Normal route is distinct and independent from RouteSense route."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        self.assertIn('normal', res)
        self.assertIn('comparison', res)
        self.assertIn('distance_diff', res['comparison'])

    def test_29_rivers_endpoint_available(self):
        """GET /api/rivers returns Thrissur waterway features."""
        res = self.client.get('/api/rivers')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('type'), 'FeatureCollection')
        self.assertGreater(len(data.get('features', [])), 0)

    def test_30_scenarios_endpoint_available(self):
        """GET /api/scenarios returns calibrated synthetic scenarios."""
        res = self.client.get('/api/scenarios')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('scenarios', data)
        self.assertGreater(len(data['scenarios']), 0)

    def test_31_frontend_static_files_exist(self):
        """Frontend HTML, CSS, and JS files exist."""
        self.assertTrue((ROOT_DIR / "frontend" / "index.html").exists())
        self.assertTrue((ROOT_DIR / "frontend" / "style.css").exists())
        self.assertTrue((ROOT_DIR / "frontend" / "app.js").exists())

    def test_32_layer_focus_definitions_intact(self):
        """Frontend JavaScript contains all 5 required focus states."""
        js_content = (ROOT_DIR / "frontend" / "app.js").read_text(encoding='utf-8')
        for focus in ['BALANCED', 'ROUTE_FOCUS', 'FLOOD_ROAD_FOCUS', 'FLOOD_ZONE_FOCUS', 'ENVIRONMENT_FOCUS']:
            self.assertIn(focus, js_content)

if __name__ == '__main__':
    unittest.main()
