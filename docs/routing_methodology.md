# RouteSense AI: Risk-Aware Routing Methodology

## 1. Road Network Representation
The routing system utilizes the Kerala roads dataset extracted into GeoJSON format. Road geometries are inherently represented as `LineString` elements, and environmental properties (elevation, slope, rainfall, distance to water) as well as the ML-predicted risk labels and probabilities are attached to these geometries as feature attributes. 

## 2. Graph Construction
To enable routing, the spatial GeoJSON is converted into a mathematical graph using the `NetworkX` library.
*   **Nodes** are formed by extracting the individual coordinate vertices (longitude, latitude) from each road `LineString`.
*   **Edges** are formed between consecutive vertices in a `LineString`. 
Each edge inherits the risk profile and attributes of its parent road feature. Physical distance for each edge is computed accurately in meters using the Haversine (Great-Circle) distance formula, properly accounting for the Earth's curvature despite the data being in a geographic CRS (EPSG:4326).

## 3. Normal Shortest-Path Algorithm
The baseline routing mechanism utilizes **Dijkstra's Algorithm**. For the "Normal Route", the algorithm is configured to minimize the sum of the physical edge lengths (`distance`). This produces the fastest/shortest route without any regard for environmental hazards.

## 4. RouteSense Risk-Aware Algorithm
The RouteSense algorithm also relies on Dijkstra's Algorithm, but uses a modified edge weight known as `routesense_cost`. By substituting distance with risk-weighted distance, the algorithm is forced to evaluate the safety of the path.

## 5. Risk Weighting
The `routesense_cost` is calculated dynamically for each edge as:
`routesense_cost = distance × risk_multiplier`

Where the default multipliers are configured as:
*   **LOW Risk (0):** 1.0 (No penalty)
*   **MEDIUM Risk (1):** 2.0 (Double distance penalty)
*   **HIGH Risk (2):** 5.0 (Quintuple distance penalty)

Because RouteSense minimizes this modified cost, it can intentionally select a slightly longer physical route when it significantly reduces exposure to high-risk road segments. 

## 6. Origin/Destination Mapping
The system accepts arbitrary Origin and Destination coordinates (longitude, latitude). The script maps these input coordinates to the closest available graph node by computing the Haversine distance to all nodes and selecting the minimum. 

## 7. Route Comparison
Both routes are calculated simultaneously and compared segment-by-segment. The system outputs metrics detailing total distance, number of segments across each risk category, and the net reduction in high-risk exposure achieved by the RouteSense route.

## 8. Limitations
**IMPORTANT:** This routing system currently operates on **Prototype / Synthetic / Heuristic** risk labels generated to demonstrate the end-to-end AI/ML pipeline. The underlying ML predictions do *not* represent real verified flood probabilities, but rather a complex learned relationship between engineered environmental factors. Therefore, this routing algorithm **must not be presented or utilized as a certified emergency navigation system**. It serves purely as an academic proof-of-concept for risk-weighted geographical navigation.
