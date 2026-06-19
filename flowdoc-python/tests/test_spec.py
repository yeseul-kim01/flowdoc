"""Unit tests for spec serialization."""

from __future__ import annotations

from flowdoc.spec import (
    Auto,
    Edge,
    Location,
    Node,
    Param,
    Returns,
    Sequence,
    Source,
    Spec,
    spec_to_dict,
    spec_to_json,
)
import json


def _minimal_spec() -> Spec:
    return Spec(
        source=Source(),
        nodes=[
            Node(
                id="app.api#greet(str)",
                simpleName="greet",
                owner="api",
                kind="method",
                location=Location(file="app/api.py", line=10),
                auto=Auto(
                    params=[Param(name="name", type="str")],
                    returns=Returns(type="str"),
                    annotations=[],
                ),
            )
        ],
        edges=[
            Edge(
                from_id="app.api#greet(str)",
                to_id="app.utils#helper()",
                callType="sync",
                site=Location(file="app/api.py", line=12),
                resolution="concrete",
            )
        ],
        sequences=[Sequence(tag="greet", entry="app.api#greet(str)")],
        guards=[],
        traces=[],
    )


def test_spec_to_dict_top_level_keys() -> None:
    """Serialized dict has all required top-level keys."""
    d = spec_to_dict(_minimal_spec())
    assert d["flowdoc"] == "0.1"
    assert "source" in d
    assert "nodes" in d
    assert "edges" in d
    assert "sequences" in d
    assert "guards" in d
    assert "traces" in d


def test_edge_uses_from_to_wire_names() -> None:
    """Edge dict uses 'from'/'to' (not 'from_id'/'to_id')."""
    d = spec_to_dict(_minimal_spec())
    edge = d["edges"][0]
    assert "from" in edge
    assert "to" in edge
    assert "from_id" not in edge
    assert "to_id" not in edge


def test_spec_to_json_is_valid() -> None:
    """spec_to_json produces parseable JSON."""
    s = spec_to_json(_minimal_spec())
    parsed = json.loads(s)
    assert parsed["flowdoc"] == "0.1"


def test_none_fields_omitted() -> None:
    """None-valued fields (e.g. missing returns) are omitted from the dict."""
    spec = _minimal_spec()
    spec.nodes[0].auto.returns = None
    d = spec_to_dict(spec)
    node = d["nodes"][0]
    assert "returns" not in node.get("auto", {})
