---
name: brand-positioning-perceptual-maps
version: "1.0"
description: Generate 3-5 perceptual maps with different dimension pairs, competitor positions, migration vectors, white-space highlighting (maps to SKL-BPA-08)
target_agents:
  - brand_positioning
triggers:
  - "perceptual map"
  - "positioning map"
  - "brand map"
  - "competitive map visual"
  - "migration vector"
priority: 8
max_tokens: 500
---

# Perceptual Map Generator

## Purpose
Produce 3-5 distinct perceptual maps using different dimension pairs to visualize the competitive landscape from multiple strategic angles. Each map includes competitor positions, the brand's current and target positions, migration vectors, and white-space highlighting.

## Methodology

### 1. Dimension Pair Selection
Select 3-5 dimension pairs from the following candidates, prioritizing pairs that reveal different strategic insights:

| Pair ID | X-Axis | Y-Axis | Strategic Lens |
|---------|--------|--------|----------------|
| MAP-1 | Price/Value | Feature Richness | Market tier positioning |
| MAP-2 | Innovation | Trust/Heritage | Disruption vs. establishment |
| MAP-3 | Specialization | Market Breadth | Niche vs. generalist |
| MAP-4 | Customer Intimacy | Operational Excellence | Value discipline focus |
| MAP-5 | Digital Maturity | Human Touch | Service delivery model |

- Use CIA profiling data (SKL-BPA-01) to determine which pairs produce the most spread among competitors
- Drop any pair where all competitors cluster within a 20% range on either axis

### 2. Position Plotting
For each map:
- Plot all profiled competitors with their normalized coordinates (0-100 on each axis)
- Plot the focal brand's **current position** based on identity context (SKL-BPA-04) and prior positioning (SKL-BPA-05)
- Plot the focal brand's **target position** based on the recommended positioning statement (SKL-BPA-06)
- Draw a **migration vector** (arrow) from current to target position

### 3. White-Space Highlighting
- Overlay white-space zones identified in SKL-BPA-01
- Shade zones with composite demand/feasibility/defensibility score >= 6 as "high opportunity"
- Shade zones with score 4-5 as "moderate opportunity"
- Leave zones < 4 unshaded

### 4. Cluster Annotations
- Circle competitor clusters (3+ competitors within 15% proximity)
- Label each cluster with a descriptor (e.g., "Premium Generalists", "Budget Disruptors")
- Annotate the strategic implication of each cluster for the focal brand

### 5. Map Metadata
For each map, include:
- Title describing the strategic lens
- Axis labels with definitions
- Legend explaining symbols (current position, target position, competitor, white-space)
- 2-3 sentence strategic insight derived from the map

## Output Schema
Write to `node_outputs.bpa_perceptual_maps` with keys:
- `maps`: list of `{map_id, title, x_axis, y_axis, strategic_lens, competitors: [{name, x, y}], focal_current: {x, y}, focal_target: {x, y}, migration_vector: {dx, dy, magnitude}, white_space_zones: [{quadrant, opportunity_level}], clusters: [{label, members[], implication}], insight: str}`
- `maps_generated`: int
- `maps_dropped`: list of `{pair_id, reason}` (pairs dropped due to insufficient spread)

## Integration Notes
- Frontend renders these as interactive scatter plots via Recharts
- SKL-BPA-10 (strategy synthesis) includes maps as visual deliverables in the strategy document
- Migration vector magnitude indicates the degree of repositioning required; large vectors may trigger SKL-BPA-12 (human escalation)
