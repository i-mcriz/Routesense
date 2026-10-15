/* ──────────────────────────────────────────────────────────
   RouteSense AI — Frontend Application Engine
   Professional GIS Flood Simulation & Safe Evacuation Routing
   ────────────────────────────────────────────────────────── */

const API = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? ''
    : 'http://localhost:5000';  // Fallback if accessed via file:///
const STUDY_CENTER = [10.5300, 76.2150]; // Thrissur Center
const STUDY_ZOOM = 13;

// ── Application State ─────────────────────────────────────
let map = null;
let streetsTileLayer = null;
let satelliteTileLayer = null;
let currentBasemap = 'streets';

// Map Layer Groups
let riskLayer = null;
let riversLayer = null;
let affectedRoadsLayer = null;
let floodZoneLayer = null;
let normalRouteLayer = null;
let rsRouteLayer = null;
let shelterMarkersLayer = null;

// Routing State
let originCoord = null;
let destCoord = null;
let originMarker = null;
let destMarker = null;
let clickMode = null; // 'origin' | 'dest' | null
let selectedProfile = 'general';
let selectedObjective = 'safest';
let latestRouteData = null;
let routeRequestId = 0; // Request versioning to discard stale async responses

// Simulation State
let floodMode = 'circle'; // 'circle' | 'zones'
let floodCenter = null;
let isPlacingCircle = false;
let isDrawingZone = false;
let currentZonePoints = [];
let tempDrawingLayer = null;
let zones = []; // Array of custom drawn flood polygons
let selectedZoneId = null;

let isSimPlaying = false;
let simPlaybackInterval = null;
let simSpeed = 1;
let simTimeElapsed = 0; // in minutes (0 to 180)
let simAutoDebounceTimer = null;
let simRequestId = 0;

let floodCircles = [];
let floodAnimInterval = null;
let routeAnimInterval = null;
let routeParticles = [];
let affectedRoadPolylines = [];
let shelterMarkers = [];

// Semantic Risk Colors
const RISK_COLORS = { 0: '#10b981', 1: '#fbbf24', 2: '#ef4444' };
const RISK_ALPHA = { 0: 0.35, 1: 0.55, 2: 0.75 };

// ── Lifecycle Initialization ──────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
    initMap();
    setupUIEventListeners();
    await Promise.all([
        loadRiskMap(),
        loadRivers()
    ]);
    setStatus('ok', 'READY: Thrissur Road Network Active');
    hideLoading();
    updateStatusDashboard(null, null);
});

// ── Leaflet Map Setup ─────────────────────────────────────
function initMap() {
    map = L.map('map', {
        preferCanvas: true,
        center: STUDY_CENTER,
        zoom: STUDY_ZOOM,
        minZoom: 12,
        maxBounds: [[10.40, 76.10], [10.66, 76.33]],
        maxBoundsViscosity: 1.0,
        zoomControl: false,
        attributionControl: true
    });

    // 1. Street View (Dark Theme - Free, No API Key Required)
    // Esri World Dark Gray Canvas with optional CartoDB Dark Matter if ?carto_key= supplied
    const hasCartoKey = typeof window !== 'undefined' && window.location && new URLSearchParams(window.location.search).has('carto_key');
    if (hasCartoKey) {
        streetsTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20,
            className: 'dark-street-tiles'
        });
    } else {
        const esriDarkBase = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 16,
            attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
            className: 'dark-street-tiles'
        });
        const esriDarkLabels = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 16,
            attribution: '',
            className: 'dark-street-tiles'
        });
        streetsTileLayer = L.layerGroup([esriDarkBase, esriDarkLabels]);
    }
    streetsTileLayer.addTo(map);

    // 2. Satellite View: Esri World Imagery (Natural full-color, completely unfiltered)
    satelliteTileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and GIS User Community'
    });

    // Setup Map Click Handler
    map.on('click', onMapClick);

    // Add Layer Groups in specific z-order
    riversLayer = L.layerGroup().addTo(map);
    riskLayer = L.layerGroup().addTo(map);
    affectedRoadsLayer = L.layerGroup().addTo(map);
    floodZoneLayer = L.layerGroup().addTo(map);
    normalRouteLayer = L.layerGroup().addTo(map);
    rsRouteLayer = L.layerGroup().addTo(map);
    shelterMarkersLayer = L.layerGroup().addTo(map);
}

// ── Basemap Switching (Requirement 2) ─────────────────────
function switchBasemap(style) {
    if (style === currentBasemap) return;

    if (style === 'streets') {
        if (map.hasLayer(satelliteTileLayer)) map.removeLayer(satelliteTileLayer);
        if (!map.hasLayer(streetsTileLayer)) map.addLayer(streetsTileLayer);
        document.getElementById('basemap-streets').classList.add('active');
        document.getElementById('basemap-satellite').classList.remove('active');
        currentBasemap = 'streets';
    } else {
        // Satellite View: Natural full color without any dark filters or transformations
        if (map.hasLayer(streetsTileLayer)) map.removeLayer(streetsTileLayer);
        if (!map.hasLayer(satelliteTileLayer)) map.addLayer(satelliteTileLayer);
        document.getElementById('basemap-satellite').classList.add('active');
        document.getElementById('basemap-streets').classList.remove('active');
        currentBasemap = 'satellite';
    }
}

// ── Adaptive Prominence Focus States ───────────────────────
let currentFocus = 'BALANCED';

function setMapFocus(focusState) {
    currentFocus = focusState;

    const opacities = {
        'BALANCED':          { particles: 1.0, affected: 0.85, flood: 0.35, rivers: 0.85, rsRoute: 1.0, normalRoute: 0.8 },
        'ROUTE_FOCUS':       { particles: 0.15, affected: 0.40, flood: 0.20, rivers: 0.30, rsRoute: 1.0, normalRoute: 0.9 },
        'FLOOD_ROAD_FOCUS':  { particles: 0.15, affected: 1.00, flood: 0.35, rivers: 0.35, rsRoute: 0.85, normalRoute: 0.75 },
        'FLOOD_ZONE_FOCUS':  { particles: 0.20, affected: 0.60, flood: 0.85, rivers: 0.40, rsRoute: 0.75, normalRoute: 0.70 },
        'ENVIRONMENT_FOCUS': { particles: 0.20, affected: 0.45, flood: 0.30, rivers: 1.00, rsRoute: 0.60, normalRoute: 0.60 }
    };

    const cfg = opacities[focusState] || opacities['BALANCED'];

    affectedRoadPolylines.forEach(polyline => {
        if (polyline && polyline.setStyle) {
            polyline.setStyle({ opacity: 0.85 * cfg.affected });
        }
    });

    floodCircles.forEach(fc => {
        if (fc.circle && fc.circle.setStyle) {
            fc.circle.setStyle({ fillOpacity: 0.15 * cfg.flood, opacity: 0.7 * cfg.flood });
        }
    });
    zones.forEach(z => {
        if (z.layer && z.layer.setStyle) {
            z.layer.setStyle({ fillOpacity: (0.15 + (z.intensity || 0.7) * 0.35) * cfg.flood, opacity: 0.8 * cfg.flood });
        }
    });

    if (riversLayer) {
        riversLayer.eachLayer(l => {
            if (l.setStyle) l.setStyle({ opacity: 0.85 * cfg.rivers });
        });
    }

    if (rsRouteLayer) {
        rsRouteLayer.eachLayer(l => {
            if (l.setStyle) {
                const isOutline = l.options.weight > 6;
                l.setStyle({ opacity: (isOutline ? 0.75 : 0.95) * cfg.rsRoute });
            }
        });
    }
    if (normalRouteLayer) {
        normalRouteLayer.eachLayer(l => {
            if (l.setStyle) l.setStyle({ opacity: 0.8 * cfg.normalRoute });
        });
    }
}

// ── Tab Switching Navigation ──────────────────────────────
function switchTab(tabName) {
    const tabs = ['simulation', 'status', 'route'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t === 'simulation' ? 'sim' : t}`);
        const panel = document.getElementById(`tab-${t}`);
        if (btn) {
            btn.classList.toggle('active', t === tabName);
            btn.setAttribute('aria-selected', t === tabName ? 'true' : 'false');
        }
        if (panel) {
            panel.classList.toggle('active', t === tabName);
        }
    });

    // Switching tabs does NOT reload or reset map state!
    if (map) {
        map.invalidateSize();
    }
}

// ── Environmental & Base Risk Layers ──────────────────────
async function loadRivers() {
    try {
        const res = await fetch(`${API}/api/rivers`);
        if (!res.ok) return;
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
            opacity: 0.8,
            dashArray: isCanal ? '4 4' : null
        }).addTo(riversLayer);

        poly.bindPopup(`<strong>${f.properties.name || 'Waterway'}</strong><br>Type: ${f.properties.type || 'Basin Channel'}`);
    });
}

async function loadRiskMap() {
    setStatus('info', 'ROAD NETWORK ACTIVE');
    // Markers appear dynamically ONLY when flood hazard is simulated in that area
    if (riskLayer) riskLayer.clearLayers();
}

function renderParticleRiskMap(geojson) {
    // Deprecated static full-map particle clutter; dots are rendered dynamically during flood simulation
    if (riskLayer) riskLayer.clearLayers();
}

// ── Map Interactions (Origin, Destination, Geometry) ──────
function onMapClick(e) {
    const { lat, lng } = e.latlng;

    // 1. Explicit Origin Selection
    if (clickMode === 'origin') {
        setOrigin(lng, lat);
        clickMode = 'dest';
        const hint = document.getElementById('map-hint');
        if (hint) {
            hint.classList.remove('hidden');
            hint.innerHTML = 'Click map to set <strong>destination</strong>';
        }
        return;
    }

    // 2. Explicit Destination Selection
    if (clickMode === 'dest') {
        setDestination(lng, lat);
        clickMode = null;
        const hint = document.getElementById('map-hint');
        if (hint) hint.classList.add('hidden');
        findRoute();
        return;
    }

    // 3. Custom Flood Zones Mode (Vertex placement)
    if (floodMode === 'zones') {
        if (!isDrawingZone) startDrawingZone();
        addZoneVertex(lng, lat);
        return;
    }

    // 4. Circular Flood Epicenter Placement
    if (isPlacingCircle || (floodMode === 'circle' && e.originalEvent?.shiftKey)) {
        setFloodCenter(lng, lat);
        togglePlaceCircleMode(false);
        return;
    }
}

function setOrigin(lon, lat) {
    originCoord = [lon, lat];
    if (originMarker) map.removeLayer(originMarker);
    originMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'origin-marker', iconSize: [16, 16], iconAnchor: [8, 8] })
    }).addTo(map);

    const disp = document.getElementById('origin-display');
    if (disp) {
        disp.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        disp.classList.add('set');
    }
    const rpOrigin = document.getElementById('rp-origin-coords');
    if (rpOrigin) rpOrigin.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function setDestination(lon, lat, customLabel = null) {
    destCoord = [lon, lat];
    if (destMarker) map.removeLayer(destMarker);
    destMarker = L.marker([lat, lon], {
        icon: L.divIcon({ className: 'dest-marker', iconSize: [16, 16], iconAnchor: [8, 8] })
    }).addTo(map);

    const disp = document.getElementById('dest-display');
    if (disp) {
        disp.textContent = customLabel || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        disp.classList.add('set');
    }
    const rpDest = document.getElementById('rp-dest-coords');
    if (rpDest) rpDest.textContent = customLabel || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
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

function useDefaults() {
    setOrigin(76.1798, 10.4900);
    setDestination(76.2500, 10.5697);
    clickMode = null;
    const hint = document.getElementById('map-hint');
    if (hint) hint.classList.add('hidden');
    findRoute();
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

    const hint = document.getElementById('map-hint');
    if (hint) {
        hint.classList.remove('hidden');
        hint.innerHTML = 'Click map to set <strong>origin</strong>, then <strong>destination</strong>';
    }
    clearRoutes();
    updateStatusDashboard(null, latestSimData);
}

// ── WINDOW 1: Flood Simulation Controls ───────────────────
function setFloodMode(mode) {
    floodMode = mode;
    const circleBtn = document.getElementById('mode-circle-btn');
    const polyBtn = document.getElementById('mode-polygon-btn');
    const circleControls = document.getElementById('circle-controls');
    const polyControls = document.getElementById('polygon-controls');

    if (mode === 'circle') {
        circleBtn.classList.add('active');
        polyBtn.classList.remove('active');
        circleControls.style.display = 'block';
        polyControls.style.display = 'none';

        floodCircles.forEach(fc => {
            if (!floodZoneLayer.hasLayer(fc.circle)) floodZoneLayer.addLayer(fc.circle);
        });
        zones.forEach(z => {
            if (z.layer && floodZoneLayer.hasLayer(z.layer)) floodZoneLayer.removeLayer(z.layer);
        });
    } else {
        circleBtn.classList.remove('active');
        polyBtn.classList.add('active');
        circleControls.style.display = 'none';
        polyControls.style.display = 'block';

        floodCircles.forEach(fc => {
            if (floodZoneLayer.hasLayer(fc.circle)) floodZoneLayer.removeLayer(fc.circle);
        });
        zones.forEach(z => {
            if (z.layer && !floodZoneLayer.hasLayer(z.layer)) floodZoneLayer.addLayer(z.layer);
        });
    }
    updateStatusDashboard(latestRouteData, latestSimData);
}

function togglePlaceCircleMode(explicitState) {
    isPlacingCircle = explicitState !== undefined ? explicitState : !isPlacingCircle;
    const btn = document.getElementById('btn-place-circle');
    const hint = document.getElementById('flood-hint');

    if (isPlacingCircle) {
        if (btn) { btn.textContent = '✕ Cancel'; btn.classList.add('danger-text'); }
        if (hint) hint.innerHTML = '<strong>Click anywhere on map</strong> to set epicenter';
        map.getContainer().classList.add('drawing-cursor');
    } else {
        if (btn) { btn.textContent = '🎯 Place Center'; btn.classList.remove('danger-text'); }
        if (hint) hint.textContent = "Click 'Place Center' or Shift+Click map";
        map.getContainer().classList.remove('drawing-cursor');
    }
}

function setFloodCenter(lon, lat) {
    floodCenter = [lon, lat];
    clearFloodMarkers();

    const radius = parseFloat(document.getElementById('flood-radius').value);
    const intensity = (parseFloat(document.getElementById('circle-intensity')?.value || 50)) / 100.0;

    // Render 3 concentric layered rings
    for (let i = 0; i < 3; i++) {
        const c = L.circle([lat, lon], {
            radius: radius * (1 - i * 0.25),
            color: '#3b82f6',
            weight: 2,
            fillColor: '#60a5fa',
            fillOpacity: 0.12 + intensity * 0.15
        }).addTo(floodZoneLayer);
        floodCircles.push({ circle: c, baseRadius: radius * (1 - i * 0.25), offset: i });
    }

    // Dynamic wave animation
    if (!floodAnimInterval) {
        let t = 0;
        floodAnimInterval = setInterval(() => {
            t += 0.05;
            floodCircles.forEach(fc => {
                const scale = 1 + 0.06 * Math.sin(t + fc.offset);
                fc.circle.setRadius(fc.baseRadius * scale);
            });
        }, 60);
    }

    document.getElementById('legend-flood').style.display = 'flex';
    debounceSimulate();
}

function clearFloodMarkers() {
    if (floodAnimInterval) { clearInterval(floodAnimInterval); floodAnimInterval = null; }
    floodCircles.forEach(fc => floodZoneLayer.removeLayer(fc.circle));
    floodCircles = [];
}

// ── Custom Flood Zones Drawing ────────────────────────────
function startDrawingZone() {
    isDrawingZone = true;
    currentZonePoints = [];
    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }
    map.getContainer().classList.add('drawing-cursor');

    document.getElementById('btn-draw-zone').style.display = 'none';
    document.getElementById('zone-drawing-active-row').style.display = 'flex';
    document.getElementById('btn-finish-poly').disabled = true;
    document.getElementById('poly-status').textContent = 'Click map to place polygon boundary vertices (min 3 points)';
}

function addZoneVertex(lon, lat) {
    currentZonePoints.push([lon, lat]);
    const latlngs = currentZonePoints.map(p => [p[1], p[0]]);

    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }

    const group = L.featureGroup();
    latlngs.forEach(ll => {
        L.circleMarker(ll, {
            radius: 4,
            color: '#38bdf8',
            fillColor: '#ffffff',
            fillOpacity: 1,
            weight: 2
        }).addTo(group);
    });

    if (currentZonePoints.length >= 3) {
        L.polygon(latlngs, {
            color: '#38bdf8',
            weight: 2.5,
            dashArray: '5 5',
            fillColor: '#38bdf8',
            fillOpacity: 0.2
        }).addTo(group);
    } else if (currentZonePoints.length === 2) {
        L.polyline(latlngs, {
            color: '#38bdf8',
            weight: 2,
            dashArray: '5 5'
        }).addTo(group);
    }

    tempDrawingLayer = group.addTo(map);

    const count = currentZonePoints.length;
    const statusHint = document.getElementById('poly-status');
    if (statusHint) {
        statusHint.textContent = count < 3
            ? `${count} point(s) placed. Click ${3 - count} more point(s).`
            : `${count} points placed. Click 'Finish Zone' to complete.`;
    }
    document.getElementById('btn-finish-poly').disabled = count < 3;
}

function finishZone() {
    if (currentZonePoints.length < 3) return;

    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }

    const zoneId = 'zone_' + Date.now();
    const zoneName = `Zone ${zones.length + 1}`;
    const defaultIntensity = 0.70;

    const latlngs = currentZonePoints.map(p => [p[1], p[0]]);
    const polygonLayer = L.polygon(latlngs, {
        color: '#38bdf8',
        weight: 2.5,
        fillColor: '#3b82f6',
        fillOpacity: 0.25 + defaultIntensity * 0.3
    }).addTo(floodZoneLayer);

    polygonLayer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        selectZone(zoneId);
    });

    const newZone = {
        id: zoneId,
        name: zoneName,
        polygon: [...currentZonePoints],
        intensity: defaultIntensity,
        layer: polygonLayer
    };

    zones.push(newZone);

    isDrawingZone = false;
    currentZonePoints = [];
    map.getContainer().classList.remove('drawing-cursor');
    document.getElementById('btn-draw-zone').style.display = 'block';
    document.getElementById('zone-drawing-active-row').style.display = 'none';
    document.getElementById('legend-flood').style.display = 'flex';

    updateZoneSelectorUI();
    selectZone(zoneId);
    debounceSimulate();
}

function cancelDrawingZone() {
    isDrawingZone = false;
    currentZonePoints = [];
    if (tempDrawingLayer) {
        map.removeLayer(tempDrawingLayer);
        tempDrawingLayer = null;
    }
    map.getContainer().classList.remove('drawing-cursor');
    document.getElementById('btn-draw-zone').style.display = 'block';
    document.getElementById('zone-drawing-active-row').style.display = 'none';
    document.getElementById('poly-status').textContent = 'Drawing cancelled.';
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
        opt.textContent = `${z.name} (${pct}% Intensity)`;
        sel.appendChild(opt);
    });

    if (selectedZoneId) sel.value = selectedZoneId;
}

function onZoneSelect(zoneId) {
    if (zoneId) selectZone(zoneId);
}

function selectZone(zoneId) {
    selectedZoneId = zoneId;
    const selectedZone = zones.find(z => z.id === zoneId);
    if (!selectedZone) return;

    zones.forEach(z => {
        const isSel = z.id === zoneId;
        z.layer.setStyle({
            color: isSel ? '#38bdf8' : '#2563eb',
            weight: isSel ? 3.5 : 2.0
        });
        if (isSel) z.layer.bringToFront();
    });

    const sel = document.getElementById('zone-selector');
    if (sel) sel.value = zoneId;

    const slider = document.getElementById('zone-rainfall-intensity');
    if (slider) {
        slider.disabled = false;
        const pct = Math.round(selectedZone.intensity * 100);
        slider.value = pct;
        document.getElementById('zone-intensity-val').textContent = `${pct}%`;
        const cat = getIntensityCategory(pct);
        const badge = document.getElementById('zone-intensity-category');
        badge.textContent = cat.label;
        badge.className = `intensity-badge ${cat.badgeClass}`;
    }
}

function deleteSelectedZone() {
    if (!selectedZoneId) return;
    const idx = zones.findIndex(z => z.id === selectedZoneId);
    if (idx === -1) return;

    const [deleted] = zones.splice(idx, 1);
    if (deleted?.layer) floodZoneLayer.removeLayer(deleted.layer);

    if (zones.length > 0) {
        selectZone(zones[0].id);
    } else {
        selectedZoneId = null;
        document.getElementById('btn-delete-zone').disabled = true;
        document.getElementById('zone-rainfall-intensity').disabled = true;
        document.getElementById('zone-intensity-val').textContent = '—';
    }

    updateZoneSelectorUI();
    debounceSimulate();
}

// ── Simulation Playback Controls ──────────────────────────
function toggleSimulationPlay() {
    isSimPlaying = !isSimPlaying;
    const btn = document.getElementById('btn-play-pause');
    const icon = document.getElementById('play-pause-icon');
    const text = document.getElementById('play-pause-text');
    const badge = document.getElementById('sim-state-badge');

    if (isSimPlaying) {
        btn.classList.add('playing');
        icon.textContent = '⏸';
        text.textContent = 'Pause';
        badge.textContent = `RUNNING (${simSpeed}×)`;
        badge.className = 'badge badge-running';

        // Clear existing interval if any to eliminate duplicates
        if (simPlaybackInterval) clearInterval(simPlaybackInterval);

        const tickRateMs = 1000 / simSpeed;
        simPlaybackInterval = setInterval(() => {
            simTimeElapsed += 2;
            if (simTimeElapsed > 180) simTimeElapsed = 180;

            document.getElementById('sim-time-slider').value = simTimeElapsed;
            document.getElementById('sim-time-display').textContent = `${simTimeElapsed} min`;

            // Progressively rise water level and spread
            const waterSlider = document.getElementById('water-level');
            const currentWater = parseFloat(waterSlider.value);
            if (currentWater < 4.8) {
                const nextWater = Math.min(5.0, currentWater + 0.05);
                waterSlider.value = nextWater.toFixed(1);
                document.getElementById('water-val').textContent = `${nextWater.toFixed(1)} m`;
            }

            simulateFlood(true);

            if (simTimeElapsed >= 180) {
                toggleSimulationPlay();
            }
        }, tickRateMs);
    } else {
        btn.classList.remove('playing');
        icon.textContent = '▶';
        text.textContent = 'Play';
        badge.textContent = 'PAUSED';
        badge.className = 'badge badge-paused';

        if (simPlaybackInterval) {
            clearInterval(simPlaybackInterval);
            simPlaybackInterval = null;
        }
    }
    updateStatusDashboard(latestRouteData, latestSimData);
}

function setSimulationSpeed(speed) {
    simSpeed = speed;
    ['speed-1x', 'speed-2x', 'speed-5x'].forEach(id => {
        document.getElementById(id).classList.remove('active');
    });
    document.getElementById(`speed-${speed}x`).classList.add('active');

    if (isSimPlaying) {
        // Restart loop with new speed rate
        toggleSimulationPlay();
        toggleSimulationPlay();
    }
}

function onSimulationTimeSlider(val) {
    simTimeElapsed = parseInt(val, 10);
    document.getElementById('sim-time-display').textContent = `${simTimeElapsed} min`;
    debounceSimulate();
}

// ── Rainfall Intensity Handlers ───────────────────────────
function getIntensityCategory(percentVal) {
    if (percentVal <= 0) return { label: 'Zero Impact (0%)', badgeClass: 'badge-zero' };
    if (percentVal <= 30) return { label: 'Low (1–30%)', badgeClass: 'badge-low' };
    if (percentVal <= 60) return { label: 'Moderate (31–60%)', badgeClass: 'badge-moderate' };
    if (percentVal <= 80) return { label: 'Heavy (61–80%)', badgeClass: 'badge-heavy' };
    return { label: 'Extreme (81–100%)', badgeClass: 'badge-extreme' };
}

function onCircleIntensityChange(val) {
    const intVal = parseInt(val, 10);
    const cat = getIntensityCategory(intVal);
    const badge = document.getElementById('circle-intensity-category');
    if (badge) {
        badge.textContent = cat.label;
        badge.className = `intensity-badge ${cat.badgeClass}`;
    }
    document.getElementById('circle-intensity-val').textContent = `${intVal}%`;
    document.getElementById('flood-intensity').value = (intVal / 100.0).toFixed(2);

    if (floodCenter) debounceSimulate();
}

function onZoneRainfallChange(val) {
    const intVal = parseInt(val, 10);
    const cat = getIntensityCategory(intVal);
    const badge = document.getElementById('zone-intensity-category');
    if (badge) {
        badge.textContent = cat.label;
        badge.className = `intensity-badge ${cat.badgeClass}`;
    }
    document.getElementById('zone-intensity-val').textContent = `${intVal}%`;

    if (!selectedZoneId) return;
    const zone = zones.find(z => z.id === selectedZoneId);
    if (!zone) return;

    zone.intensity = intVal / 100.0;
    zone.layer.setStyle({
        fillOpacity: 0.15 + (intVal / 100.0) * 0.40
    });

    debounceSimulate();
}

// ── Scenario Presets ──────────────────────────────────────
function applyScenarioPreset(scenarioId) {
    if (!scenarioId) return;

    const presets = {
        'SCN_FLOOD_PUZHAKKAL_LOWLAND': { center: [76.1850, 10.5350], radius: 2200, intensity: 75, water_level: 2.2 },
        'SCN_FLOOD_KOLE_BREACH': { center: [76.1750, 10.4950], radius: 2800, intensity: 85, water_level: 3.0 },
        'SCN_FLOOD_SWARAJ_ROUND_FLASH': { center: [76.2144, 10.5276], radius: 1200, intensity: 60, water_level: 1.4 },
        'SCN_FLOOD_KURIACHIRA_INUNDATION': { center: [76.2250, 10.5050], radius: 1600, intensity: 70, water_level: 1.8 }
    };

    const scn = presets[scenarioId];
    if (!scn) return;

    setFloodMode('circle');
    document.getElementById('circle-intensity').value = scn.intensity;
    onCircleIntensityChange(scn.intensity);
    document.getElementById('water-level').value = scn.water_level;
    document.getElementById('water-val').textContent = `${scn.water_level} m`;
    document.getElementById('flood-radius').value = scn.radius;
    document.getElementById('radius-val').textContent = `${scn.radius}m`;

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
                water_level: waterLevel
            }))
        };
    }
}

// ── Flood Simulation Execution ────────────────────────────
let latestSimData = null;

function debounceSimulate() {
    if (simAutoDebounceTimer) clearTimeout(simAutoDebounceTimer);
    simAutoDebounceTimer = setTimeout(() => {
        simulateFlood(false);
    }, 120);
}

async function simulateFlood(fromPlayback = false) {
    if (floodMode === 'circle' && !floodCenter) {
        let center = null;
        if (latestRouteData?.routesense?.coordinates?.length) {
            const coords = latestRouteData.routesense.coordinates;
            center = coords[Math.floor(coords.length / 2)];
        } else if (latestRouteData?.normal?.coordinates?.length) {
            const coords = latestRouteData.normal.coordinates;
            center = coords[Math.floor(coords.length / 2)];
        } else if (originCoord && destCoord) {
            center = [(originCoord[0] + destCoord[0]) / 2, (originCoord[1] + destCoord[1]) / 2];
        } else {
            center = [76.2150, 10.5300];
        }
        setFloodCenter(center[0], center[1]);
    }

    const floodPayload = buildFloodPayload();
    if (!floodPayload) {
        if (!fromPlayback) setStatus('info', 'PLACE FLOOD EPICENTER OR DRAW ZONE TO SIMULATE');
        return;
    }

    const currentReqId = ++simRequestId;
    try {
        const res = await fetch(`${API}/api/simulate-flood`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(floodPayload)
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const simData = await res.json();

        // Discard out-of-order stale response
        if (currentReqId !== simRequestId) return;

        latestSimData = simData;
        renderAffectedRoads(simData.affected_roads || []);

        // Show Inundation ETA Card
        const etaCard = document.getElementById('flood-eta-card');
        if (etaCard && simData.avg_inundation_eta) {
            etaCard.style.display = 'flex';
            document.getElementById('flood-eta-value').textContent = simData.avg_inundation_eta;
            const urgencyEl = document.getElementById('flood-eta-urgency');
            const mins = simData.avg_inundation_minutes || 60;
            if (mins < 45) {
                urgencyEl.textContent = 'CRITICAL SURGE <45m';
                urgencyEl.className = 'eta-urgency critical';
            } else if (mins < 120) {
                urgencyEl.textContent = 'RAPID SURGE <2h';
                urgencyEl.className = 'eta-urgency high';
            } else {
                urgencyEl.textContent = 'SLOW PROPAGATION';
                urgencyEl.className = 'eta-urgency moderate';
            }
        }

        // Revalidate active route if points exist, WITHOUT hijacking destination
        if (originCoord && destCoord) {
            findRoute(true); // Silent revalidation
        } else {
            updateStatusDashboard(latestRouteData, simData);
        }

    } catch (e) {
        console.error('Simulation error:', e);
    }
}

function renderAffectedRoads(affectedRoads) {
    affectedRoadsLayer.clearLayers();
    riskLayer.clearLayers();
    affectedRoadPolylines = [];

    if (!affectedRoads || affectedRoads.length === 0) {
        document.getElementById('legend-affected').style.display = 'none';
        return;
    }

    document.getElementById('legend-affected').style.display = 'flex';
    const canvas = L.canvas({ padding: 0.2 });

    affectedRoads.forEach(road => {
        const coords = [
            [road.coordinates[0][1], road.coordinates[0][0]],
            [road.coordinates[1][1], road.coordinates[1][0]]
        ];

        const elev = (road.elevation != null && !isNaN(road.elevation)) ? Number(road.elevation) : 15.0;
        const isLowElev = elev < 15.0;
        const isMedElev = elev >= 15.0 && elev <= 25.0;

        let color = '#fbbf24'; // Caution
        let weight = 2.5;
        let opacity = 0.75;

        if (road.impassable || road.effective_risk === 2 || isLowElev) {
            color = '#ef4444'; // Red (High risk / blocked)
            weight = 4.0;
            opacity = 0.95;
        } else if (road.effective_risk === 1 || road.flood_penalty > 0.3 || isMedElev) {
            color = '#f97316'; // Orange (Elevated risk)
            weight = 3.2;
            opacity = 0.85;
        }

        const polyline = L.polyline(coords, { color, weight, opacity }).addTo(affectedRoadsLayer);
        const statusLabel = road.impassable ? 'IMPASSABLE / BLOCKED' : (isLowElev ? 'CRITICAL LOW ELEVATION' : (isMedElev ? 'MEDIUM ELEVATION HAZARD' : 'ELEVATED RISK'));
        polyline.bindPopup(
            `<strong>Flood-Affected Road Segment</strong><br>` +
            `Elevation: <strong style="color:${isLowElev ? '#ef4444' : (isMedElev ? '#f97316' : '#10b981')}">${elev.toFixed(1)} m</strong> (${isLowElev ? 'Low Ground Submerged' : (isMedElev ? 'Medium Ground Waterlogging' : 'High Ground')})<br>` +
            `Status: <span style="color:${color};font-weight:700">${statusLabel}</span><br>` +
            `Risk: ${road.original_risk} &rarr; <strong>${road.effective_risk}</strong><br>` +
            `Flood Penalty: ${road.flood_penalty || '0'}`
        );
        affectedRoadPolylines.push(polyline);

        // ── Render Elevation-Based Circle Markers in Flooded Area ──
        // Lower elevation: RED circle marked
        // Medium elevation: ORANGE circle marked
        const midLat = (coords[0][0] + coords[1][0]) * 0.5;
        const midLng = (coords[0][1] + coords[1][1]) * 0.5;

        let dotColor = null;
        let dotRadius = 4.5;
        let dotCategory = '';

        if (isLowElev) {
            dotColor = '#ef4444'; // Red circle marked for lower elevation (<15m)
            dotRadius = 5.0;
            dotCategory = 'Low Elevation Danger (<15m) — Submerged';
        } else if (isMedElev) {
            dotColor = '#f97316'; // Orange circle marked for medium elevation (15-25m)
            dotRadius = 4.0;
            dotCategory = 'Medium Elevation Caution (15–25m) — Waterlogging';
        }

        if (dotColor) {
            const marker = L.circleMarker([midLat, midLng], {
                radius: dotRadius,
                color: '#ffffff',
                weight: 1.2,
                fillColor: dotColor,
                fillOpacity: 0.9,
                renderer: canvas
            });
            marker.bindPopup(
                `<strong>Elevation Flood Warning</strong><br>` +
                `Elevation: <strong style="color:${dotColor}">${elev.toFixed(1)} m</strong><br>` +
                `Category: <strong>${dotCategory}</strong><br>` +
                `Status: <span style="color:${dotColor};font-weight:700">${statusLabel}</span>`
            );
            riskLayer.addLayer(marker);
        }
    });
}

function resetFlood() {
    floodCenter = null;
    clearFloodMarkers();
    togglePlaceCircleMode(false);

    if (isDrawingZone) cancelDrawingZone();
    zones.forEach(z => {
        if (z.layer) floodZoneLayer.removeLayer(z.layer);
    });
    zones = [];
    selectedZoneId = null;
    updateZoneSelectorUI();

    floodZoneLayer.clearLayers();
    affectedRoadsLayer.clearLayers();
    riskLayer.clearLayers();
    affectedRoadPolylines = [];
    latestSimData = null;

    document.getElementById('legend-flood').style.display = 'none';
    document.getElementById('legend-affected').style.display = 'none';
    document.getElementById('scenario-select').value = '';

    const etaCard = document.getElementById('flood-eta-card');
    if (etaCard) etaCard.style.display = 'none';
    dismissHazardAlert();

    // Reset Sliders
    document.getElementById('circle-intensity').value = 50;
    onCircleIntensityChange(50);
    document.getElementById('water-level').value = 1.0;
    document.getElementById('water-val').textContent = '1.0 m';
    document.getElementById('flood-radius').value = 2000;
    document.getElementById('radius-val').textContent = '2000m';

    // Stop Playback
    if (isSimPlaying) toggleSimulationPlay();
    simTimeElapsed = 0;
    document.getElementById('sim-time-slider').value = 0;
    document.getElementById('sim-time-display').textContent = '0 min';

    if (originCoord && destCoord) {
        findRoute();
    } else {
        updateStatusDashboard(latestRouteData, null);
    }
    setStatus('ok', 'NORMAL CONDITIONS RESTORED');
}

// ── WINDOW 3: Route Calculation & Road Following Paths ────
function selectProfile(profile) {
    selectedProfile = profile;
    document.querySelectorAll('[data-profile]').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`[data-profile="${profile}"]`);
    if (btn) btn.classList.add('active');

    if (originCoord && destCoord) {
        findRoute();
    }
}

function selectObjective(obj) {
    selectedObjective = obj;
    document.querySelectorAll('[data-objective]').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`[data-objective="${obj}"]`);
    if (btn) btn.classList.add('active');

    if (originCoord && destCoord) {
        findRoute();
    }
}

async function findRoute(silent = false) {
    if (!originCoord || !destCoord) {
        useDefaults();
        return;
    }

    const currentReqId = ++routeRequestId;
    const btn = document.getElementById('btn-route');
    if (!silent && btn) {
        btn.disabled = true;
        btn.textContent = 'CALCULATING…';
        setStatus('info', 'CALCULATING SAFE EVACUATION ROUTE');
    }

    const payload = {
        origin: originCoord,
        destination: destCoord,
        profile: selectedProfile,
        objective: selectedObjective,
        flood: buildFloodPayload()
    };

    try {
        const res = await fetch(`${API}/api/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Discard out-of-order stale response
        if (currentReqId !== routeRequestId) return;

        // Instant Shelter Reallocation if destination was blocked
        if (data.reallocated && data.reallocated_shelter) {
            const sh = data.reallocated_shelter;
            setDestination(sh.coordinates[0], sh.coordinates[1], `🛡️ ${sh.name}`);
            setStatus('caution', `DESTINATION BLOCKED: REALLOCATED TO 🛡️ ${sh.name.toUpperCase()}`);
        }

        latestRouteData = data;
        renderRoutes(data);
        renderRouteDetails(data);
        if (data.flood_active && data.affected_roads) {
            renderAffectedRoads(data.affected_roads);
        }
        updateStatusDashboard(data, latestSimData);

        if (data.routesense) {
            setStatus('ok', data.flood_active ? (data.reallocated ? 'SAFE CORRIDOR: SHELTER REALLOCATED' : 'SAFE ROUTE: FLOOD HAZARD EVADED') : 'OPTIMAL EVACUATION ROUTE');
        } else {
            setStatus('danger', 'NO SAFE ROUTE AVAILABLE — REQUEST RESCUE');
        }
    } catch (e) {
        console.error('Routing failed:', e);
        if (!silent) setStatus('danger', 'ROUTING ERROR: Path unreachable');
    }

    if (btn) {
        btn.disabled = false;
        btn.textContent = 'FIND SAFE ROUTE';
    }
}

function clearRoutes() {
    normalRouteLayer.clearLayers();
    rsRouteLayer.clearLayers();
    if (routeAnimInterval) { clearInterval(routeAnimInterval); routeAnimInterval = null; }
    routeParticles = [];
    latestRouteData = null;
    document.getElementById('route-path-results').style.display = 'none';
    document.getElementById('rescue-banner-route').style.display = 'none';
}

function renderRoutes(data) {
    clearRoutes();

    // 1. Base unrestricted route (dashed blue #38bdf8) for reference
    if (data.normal?.coordinates) {
        const latlngs = data.normal.coordinates.map(c => [c[1], c[0]]);
        L.polyline(latlngs, {
            color: '#38bdf8',
            weight: 3.5,
            opacity: 0.85,
            dashArray: '6 6'
        }).addTo(normalRouteLayer).bindPopup(
            `<strong>Unrestricted Shortest Path</strong><br>` +
            `Distance: ${(data.normal.distance / 1000).toFixed(2)} km<br>` +
            `<span style="color:#38bdf8;font-weight:600">Base unrestricted reference corridor</span>`
        );
    }

    // 2. Active safe route (thick emerald #059669 casing with risk-classified color segments)
    if (data.routesense?.coordinates) {
        const coords = data.routesense.coordinates;
        const latlngs = coords.map(c => [c[1], c[0]]);

        // Outer Casing Polyline: Thick emerald casing
        L.polyline(latlngs, {
            color: '#059669',
            weight: 8,
            opacity: 0.85,
            lineCap: 'round',
            lineJoin: 'round'
        }).addTo(rsRouteLayer);

        // Segment-by-segment true risk rendering
        if (data.routesense.geojson?.features) {
            data.routesense.geojson.features.forEach(feat => {
                const segCoords = feat.geometry.coordinates.map(c => [c[1], c[0]]);
                const riskVal = feat.properties.predicted_risk;
                const segColor = RISK_COLORS[riskVal] || '#10b981';

                L.polyline(segCoords, {
                    color: segColor,
                    weight: 4,
                    opacity: 0.95
                }).addTo(rsRouteLayer).bindPopup(
                    `<strong>Evacuation Road Segment</strong><br>` +
                    `Effective Risk: <strong>${feat.properties.risk_label || 'Safe'}</strong><br>` +
                    `Road Type: ${feat.properties.highway || 'Standard'}<br>` +
                    `Elevation: ${feat.properties.elevation} m`
                );
            });
        }

        // Animated traveling green particles along the active path
        animateRouteParticles(coords);
    }

    // Single smooth zoom on route arrival
    const coordsToFit = (data.routesense?.coordinates && data.routesense.coordinates.length > 0)
        ? data.routesense.coordinates
        : (data.normal?.coordinates && data.normal.coordinates.length > 0)
            ? data.normal.coordinates
            : null;
    if (coordsToFit && coordsToFit.length > 0) {
        const routeBounds = L.latLngBounds(coordsToFit.map(c => [c[1], c[0]]));
        if (routeBounds.isValid()) {
            map.fitBounds(routeBounds, { padding: [60, 60], maxZoom: 16, animate: true, duration: 1.0 });
        }
    }
}

function renderRouteDetails(data) {
    const resultsPanel = document.getElementById('route-path-results');
    const rescueBanner = document.getElementById('rescue-banner-route');

    if (data.routesense) {
        resultsPanel.style.display = 'block';
        rescueBanner.style.display = 'none';

        const distKm = (data.routesense.distance / 1000).toFixed(2);
        document.getElementById('rp-distance').textContent = `${distKm} km`;

        // Estimated Travel Time based on profile average speeds
        const speedKmh = selectedProfile === 'emergency' ? 55 : (selectedProfile === 'elderly' ? 25 : 35);
        const etaMinutes = Math.max(1, Math.round((data.routesense.distance / 1000 / speedKmh) * 60));
        document.getElementById('rp-eta').textContent = `~${etaMinutes} min`;

        // Risk Level
        const highCount = data.routesense.risk_counts['2'] || 0;
        const medCount = data.routesense.risk_counts['1'] || 0;
        const riskLabel = highCount > 0 ? 'High' : (medCount > 0 ? 'Moderate' : 'Low');
        document.getElementById('rp-risk').textContent = riskLabel;
        document.getElementById('rp-highsegs').textContent = `${highCount} Segments`;

        // Safety Badge
        const badge = document.getElementById('route-safety-badge');
        const safety = data.route_safety || (highCount === 0 ? 'safe' : 'caution');
        if (safety === 'safe') {
            badge.textContent = 'VERIFIED SAFE';
            badge.className = 'badge badge-safe';
        } else if (safety === 'caution') {
            badge.textContent = 'CAUTION';
            badge.className = 'badge badge-caution';
        } else if (safety === 'elevated') {
            badge.textContent = 'ELEVATED RISK';
            badge.className = 'badge badge-elevated';
        } else {
            badge.textContent = 'HIGH RISK';
            badge.className = 'badge badge-blocked';
        }

        // Warning Box
        const warnBox = document.getElementById('rp-warning-box');
        if (data.flood_active) {
            warnBox.style.display = 'block';
            warnBox.textContent = `Flood evasion active: safe detour detours around inundated zones (avoided ${data.comparison?.high_risk_avoided || 0} hazard roads).`;
        } else {
            warnBox.style.display = 'none';
        }
    } else {
        // NO SAFE ROUTE AVAILABLE (Requirement: Must display exact string)
        resultsPanel.style.display = 'none';
        rescueBanner.style.display = 'flex';
    }
}

function animateRouteParticles(coords) {
    if (coords.length < 2) return;
    const NUM_PARTICLES = 8;
    const particles = [];

    for (let i = 0; i < NUM_PARTICLES; i++) {
        const marker = L.circleMarker([0, 0], {
            radius: 3,
            color: '#ecfdf5',
            fillColor: '#10b981',
            fillOpacity: 0.95,
            weight: 1
        }).addTo(rsRouteLayer);
        particles.push({ marker, progress: i / NUM_PARTICLES });
    }

    routeParticles = particles;
    routeAnimInterval = setInterval(() => {
        particles.forEach(p => {
            p.progress += 0.004;
            if (p.progress > 1) p.progress = 0;
            const idx = p.progress * (coords.length - 1);
            const i = Math.floor(idx);
            const t = idx - i;
            const c1 = coords[Math.min(i, coords.length - 1)];
            const c2 = coords[Math.min(i + 1, coords.length - 1)];
            const lon = c1[0] + (c2[0] - c1[0]) * t;
            const lat = c1[1] + (c2[1] - c1[1]) * t;
            p.marker.setLatLng([lat, lon]);
        });
    }, 45);
}

// ── WINDOW 2: Status Monitoring Dashboard ─────────────────
function updateStatusDashboard(routeData, simData) {
    const isFloodActive = Boolean(floodCenter || zones.length > 0);

    // 1. Flood Conditions
    const severityPill = document.getElementById('st-severity-pill');
    const rainfallEl = document.getElementById('st-rainfall');
    const simStateEl = document.getElementById('st-sim-state');
    const affectedAreasEl = document.getElementById('st-affected-areas');
    const highRiskEl = document.getElementById('st-highrisk-count');
    const blockedEl = document.getElementById('st-blocked-count');
    const waterLevelEl = document.getElementById('st-water-level');
    const floodDot = document.getElementById('st-flood-dot');

    const intensityVal = floodMode === 'circle'
        ? parseInt(document.getElementById('circle-intensity')?.value || 50, 10)
        : (zones.length > 0 ? Math.round((zones[0]?.intensity || 0.7) * 100) : 0);

    if (isFloodActive) {
        simStateEl.textContent = isSimPlaying ? `Running (${simSpeed}×)` : 'Active (Paused)';
        rainfallEl.textContent = `${intensityVal}% (${getIntensityCategory(intensityVal).label.split(' ')[0]})`;
        waterLevelEl.textContent = `${parseFloat(document.getElementById('water-level')?.value || 1.0).toFixed(1)} m`;

        if (intensityVal > 80) {
            severityPill.textContent = 'Extreme';
            severityPill.className = 'status-pill pill-red';
            floodDot.className = 'status-indicator danger';
        } else if (intensityVal > 60) {
            severityPill.textContent = 'Severe';
            severityPill.className = 'status-pill pill-orange';
            floodDot.className = 'status-indicator elevated';
        } else if (intensityVal > 30) {
            severityPill.textContent = 'Moderate';
            severityPill.className = 'status-pill pill-yellow';
            floodDot.className = 'status-indicator caution';
        } else {
            severityPill.textContent = 'Minor';
            severityPill.className = 'status-pill pill-green';
            floodDot.className = 'status-indicator safe';
        }

        const affCount = simData?.affected_count || simData?.affected_roads?.length || 0;
        affectedAreasEl.textContent = `${affCount} road segments`;

        let blockedCount = 0;
        let highCount = 0;
        if (simData?.affected_roads) {
            simData.affected_roads.forEach(r => {
                if (r.impassable) blockedCount++;
                else if (r.effective_risk === 2) highCount++;
            });
        }
        highRiskEl.textContent = highCount;
        blockedEl.textContent = blockedCount;
    } else {
        simStateEl.textContent = 'Inactive';
        rainfallEl.textContent = 'Unavailable';
        waterLevelEl.textContent = 'Baseline (0 m)';
        severityPill.textContent = 'Normal';
        severityPill.className = 'status-pill pill-green';
        floodDot.className = 'status-indicator safe';
        affectedAreasEl.textContent = 'None';
        highRiskEl.textContent = '0';
        blockedEl.textContent = '0';
    }

    // 2. Route Safety Status (Window 2)
    const routeSafetyPill = document.getElementById('st-route-safety-pill');
    const routeRiskEl = document.getElementById('st-route-risk');
    const routeClearanceEl = document.getElementById('st-route-clearance');
    const routeAltEl = document.getElementById('st-route-alt-available');
    const routeDot = document.getElementById('st-route-dot');
    const rescueBanner = document.getElementById('rescue-banner-status');
    const warningsList = document.getElementById('st-warnings-list');

    warningsList.innerHTML = '';

    if (!routeData) {
        routeSafetyPill.textContent = 'No Route Selected';
        routeSafetyPill.className = 'status-pill pill-grey';
        routeRiskEl.textContent = 'Unavailable';
        routeClearanceEl.textContent = 'Unavailable';
        routeAltEl.textContent = 'Unknown';
        routeDot.className = 'status-indicator unknown';
        rescueBanner.style.display = 'none';

        warningsList.innerHTML = '<div class="warning-item info">Select starting point and destination in Route Path tab.</div>';
        return;
    }

    if (routeData.routesense) {
        rescueBanner.style.display = 'none';
        const safety = routeData.route_safety || 'safe';

        if (safety === 'safe') {
            routeSafetyPill.textContent = 'VERIFIED SAFE';
            routeSafetyPill.className = 'status-pill pill-green';
            routeDot.className = 'status-indicator safe';
            routeClearanceEl.textContent = '100% Hazard Cleared';
        } else if (safety === 'caution') {
            routeSafetyPill.textContent = 'CAUTION';
            routeSafetyPill.className = 'status-pill pill-yellow';
            routeDot.className = 'status-indicator caution';
            routeClearanceEl.textContent = 'Passable (>90% Clear)';
        } else if (safety === 'elevated') {
            routeSafetyPill.textContent = 'ELEVATED RISK';
            routeSafetyPill.className = 'status-pill pill-orange';
            routeDot.className = 'status-indicator elevated';
            routeClearanceEl.textContent = 'Reduced Clearance';
        } else {
            routeSafetyPill.textContent = 'BLOCKED';
            routeSafetyPill.className = 'status-pill pill-red';
            routeDot.className = 'status-indicator danger';
            routeClearanceEl.textContent = 'Hazard Proximity Warning';
        }

        const highCount = routeData.routesense.risk_counts['2'] || 0;
        routeRiskEl.textContent = highCount === 0 ? 'Low (Minimal Danger)' : `${highCount} High-Risk Segs`;
        routeAltEl.textContent = 'Active Safe Corridor Verified';

        // Populate Warnings
        if (isFloodActive) {
            warningsList.innerHTML += '<div class="warning-item warning">Active flood hazard in district. Overland route safely detours impassable sections.</div>';
        }
        if (selectedProfile === 'elderly') {
            warningsList.innerHTML += '<div class="warning-item info">Elderly safety profile active: stairs, steep slopes, and narrow pathways are excluded.</div>';
        } else if (selectedProfile === 'wheelchair') {
            warningsList.innerHTML += '<div class="warning-item info">Wheelchair accessible profile active: stairs and slopes > 8% are excluded.</div>';
        }
    } else {
        // NO SAFE ROUTE AVAILABLE (Requirement: Must display exact string)
        routeSafetyPill.textContent = 'BLOCKED';
        routeSafetyPill.className = 'status-pill pill-red';
        routeDot.className = 'status-indicator danger';
        routeRiskEl.textContent = 'Extreme Danger';
        routeClearanceEl.textContent = '0% (Corridor Blocked)';
        routeAltEl.textContent = 'None Available';

        // Display exact rescue required prompt
        rescueBanner.style.display = 'flex';
        warningsList.innerHTML += '<div class="warning-item danger">CRITICAL: No safe route available — request rescue assistance. All overland road corridors to destination are submerged.</div>';
    }
}

// ── Shelter Discovery Integration ─────────────────────────
async function findNearestSafeSpot() {
    const btn = document.getElementById('btn-find-safe-spot');
    btn.disabled = true;
    btn.textContent = 'LOCATING SAFE SHELTER…';
    setStatus('info', 'EVALUATING ACCESSIBLE SAFE SHELTERS BY ROAD DISTANCE');

    try {
        if (!originCoord) useDefaults();
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
            alert(data.error || 'No safe shelter is currently reachable by road.');
            btn.disabled = false;
            btn.textContent = '🛡️ FIND SAFE SHELTER';
            return;
        }

        const bestShelter = data.best_shelter;
        const allShelters = data.all_shelters || [];

        // Render shelters on map
        shelterMarkersLayer.clearLayers();
        allShelters.forEach(sh => {
            const isTarget = sh.id === bestShelter.id;
            const m = L.circleMarker([sh.coordinates[1], sh.coordinates[0]], {
                radius: isTarget ? 12 : 7,
                color: '#ffffff',
                weight: isTarget ? 3 : 1.5,
                fillColor: isTarget ? '#10b981' : '#64748b',
                fillOpacity: 0.95
            }).addTo(shelterMarkersLayer);

            m.bindPopup(
                `<strong>🛡️ ${sh.name}</strong><br>` +
                `Road Distance: <strong>${sh.road_distance_km} km</strong><br>` +
                `Elevation: <strong>${sh.elevation} m</strong> (High Ground)<br>` +
                `Capacity: ${sh.capacity} persons<br>` +
                `Contact: ${sh.contact}`
            );
            if (isTarget) m.openPopup();
        });

        // Set destination to this shelter and route
        setDestination(bestShelter.coordinates[0], bestShelter.coordinates[1], `🛡️ ${bestShelter.name}`);

        if (data.route) {
            latestRouteData = data.route;
            renderRoutes(data.route);
            renderRouteDetails(data.route);
            updateStatusDashboard(data.route, latestSimData);
        }

        setStatus('ok', `SAFE HAVEN LOCATED: ${bestShelter.name} (${bestShelter.road_distance_km} km)`);
    } catch (e) {
        console.error('Failed to find shelter:', e);
        setStatus('danger', 'ERROR: Shelter search failed');
    }

    btn.disabled = false;
    btn.textContent = '🛡️ FIND SAFE SHELTER';
}

// ── GPS User Positioning ──────────────────────────────────
function locateUser() {
    if (!navigator.geolocation) {
        alert('Geolocation is not supported by your browser.');
        return;
    }

    const btn = document.getElementById('btn-gps-origin');
    if (btn) btn.textContent = '⏳ GPS…';
    setStatus('info', 'ACQUIRING GPS FIX…');

    navigator.geolocation.getCurrentPosition(
        (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            let activeLat = lat;
            let activeLon = lon;

            const inStudyArea = (lon >= 76.15 && lon <= 76.28 && lat >= 10.45 && lat <= 10.61);
            if (!inStudyArea) {
                // If user is testing outside Thrissur study area, position in central Thrissur
                activeLat = 10.528;
                activeLon = 76.214;
            }

            setOrigin(activeLon, activeLat);
            map.flyTo([activeLat, activeLon], 14, { animate: true, duration: 0.8 });
            if (btn) btn.textContent = '📍 Active';
            setStatus('ok', 'GPS LOCATION LOCKED');

            if (destCoord) findRoute();
        },
        (err) => {
            console.warn('Geolocation error:', err);
            if (btn) btn.textContent = '📍 GPS';
            alert('Could not acquire live GPS. Please click on the map to set starting location.');
        },
        { enableHighAccuracy: true, timeout: 8000 }
    );
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
        document.getElementById('mobile-qr-img').src = data.qr_url;
    } catch (e) {
        const hostUrl = window.location.origin;
        document.getElementById('mobile-url-link').textContent = hostUrl;
        document.getElementById('mobile-url-link').href = hostUrl;
        document.getElementById('mobile-qr-img').src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(hostUrl)}`;
    }
}

function closeMobileConnectModal() {
    document.getElementById('mobile-modal').style.display = 'none';
}

function dismissHazardAlert() {
    const banner = document.getElementById('dynamic-hazard-alert');
    if (banner) banner.style.display = 'none';
}

// ── Status & Utilities ────────────────────────────────────
function setStatus(type, text) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-text');
    if (dot) dot.className = type;
    if (label) label.textContent = text;
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
        setTimeout(() => overlay.remove(), 400);
    }
}

// ── Slider Event Binding ──────────────────────────────────
function setupUIEventListeners() {
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
        if (el) {
            el.addEventListener('input', () => {
                const w = parseFloat(document.getElementById('water-level')?.value || 1.0);
                const r = parseFloat(document.getElementById('flood-radius')?.value || 2000);
                document.getElementById('water-val').textContent = `${w.toFixed(1)} m`;
                document.getElementById('radius-val').textContent = `${r}m`;

                if (floodCenter && floodCircles.length > 0) {
                    floodCircles.forEach((fc, i) => {
                        fc.baseRadius = r * (1 - i * 0.25);
                        fc.circle.setRadius(fc.baseRadius);
                    });
                }
                debounceSimulate();
            });
        }
    });
}
