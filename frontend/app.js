/* ──────────────────────────────────────────────────────────
   RouteSense AI — Frontend Application
   Particle-style risk map with flood simulation & routing
   ────────────────────────────────────────────────────────── */

const API = '';  // same-origin
const STUDY_CENTER = [10.53, 76.215];
const STUDY_ZOOM = 13;

// ── State ─────────────────────────────────────────────────
let map;
let streetsTileLayer, satelliteTileLayer;
let currentBasemap = 'streets';

let riskLayer, normalRouteLayer, rsRouteLayer, floodZoneLayer, affectedRoadsLayer, riversLayer;
let originMarker = null, destMarker = null;
let originCoord = null, destCoord = null;
let clickMode = null; // 'origin' | 'dest' | null
let selectedProfile = 'general';
let floodMode = 'circle'; // 'circle' | 'zones'
let floodCenter = null;
let isPlacingCircle = false;
let isDrawingZone = false;
let currentZonePoints = []; // [[lon, lat], ...]
let tempDrawingLayer = null;
let zones = []; // [{ id, name, polygon: [[lon,lat],...], intensity: 0.70, water_level: 1.0, layer }]
let selectedZoneId = null;

let routeAnimInterval = null;
let particleLayers = [];
let routeParticles = [];
let affectedRoadPolylines = [];
let currentFocus = 'BALANCED';

// Risk colors
const RISK_COLORS = { 0: '#34d399', 1: '#fbbf24', 2: '#ef4444' };
const RISK_ALPHA = { 0: 0.35, 1: 0.5, 2: 0.65 };

// ── Initialize ────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
    initMap();
    await Promise.all([
        loadRiskMap(),
        loadRivers()
    ]);
    setStatus('ok', 'READY: Thrissur Evacuation System');
    hideLoading();
});

function initMap() {
    const bounds = L.latLngBounds(
        [10.46, 76.15], // SouthWest
        [10.60, 76.28]  // NorthEast
    );

    map = L.map('map', {
        preferCanvas: true, // GPU Hardware Accelerated Canvas (NVIDIA RTX / WebGL)
        center: STUDY_CENTER,
        zoom: STUDY_ZOOM,
        minZoom: 12,
        maxBounds: bounds,
        maxBoundsViscosity: 1.0,
        zoomControl: false,
        attributionControl: true
    });

    // Basemaps (Default: OpenStreetMap as street map; Satellite as alternative)
    streetsTileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    satelliteTileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and GIS User Community',
        maxZoom: 19
    });

    // Map click handler
    map.on('click', onMapClick);

    // Initialize layer groups in proper rendering order (bottom to top)
    riversLayer = L.layerGroup().addTo(map);
    riskLayer = L.layerGroup().addTo(map);
    affectedRoadsLayer = L.layerGroup().addTo(map);
    floodZoneLayer = L.layerGroup().addTo(map);
    normalRouteLayer = L.layerGroup().addTo(map);
    rsRouteLayer = L.layerGroup().addTo(map);
}

// ── Basemap & Layer Controls ──────────────────────────────

function switchBasemap(style) {
    if (style === currentBasemap) return;
    if (style === 'streets') {
        map.removeLayer(satelliteTileLayer);
        map.addLayer(streetsTileLayer);
        document.getElementById('basemap-streets').classList.add('active');
        document.getElementById('basemap-satellite').classList.remove('active');
        currentBasemap = 'streets';
    } else {
        map.removeLayer(streetsTileLayer);
        map.addLayer(satelliteTileLayer);
        document.getElementById('basemap-satellite').classList.add('active');
        document.getElementById('basemap-streets').classList.remove('active');
        currentBasemap = 'satellite';
    }
}

function toggleLayerGroup(groupName, isVisible) {
    const layerMap = {
        'particles': riskLayer,
        'affected': affectedRoadsLayer,
        'flood': floodZoneLayer,
        'rivers': riversLayer,
        'routesense': rsRouteLayer,
        'normal': normalRouteLayer
    };
    const layer = layerMap[groupName];
    if (!layer) return;

    if (isVisible) {
        if (!map.hasLayer(layer)) map.addLayer(layer);
    } else {
        if (map.hasLayer(layer)) map.removeLayer(layer);
    }
}

// ── Adaptive Prominence Focus States ───────────────────────

function setMapFocus(focusState) {
    currentFocus = focusState;
    document.querySelectorAll('.focus-btn').forEach(btn => btn.classList.remove('active'));

    const btnIdMap = {
        'BALANCED': 'focus-balanced',
        'ROUTE_FOCUS': 'focus-route',
        'FLOOD_ROAD_FOCUS': 'focus-flood-road',
        'FLOOD_ZONE_FOCUS': 'focus-flood-zone',
        'ENVIRONMENT_FOCUS': 'focus-env'
    };
    const activeBtn = document.getElementById(btnIdMap[focusState]);
    if (activeBtn) activeBtn.classList.add('active');

    // Define opacity profiles per focus state without altering whole map container
    const opacities = {
        'BALANCED':          { particles: 1.0, affected: 0.85, flood: 0.35, rivers: 0.85, rsRoute: 1.0, normalRoute: 0.8 },
        'ROUTE_FOCUS':       { particles: 0.15, affected: 0.40, flood: 0.20, rivers: 0.30, rsRoute: 1.0, normalRoute: 0.9 },
        'FLOOD_ROAD_FOCUS':  { particles: 0.15, affected: 1.00, flood: 0.35, rivers: 0.35, rsRoute: 0.85, normalRoute: 0.75 },
        'FLOOD_ZONE_FOCUS':  { particles: 0.20, affected: 0.60, flood: 0.85, rivers: 0.40, rsRoute: 0.75, normalRoute: 0.70 },
        'ENVIRONMENT_FOCUS': { particles: 0.20, affected: 0.45, flood: 0.30, rivers: 1.00, rsRoute: 0.60, normalRoute: 0.60 }
    };

    const cfg = opacities[focusState] || opacities['BALANCED'];

    // Update particles opacity
    particleLayers.forEach(p => {
        const baseAlpha = RISK_ALPHA[p.origRisk] || 0.3;
        p.marker.setStyle({ fillOpacity: baseAlpha * cfg.particles });
    });

    // Update affected roads opacity
    affectedRoadPolylines.forEach(a => {
        a.polyline.setStyle({ opacity: a.baseOpacity * cfg.affected });
    });

    // Update flood zone opacity
    floodCircles.forEach(fc => {
        fc.circle.setStyle({ fillOpacity: 0.15 * cfg.flood, opacity: 0.7 * cfg.flood });
    });
    zones.forEach(z => {
        if (z.layer && z.layer.setStyle) {
            z.layer.setStyle({ fillOpacity: (0.15 + (z.intensity || 0.7) * 0.35) * cfg.flood, opacity: 0.8 * cfg.flood });
        }
    });

    // Update rivers opacity
    riversLayer.eachLayer(l => {
        if (l.setStyle) l.setStyle({ opacity: 0.9 * cfg.rivers });
    });

    // Update routes opacity
    rsRouteLayer.eachLayer(l => {
        if (l.setStyle) {
            // green outline vs risk inner segment
            const isOutline = l.options.weight > 6;
            l.setStyle({ opacity: (isOutline ? 0.7 : 0.95) * cfg.rsRoute });
        }
    });
    normalRouteLayer.eachLayer(l => {
        if (l.setStyle) l.setStyle({ opacity: 0.8 * cfg.normalRoute });
    });
}

// ── Rivers & Environmental Features ───────────────────────

async function loadRivers() {
    try {
        const res = await fetch(`${API}/api/rivers`);
        const geojson = await res.json();
        renderRivers(geojson);
    } catch (e) {
        console.warn('Rivers layer unavailable:', e);
    }
}

function renderRivers(geojson) {
    riversLayer.clearLayers();
    if (!geojson || !geojson.features) return;

    geojson.features.forEach(f => {
        const coords = f.geometry.coordinates.map(c => [c[1], c[0]]);
        const isCanal = f.properties.type && f.properties.type.includes('canal');
        const poly = L.polyline(coords, {
            color: '#06b6d4',
            weight: isCanal ? 2.0 : 3.5,
            opacity: 0.85,
            dashArray: isCanal ? '4 4' : null
        }).addTo(riversLayer);

        poly.bindPopup(`<strong>${f.properties.name || 'Waterway'}</strong><br>Type: ${f.properties.type || 'Channel'}`);
    });
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

// ── Map Click & Drawing / Interaction Modes ───────────────

function onMapClick(e) {
    const { lat, lng } = e.latlng;

    // 1. Explicit Start & Destination Selection
    if (clickMode === 'origin') {
        setOrigin(lng, lat);
        clickMode = 'dest';
        const hint = document.getElementById('map-hint');
        if (hint) {
            hint.classList.remove('hidden');
            hint.innerHTML = 'Click map to set <strong>destination</strong>';
        }
        return;
    } else if (clickMode === 'dest') {
        setDestination(lng, lat);
        clickMode = null;
        const hint = document.getElementById('map-hint');
        if (hint) hint.classList.add('hidden');
        findRoute();
        return;
    }

    // 2. Custom Flood Zone Mode: clicking map places vertices
    if (floodMode === 'zones') {
        if (!isDrawingZone) {
            startDrawingZone();
        }
        addZoneVertex(lng, lat);
        return;
    }

    // 3. Circle Mode (baseline): clicking map places flood center immediately
    if (floodMode === 'circle' || isPlacingCircle || e.originalEvent?.shiftKey) {
        setFloodCenter(lng, lat);
        if (isPlacingCircle) {
            togglePlaceCircleMode(false);
        }
        return;
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

function setClickMode(mode) {
    clickMode = mode;
    const hint = document.getElementById('map-hint');
    if (hint) {
        hint.classList.remove('hidden');
        hint.innerHTML = mode === 'origin' ? 'Click map to set <strong>origin</strong>' : 'Click map to set <strong>destination</strong>';
    }
    setStatus('info', `CLICK MAP TO SET ${mode.toUpperCase()}`);
}

// ── Flood Simulation Controls ─────────────────────────────

let floodCircles = [];
let floodAnimInterval = null;
let autoSimulateTimer = null;

function debounceAutoSimulate(delay = 80) {
    if (autoSimulateTimer) clearTimeout(autoSimulateTimer);
    autoSimulateTimer = setTimeout(() => {
        window.requestAnimationFrame(() => {
            simulateFlood();
        });
    }, delay);
}

function setFloodMode(mode) {
    floodMode = mode;
    if (mode === 'circle') {
        document.getElementById('mode-circle-btn').classList.add('active');
        document.getElementById('mode-polygon-btn').classList.remove('active');
        document.getElementById('circle-controls').style.display = 'block';
        document.getElementById('polygon-controls').style.display = 'none';
        setStatus('ok', 'CIRCLE FLOOD MODE: Click map to place flood center');

        // Show circles, hide custom zones
        floodCircles.forEach(fc => {
            if (!floodZoneLayer.hasLayer(fc.circle)) floodZoneLayer.addLayer(fc.circle);
        });
        zones.forEach(z => {
            if (z.layer && floodZoneLayer.hasLayer(z.layer)) floodZoneLayer.removeLayer(z.layer);
        });
    } else {
        document.getElementById('mode-circle-btn').classList.remove('active');
        document.getElementById('mode-polygon-btn').classList.add('active');
        document.getElementById('circle-controls').style.display = 'none';
        document.getElementById('polygon-controls').style.display = 'block';
        setStatus('info', 'CUSTOM FLOOD ZONES: Click map to draw zone vertices');

        // Hide circles, show custom zones
        floodCircles.forEach(fc => {
            if (floodZoneLayer.hasLayer(fc.circle)) floodZoneLayer.removeLayer(fc.circle);
        });
        zones.forEach(z => {
            if (z.layer && !floodZoneLayer.hasLayer(z.layer)) floodZoneLayer.addLayer(z.layer);
        });

        // Automatically activate drawing if no custom zones exist yet
        if (zones.length === 0 && !isDrawingZone) {
            startDrawingZone();
        }
    }
    debounceAutoSimulate(80);
}

// ── Baseline Circular Flood Placement ──

function togglePlaceCircleMode(explicitState) {
    if (explicitState !== undefined) {
        isPlacingCircle = explicitState;
    } else {
        isPlacingCircle = !isPlacingCircle;
    }
    const btn = document.getElementById('btn-place-circle');
    const hint = document.getElementById('flood-hint');
    if (isPlacingCircle) {
        if (btn) {
            btn.textContent = '✕ Cancel';
            btn.classList.add('danger-text');
        }
        if (hint) hint.innerHTML = '<strong>Click anywhere on map</strong> to place center';
        setStatus('warning', 'CLICK MAP TO SET CIRCLE CENTER');
        map.getContainer().classList.add('drawing-cursor');
    } else {
        if (btn) {
            btn.textContent = '🎯 Place Center';
            btn.classList.remove('danger-text');
        }
        if (hint) hint.textContent = "Click 'Place Center' or Shift+Click map";
        map.getContainer().classList.remove('drawing-cursor');
    }
}

function setFloodCenter(lon, lat) {
    floodCenter = [lon, lat];
    clearFloodMarkers();

    const radius = parseFloat(document.getElementById('flood-radius').value);
    const circleIntensity = (parseFloat(document.getElementById('circle-intensity')?.value || 50)) / 100.0;

    // Create 3 concentric circles for layered flood visual
    for (let i = 0; i < 3; i++) {
        const c = L.circle([lat, lon], {
            radius: radius * (1 - i * 0.25),
            color: '#3b82f6',
            weight: 2,
            fillColor: '#60a5fa',
            fillOpacity: 0.12 + circleIntensity * 0.15,
            className: 'water-ring'
        }).addTo(floodZoneLayer);
        floodCircles.push({ circle: c, baseRadius: radius * (1 - i * 0.25), offset: i });
    }

    // Animate breathing/rising water effect
    let t = 0;
    floodAnimInterval = setInterval(() => {
        t += 0.05;
        floodCircles.forEach(fc => {
            const scale = 1 + 0.08 * Math.sin(t + fc.offset);
            fc.circle.setRadius(fc.baseRadius * scale);
            fc.circle.setStyle({ fillOpacity: 0.12 + 0.08 * Math.sin(t * 1.5 + fc.offset) });
        });
    }, 50);

    document.getElementById('legend-flood').style.display = 'flex';
    setStatus('warning', 'FLOOD CENTER PLACED');

    // Automatically trigger live flood simulation and dynamic rerouting
    debounceAutoSimulate(100);
}

function clearFloodMarkers() {
    if (floodAnimInterval) { clearInterval(floodAnimInterval); floodAnimInterval = null; }
    floodCircles.forEach(fc => floodZoneLayer.removeLayer(fc.circle));
    floodCircles = [];
}

// ── Custom Flood Zones Drawing & Selection Workflow ───────

function startDrawingZone() {
    isDrawingZone = true;
    currentZonePoints = [];
    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }

    map.getContainer().classList.add('drawing-cursor');
    const drawBtn = document.getElementById('btn-draw-zone');
    const activeRow = document.getElementById('zone-drawing-active-row');
    const finishBtn = document.getElementById('btn-finish-poly');
    const statusHint = document.getElementById('poly-status');

    if (drawBtn) drawBtn.style.display = 'none';
    if (activeRow) activeRow.style.display = 'flex';
    if (finishBtn) finishBtn.disabled = true;
    if (statusHint) statusHint.textContent = 'Click map to place boundary vertices (minimum 3 points)';

    setStatus('warning', 'DRAWING FLOOD ZONE: Click points along boundary');
}

function addZoneVertex(lon, lat) {
    currentZonePoints.push([lon, lat]);
    const latlngs = currentZonePoints.map(p => [p[1], p[0]]);

    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }

    const group = L.featureGroup();
    // Vertex dots
    latlngs.forEach(ll => {
        L.circleMarker(ll, {
            radius: 5,
            color: '#38bdf8',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 2
        }).addTo(group);
    });

    if (currentZonePoints.length === 2) {
        L.polyline(latlngs, {
            color: '#38bdf8',
            weight: 3,
            dashArray: '6 6'
        }).addTo(group);
    } else if (currentZonePoints.length >= 3) {
        L.polygon(latlngs, {
            color: '#38bdf8',
            weight: 3,
            dashArray: '6 6',
            fillColor: '#38bdf8',
            fillOpacity: 0.25
        }).addTo(group);
    }

    tempDrawingLayer = group.addTo(map);

    const count = currentZonePoints.length;
    const statusHint = document.getElementById('poly-status');
    if (statusHint) {
        if (count < 3) {
            statusHint.textContent = `${count} points placed. Click at least ${3 - count} more point(s) to form a zone.`;
        } else {
            statusHint.textContent = `${count} points placed. Click Finish Zone when done.`;
        }
    }

    const finishBtn = document.getElementById('btn-finish-poly');
    if (finishBtn) {
        finishBtn.disabled = count < 3;
    }
}

function finishZone() {
    if (currentZonePoints.length < 3) {
        alert("Please click at least 3 points on the map to define a flood zone area.");
        return;
    }

    // Shoelace formula area check to reject collapsed / zero-area polygons
    let area = 0;
    for (let i = 0; i < currentZonePoints.length; i++) {
        const j = (i + 1) % currentZonePoints.length;
        area += currentZonePoints[i][0] * currentZonePoints[j][1];
        area -= currentZonePoints[j][0] * currentZonePoints[i][1];
    }
    area = Math.abs(area) * 0.5;
    if (area < 0.00000001) {
        alert("Invalid flood zone: Region has zero area. Please click points around a visible area.");
        return;
    }

    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }

    const zoneId = 'zone_' + Date.now();
    const zoneName = `Zone ${zones.length + 1}`;
    const defaultIntensity = 0.70; // 70% simulated rainfall

    const latlngs = currentZonePoints.map(p => [p[1], p[0]]);
    const polygonLayer = L.polygon(latlngs, {
        color: '#3b82f6',
        weight: 2.5,
        fillColor: '#3b82f6',
        fillOpacity: 0.25 + defaultIntensity * 0.35,
        className: 'flood-custom-zone'
    }).addTo(floodZoneLayer);

    // Clicking zone on map selects it!
    polygonLayer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        selectZone(zoneId);
    });

    const newZone = {
        id: zoneId,
        name: zoneName,
        polygon: [...currentZonePoints],
        intensity: defaultIntensity,
        water_level: parseFloat(document.getElementById('water-level')?.value || 1.0),
        layer: polygonLayer
    };

    zones.push(newZone);

    // Reset drawing UI
    isDrawingZone = false;
    currentZonePoints = [];
    map.getContainer().classList.remove('drawing-cursor');
    const drawBtn = document.getElementById('btn-draw-zone');
    if (drawBtn) drawBtn.style.display = 'block';
    const activeRow = document.getElementById('zone-drawing-active-row');
    if (activeRow) activeRow.style.display = 'none';
    const statusHint = document.getElementById('poly-status');
    if (statusHint) statusHint.textContent = `Created ${zoneName}. Select to adjust simulated rainfall.`;
    document.getElementById('legend-flood').style.display = 'flex';

    updateZoneSelectorUI();
    selectZone(zoneId);

    // Commit state and trigger live simulation
    debounceAutoSimulate(100);
}

function cancelDrawingZone() {
    isDrawingZone = false;
    currentZonePoints = [];
    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }
    map.getContainer().classList.remove('drawing-cursor');
    const drawBtn = document.getElementById('btn-draw-zone');
    const activeRow = document.getElementById('zone-drawing-active-row');
    const statusHint = document.getElementById('poly-status');

    if (drawBtn) drawBtn.style.display = 'block';
    if (activeRow) activeRow.style.display = 'none';
    if (statusHint) statusHint.textContent = 'Drawing cancelled. No flood zone created.';
    setStatus('ok', 'DRAWING CANCELLED');
}

function updateZoneSelectorUI() {
    const sel = document.getElementById('zone-selector');
    const badge = document.getElementById('zone-count-badge');
    if (badge) badge.textContent = zones.length;

    if (!sel) return;
    sel.innerHTML = '';

    if (zones.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No custom zones created';
        sel.appendChild(opt);
        document.getElementById('btn-delete-zone').disabled = true;
        document.getElementById('zone-rainfall-intensity').disabled = true;
        return;
    }

    document.getElementById('btn-delete-zone').disabled = false;
    document.getElementById('zone-rainfall-intensity').disabled = false;

    zones.forEach(z => {
        const opt = document.createElement('option');
        opt.value = z.id;
        const pct = Math.round(z.intensity * 100);
        const cat = getIntensityCategory(pct);
        opt.textContent = `${z.name} (${pct}% - ${cat.label.split(' ')[0]})`;
        sel.appendChild(opt);
    });

    if (selectedZoneId) {
        sel.value = selectedZoneId;
    }
}

function onZoneSelect(zoneId) {
    if (!zoneId) return;
    selectZone(zoneId);
}

function selectZone(zoneId) {
    selectedZoneId = zoneId;
    const selectedZone = zones.find(z => z.id === zoneId);
    if (!selectedZone) return;

    // Visual distinction: selected zone gets bright cyan highlight border and higher prominence
    zones.forEach(z => {
        const isSel = z.id === zoneId;
        const pct = Math.round(z.intensity * 100);
        if (isSel) {
            z.layer.setStyle({
                color: '#38bdf8',
                weight: 4.0,
                fillColor: '#38bdf8',
                fillOpacity: 0.20 + (pct / 100) * 0.40
            });
            z.layer.bringToFront();
        } else {
            z.layer.setStyle({
                color: '#3b82f6',
                weight: 2.0,
                fillColor: '#3b82f6',
                fillOpacity: 0.12 + (pct / 100) * 0.25
            });
        }
    });

    const sel = document.getElementById('zone-selector');
    if (sel) sel.value = zoneId;

    const slider = document.getElementById('zone-rainfall-intensity');
    if (slider) {
        slider.disabled = false;
        const pct = Math.round(selectedZone.intensity * 100);
        slider.value = pct;
        const valEl = document.getElementById('zone-intensity-val');
        if (valEl) valEl.textContent = `${pct}%`;

        const cat = getIntensityCategory(pct);
        const badge = document.getElementById('zone-intensity-category');
        if (badge) {
            badge.textContent = cat.label;
            badge.className = `intensity-badge ${cat.badgeClass}`;
        }
    }

    document.getElementById('btn-delete-zone').disabled = false;
    setStatus('warning', `SELECTED ${selectedZone.name.toUpperCase()} (${Math.round(selectedZone.intensity * 100)}%)`);
}

function deleteSelectedZone() {
    if (!selectedZoneId) return;
    const idx = zones.findIndex(z => z.id === selectedZoneId);
    if (idx === -1) return;

    const [deleted] = zones.splice(idx, 1);
    if (deleted && deleted.layer) {
        floodZoneLayer.removeLayer(deleted.layer);
    }

    if (zones.length > 0) {
        const nextZone = zones[Math.max(0, idx - 1)];
        selectZone(nextZone.id);
    } else {
        selectedZoneId = null;
        document.getElementById('btn-delete-zone').disabled = true;
        document.getElementById('zone-rainfall-intensity').disabled = true;
        document.getElementById('zone-intensity-val').textContent = '—';
        document.getElementById('zone-intensity-category').textContent = 'No Selection';
        document.getElementById('zone-intensity-category').className = 'intensity-badge badge-zero';
    }

    updateZoneSelectorUI();
    setStatus('info', `DELETED ${deleted.name.toUpperCase()}`);

    // Automatically recompute: unaffected roads cleanly restore to baseline
    debounceAutoSimulate(100);
}

// ── Rainfall Intensity Helpers & Sliders ──────────────────

function getIntensityCategory(percentVal) {
    if (percentVal <= 0) {
        return { label: 'No Added Impact (0%)', badgeClass: 'badge-zero' };
    } else if (percentVal <= 30) {
        return { label: 'Low Rainfall (1–30%)', badgeClass: 'badge-low' };
    } else if (percentVal <= 60) {
        return { label: 'Moderate Rainfall (31–60%)', badgeClass: 'badge-moderate' };
    } else if (percentVal <= 80) {
        return { label: 'Heavy Rainfall (61–80%)', badgeClass: 'badge-heavy' };
    } else {
        return { label: 'Extreme Rainfall (81–100%)', badgeClass: 'badge-extreme' };
    }
}

function onCircleIntensityChange(val) {
    const intVal = parseInt(val, 10);
    const cat = getIntensityCategory(intVal);
    const badge = document.getElementById('circle-intensity-category');
    if (badge) {
        badge.textContent = cat.label;
        badge.className = `intensity-badge ${cat.badgeClass}`;
    }
    const valEl = document.getElementById('circle-intensity-val');
    if (valEl) valEl.textContent = `${intVal}%`;

    const compat = document.getElementById('flood-intensity');
    if (compat) compat.value = (intVal / 100.0).toFixed(2);

    if (floodCenter && floodCircles.length > 0) {
        const intensity = intVal / 100.0;
        floodCircles.forEach(fc => {
            fc.circle.setStyle({
                color: `rgba(59,130,246,${0.3 + intensity * 0.4})`,
                fillColor: `rgba(59,130,246,${0.1 + intensity * 0.25})`
            });
        });
    }

    if (floodCenter) {
        debounceAutoSimulate(150);
    }
}

function onZoneRainfallChange(val) {
    const intVal = parseInt(val, 10);
    const cat = getIntensityCategory(intVal);
    const badge = document.getElementById('zone-intensity-category');
    if (badge) {
        badge.textContent = cat.label;
        badge.className = `intensity-badge ${cat.badgeClass}`;
    }
    const valEl = document.getElementById('zone-intensity-val');
    if (valEl) valEl.textContent = `${intVal}%`;

    if (!selectedZoneId) return;
    const zone = zones.find(z => z.id === selectedZoneId);
    if (!zone) return;

    zone.intensity = intVal / 100.0;

    // Visual feedback on zone polygon: color & opacity scale with rainfall intensity
    const alpha = 0.15 + (intVal / 100.0) * 0.40;
    zone.layer.setStyle({
        fillOpacity: alpha,
        color: zone.id === selectedZoneId ? '#38bdf8' : '#3b82f6'
    });

    // Update zone tooltip
    zone.layer.bindTooltip(
        `<strong>${zone.name}</strong><br>Simulated Rainfall: <strong>${intVal}%</strong> (${cat.label})`
    );

    // Update select dropdown option text
    const opt = document.querySelector(`#zone-selector option[value="${zone.id}"]`);
    if (opt) {
        opt.textContent = `${zone.name} (${intVal}% - ${cat.label.split(' ')[0]})`;
    }

    // Debounced recalculation of road risks and routing
    debounceAutoSimulate(150);
}

// ── Defaults & Clear ──────────────────────────────────────

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

// ── Scenario Presets ──────────────────────────────────────

function applyScenarioPreset(scenarioId) {
    if (!scenarioId) return;

    const presets = {
        'SCN_FLOOD_PUZHAKKAL_LOWLAND': {
            center: [76.1850, 10.5350], radius: 2200, intensity: 0.75, water_level: 2.2
        },
        'SCN_FLOOD_KOLE_BREACH': {
            center: [76.1750, 10.4950], radius: 2800, intensity: 0.85, water_level: 3.0
        },
        'SCN_FLOOD_SWARAJ_ROUND_FLASH': {
            center: [76.2144, 10.5276], radius: 1200, intensity: 0.60, water_level: 1.4
        },
        'SCN_FLOOD_KURIACHIRA_INUNDATION': {
            center: [76.2250, 10.5050], radius: 1600, intensity: 0.70, water_level: 1.8
        }
    };

    const scn = presets[scenarioId];
    if (!scn) return;

    setFloodMode('circle');
    const circleSlider = document.getElementById('circle-intensity');
    if (circleSlider) {
        const pct = Math.round(scn.intensity * 100);
        circleSlider.value = pct;
        onCircleIntensityChange(pct);
    }
    document.getElementById('water-level').value = scn.water_level;
    document.getElementById('flood-radius').value = scn.radius;
    updateSliderLabels();

    setFloodCenter(scn.center[0], scn.center[1]);
    simulateFlood();
}

function buildFloodPayload() {
    const waterLevel = parseFloat(document.getElementById('water-level')?.value || 1.0);
    const circleIntensity = (parseFloat(document.getElementById('circle-intensity')?.value || 50)) / 100.0;
    const radius = parseFloat(document.getElementById('flood-radius')?.value || 2000);

    if (floodMode === 'circle') {
        if (!floodCenter) return null;
        return {
            active: true,
            center: floodCenter,
            radius: radius,
            intensity: circleIntensity,
            water_level: waterLevel,
            flood_zones: []
        };
    } else {
        // 'zones' mode: custom drawn flood zones
        if (zones.length === 0) return null;
        return {
            active: true,
            center: null,
            radius: radius,
            intensity: circleIntensity,
            water_level: waterLevel,
            flood_zones: zones.map(z => ({
                id: z.id,
                name: z.name,
                polygon: z.polygon,
                intensity: z.intensity,
                water_level: z.water_level || waterLevel
            }))
        };
    }
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
        flood: buildFloodPayload()
    };

    try {
        const res = await fetch(`${API}/api/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.error) {
            setStatus('danger', data.error.toUpperCase());
            btn.textContent = 'FIND SAFER ROUTE';
            btn.disabled = false;
            return;
        }

        renderRoutes(data);
        renderImpact(data);

        // Auto focus switch: if route found, focus on route; if flood active with roads, focus flood roads
        if (data.routesense) {
            setMapFocus('ROUTE_FOCUS');
            setStatus(data.flood_active ? 'warning' : 'ok', data.flood_active ? 'SAFE ROUTE (FLOOD EVASION)' : 'OPTIMAL SAFE ROUTE');
        } else {
            setMapFocus('FLOOD_ROAD_FOCUS');
            setStatus('danger', 'NO SAFE ROUTE AVAILABLE');
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

    const isFloodActive = Boolean(data.flood_active);

    // 1. Normal route (Minimizes physical road distance)
    if (data.normal && data.normal.coordinates) {
        const latlngs = data.normal.coordinates.map(c => [c[1], c[0]]);

        if (!isFloodActive) {
            // When NO flood is active, this is the primary SHORTEST DIRECT ROUTE!
            // Render prominent vibrant blue solid line with casing
            L.polyline(latlngs, {
                color: '#0369a1',
                weight: 7,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(normalRouteLayer);

            const directLine = L.polyline(latlngs, {
                color: '#38bdf8',
                weight: 4.5,
                opacity: 0.95,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(normalRouteLayer);

            directLine.bindPopup(
                `<strong>Direct Shortest Road Route</strong><br>` +
                `Total Distance: <strong>${(data.normal.distance / 1000).toFixed(2)} km</strong><br>` +
                `Status: <span style="color:#38bdf8;font-weight:700">Clear Road (No Flood Hazard)</span>`
            );
        } else {
            // During flood: thin blue dashed line showing the baseline path that may cross hazards
            L.polyline(latlngs, {
                color: '#60a5fa',
                weight: 3.5,
                opacity: 0.8,
                dashArray: '8 6'
            }).addTo(normalRouteLayer);
        }
    }

    // 2. Render Affected Roads (Requirement 2)
    if (data.affected_roads && data.affected_roads.length > 0) {
        renderAffectedRoads(data.affected_roads);
    }

    // 3. Recommended RouteSense route
    if (data.routesense && data.routesense.coordinates) {
        const coords = data.routesense.coordinates;
        const latlngs = coords.map(c => [c[1], c[0]]);

        if (isFloodActive) {
            // FLOOD ACTIVE: RouteSense is the active flood-evasion corridor!
            // Layer 1 (Bottom): Green outline / outer casing polyline
            L.polyline(latlngs, {
                color: '#16a34a',
                weight: 8,
                opacity: 0.70,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(rsRouteLayer);

            // Layer 2 (Middle): Multi-segment risk colored lines from GeoJSON
            if (data.routesense.geojson && data.routesense.geojson.features) {
                data.routesense.geojson.features.forEach(feat => {
                    const segCoords = feat.geometry.coordinates.map(c => [c[1], c[0]]);
                    const riskVal = feat.properties.predicted_risk;
                    const segColor = RISK_COLORS[riskVal] || '#34d399';

                    const segLine = L.polyline(segCoords, {
                        color: segColor,
                        weight: 4,
                        opacity: 0.95
                    }).addTo(rsRouteLayer);

                    segLine.bindPopup(
                        `<strong>Safe Evacuation Segment</strong><br>` +
                        `Effective Risk: <strong>${feat.properties.risk_label || 'Safe'}</strong><br>` +
                        `Highway: ${feat.properties.highway || 'road'}<br>` +
                        `Length: ${feat.properties.distance} m`
                    );
                });
            } else {
                L.polyline(latlngs, {
                    color: '#34d399',
                    weight: 4,
                    opacity: 0.95
                }).addTo(rsRouteLayer);
            }

            // Layer 3 (Top): Animated particles flowing along flood evasion corridor
            animateRouteParticles(coords);
        } else {
            // NO FLOOD: Check if shortest route and safe route are identical
            const sameRoute = !data.comparison?.routes_differ;
            if (sameRoute) {
                // Shortest route is already safe, animate particles on it!
                animateRouteParticles(data.normal?.coordinates || coords);
            } else {
                // Route differs due to profile constraints (e.g. elderly slope avoidance)
                L.polyline(latlngs, {
                    color: '#10b981',
                    weight: 4,
                    opacity: 0.85,
                    dashArray: '6 6'
                }).addTo(rsRouteLayer).bindPopup(
                    `<strong>Risk-Averse Profile Route</strong><br>` +
                    `Total Distance: ${(data.routesense.distance / 1000).toFixed(2)} km`
                );
                animateRouteParticles(data.normal?.coordinates || coords);
            }
        }
    }
}

// ── Render Affected Roads (Requirement 2) ──────────────────

function renderAffectedRoads(affectedRoads) {
    affectedRoadsLayer.clearLayers();
    affectedRoadPolylines = [];

    if (!affectedRoads || affectedRoads.length === 0) {
        document.getElementById('legend-affected').style.display = 'none';
        return;
    }

    document.getElementById('legend-affected').style.display = 'flex';

    affectedRoads.forEach(road => {
        const coords = [
            [road.coordinates[0][1], road.coordinates[0][0]],
            [road.coordinates[1][1], road.coordinates[1][0]]
        ];

        let color = '#fbbf24';  // yellow (minor)
        let weight = 2.5;
        let baseOpacity = 0.7;

        if (road.impassable || road.effective_risk === 2) {
            color = '#ef4444';  // red (high danger / impassable)
            weight = 4.0;
            baseOpacity = 0.9;
        } else if (road.effective_risk === 1 || road.flood_penalty > 0.3) {
            color = '#f97316';  // orange (intermediate)
            weight = 3.2;
            baseOpacity = 0.8;
        }

        const polyline = L.polyline(coords, {
            color: color,
            weight: weight,
            opacity: baseOpacity
        }).addTo(affectedRoadsLayer);

        const statusLabel = road.impassable ? 'IMPASSABLE / CLOSED' : (road.effective_risk === 2 ? 'HIGH RISK' : 'ELEVATED RISK');
        const etaText = road.inundation_eta ? `<br>⏱️ Flood Arrival ETA: <strong>${road.inundation_eta}</strong> (${road.inundation_urgency || 'HIGH'})` : '';
        polyline.bindPopup(
            `<strong>Flood Affected Road</strong><br>` +
            `Status: <span style="color:${color};font-weight:600">${statusLabel}</span><br>` +
            `Original Risk: ${road.original_risk} &rarr; Effective Risk: ${road.effective_risk}<br>` +
            `Elevation: ${road.elevation ? road.elevation + ' m' : 'N/A'}${etaText}<br>` +
            `Flood Penalty: ${road.flood_penalty || 'N/A'}`
        );

        affectedRoadPolylines.push({ polyline, baseOpacity });
    });
}

function animateRouteParticles(coords) {
    const totalPoints = coords.length;
    if (totalPoints < 2) return;

    const NUM_PARTICLES = 10;
    const particles = [];

    for (let i = 0; i < NUM_PARTICLES; i++) {
        const marker = L.circleMarker([0, 0], {
            radius: 3.5,
            color: '#ecfdf5',
            fillColor: '#10b981',
            fillOpacity: 0.95,
            weight: 1
        }).addTo(rsRouteLayer);
        particles.push({
            marker,
            progress: i / NUM_PARTICLES
        });
    }

    routeParticles = particles;

    routeAnimInterval = setInterval(() => {
        particles.forEach(p => {
            p.progress += 0.0035;
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

    if (r && c) {
        document.getElementById('metric-dist').textContent =
            `${(n.distance / 1000).toFixed(2)} → ${(r.distance / 1000).toFixed(2)} km`;
        document.getElementById('metric-high').textContent =
            `${n.risk_counts['2'] || 0} → ${r.risk_counts['2'] || 0}`;
        document.getElementById('metric-reduction').textContent =
            `${c.risk_reduction_pct}%`;
        document.getElementById('metric-dist-change').textContent =
            `${c.distance_pct > 0 ? '+' : ''}${c.distance_pct}%`;

        const msg = document.getElementById('route-status-msg');
        if (!data.flood_active) {
            if (c.routes_differ) {
                msg.textContent = `Clear conditions: Direct shortest path is ${(n.distance / 1000).toFixed(2)} km. Profile detour is ${(r.distance / 1000).toFixed(2)} km.`;
                msg.style.color = '#38bdf8';
            } else {
                msg.textContent = `Direct shortest path is optimal and clear (${(n.distance / 1000).toFixed(2)} km).`;
                msg.style.color = '#38bdf8';
            }
        } else {
            if (c.routes_differ) {
                msg.textContent = `Flood evasion active: avoiding ${c.high_risk_avoided} inundated / high-risk segments.`;
                msg.style.color = '#34d399';
            } else {
                msg.textContent = 'Both routes follow identical roads — shortest path is clear of flood waters.';
                msg.style.color = 'rgba(255,255,255,0.6)';
            }
        }
    } else {
        // No safe route available case
        document.getElementById('metric-dist').textContent = `${(n.distance / 1000).toFixed(2)} km (Shortest)`;
        document.getElementById('metric-high').textContent = `${n.risk_counts['2'] || 0} High-Risk`;
        document.getElementById('metric-reduction').textContent = 'BLOCKED';
        document.getElementById('metric-dist-change').textContent = 'N/A';

        const msg = document.getElementById('route-status-msg');
        msg.textContent = data.routesense_error || "No route satisfying the configured safety constraints is available.";
        msg.style.color = '#ef4444';
    }
}

// ── Flood Simulation Trigger ──────────────────────────────

async function simulateFlood() {
    const intensity = (parseFloat(document.getElementById('circle-intensity')?.value || 50)) / 100.0;
    const waterLevel = parseFloat(document.getElementById('water-level')?.value || 1.0);
    const radius = parseFloat(document.getElementById('flood-radius')?.value || 2000);

    let floodPayload = buildFloodPayload();
    if (!floodPayload) {
        if (floodMode === 'circle') {
            // Default center at central Thrissur [76.2144, 10.5276] (Swaraj Round)
            setFloodCenter(76.2144, 10.5276);
            floodPayload = buildFloodPayload();
        } else {
            setStatus('warning', 'DRAW AT LEAST ONE FLOOD ZONE FIRST');
            if (!isDrawingZone) startDrawingZone();
            return;
        }
    }
    if (!floodPayload) return;

    if (floodMode === 'circle' && floodCenter) {
        setStatus('info', 'SIMULATING CIRCULAR FLOOD');
        floodCircles.forEach((fc, i) => {
            fc.baseRadius = radius * (1 - i * 0.25);
            fc.circle.setStyle({
                color: `rgba(59,130,246,${0.3 + intensity * 0.4})`,
                fillColor: `rgba(59,130,246,${0.1 + intensity * 0.2})`
            });
        });
    } else {
        setStatus('info', 'SIMULATING CUSTOM FLOOD ZONES');
    }

    // Call backend flood simulation to retrieve affected roads independently
    const simPayload = {
        intensity: floodPayload.intensity,
        water_level: floodPayload.water_level,
        radius: floodPayload.radius,
        center: floodPayload.center,
        flood_zones: floodPayload.flood_zones
    };

    let simData = null;
    try {
        const res = await fetch(`${API}/api/simulate-flood`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(simPayload)
        });
        simData = await res.json();
        if (simData.affected_roads) {
            renderAffectedRoads(simData.affected_roads);
        }

        // Display Inundation ETA Card
        const etaCard = document.getElementById('flood-eta-card');
        if (etaCard && simData.avg_inundation_eta) {
            etaCard.style.display = 'flex';
            document.getElementById('flood-eta-value').textContent = simData.avg_inundation_eta;
            const urgencyEl = document.getElementById('flood-eta-urgency');
            const mins = simData.avg_inundation_minutes || 60;
            if (mins < 45) {
                urgencyEl.textContent = 'CRITICAL SURGE (<45m)';
                urgencyEl.className = 'eta-urgency critical';
            } else if (mins < 120) {
                urgencyEl.textContent = 'RAPID INUNDATION (<2h)';
                urgencyEl.className = 'eta-urgency high';
            } else {
                urgencyEl.textContent = 'SLOW PROPAGATION (>2h)';
                urgencyEl.className = 'eta-urgency moderate';
            }
        }
    } catch (e) {
        console.error('Simulate flood failed:', e);
    }

    // Dynamic Rerouting & Intelligent Multi-Shelter Evaluation
    if (originCoord && destCoord) {
        triggerHazardAlert("Flooding detected! Evaluating nearest safe shelters and alternative evacuation corridors...");

        const reroutePayload = {
            origin: originCoord,
            current_destination: destCoord,
            profile: selectedProfile,
            flood: floodPayload
        };

        try {
            const rRes = await fetch(`${API}/api/reroute-shelter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reroutePayload)
            });
            const rData = await rRes.json();

            if (rData.rerouted && rData.best_shelter) {
                // Shelter reroute triggered: alternative shelter is closer/safer than detouring to current destination
                const newSh = rData.best_shelter;
                setDestination(newSh.coordinates[0], newSh.coordinates[1]);
                document.getElementById('dest-display').textContent = `🛡️ ${newSh.name} (Rerouted Safe Haven)`;

                renderRoutes(rData.route);
                renderImpact(rData.route);
                setMapFocus('ROUTE_FOCUS');

                const alertMsg = rData.distance_saved
                    ? `⚠️ REROUTED TO CLOSER SHELTER: Original path had ${rData.original_distance}m flood detour. Switched to ${newSh.name} (Saved ${rData.distance_saved}m)!`
                    : `⚠️ REROUTED: Original path impassable! Switched to accessible safe haven: ${newSh.name}!`;

                showHazardResolved(alertMsg);
            } else if (rData.route) {
                renderRoutes(rData.route);
                renderImpact(rData.route);
                setMapFocus('ROUTE_FOCUS');
                if (rData.route.routesense) {
                    showHazardResolved("Evasion corridor activated! Route safely detoured around inundated roads.");
                } else {
                    triggerHazardAlert("CRITICAL: All evacuation routes to destination are blocked by rising water!");
                }
            }
        } catch (err) {
            console.error("Dynamic shelter reroute error:", err);
            await findRoute();
        }
    } else {
        setMapFocus('FLOOD_ROAD_FOCUS');
        const count = (simData && simData.affected_count !== undefined) ? simData.affected_count : (simData && simData.affected_roads ? simData.affected_roads.length : 0);
        setStatus('warning', `FLOOD SIMULATION ACTIVE (${count} road segments affected)`);
    }
}

function resetFlood() {
    // 1. Reset circular flood
    floodCenter = null;
    clearFloodMarkers();
    togglePlaceCircleMode(false);

    // 2. Reset custom zones
    if (isDrawingZone) cancelDrawingZone();
    zones.forEach(z => {
        if (z.layer) floodZoneLayer.removeLayer(z.layer);
    });
    zones = [];
    selectedZoneId = null;
    if (tempDrawingLayer) {
        floodZoneLayer.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }
    updateZoneSelectorUI();

    // 3. Clear layers & overlays
    floodZoneLayer.clearLayers();
    affectedRoadsLayer.clearLayers();
    affectedRoadPolylines = [];
    document.getElementById('legend-flood').style.display = 'none';
    document.getElementById('legend-affected').style.display = 'none';
    document.getElementById('scenario-select').value = '';

    const etaCard = document.getElementById('flood-eta-card');
    if (etaCard) etaCard.style.display = 'none';
    dismissHazardAlert();

    // 4. Reset sliders
    const circleIntensitySlider = document.getElementById('circle-intensity');
    if (circleIntensitySlider) circleIntensitySlider.value = 50;
    onCircleIntensityChange(50);

    const zoneSlider = document.getElementById('zone-rainfall-intensity');
    if (zoneSlider) {
        zoneSlider.value = 70;
        zoneSlider.disabled = true;
    }
    const zoneVal = document.getElementById('zone-intensity-val');
    if (zoneVal) zoneVal.textContent = '—';
    const zoneCat = document.getElementById('zone-intensity-category');
    if (zoneCat) {
        zoneCat.textContent = 'No Selection';
        zoneCat.className = 'intensity-badge badge-zero';
    }

    document.getElementById('water-level').value = 1.0;
    document.getElementById('water-val').textContent = '1.0 m';
    document.getElementById('flood-radius').value = 2000;
    document.getElementById('radius-val').textContent = '2000m';

    // 5. Recalculate route without flood if points exist
    if (originCoord && destCoord) {
        findRoute();
    } else {
        setMapFocus('BALANCED');
    }

    setStatus('ok', 'NORMAL CONDITIONS');
}

// ── Live GPS User Location (Client Mode) ──────────────────

let userLocationMarker = null;

function locateUser() {
    if (!navigator.geolocation) {
        alert("Geolocation is not supported by your browser or device.");
        return;
    }

    setStatus('info', 'ACQUIRING GPS SIGNAL…');
    const btn = document.getElementById('btn-gps-origin');
    if (btn) btn.textContent = '⏳ Locating…';

    navigator.geolocation.getCurrentPosition(
        (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;

            // In-bounds check for Thrissur study area
            let activeLat = lat;
            let activeLon = lon;
            const inStudyArea = (lon >= 76.15 && lon <= 76.28 && lat >= 10.45 && lat <= 10.60);

            if (!inStudyArea) {
                // If user is testing remotely outside Thrissur, map to central Thrissur for live simulation
                activeLat = 10.518;
                activeLon = 76.214;
            }

            if (userLocationMarker) {
                map.removeLayer(userLocationMarker);
            }

            const pulseIcon = L.divIcon({
                className: 'user-gps-pulse-wrapper',
                html: '<div class="user-gps-pulse"></div>',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });

            userLocationMarker = L.marker([activeLat, activeLon], { icon: pulseIcon }).addTo(map);
            userLocationMarker.bindPopup(
                `<b>📍 Live Client Position</b><br>Accuracy: ~${Math.round(pos.coords.accuracy)}m${!inStudyArea ? '<br><small>(Demo-positioned in Thrissur)</small>' : ''}`
            ).openPopup();

            setOrigin(activeLon, activeLat);
            map.flyTo([activeLat, activeLon], 14, { animate: true, duration: 1.0 });

            if (btn) btn.textContent = '📍 GPS Active';
            setStatus('ok', 'LIVE GPS LOCKED');

            if (destCoord) {
                findRoute();
            }
        },
        (err) => {
            console.warn("Geolocation warning:", err);
            setStatus('warning', 'GPS ACCESS DENIED / UNAVAILABLE');
            if (btn) btn.textContent = '📍 Live GPS';
            alert("Could not access live GPS. Please enable location permissions or click on the map to set origin.");
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 }
    );
}

// ── Find Safe Spot (Shelters) ─────────────────────────────

let shelterMarkers = [];

async function findNearestSafeSpot() {
    const btn = document.getElementById('btn-find-safe-spot');
    btn.disabled = true;
    btn.textContent = 'LOCATING NEAREST SHELTER…';
    setStatus('info', 'EVALUATING TRUE ROAD DISTANCE & HAZARD CLEARANCE');

    try {
        if (!originCoord) {
            useDefaults();
        }
        const startPt = originCoord || [76.1798, 10.4900];

        const payload = {
            origin: startPt,
            profile: selectedProfile,
            flood: buildFloodPayload()
        };

        const res = await fetch(`${API}/api/nearest-shelter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.error || !data.best_shelter) {
            alert(data.error || "No safe shelter is currently reachable by road.");
            btn.disabled = false;
            btn.textContent = '🛡️ FIND SAFE SPOT (SHELTER)';
            return;
        }

        const bestShelter = data.best_shelter;
        const allShelters = data.all_shelters || [];

        // Render all shelters on map with true road distances
        shelterMarkers.forEach(m => map.removeLayer(m));
        shelterMarkers = [];

        allShelters.forEach(sh => {
            const isTarget = sh.id === bestShelter.id;
            const m = L.circleMarker([sh.coordinates[1], sh.coordinates[0]], {
                radius: isTarget ? 13 : 8,
                color: '#ffffff',
                weight: isTarget ? 3.5 : 1.5,
                fillColor: isTarget ? '#10b981' : '#475569',
                fillOpacity: 0.95
            }).addTo(map);

            m.bindPopup(
                `<strong>🛡️ ${sh.name}</strong><br>` +
                `Road Distance: <strong style="color:#10b981;font-size:13px">${sh.road_distance_km} km</strong> (${sh.road_distance_m} m)<br>` +
                `Status: <span style="color:#10b981;font-weight:700">${sh.status}</span><br>` +
                `Elevation: <strong>${sh.elevation} m</strong> (High Ground)<br>` +
                `Capacity: <strong>${sh.capacity} persons</strong><br>` +
                `Emergency Contact: ${sh.contact}<br>` +
                `Supplies: ${sh.supplies.join(', ')}`
            );

            if (isTarget) {
                m.openPopup();
            }
            shelterMarkers.push(m);
        });

        // Set destination to this shelter
        setDestination(bestShelter.coordinates[0], bestShelter.coordinates[1]);
        document.getElementById('dest-display').textContent = `🛡️ ${bestShelter.name} (${bestShelter.road_distance_km} km)`;

        // Immediately render the shortest direct evacuation path to this shelter
        if (data.route) {
            renderRoutes(data.route);
            renderImpact(data.route);
            setMapFocus('ROUTE_FOCUS');
        }

        setStatus('ok', `SHORTEST PATH TO ${bestShelter.name.toUpperCase()} (${bestShelter.road_distance_km} KM)`);

    } catch (e) {
        console.error("Failed to find safe spot:", e);
        setStatus('danger', 'FAILED TO LOCATE SAFE SHELTER');
    }
    btn.disabled = false;
    btn.textContent = '🛡️ FIND SAFE SPOT (SHELTER)';
}

function haversineMeters(p1, p2) {
    const lon1 = p1[0], lat1 = p1[1];
    const lon2 = p2[0], lat2 = p2[1];
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad;
    const dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * rad) * Math.cos(lat2 * rad) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return 6371000 * c;
}

// ── Mobile Connect Modal ──────────────────────────────────

async function openMobileConnectModal() {
    const modal = document.getElementById('mobile-modal');
    modal.style.display = 'flex';
    try {
        const res = await fetch(`${API}/api/network-info`);
        const data = await res.json();
        const urlLink = document.getElementById('mobile-url-link');
        urlLink.href = data.mobile_url;
        urlLink.textContent = data.mobile_url;

        const qrImg = document.getElementById('mobile-qr-img');
        qrImg.src = data.qr_url;
    } catch (e) {
        console.warn("Could not fetch network info:", e);
        const hostUrl = window.location.origin;
        document.getElementById('mobile-url-link').textContent = hostUrl;
        document.getElementById('mobile-url-link').href = hostUrl;
        document.getElementById('mobile-qr-img').src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(hostUrl)}`;
    }
}

function closeMobileConnectModal() {
    document.getElementById('mobile-modal').style.display = 'none';
}

// ── Dynamic Hazard Alerts ─────────────────────────────────

function triggerHazardAlert(message) {
    const banner = document.getElementById('dynamic-hazard-alert');
    const text = document.getElementById('hazard-alert-text');
    if (banner && text) {
        banner.style.background = 'rgba(220, 38, 38, 0.95)';
        banner.style.borderColor = '#ef4444';
        text.textContent = message;
        banner.style.display = 'flex';
    }
}

function showHazardResolved(message) {
    const banner = document.getElementById('dynamic-hazard-alert');
    const text = document.getElementById('hazard-alert-text');
    if (banner && text) {
        banner.style.background = 'rgba(16, 185, 129, 0.95)';
        banner.style.borderColor = '#10b981';
        text.textContent = message;
        banner.style.display = 'flex';
        setTimeout(() => {
            dismissHazardAlert();
            banner.style.background = 'rgba(220, 38, 38, 0.95)';
            banner.style.borderColor = '#ef4444';
        }, 5000);
    }
}

function dismissHazardAlert() {
    const banner = document.getElementById('dynamic-hazard-alert');
    if (banner) banner.style.display = 'none';
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
    if (overlay) {
        overlay.classList.add('hidden');
        setTimeout(() => overlay.remove(), 700);
    }
}

// ── Slider Real-Time Reactive Routing ─────────────────────

function updateSliderLabels() {
    const waterLevel = parseFloat(document.getElementById('water-level')?.value || 1.0);
    const radius = parseFloat(document.getElementById('flood-radius')?.value || 2000);

    const waterValEl = document.getElementById('water-val');
    if (waterValEl) waterValEl.textContent = waterLevel.toFixed(1) + ' m';

    const radiusValEl = document.getElementById('radius-val');
    if (radiusValEl) radiusValEl.textContent = radius + 'm';

    // Update active circle visual radius and color live
    if (floodCenter && floodCircles.length > 0) {
        const circleInt = (parseFloat(document.getElementById('circle-intensity')?.value || 50)) / 100.0;
        floodCircles.forEach((fc, i) => {
            fc.baseRadius = radius * (1 - i * 0.25);
            fc.circle.setRadius(fc.baseRadius);
            fc.circle.setStyle({
                color: `rgba(59,130,246,${0.3 + circleInt * 0.4})`,
                fillColor: `rgba(59,130,246,${0.1 + circleInt * 0.25})`
            });
        });
    }

    // Trigger auto-simulation on slider adjustment
    if (floodCenter || zones.length > 0) {
        debounceAutoSimulate(180);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const circleSlider = document.getElementById('circle-intensity');
    if (circleSlider) {
        circleSlider.addEventListener('input', (e) => onCircleIntensityChange(e.target.value));
        onCircleIntensityChange(circleSlider.value);
    }

    const zoneSlider = document.getElementById('zone-rainfall-intensity');
    if (zoneSlider) {
        zoneSlider.addEventListener('input', (e) => onZoneRainfallChange(e.target.value));
    }

    ['water-level', 'flood-radius'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', updateSliderLabels);
    });
});
