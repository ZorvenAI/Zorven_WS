"""Deterministic generator for a 45-minute two-speaker onboarding fixture.

Produces ~600-700 JSONL events spanning 0-2700s with compressed delay_ms
so FakeSTTAdapter replays complete in ~60-90 seconds. Stream rollover
boundaries at ~280s intervals exercise the dedup logic.

Usage: python tests/fixtures/gen_45min.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 42
DURATION_S = 2700.0
ROLLOVER_INTERVAL_S = 280.0
OUTPUT = Path(__file__).parent / "two_speaker_45min.jsonl"

INTERVIEWER_PHRASES = [
    "Tell me more about your company background.",
    "What year was the business founded?",
    "Who are your primary competitors in this space?",
    "How would you describe your brand personality?",
    "What makes your product unique compared to alternatives?",
    "Can you walk me through your target customer profile?",
    "What is your current marketing strategy?",
    "How do customers typically discover your brand?",
    "What are your top three business goals for the next year?",
    "Tell me about your pricing strategy.",
    "What channels do you use for customer acquisition?",
    "How do you measure brand awareness today?",
    "What does your competitive landscape look like?",
    "Can you describe your ideal customer journey?",
    "What are the biggest challenges your brand faces?",
    "How do you differentiate from your closest competitor?",
    "What is your brand mission statement?",
    "Tell me about your company values.",
    "Where do you see the brand in five years?",
    "What social media platforms are most effective for you?",
    "How do you handle customer feedback?",
    "What is your current monthly marketing budget?",
    "Tell me about your team structure.",
    "How do you onboard new customers?",
    "What does your sales funnel look like?",
]

RESPONDENT_PHRASES = [
    "We were founded in 2018 by two former tech executives.",
    "Our main product is a SaaS platform for small businesses.",
    "We currently serve about three thousand active customers.",
    "Our biggest competitor is Acme Corp, but we focus on a different niche.",
    "The brand personality is modern, approachable, and trustworthy.",
    "We price competitively at forty-nine dollars per month for the base plan.",
    "Most customers find us through organic search and word of mouth.",
    "Our target audience is small business owners aged 30 to 55.",
    "We spend about fifteen thousand dollars per month on marketing.",
    "The team is twenty people across engineering, sales, and support.",
    "We differentiate by offering personalized onboarding for every client.",
    "Our mission is to make technology accessible for small businesses.",
    "We value transparency, innovation, and customer success above all.",
    "In five years we want to be the leading platform in our vertical.",
    "Instagram and LinkedIn are our most effective channels.",
    "We do quarterly NPS surveys and weekly support ticket analysis.",
    "Customer acquisition cost is around one hundred twenty dollars.",
    "Our retention rate is about ninety-two percent annually.",
    "We launched a referral program that drives thirty percent of new signups.",
    "The biggest challenge is scaling support while maintaining quality.",
    "We recently expanded into three new regional markets.",
    "Our average deal size is about five hundred dollars annually.",
    "We use a combination of content marketing and paid search.",
    "Our customer lifetime value is roughly two thousand dollars.",
    "We have partnerships with several industry associations.",
]


def _partial_text(full: str, frac: float) -> str:
    words = full.split()
    n = max(1, int(len(words) * frac))
    return " ".join(words[:n]).lower().rstrip(".,!?")


def generate() -> list[dict]:
    rng = random.Random(SEED)
    events: list[dict] = []
    t = 0.0
    speaker = 0

    while t < DURATION_S:
        if speaker == 0:
            phrase = rng.choice(INTERVIEWER_PHRASES)
        else:
            phrase = rng.choice(RESPONDENT_PHRASES)

        phrase_duration = rng.uniform(2.0, 6.0)
        t_start = round(t, 1)
        t_end = round(t + phrase_duration, 1)

        events.append(
            {
                "text": _partial_text(phrase, 0.3),
                "is_final": False,
                "t_start": t_start,
                "t_end": round(t_start + phrase_duration * 0.3, 1),
                "stability": round(rng.uniform(0.4, 0.7), 1),
                "delay_ms": rng.randint(1, 3),
            }
        )

        events.append(
            {
                "text": _partial_text(phrase, 0.6),
                "is_final": False,
                "t_start": t_start,
                "t_end": round(t_start + phrase_duration * 0.6, 1),
                "stability": round(rng.uniform(0.6, 0.8), 1),
                "delay_ms": rng.randint(1, 3),
            }
        )

        events.append(
            {
                "text": phrase,
                "is_final": True,
                "t_start": t_start,
                "t_end": t_end,
                "stability": 1.0,
                "delay_ms": rng.randint(1, 3),
            }
        )

        pause = rng.uniform(1.0, 4.0)
        t = t_end + pause

        if rng.random() < 0.4:
            speaker = 1 - speaker

    return events


def main() -> None:
    events = generate()
    with open(OUTPUT, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    finals = [e for e in events if e["is_final"]]
    max_t = max(e["t_end"] for e in events)
    rollovers = int(max_t / ROLLOVER_INTERVAL_S)
    print(
        f"Generated {len(events)} events "
        f"({len(finals)} finals, {len(events) - len(finals)} partials), "
        f"spanning {max_t:.1f}s, "
        f"~{rollovers} stream rollovers"
    )


if __name__ == "__main__":
    main()
