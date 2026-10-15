"""
RouteSense AI - 5 Core Routing Engine Invariant Scenarios
Verifies the 5 multi-hazard routing scenarios for Thrissur:
1. Dry shortest: rs_dist == normal_dist with 0 detour penalties
2. Nearest shelter distance sorting: strictly ascending by road_distance_m
3. Flooded alternative safe detour: routes around hazard on G_passable
4. Automatic shelter reallocation: when destination is blocked, finds nearest reachable shelter
5. Rescue message when trapped: returns blocked, routesense=None, and rescue assistance text
"""

import unittest
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from backend.app import (
    G_BASE, NODE_LIST, DEFAULT_ORIGIN, DEFAULT_DEST,
    nearest_node, run_routing, app
)


class TestRoutingInvariants(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_01_dry_shortest_route_invariant(self):
        """Scenario 1: Dry condition (flood_active == False): routesense equals normal shortest route."""
        res = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        self.assertIsNotNone(res.get('routesense'))
        self.assertEqual(res['routesense']['distance'], res['normal']['distance'])
        self.assertEqual(res['comparison']['distance_diff'], 0.0)
        self.assertEqual(res['comparison']['distance_pct'], 0.0)
        self.assertFalse(res['comparison']['routes_differ'])
        self.assertFalse(res['flood_active'])

    def test_02_nearest_shelter_distance_sorting(self):
        """Scenario 2: /api/nearest-shelter must sort shelters strictly by road_distance_m ascending."""
        response = self.client.post('/api/nearest-shelter', json={
            'origin': DEFAULT_ORIGIN,
            'profile': 'general'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('all_shelters', data)
        shelters = data['all_shelters']
        self.assertGreater(len(shelters), 1)

        distances = [s['road_distance_m'] for s in shelters]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual(shelters[0]['id'], data['best_shelter']['id'])

    def test_03_flooded_alternative_safe_detour(self):
        """Scenario 3: Flood on route finds safe alternative on G_passable with routes_differ=True."""
        midpoint = [(DEFAULT_ORIGIN[0] + DEFAULT_DEST[0]) / 2,
                    (DEFAULT_ORIGIN[1] + DEFAULT_DEST[1]) / 2]
        res = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=midpoint, flood_radius=1500,
            flood_intensity=0.9, water_level=2.5
        )
        self.assertIsNotNone(res.get('routesense'))
        self.assertTrue(res['comparison']['routes_differ'])
        self.assertTrue(res['flood_active'])
        for feat in res['routesense']['geojson']['features']:
            self.assertFalse(feat['properties'].get('impassable', False))
            self.assertLessEqual(feat['properties'].get('flood_penalty', 0), 0.85)

    def test_04_automatic_shelter_reallocation(self):
        """Scenario 4: When destination is blocked, automatically reallocates to closest reachable shelter."""
        # Flood centered directly on DEFAULT_DEST blocks destination
        res = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=DEFAULT_DEST, flood_radius=2500,
            flood_intensity=1.0, water_level=4.0,
            auto_reallocate=True
        )
        self.assertTrue(res.get('reallocated'))
        self.assertIsNotNone(res.get('reallocated_shelter'))
        self.assertIn('name', res['reallocated_shelter'])
        self.assertIsNotNone(res.get('reallocation_reason'))
        self.assertIsNotNone(res.get('routesense'))
        self.assertTrue(res.get('route_validated'))

        # Also verify via /api/route endpoint
        api_res = self.client.post('/api/route', json={
            'origin': DEFAULT_ORIGIN,
            'destination': DEFAULT_DEST,
            'profile': 'general',
            'flood': {
                'active': True,
                'center': DEFAULT_DEST,
                'radius': 2500,
                'intensity': 1.0,
                'water_level': 4.0
            }
        })
        api_data = api_res.get_json()
        self.assertTrue(api_data.get('reallocated'))
        self.assertIsNotNone(api_data.get('reallocated_shelter'))
        self.assertIsNotNone(api_data.get('routesense'))

    def test_05_rescue_message_when_trapped(self):
        """Scenario 5: Completely trapped origin returns blocked status and rescue assistance message."""
        # Flood engulfing origin and all immediate surroundings
        res = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=DEFAULT_ORIGIN, flood_radius=5000,
            flood_intensity=1.0, water_level=5.0,
            auto_reallocate=True
        )
        self.assertEqual(res.get('route_safety'), 'blocked')
        self.assertIsNone(res.get('routesense'))
        self.assertFalse(res.get('route_validated'))
        self.assertIn("No safe route available — request rescue assistance.", res.get('error', ''))


if __name__ == '__main__':
    unittest.main()
