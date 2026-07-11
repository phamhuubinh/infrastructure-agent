from __future__ import annotations

from src.shared.discovery.observation import Observation


def extract_known_facts(observations: tuple[Observation, ...]) -> dict[str, object]:
    """
    Deterministically extract Known Facts from Observations.

    Known Facts are small, flat, reasoning-friendly summaries.
    They NEVER contain raw API payloads, large lists, or nested objects.

    This component does NOT:
    - perform reasoning
    - evaluate quality
    - recommend actions
    - infer intent
    """
    facts: dict[str, object] = {}
    for obs in observations:
        if not obs.success or obs.data is None:
            continue
        key = f"{obs.tool}:{obs.arguments.get('source', '')}:{obs.arguments.get('resource', obs.arguments.get('action', ''))}"
        raw = obs.data
        if isinstance(raw, dict):
            flat: dict[str, object] = {}
            for k, v in raw.items():
                if isinstance(v, (str, int, float, bool)):
                    flat[k] = v
                elif isinstance(v, list):
                    flat[f"{k}_count"] = len(v)
                elif isinstance(v, dict):
                    if len(str(v)) < 300:
                        flat[k] = v
                    else:
                        flat[f"{k}_summary"] = str(list(v.keys())[:5])
            facts[key] = flat
        elif isinstance(raw, list):
            facts[key] = {"count": len(raw)}
        else:
            facts[key] = {"value": str(raw)[:200]}
    return facts
