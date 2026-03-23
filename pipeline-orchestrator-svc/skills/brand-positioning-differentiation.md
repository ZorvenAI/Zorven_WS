---
name: brand-positioning-differentiation
version: "1.0"
description: Points of Parity, Points of Difference, Reasons to Believe, positioning proof points, competitive vulnerability assessment (maps to SKL-BPA-09)
target_agents:
  - brand_positioning
triggers:
  - "differentiation"
  - "points of parity"
  - "points of difference"
  - "reasons to believe"
  - "proof points"
  - "POP POD RTB"
priority: 9
max_tokens: 500
---

# Differentiation Framework

## Purpose
Define the brand's Points of Parity (POPs), Points of Difference (PODs), and Reasons to Believe (RTBs) that substantiate the recommended positioning statement. Includes proof point mapping and competitive vulnerability assessment.

## Methodology

### 1. Points of Parity (POPs)
Identify category must-haves that the brand MUST match to be considered a legitimate competitor:
- Source from SKL-BPA-02 table-stakes needs
- Cross-reference with CIA competitor capabilities that are universal in the category
- For each POP, assess brand's current delivery: **Meets** / **Partially Meets** / **Does Not Meet**
- POPs with "Does Not Meet" are flagged as critical gaps requiring remediation before positioning launch

### 2. Points of Difference (PODs)
Identify attributes where the brand can claim meaningful superiority:
- Source from SKL-BPA-02 differentiators and delighters
- Cross-reference with SKL-BPA-01 white-space zones and competitive gaps
- Validate each POD against three criteria:
  - **Desirability**: Customers actually want this (evidence from VoCA/APA data)
  - **Deliverability**: Brand can credibly deliver (evidence from Company capabilities, identity anchor)
  - **Differentiability**: Competitors cannot easily match (evidence from CIA profiling)
- Score each criterion 1-5; PODs must score >= 3 on all three to qualify

### 3. Reasons to Believe (RTBs)
For each qualifying POD, construct supporting evidence:
- **Factual RTBs**: Statistics, awards, certifications, patents, customer counts
- **Demonstrative RTBs**: Case studies, testimonials, product demonstrations
- **Endorsement RTBs**: Expert validation, media coverage, analyst reports
- **Heritage RTBs**: Founding story, track record, years of experience
- Source from Discovery agent output, RAG context (SKL-BPA-05), and Company model

### 4. Proof Point Matrix
Build a matrix mapping each POD to its RTBs:

| POD | RTB Type | Evidence | Source | Strength (1-5) |
|-----|----------|----------|--------|-----------------|
| ... | Factual  | "10K+ customers" | Company model | 4 |

### 5. Competitive Vulnerability Assessment
For each POD, assess vulnerability to competitive response:
- **Imitation Risk** (1-5): How easily can competitors copy this POD?
- **Substitution Risk** (1-5): Can competitors offer an alternative that neutralizes the POD?
- **Leapfrog Risk** (1-5): Can competitors skip past this POD entirely?
- **Composite Vulnerability** = average of three risk scores
- PODs with vulnerability >= 4 are flagged as "defensibility concern"

## Output Schema
Write to `node_outputs.bpa_differentiation` with keys:
- `pops`: list of `{attribute, delivery_status, gap_flag: bool}`
- `pods`: list of `{attribute, desirability, deliverability, differentiability, qualified: bool}`
- `rtbs`: list of `{pod_attribute, rtb_type, evidence, source, strength}`
- `proof_matrix`: list of `{pod, rtbs: [{type, evidence, strength}]}`
- `vulnerability`: list of `{pod, imitation_risk, substitution_risk, leapfrog_risk, composite, defensibility_concern: bool}`
- `critical_pop_gaps`: list of `{attribute, remediation_priority}`
- `differentiation_score`: float (0-100, composite across all qualified PODs)

## Integration Notes
- `differentiation_score` < 40 triggers SKL-BPA-12 (human escalation for low differentiation)
- SKL-BPA-10 (strategy synthesis) uses the full POP/POD/RTB framework as a core deliverable section
- SKL-BPA-06 (statement generator) references PODs during constraint validation
