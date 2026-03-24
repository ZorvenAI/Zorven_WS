---
name: brand-architecture-hierarchy-builder
version: "1.0"
description: Build brand hierarchy tree with recursive nodes (master, sub_brand, product_line, endorsed, independent) in JSON format for React Flow visualization (maps to SKL-BAA-07)
target_agents:
  - brand_architecture
triggers:
  - "hierarchy builder"
  - "brand hierarchy"
  - "brand tree"
  - "portfolio structure"
  - "architecture visualization"
priority: 10
max_tokens: 600
---

# Brand Hierarchy Builder

## Purpose
Construct a structured brand hierarchy tree based on the recommended architecture model, existing portfolio items, and audience alignment data. The output is a recursive JSON tree optimized for React Flow visualization on the frontend workspace canvas.

## Methodology

### 1. Input Collection
- Read SKL-BAA-06 `baa_model_recommendation` for the recommended architecture model
- Read SKL-BAA-03 `baa_portfolio` for existing portfolio items and current hierarchy
- Read SKL-BAA-02 `baa_audience_alignment` for segment-to-brand mapping (if available)
- Read SKL-BAA-05 `baa_rag_context` for architecture constraints from prior decisions (if available)
- If model recommendation is absent, trigger SKL-BAA-12 and default to current portfolio structure

### 2. Node Type Definitions

| Node Type | Visual Style | Role in Hierarchy |
|-----------|-------------|-------------------|
| `master` | Primary node, largest, brand color | Root of the tree, the parent brand |
| `sub_brand` | Secondary node, parent name visible | Extension sharing parent brand equity |
| `product_line` | Tertiary node, category-focused | Specific product category under a brand |
| `endorsed` | Secondary node, "by Parent" suffix | Semi-independent brand with parent endorsement |
| `independent` | Standalone node, no parent linkage | Fully autonomous brand in the portfolio |

### 3. Hierarchy Construction Rules
Based on the recommended architecture model, apply construction rules:

**Branded House**:
- Single `master` root node
- All offerings as `sub_brand` or `product_line` nodes directly under master
- Maximum depth: 3 levels (master > sub_brand > product_line)

**House of Brands**:
- Invisible parent holding node (or corporate node if the parent brand has market presence)
- Each brand as an `independent` node at level 1
- Product lines under each independent brand at level 2

**Endorsed**:
- `master` root node
- `endorsed` nodes at level 1, each showing "by {master_brand}"
- `product_line` nodes under each endorsed brand at level 2

**Hybrid**:
- `master` root node
- Mix of `sub_brand`, `endorsed`, and `independent` nodes at level 1
- `product_line` nodes at level 2-3

**Sub-Brand**:
- `master` root node
- `sub_brand` nodes at level 1 with "{master} {modifier}" naming
- `product_line` nodes under sub-brands at level 2

### 4. Recursive Tree Node Schema
Each node in the tree follows this recursive structure:
```json
{
  "id": "unique_node_id",
  "brand_name": "Brand Name",
  "node_type": "master|sub_brand|product_line|endorsed|independent",
  "tier": "premium|mid|value|corporate",
  "target_segment": "segment description",
  "status": "existing|recommended_new|recommended_restructure",
  "relationship_label": "by Parent|from Parent|null",
  "metadata": {
    "category": "product category",
    "positioning_note": "brief positioning context"
  },
  "children": []
}
```

### 5. Placement Optimization
- Existing portfolio items (from SKL-BAA-03) are placed with `status: "existing"`
- Recommended structural changes are placed with `status: "recommended_restructure"`
- Suggested new brands/tiers to fill portfolio gaps are placed with `status: "recommended_new"`
- Respect architecture constraints from RAG context (SKL-BAA-05)

### 6. React Flow Layout Hints
Generate layout metadata for frontend rendering:
- `layout_direction`: "TB" (top-to-bottom) for hierarchical models, "LR" (left-to-right) for flat models
- `node_count`: Total nodes in the tree
- `max_depth`: Maximum hierarchy depth
- `edge_type`: "smoothstep" for parent-child, "dashed" for endorsed relationships

## Output Schema
Write to `node_outputs.baa_hierarchy` with keys:
- `tree`: Recursive node structure (root node with nested `children`)
- `flat_nodes`: list of `{id, brand_name, node_type, tier, status, parent_id}` (for easier processing)
- `edges`: list of `{source_id, target_id, relationship_type}` (for React Flow)
- `layout_hints`: `{layout_direction, node_count, max_depth, edge_type}`
- `changes_from_current`: list of `{action: "add"|"restructure"|"remove", node_id, description}`
- `hierarchy_stats`: `{total_nodes: int, existing_nodes: int, new_nodes: int, restructured_nodes: int, depth: int}`

## Integration Notes
- This output is designed for direct consumption by the frontend `WorkflowCanvas` component via React Flow
- SKL-BAA-08 (naming designer) uses the hierarchy to validate naming pattern consistency
- SKL-BAA-10 (strategy synthesis) includes the hierarchy visualization in the strategy document
- The `flat_nodes` and `edges` arrays can be directly mapped to React Flow `nodes` and `edges` props
