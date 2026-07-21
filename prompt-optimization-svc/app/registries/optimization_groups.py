"""Optimization group definitions per §4.2.

Groups define sets of prompts that are optimized jointly so they
evolve together and avoid local optima.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizationGroup:
    """A named group of prompts optimized jointly."""

    name: str
    prompt_names: tuple[str, ...]
    agent_codes: tuple[str, ...]
    workflow: int
    description: str = ""


# §4.2 Optimization Groups
OPTIMIZATION_GROUPS: dict[str, OptimizationGroup] = {
    "wf3-creative-pipeline": OptimizationGroup(
        name="wf3-creative-pipeline",
        prompt_names=(
            "zorven-wf3-caa-blueprint",
            "zorven-wf3-caa-blueprint-synthesis",
            "zorven-wf3-cga-copywriting",
            "zorven-wf3-cga-compliance",
            "zorven-wf3-cga-creative-director",
            "zorven-wf3-adpub-publishing",
        ),
        agent_codes=("caa", "cga", "adpub"),
        workflow=3,
        description=(
            "Campaign architecture + creative generation + ad publishing "
            "optimized jointly for coherent Meta Ads campaigns"
        ),
    ),
    "wf3-optimization-loop": OptimizationGroup(
        name="wf3-optimization-loop",
        prompt_names=(
            "zorven-wf3-coa-recommendation",
            "zorven-wf3-coa-reporter",
            "zorven-wf3-ila-extraction",
        ),
        agent_codes=("coa", "ila"),
        workflow=3,
        description=(
            "Campaign optimization + intelligence loop optimized "
            "jointly for continuous improvement feedback"
        ),
    ),
    "wf1-discovery-pipeline": OptimizationGroup(
        name="wf1-discovery-pipeline",
        prompt_names=(
            "zorven-wf1-mra-planning",
            "zorven-wf1-mra-synthesis",
            "zorven-wf1-cia-planning",
            "zorven-wf1-cia-benchmarking",
            "zorven-wf1-apa-planning",
            "zorven-wf1-apa-synthesis",
            "zorven-wf1-tcia-scoring",
            "zorven-wf1-tcia-report-synthesis",
            "zorven-wf1-voca-sentiment-analysis",
            "zorven-wf1-voca-synthesis",
        ),
        agent_codes=("mra", "cia", "apa", "tcia", "voca"),
        workflow=1,
        description="WF1 brand discovery agents optimized together",
    ),
    "wf2-brand-strategy-pipeline": OptimizationGroup(
        name="wf2-brand-strategy-pipeline",
        prompt_names=(
            "zorven-wf2-bpa-positioning",
            "zorven-wf2-baa-hierarchy",
            "zorven-wf2-bpv-personality",
            "zorven-wf2-nta-naming",
            "zorven-wf2-nta-tagline",
            "zorven-wf2-bsa-narrative",
            "zorven-wf2-bsa-origin",
        ),
        agent_codes=("bpa", "baa", "bpv", "nta", "bsa"),
        workflow=2,
        description="WF2 brand strategy agents optimized together",
    ),
}


def get_group(name: str) -> OptimizationGroup:
    """Get an optimization group by name. Raises KeyError if not found."""
    if name not in OPTIMIZATION_GROUPS:
        raise KeyError(
            f"Unknown optimization group '{name}'. "
            f"Valid groups: {', '.join(OPTIMIZATION_GROUPS.keys())}"
        )
    return OPTIMIZATION_GROUPS[name]
