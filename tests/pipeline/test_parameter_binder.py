from __future__ import annotations

from unittest import mock

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_graph import ExecutionGraph, ExecutionNode
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_runtime import ExecutionRuntime
from src.pipeline.parameter_binder import MissingParameterError, ParameterBinder
from src.pipeline.parameter_extractor import ExtractedParams
from src.pipeline.time_range_resolver import TimeRangeResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


def _route(name: str, params: ExtractedParams):
    router = CapabilityRouter()
    router.build_routes(KnowledgeTool())
    routed = router.resolve_with_metadata(name, params)
    assert routed is not None
    return routed


def test_specific_service_binds_to_get_service_name() -> None:
    params = ExtractedParams(service_name="nginx")
    ((source, resource), metadata) = _route("Service Status", params)

    bound = ParameterBinder().bind(
        source=source,
        resource=resource,
        metadata=metadata,
        extracted_params=params,
    )

    assert resource == "get_service"
    assert bound.arguments["name"] == "nginx"


def test_ping_path_port_and_timeframe_bind_from_metadata() -> None:
    ping = ExtractedParams(ping_target="example.com")
    ((source, resource), metadata) = _route("Network Latency", ping)
    bound = ParameterBinder().bind(
        source=source,
        resource=resource,
        metadata=metadata,
        extracted_params=ping,
    )
    assert bound.arguments["target"] == "example.com"

    path_params = ExtractedParams(path="/var/log")
    ((source, resource), metadata) = _route("Storage Information", path_params)
    bound = ParameterBinder().bind(
        source=source,
        resource=resource,
        metadata=metadata,
        extracted_params=path_params,
    )
    assert bound.arguments["path"] == "/var/log"

    port_params = ExtractedParams(port="443")
    ((source, resource), metadata) = _route("Port Discovery", port_params)
    bound = ParameterBinder().bind(
        source=source,
        resource=resource,
        metadata=metadata,
        extracted_params=port_params,
    )
    assert bound.arguments["port"] == 443

    log_params = ExtractedParams(service_name="nginx", time_range="7d")
    ((source, resource), metadata) = _route("Service Log Discovery", log_params)
    timeframe = TimeRangeResolver().resolve("nginx logs 7 ngày", now=2_000_000_000)
    bound = ParameterBinder().bind(
        source=source,
        resource=resource,
        metadata=metadata,
        extracted_params=log_params,
        timeframe=timeframe,
    )
    assert bound.arguments["since"] < bound.arguments["until"]


def test_missing_required_parameter_fails_before_dispatch() -> None:
    params = ExtractedParams()
    ((source, resource), metadata) = _route("Network Latency", params)

    with pytest.raises(MissingParameterError, match="target"):
        ParameterBinder().bind(
            source=source,
            resource=resource,
            metadata=metadata,
            extracted_params=params,
        )


def test_runtime_dispatches_nginx_as_a_validated_name_argument() -> None:
    real_tool = KnowledgeTool()
    router = CapabilityRouter()
    router.build_routes(real_tool)
    dispatch = mock.Mock(spec=KnowledgeTool)
    dispatch.execute.return_value = ToolResult(success=True, data={"active": "active"})
    runtime = ExecutionRuntime(dispatch, router=router)
    step = ExecutionStep(CapabilityReference("Service Status", "Service Status"))
    graph = ExecutionGraph(nodes=(ExecutionNode(step),))

    runtime.execute(graph, extracted_params=ExtractedParams(service_name="nginx"))

    dispatch.execute.assert_called_once_with(
        {"source": "localhost", "resource": "get_service", "name": "nginx"}
    )
