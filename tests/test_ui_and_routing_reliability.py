"""
RouteSense AI - Targeted UI & Routing Reliability Tests
Tests the 3-panel UI architecture, basemap configuration, route safety classification,
and rescue assistance handling required by the specification.
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


class TestUIRoutingReliability(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_01_no_flooding_efficient_route(self):
        """Scenario 1: With no flooding, routing returns an efficient route with valid safety status."""
        result = run_routing(DEFAULT_ORIGIN, DEFAULT_DEST, 'general')
        self.assertIsNotNone(result.get('routesense'))
        self.assertIn(result.get('route_safety'), ['safe', 'caution'])
        self.assertTrue(result.get('route_validated'))
        self.assertGreater(result['routesense']['distance'], 0)

        # Between verified low-risk locations, route safety must be strictly 'safe'
        town_hall = [76.2168, 10.5276]
        model_boys = [76.2205, 10.5255]
        safe_res = run_routing(town_hall, model_boys, 'general')
        self.assertIsNotNone(safe_res.get('routesense'))
        self.assertEqual(safe_res.get('route_safety'), 'safe')
        self.assertEqual(safe_res['routesense']['risk_counts'].get(2, 0), 0)

    def test_02_flooding_outside_route_remains_safe(self):
        """Scenario 2: Flooding outside the corridor keeps the route valid and safe."""
        far_point = [76.1600, 10.4600]
        result = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=far_point, flood_radius=1000,
            flood_intensity=0.8, water_level=2.0
        )
        self.assertIsNotNone(result.get('routesense'))
        self.assertIn(result.get('route_safety'), ['safe', 'caution'])
        self.assertTrue(result.get('route_validated'))

    def test_03_flooding_blocks_direct_path_finds_safe_detour(self):
        """Scenario 3: Flooding on normal path safely detours around hazard."""
        midpoint = [(DEFAULT_ORIGIN[0] + DEFAULT_DEST[0]) / 2,
                    (DEFAULT_ORIGIN[1] + DEFAULT_DEST[1]) / 2]
        result = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=midpoint, flood_radius=1200,
            flood_intensity=0.9, water_level=2.5
        )
        if result.get('routesense'):
            for feat in result['routesense']['geojson']['features']:
                self.assertFalse(feat['properties'].get('impassable', False))
            self.assertTrue(result['comparison']['routes_differ'])

    def test_04_all_routes_blocked_returns_rescue_required_status(self):
        """Scenario 4: When destination is engulfed in deep flood, no safe route is returned."""
        result = run_routing(
            DEFAULT_ORIGIN, DEFAULT_DEST, 'general',
            flood_center=DEFAULT_DEST, flood_radius=3000,
            flood_intensity=1.0, water_level=4.0
        )
        self.assertIsNone(result.get('routesense'))
        self.assertEqual(result.get('route_safety'), 'blocked')
        self.assertFalse(result.get('route_validated'))

    def test_05_unreachable_destination_handled_gracefully(self):
        """Scenario 5: Coordinates far outside the study area return an error dictionary cleanly."""
        res = self.client.post('/api/route', json={
            'origin': [0.0, 0.0],
            'destination': [0.0, 0.0],
            'profile': 'general'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('error', data)

    def test_06_frontend_html_three_panels_and_rescue_text(self):
        """Scenario 6: HTML has all three tabs and the exact rescue text."""
        html_path = ROOT_DIR / "frontend" / "index.html"
        content = html_path.read_text(encoding='utf-8')

        self.assertIn('id="tab-simulation"', content)
        self.assertIn('id="tab-status"', content)
        self.assertIn('id="tab-route"', content)

        self.assertIn('id="btn-play-pause"', content)
        self.assertIn('speed-1x', content)
        self.assertIn('speed-2x', content)
        self.assertIn('speed-5x', content)

        self.assertIn("No safe route available — request rescue assistance.", content)

    def test_07_frontend_basemap_dark_street_and_natural_satellite(self):
        """Scenario 7: App.js uses dark street tiles and natural satellite tiles."""
        js_path = ROOT_DIR / "frontend" / "app.js"
        content = js_path.read_text(encoding='utf-8')

        self.assertIn("cartocdn.com/dark_all", content)
        self.assertIn("arcgisonline.com/ArcGIS/rest/services/World_Imagery", content)
        self.assertIn("function switchBasemap", content)

    def test_08_css_no_global_map_filters(self):
        """Scenario 8: Style.css does not apply dark filter to entire map container."""
        css_path = ROOT_DIR / "frontend" / "style.css"
        content = css_path.read_text(encoding='utf-8')

        self.assertNotIn("filter: invert", content)
        self.assertNotIn("filter: grayscale", content)


if __name__ == '__main__':
    unittest.main()
