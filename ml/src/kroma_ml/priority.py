from dataclasses import dataclass


@dataclass(frozen=True)
class ThreatInputs:
    wind: float
    fuel: float
    dryness: float
    slope: float
    growth: float


@dataclass(frozen=True)
class PriorityInputs:
    confidence: float
    threat: float
    exposure: float
    accessibility: float
    freshness: float


def _validate(values: tuple[float, ...]) -> None:
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError("all components must be finite and between 0 and 1")


def threat_score(inputs: ThreatInputs) -> dict[str, float]:
    components = {
        "wind": inputs.wind,
        "fuel": inputs.fuel,
        "dryness": inputs.dryness,
        "slope": inputs.slope,
        "growth": inputs.growth,
    }
    _validate(tuple(components.values()))
    weights = {"wind": 0.25, "fuel": 0.25, "dryness": 0.2, "slope": 0.1, "growth": 0.2}
    return {
        "score": round(sum(components[name] * weight for name, weight in weights.items()), 4),
        **{name: round(components[name] * weight, 4) for name, weight in weights.items()},
    }


def priority_score(inputs: PriorityInputs) -> dict[str, float]:
    components = {
        "confidence": inputs.confidence,
        "threat": inputs.threat,
        "exposure": inputs.exposure,
        "accessibility": inputs.accessibility,
        "freshness": inputs.freshness,
    }
    _validate(tuple(components.values()))
    weights = {
        "confidence": 0.25,
        "threat": 0.3,
        "exposure": 0.25,
        "accessibility": 0.1,
        "freshness": 0.1,
    }
    contributions = {
        name: round(100 * components[name] * weight, 2) for name, weight in weights.items()
    }
    return {"score": round(sum(contributions.values()), 2), **contributions}
