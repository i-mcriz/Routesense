import urllib.request
import json

# 1. Test frontend files served
for path in ['/', '/style.css', '/app.js']:
    req = urllib.request.urlopen(f'http://127.0.0.1:5000{path}')
    assert req.status == 200, f'Failed {path}'
print('[OK] Frontend files served successfully')

# 2. Test /api/route with multi-zone payload
payload = {
    'origin': [76.1798, 10.4900],
    'destination': [76.2500, 10.5696],
    'profile': 'general',
    'flood': {
        'active': True,
        'flood_zones': [
            {'id': 'z1', 'polygon': [[76.21, 10.52], [76.22, 10.52], [76.22, 10.53], [76.21, 10.53]], 'intensity': 0.75, 'water_level': 1.5}
        ]
    }
}
req = urllib.request.Request('http://127.0.0.1:5000/api/route', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(req).read().decode())
assert 'normal' in resp and 'routesense' in resp
assert resp['flood_active'] is True
assert resp['affected_roads_count'] > 0
print(f"[OK] /api/route with flood_zones: normal dist={resp['normal']['distance']}m, rs dist={resp['routesense']['distance']}m, affected={resp['affected_roads_count']}")

# 3. Test /api/simulate-flood with flood_zones
sim_payload = {
    'flood_zones': [
        {'id': 'z1', 'polygon': [[76.21, 10.52], [76.22, 10.52], [76.22, 10.53], [76.21, 10.53]], 'intensity': 0.85, 'water_level': 2.0}
    ]
}
req_sim = urllib.request.Request('http://127.0.0.1:5000/api/simulate-flood', data=json.dumps(sim_payload).encode(), headers={'Content-Type': 'application/json'})
resp_sim = json.loads(urllib.request.urlopen(req_sim).read().decode())
assert resp_sim['affected_count'] > 0
print(f"[OK] /api/simulate-flood with flood_zones: affected={resp_sim['affected_count']}, ETA={resp_sim.get('avg_inundation_eta', 'N/A')}")
