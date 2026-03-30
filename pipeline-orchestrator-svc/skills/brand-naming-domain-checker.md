---
name: brand-naming-domain-checker
version: "1.0"
description: Perform DNS lookups to check domain availability for name candidates across common TLDs, compute domain viability scores (maps to SKL-NTA-06)
target_agents:
  - naming_tagline
triggers:
  - "domain checker"
  - "domain availability"
  - "dns lookup"
  - "domain check"
  - "web domain"
priority: 9
max_tokens: 400
---

# Domain Availability Checker

## Purpose
Verify domain name availability for each name candidate across priority TLDs (.com, .io, .co, .ai, industry-specific). Domain availability is a practical constraint — even a perfect brand name loses value if no reasonable domain can be secured.

## Methodology

### 1. Candidate Collection
- Read `node_outputs.nta_name_candidates` from SKL-NTA-09 for the list of name candidates
- For each candidate, generate domain variations:
  - Exact match: `{name}.{tld}`
  - Hyphenated: `{word1}-{word2}.{tld}` (if multi-word)
  - Abbreviated: Common abbreviations of the name
  - Prefixed: `get{name}`, `try{name}`, `use{name}` (fallback options)

### 2. TLD Priority Order
Check domains in priority order:
1. `.com` (highest commercial value)
2. `.io` (tech-focused brands)
3. `.co` (modern alternative)
4. `.ai` (AI/tech brands)
5. Industry-specific: `.health`, `.finance`, `.shop`, `.studio` (based on `input_context.company.industry`)
6. Country-code: `.us`, `.uk`, `.de` (based on target market)

### 3. DNS Resolution Check
For each domain variation:
- Perform async DNS A/AAAA record lookup
- If no DNS records exist: mark as `likely_available`
- If DNS records exist: mark as `taken`
- Note: DNS check is a heuristic — true availability requires WHOIS or registrar API (v2)
- Rate limit: max 20 DNS queries per candidate, max 100 total per execution

### 4. Domain Viability Scoring (0-100)
For each candidate, compute a domain viability score:
- **Exact .com available** (40 points): The gold standard
- **Exact alternative TLD available** (20 points): .io, .co, .ai
- **Variant available on .com** (15 points): get{name}.com, {name}app.com
- **Exact match on industry TLD** (15 points): {name}.health, {name}.ai
- **Only prefixed/modified available** (10 points): Less desirable but workable
- **No viable domain found** (0 points): Major practical concern

### 5. Recommendation
For each candidate, recommend the best available domain option:
- Primary recommendation: The highest-value available domain
- Alternative recommendations: Up to 3 fallback options
- Flag candidates where no viable domain exists

## Output Schema
Write to `node_outputs.nta_domain_check` with keys:
- `domain_results`: list of `{candidate_name, domains_checked: [{domain, tld, status: "likely_available"|"taken", variation_type}], viability_score: int, recommended_domain: str|null, alternatives: []}`
- `summary`: `{candidates_checked: int, all_clear: int, partial_available: int, no_domain: int}`
- `check_method`: "dns_heuristic" (v1) or "whois_verified" (v2)
- `rate_limit_hit`: bool

## Integration Notes
- Downstream consumers: SKL-NTA-10 (name scorer uses viability_score as a scoring dimension)
- DNS checks are best-effort heuristics — `likely_available` does not guarantee registrability
- v2 will integrate with a domain registrar API (e.g., Namecheap, GoDaddy) for definitive availability
- Execution is async with concurrent DNS lookups for performance
