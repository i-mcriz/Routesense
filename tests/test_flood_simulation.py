"""
RouteSense AI - Targeted Flood Simulation Tests
Validates the new multi-zone drawing, zone selection, independent 0-100% rainfall intensity,
overlapping zones combination rule, zone deletion restoration, and circular simulation baseline.
"""

import unittest
import sys
from pathlib import Path
import networkx as nx
from shapely.geometry import Polygon, Point

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from backend.app import (
    G_BASE, NODE_LIST, IMPASSABLE_THRESHOLD, DEFAULT_ORIGIN, DEFAULT_DEST,
    nearest_node, compute_edge_weights, run_routing, app
)


class TestTargetedFloodSimulation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.origin_node, _ = nearest_node(G_BASE, tuple(DEFAULT_ORIGIN), NODE_LIST)
        cls.dest_node, _ = nearest_node(G_BASE, tuple(DEFAULT_DEST), NODE_LIST)

        # Build two adjacent and partially overlapping polygon zones around Thrissur center
        # Zone A: Swaraj Round area
        cls.zone_a_poly = [
            [76.2100, 10.5220],
            [76.2200, 10.5220],
            [76.2200, 10.5320],
            [76.2100, 10.5320]
        ]
        # Zone B: Overlaps eastern half of Zone A
        cls.zone_b_poly = [
            [76.2150, 10.5220],
            [76.2250, 10.5220],
            [76.2250, 10.5320],
            [76.2150, 10.5320]
        ]

    def test_01_baseline_circular_flood_preserved(self):
        """Preserve existing circular flood simulation as the baseline."""
        mid = [(DEFAULT_ORIGIN[0] + DEFAULT_DEST[0]) / 2, (DEFAULT_ORIGIN[1] + DEFAULT_DEST[1]) / 2]
        G_circ = compute_edge_weights(G_BASE, 'general', flood_center=mid, flood_radius=1500,
                                      flood_intensity=0.8, water_level=2.0)
        penalties = [d['flood_penalty'] for _, _, d in G_circ.edges(data=True) if d['flood_penalty'] > 0]
        self.assertGreater(len(penalties), 0, "Circular flood must generate positive flood penalties on nearby roads")

    def test_02_single_zone_rainfall_intensity_scaling(self):
        """Increasing simulated rainfall intensity (0-100%) increases flood penalties consistently."""
        zone_low = [{'id': 'z1', 'polygon': self.zone_a_poly, 'intensity': 0.20, 'water_level': 1.0}]
        zone_high = [{'id': 'z1', 'polygon': self.zone_a_poly, 'intensity': 0.80, 'water_level': 1.0}]

        G_low = compute_edge_weights(G_BASE, 'general', flood_zones=zone_low)
        G_high = compute_edge_weights(G_BASE, 'general', flood_zones=zone_high)

        affected_low = { (u, v): d['flood_penalty'] for u, v, d in G_low.edges(data=True) if d['flood_penalty'] > 0 }
        affected_high = { (u, v): d['flood_penalty'] for u, v, d in G_high.edges(data=True) if d['flood_penalty'] > 0 }

        self.assertGreater(len(affected_low), 0)
        self.assertEqual(len(affected_low), len(affected_high))

        for edge, pen_low in affected_low.items():
            pen_high = affected_high[edge]
            self.assertGreater(pen_high, pen_low, "Higher simulated rainfall intensity must result in higher penalty")

    def test_03_zero_rainfall_intensity_causes_zero_penalty(self):
        """A simulated rainfall intensity of 0% introduces no additional flood penalty."""
        zone_zero = [{'id': 'z0', 'polygon': self.zone_a_poly, 'intensity': 0.0, 'water_level': 1.0}]
        G_zero = compute_edge_weights(G_BASE, 'general', flood_zones=zone_zero)

        penalties = [d['flood_penalty'] for _, _, d in G_zero.edges(data=True) if d['flood_penalty'] > 0]
        self.assertEqual(len(penalties), 0, "Zone with 0% rainfall intensity must not add penalties")

    def test_04_multiple_zones_independent_intensities(self):
        """Multiple zones have independent rainfall intensities without cross-contamination."""
        zones = [
            {'id': 'za', 'polygon': self.zone_a_poly, 'intensity': 0.25, 'water_level': 1.0},
            {'id': 'zb', 'polygon': [[76.2400, 10.5500], [76.2500, 10.5500], [76.2500, 10.5600], [76.2400, 10.5600]], 'intensity': 0.85, 'water_level': 1.0}
        ]
        G_multi = compute_edge_weights(G_BASE, 'general', flood_zones=zones)

        # Verify roads in zone A have lower penalty and roads in zone B have higher penalty
        sp_a = Polygon(self.zone_a_poly)
        sp_b = Polygon(zones[1]['polygon'])

        penalties_a = []
        penalties_b = []

        for u, v, d in G_multi.edges(data=True):
            pt = Point((u[0] + v[0]) * 0.5, (u[1] + v[1]) * 0.5)
            if sp_a.contains(pt) and d['flood_penalty'] > 0:
                penalties_a.append(d['flood_penalty'])
            elif sp_b.contains(pt) and d['flood_penalty'] > 0:
                penalties_b.append(d['flood_penalty'])

        self.assertGreater(len(penalties_a), 0)
        self.assertGreater(len(penalties_b), 0)
        self.assertLess(max(penalties_a), min(penalties_b), "Independent intensities must be preserved across zones")

    def test_05_overlapping_zones_deterministic_max_combination(self):
        """Overlapping zones combine deterministically using max(penalties) without runaway compounding."""
        # Zone A has intensity 0.40, Zone B has intensity 0.80
        zones = [
            {'id': 'za', 'polygon': self.zone_a_poly, 'intensity': 0.40, 'water_level': 1.0},
            {'id': 'zb', 'polygon': self.zone_b_poly, 'intensity': 0.80, 'water_level': 1.0}
        ]
        G_combined = compute_edge_weights(G_BASE, 'general', flood_zones=zones)
        G_only_b = compute_edge_weights(G_BASE, 'general', flood_zones=[zones[1]])

        # In the overlap area, penalty should equal the max (i.e. Zone B's penalty)
        sp_a = Polygon(self.zone_a_poly)
        sp_b = Polygon(self.zone_b_poly)
        overlap = sp_a.intersection(sp_b)

        tested_edges = 0
        for u, v, d_comb in G_combined.edges(data=True):
            pt = Point((u[0] + v[0]) * 0.5, (u[1] + v[1]) * 0.5)
            if overlap.contains(pt):
                d_b = G_only_b[u][v]
                self.assertAlmostEqual(d_comb['flood_penalty'], d_b['flood_penalty'], places=3)
                tested_edges += 1

        self.assertGreater(tested_edges, 0, "Must test edges inside the overlap region")

    def test_06_zone_deletion_restores_baseline_on_unaffected_roads(self):
        """Deleting a zone cleanly restores unaffected road segments to baseline risk."""
        zones = [
            {'id': 'za', 'polygon': self.zone_a_poly, 'intensity': 0.70, 'water_level': 1.0},
            {'id': 'zb', 'polygon': [[76.2400, 10.5500], [76.2500, 10.5500], [76.2500, 10.5600], [76.2400, 10.5600]], 'intensity': 0.85, 'water_level': 1.0}
        ]
        # Simulate both zones
        G_both = compute_edge_weights(G_BASE, 'general', flood_zones=zones)
        # Simulate after deleting Zone A (only Zone B remains)
        G_after_del = compute_edge_weights(G_BASE, 'general', flood_zones=[zones[1]])

        sp_a = Polygon(self.zone_a_poly)
        for u, v, d_del in G_after_del.edges(data=True):
            pt = Point((u[0] + v[0]) * 0.5, (u[1] + v[1]) * 0.5)
            if sp_a.contains(pt):
                # Roads in Zone A must be completely restored to baseline
                orig_risk = G_BASE[u][v]['predicted_risk']
                self.assertEqual(d_del['flood_penalty'], 0.0)
                self.assertEqual(d_del['effective_risk'], orig_risk)
                self.assertFalse(d_del['impassable'])

    def test_07_coexistence_of_circular_and_zone_simulation(self):
        """Circular flood and custom flood zones can coexist seamlessly."""
        mid = [76.2300, 10.5100]
        zones = [{'id': 'za', 'polygon': self.zone_a_poly, 'intensity': 0.75, 'water_level': 1.0}]
        G_coexist = compute_edge_weights(G_BASE, 'general', flood_center=mid, flood_radius=1200,
                                         flood_intensity=0.6, water_level=1.0, flood_zones=zones)

        sp_a = Polygon(self.zone_a_poly)
        c_penalties = 0
        z_penalties = 0
        for u, v, d in G_coexist.edges(data=True):
            if d['flood_penalty'] > 0:
                pt = Point((u[0] + v[0]) * 0.5, (u[1] + v[1]) * 0.5)
                if sp_a.contains(pt):
                    z_penalties += 1
                else:
                    c_penalties += 1

        self.assertGreater(z_penalties, 0)
        self.assertGreater(c_penalties, 0)

    def test_08_api_route_with_flood_zones(self):
        """POST /api/route successfully accepts flood_zones payload and routes safely."""
        payload = {
            'origin': DEFAULT_ORIGIN,
            'destination': DEFAULT_DEST,
            'profile': 'general',
            'flood': {
                'active': True,
                'flood_zones': [
                    {'id': 'z1', 'polygon': self.zone_a_poly, 'intensity': 0.85, 'water_level': 2.0}
                ]
            }
        }
        res = self.client.post('/api/route', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('normal', data)
        self.assertTrue(data['flood_active'])
        self.assertGreater(data['affected_roads_count'], 0)


if __name__ == '__main__':
    unittest.main()
