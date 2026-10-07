/* ──────────────────────────────────────────────────────────
   RouteSense AI — Frontend Application
   Particle-style risk map with flood simulation & routing
   ────────────────────────────────────────────────────────── */

const API = '';  // same-origin
const STUDY_CENTER = [10.53, 76.215];
const STUDY_ZOOM = 13;

// ── State ─────────────────────────────────────────────────
let map, riskLayer, normalRouteLayer, rsRouteLayer, floodZoneLayer, floodMarker;
let originMarker = null, destMarker = null;
let originCoord = null, destCoord = null;
let clickMode = 'origin'; // 'origin' | 'dest' | null
let selectedProfile = 'general';
let floodCenter = null;
let routeAnimInterval = null;
let particleLayers = [];
let routeParticles = [];

// Risk colors
const RISK_COLORS = { 0: '#34d399', 1: '#fbbf24', 2: '#ef4444' };
const RISK_ALPHA = { 0: 0.35, 1: 0.5, 2: 0.65 };

// ── Initialize ────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
    initMap();
    await loadRiskMap();
    setStatus('ok', 'NORMAL CONDITIONS');
    hideLoading();
});

function initMap() {
    const bounds = L.latLngBounds(
        [10.46, 76.15], // SouthWest
        [10.60, 76.28]  // NorthEast
    );

    map = L.map('map', {
        center: STUDY_CENTER,
        zoom: STUDY_ZOOM,
        minZoom: 12,
        maxBounds: bounds,
        maxBoundsViscosity: 1.0,
        zoomControl: false,
        attributionControl: true
    });

    // Satellite tile layer (No API key required)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        maxZoom: 19
    }).addTo(map);

    // Map click handler
    map.on('click', onMapClick);

    // Initialize layer groups
    riskLayer = L.layerGroup().addTo(map);
    normalRouteLayer = L.layerGroup().addTo(map);
    rsRouteLayer = L.layerGroup().addTo(map);
    floodZoneLayer = L.layerGroup().addTo(map);
}

// ── Risk Map (Particle Style) ─────────────────────────────

async function loadRiskMap() {
    setStatus('info', 'LOADING RISK MAP');
    try {
        const res = await fetch(`${API}/api/risk-map`);
        const geojson = await res.json();
        renderParticleRiskMap(geojson);
    } catch (e) {
        console.error('Failed to load risk map:', e);
        setStatus('danger', 'LOAD ERROR');
    }
}

function renderParticleRiskMap(geojson) {
    riskLayer.clearLayers();
    particleLayers = [];

    const canvas = L.canvas({ padding: 0.2 });

    geojson.features.forEach(f => {
        const coords = f.geometry.coordinates;
        const risk = f.properties.predicted_risk;
        const color = RISK_COLORS[risk] || RISK_COLORS[0];
        const alpha = RISK_ALPHA[risk] || 0.3;

        // Sample particles along the LineString
        const step = risk === 2 ? 0.0004 : (risk === 1 ? 0.0007 : 0.0012);

        for (let i = 0; i < coords.length - 1; i++) {
            const [x1, y1] = coords[i];
            const [x2, y2] = coords[i + 1];
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx * dx + dy * dy);
            const n = Math.max(1, Math.floor(len / step));

            for (let j = 0; j <= n; j++) {
                const t = j / n;
                const px = x1 + dx * t;
                const py = y1 + dy * t;
                const marker = L.circleMarker([py, px], {
                    radius: risk === 2 ? 2.0 : (risk === 1 ? 1.6 : 1.2),
                    color: color,
                    fillColor: color,
                    fillOpacity: alpha,
                    weight: 0,
                    renderer: canvas
                });
                riskLayer.addLayer(marker);
                particleLayers.push({ marker, risk, origRisk: risk });
            }
        }
    });
}

// ── Map Click ─────────────────────────────────────────────

function onMapClick(e) {
    const { lat, lng } = e.latlng;

    // Check if user is placing a flood center (Shift+Click or flood mode)
    if (e.originalEvent.shiftKey || document.getElementById('flood-panel').classList.contains('flood-placing')) {
        setFloodCenter(lng, lat);
        return;
    }

    if (clickMode === 'origin') {
        setOrigin(lng, lat);
        clickMode = 'dest';
        document.getElementById('map-hint').innerHTML = 'Click map to set <strong>destination</strong>';
    } else if (clickMode === 'dest') {
        setDestination(lng, lat);
        clickMode = null;
        document.getElementById('map-hint').classList.add('hidden');
    } else {
        // Cycle: set as flood center with shift, or re-set origin
        setFloodCenter(lng, lat);
    }
}

function setOrigin(lon, lat) {
    originCoord = [lon, lat];
    if (originMarker) map.removeLayer(originMarker);
    originMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'origin-marker', iconSize: [18, 18], iconAnchor: [9, 9] })
    }).addTo(map);
    document.getElementById('origin-display').textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    document.getElementById('origin-display').classList.add('set');
}

function setDestination(lon, lat) {
    destCoord = [lon, lat];
    if (destMarker) map.removeLayer(destMarker);
    destMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'dest-marker', iconSize: [18, 18], iconAnchor: [9, 9] })
    }).addTo(map);
    document.getElementById('dest-display').textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    document.getElementById('dest-display').classList.add('set');
}

let floodCircles = [];
let floodAnimInterval = null;

function setFloodCenter(lon, lat) {
    floodCenter = [lon, lat];
    clearFloodMarkers();

    const radius = parseFloat(document.getElementById('flood-radius').value);

    // Create multiple concentric circles for a 3D-ish water effect
    for(let i=0; i<3; i++) {
        const c = L.circle([lat, lon], {
            radius: radius * (1 - i*0.25),
            color: '#3b82f6',
            weight: 2,
            fillColor: '#60a5fa',
            fillOpacity: 0.15,
            className: 'water-ring'
        }).addTo(map);
        floodCircles.push({circle: c, baseRadius: radius * (1 - i*0.25), offset: i});
    }

    // Animate breathing/rising water effect
    let t = 0;
    floodAnimInterval = setInterval(() => {
        t += 0.05;
        floodCircles.forEach(fc => {
            const scale = 1 + 0.08 * Math.sin(t + fc.offset);
            fc.circle.setRadius(fc.baseRadius * scale);
            fc.circle.setStyle({fillOpacity: 0.15 + 0.1 * Math.sin(t*1.5 + fc.offset)});
        });
    }, 50);

    document.getElementById('legend-flood').style.display = 'flex';
    setStatus('warning', 'FLOOD CENTER PLACED');
}

function clearFloodMarkers() {
    if (floodAnimInterval) { clearInterval(floodAnimInterval); floodAnimInterval = null; }
    floodCircles.forEach(fc => map.removeLayer(fc.circle));
    floodCircles = [];
    if (floodMarker) { map.removeLayer(floodMarker); floodMarker = null; }
}

// ── Defaults ──────────────────────────────────────────────

function useDefaults() {
    setOrigin(76.1798295, 10.4900642);
    setDestination(76.2500925, 10.5696931);
    clickMode = null;
    document.getElementById('map-hint').classList.add('hidden');
}

function clearPoints() {
    if (originMarker) { map.removeLayer(originMarker); originMarker = null; }
    if (destMarker) { map.removeLayer(destMarker); destMarker = null; }
    originCoord = null;
    destCoord = null;
    clickMode = 'origin';
    document.getElementById('origin-display').textContent = 'Click map or use default';
    document.getElementById('dest-display').textContent = 'Click map or use default';
    document.getElementById('origin-display').classList.remove('set');
    document.getElementById('dest-display').classList.remove('set');
    document.getElementById('map-hint').classList.remove('hidden');
    document.getElementById('map-hint').innerHTML = 'Click map to set <strong>origin</strong>, then <strong>destination</strong>';
    clearRoutes();
}

// ── Profiles ──────────────────────────────────────────────

function selectProfile(profile) {
    selectedProfile = profile;
    document.querySelectorAll('.profile-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-profile="${profile}"]`).classList.add('active');
}

// ── Routing ───────────────────────────────────────────────

async function findRoute() {
    if (!originCoord || !destCoord) {
        useDefaults();
    }

    const btn = document.getElementById('btn-route');
    btn.disabled = true;
    btn.textContent = 'CALCULATING…';
    setStatus('info', 'ROUTING IN PROGRESS');

    const payload = {
        origin: originCoord,
        destination: destCoord,
        profile: selectedProfile,
        flood: null
    };

    if (floodCenter) {
        payload.flood = {
            active: true,
            center: floodCenter,
            radius: parseFloat(document.getElementById('flood-radius').value),
            intensity: parseFloat(document.getElementById('flood-intensity').value),
            water_level: parseFloat(document.getElementById('water-level').value)
        };
    }

    try {
        const res = await fetch(`${API}/api/route`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();

        if (data.error) {
            setStatus('danger', data.error.toUpperCase());
            btn.textContent = 'FIND SAFER ROUTE';
            btn.disabled = false;
            return;
        }

        renderRoutes(data);
        renderImpact(data);

        if (data.flood_active) {
            setStatus('warning', 'FLOOD SIMULATION ACTIVE');
        } else {
            setStatus('ok', 'ROUTE UPDATED');
        }
    } catch (e) {
        console.error('Routing error:', e);
        setStatus('danger', 'ROUTING FAILED');
    }

    btn.textContent = 'FIND SAFER ROUTE';
    btn.disabled = false;
}

function clearRoutes() {
    normalRouteLayer.clearLayers();
    rsRouteLayer.clearLayers();
    if (routeAnimInterval) { clearInterval(routeAnimInterval); routeAnimInterval = null; }
    routeParticles = [];
    document.getElementById('impact-panel').style.display = 'none';
}

function renderRoutes(data) {
    clearRoutes();

    // Normal route — thin blue line
    if (data.normal && data.normal.coordinates) {
        const latlngs = data.normal.coordinates.map(c => [c[1], c[0]]);
        L.polyline(latlngs, {
            color: '#60a5fa',
            weight: 3,
            opacity: 0.5,
            dashArray: '8 6'
        }).addTo(normalRouteLayer);
    }

    // RouteSense route — particle-animated purple
    if (data.routesense && data.routesense.coordinates) {
        const coords = data.routesense.coordinates;
        const latlngs = coords.map(c => [c[1], c[0]]);

        // Base line
        L.polyline(latlngs, {
            color: '#c084fc',
            weight: 4,
            opacity: 0.7
        }).addTo(rsRouteLayer);

        // Animate particles along route
        animateRouteParticles(coords);
    }
}

function animateRouteParticles(coords) {
    // Create a set of particles that travel along the route
    const totalPoints = coords.length;
    if (totalPoints < 2) return;

    const NUM_PARTICLES = 8;
    const particles = [];

    for (let i = 0; i < NUM_PARTICLES; i++) {
        const marker = L.circleMarker([0, 0], {
            radius: 4,
            color: '#e9d5ff',
            fillColor: '#c084fc',
            fillOpacity: 0.9,
            weight: 1
        }).addTo(rsRouteLayer);
        particles.push({
            marker,
            progress: i / NUM_PARTICLES  // stagger start
        });
    }

    routeParticles = particles;

    routeAnimInterval = setInterval(() => {
        particles.forEach(p => {
            p.progress += 0.003;
            if (p.progress > 1) p.progress = 0;

            const idx = p.progress * (totalPoints - 1);
            const i = Math.floor(idx);
            const t = idx - i;
            const c1 = coords[Math.min(i, totalPoints - 1)];
            const c2 = coords[Math.min(i + 1, totalPoints - 1)];
            const lon = c1[0] + (c2[0] - c1[0]) * t;
            const lat = c1[1] + (c2[1] - c1[1]) * t;
            p.marker.setLatLng([lat, lon]);
        });
    }, 40);
}

// ── Impact Panel ──────────────────────────────────────────

function renderImpact(data) {
    const panel = document.getElementById('impact-panel');
    panel.style.display = 'block';

    const n = data.normal;
    const r = data.routesense;
    const c = data.comparison;

    document.getElementById('metric-dist').textContent =
        `${(n.distance / 1000).toFixed(2)} → ${(r.distance / 1000).toFixed(2)} km`;
    document.getElementById('metric-high').textContent =
        `${n.risk_counts['2'] || 0} → ${r.risk_counts['2'] || 0}`;
    document.getElementById('metric-reduction').textContent =
        `${c.risk_reduction_pct}%`;
    document.getElementById('metric-dist-change').textContent =
        `${c.distance_pct > 0 ? '+' : ''}${c.distance_pct}%`;

    const msg = document.getElementById('route-status-msg');
    if (c.routes_differ) {
        msg.textContent = `RouteSense found a safer route, avoiding ${c.high_risk_avoided} high-risk segments.`;
        msg.style.color = '#34d399';
    } else {
        msg.textContent = 'Both routes are identical — the shortest path is already safe.';
        msg.style.color = 'rgba(255,255,255,0.4)';
    }
}

// ── Flood Simulation ──────────────────────────────────────

async function simulateFlood() {
    if (!floodCenter) {
        setStatus('warning', 'PLACE FLOOD CENTER FIRST');
        // Enable shift-click mode hint
        return;
    }

    setStatus('info', 'SIMULATING FLOOD');

    const intensity = parseFloat(document.getElementById('flood-intensity').value);
    const waterLevel = parseFloat(document.getElementById('water-level').value);
    const radius = parseFloat(document.getElementById('flood-radius').value);
    
    floodCircles.forEach((fc, i) => {
        fc.baseRadius = radius * (1 - i*0.25);
        fc.circle.setStyle({
            color: `rgba(59,130,246,${0.3 + intensity * 0.4})`,
            fillColor: `rgba(59,130,246,${0.1 + intensity * 0.2})`
        });
    });

    // If route exists, recalculate
    if (originCoord && destCoord) {
        await findRoute();
    }

    setStatus('warning', 'FLOOD SIMULATION ACTIVE');
}

function resetFlood() {
    floodCenter = null;
    clearFloodMarkers();
    floodZoneLayer.clearLayers();
    document.getElementById('legend-flood').style.display = 'none';

    // Reset sliders
    document.getElementById('flood-intensity').value = 0.5;
    document.getElementById('water-level').value = 1.0;
    document.getElementById('flood-radius').value = 2000;
    updateSliderLabels();

    // Recalculate route without flood if points exist
    if (originCoord && destCoord) {
        findRoute();
    }

    setStatus('ok', 'NORMAL CONDITIONS');
}

// ── Panel Toggle ──────────────────────────────────────────

function togglePanel(id) {
    document.getElementById(id).classList.toggle('collapsed');
}

// ── Status ────────────────────────────────────────────────

function setStatus(type, text) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-text');
    dot.className = type;
    label.textContent = text;
}

// ── Loading ───────────────────────────────────────────────

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    overlay.classList.add('hidden');
    setTimeout(() => overlay.remove(), 700);
}

// ── Slider Label Updates ──────────────────────────────────

function updateSliderLabels() {
    document.getElementById('intensity-val').textContent =
        parseFloat(document.getElementById('flood-intensity').value).toFixed(2);
    document.getElementById('water-val').textContent =
        parseFloat(document.getElementById('water-level').value).toFixed(1) + ' m';
    document.getElementById('radius-val').textContent =
        document.getElementById('flood-radius').value + 'm';
}

document.addEventListener('DOMContentLoaded', () => {
    ['flood-intensity', 'water-level', 'flood-radius'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateSliderLabels);
    });
});
