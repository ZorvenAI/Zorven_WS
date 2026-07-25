# OD-002: STT Language Mode — Fixed per Tenant vs Auto-Detect

**Status**: Accepted
**Date**: 2026-07-25
**Deciders**: Engineering team
**Spike**: A-01 — STT v2 streaming latency and diarization

## Context

Google Cloud STT v2 supports two language configuration modes for recognizers:
1. **Fixed language**: A single language code (e.g., `en-US`) — the recognizer expects all audio in that language
2. **Multi-language (auto-detect)**: Up to 3 language codes (e.g., `en-US`, `es-US`, `fr-FR`) — the recognizer auto-detects which language is being spoken

The Onboarding Intelligence Agent needs to transcribe live meetings. The question is whether to configure a fixed language per tenant or use auto-detection per session.

## Decision

**Use fixed language per tenant, defaulting to `en-US`.**

Add a `preferred_stt_language` field to the tenant model in a future story, allowing tenants to select their primary meeting language. Default to `en-US` for MVP.

## Evidence

From A-01 spike measurements (577 samples per recognizer, TTS-generated 2-speaker fixture):

| Metric | Fixed (en-US) | Multi-language | Delta |
|---|---|---|---|
| p50 latency | 13.4ms | 7.9ms | -5.5ms |
| p95 latency | 410.1ms | 413.8ms | +3.7ms |
| Max latency | 1918.5ms | 2527.9ms | +609.4ms |
| Batch confidence | 0.983-0.992 | — | — |
| Cost per hour | $0.96 | $0.96 | $0.00 |

Performance is essentially identical. Multi-language has a slightly higher max latency (one outlier), but median and p95 are comparable.

## Rationale

Despite multi-language performing well, we choose fixed-per-tenant because:

1. **Predictability**: Fixed language avoids rare misdetection where the recognizer might briefly classify English with an accent as another language, causing transcription artifacts.

2. **Diarization compatibility**: If Google adds streaming diarization support in the future, fixed-language recognizers are more likely to support it first (diarization already doesn't work with multi-language recognizers at recognizer creation time).

3. **Simplicity**: One recognizer resource per language, rather than managing language combinations.

4. **Tenant control**: Tenants know their meeting language in advance. Auto-detection adds complexity without clear user value for the onboarding use case (structured 1:1 meetings).

5. **Escape hatch**: The `preferred_stt_language` field can be changed to a multi-language configuration later if user research reveals demand, with no architectural changes required.

## Consequences

- Tenant data model needs `preferred_stt_language: str` field (default `"en-US"`) — addressed in a future story
- One recognizer resource per supported language must be pre-created in GCP
- Tenants conducting meetings in non-English languages need to update their language preference
- If a meeting switches languages mid-stream, the transcription quality for the non-primary language will degrade

## Alternatives Considered

### Auto-detect per session
- **Pros**: Zero configuration, handles multilingual meetings
- **Cons**: Slightly higher max latency outliers, potential misdetection artifacts, cannot use diarization at recognizer level
- **Why rejected**: Onboarding meetings are structured 1:1 conversations in a known language; auto-detection adds risk without value

### Per-session language selection
- **Pros**: Fine-grained control per meeting
- **Cons**: Adds UI complexity for the meeting host; most tenants will use the same language every time
- **Why rejected**: Premature optimization; `preferred_stt_language` at tenant level covers 95%+ of cases
