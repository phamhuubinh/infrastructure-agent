from __future__ import annotations

import json
from datetime import datetime, timezone

from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance, claim_source_links

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def test_provenance_serialization_redacts_secret_query_and_is_traceable() -> None:
    provenance = Provenance(
        source="grafana",
        capability="query",
        target="server-1",
        observed_at=NOW,
        source_reference="https://grafana.example/d/node?token=secret&from=1",
    )
    fact = Fact(
        "system",
        "cpu.usage",
        42,
        "percent",
        NOW,
        NOW,
        "grafana",
        "server-1",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )

    serialized = json.dumps(fact.to_dict())
    links = claim_source_links((fact,))
    assert "secret" not in serialized
    assert links[0].provenance_id == provenance.id
    assert links[0].href is not None


def test_relative_source_reference_uses_configured_base_only() -> None:
    provenance = Provenance("grafana", "dashboards", "grafana", NOW, "/d/abc")
    fact = Fact(
        "dashboard:abc",
        "monitoring.dashboard",
        {"title": "Node"},
        "record",
        NOW,
        NOW,
        "grafana",
        "grafana",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )

    assert claim_source_links((fact,))[0].href is None
    assert (
        claim_source_links((fact,), base_urls={"grafana": "https://grafana.example"})[
            0
        ].href
        == "https://grafana.example/d/abc"
    )


def test_parameter_secrets_are_redacted_before_identity_and_serialization() -> None:
    provenance = Provenance(
        "grafana",
        "query",
        "server-1",
        NOW,
        parameters=(
            ("token", "outer-secret"),
            ("filters", {"api_key": "nested-secret", "region": "apac"}),
        ),
    )

    serialized = json.dumps(provenance.to_dict())

    assert "outer-secret" not in serialized
    assert "nested-secret" not in serialized
    assert "apac" in serialized
