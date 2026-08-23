from __future__ import annotations


from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact_normalizers import FactNormalizerRegistry
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus


class EvidenceMerge:
    """Normalize reviewed tool results into evidence packages.

    This boundary converts one trusted ToolResult into canonical evidence,
    preserving failure, partial-data, fact, and provenance semantics.

    Never performs planning, routing, assessment, or reasoning.
    """

    def __init__(
        self,
        normalizers: FactNormalizerRegistry | None = None,
        *,
        canonical_facts: bool = True,
        structured_command_result: bool = True,
    ) -> None:
        self._normalizers = normalizers or FactNormalizerRegistry()
        self._canonical_facts = canonical_facts
        self._structured_command_result = structured_command_result


    def package_from_result(
        self,
        *,
        capability_name: str,
        evidence_name: str,
        result: ToolResult,
        target: str,
        source_tool: str | None = None,
        timeframe: object | None = None,
    ) -> EvidencePackage:
        """Build one normal evidence receipt without an investigation plan.

        Runtime adapters that already have one reviewed ``ToolResult`` use
        this shared conversion so failure, partial-data, Fact, and provenance
        semantics remain identical to ordinary execution-engine collection.
        """

        status = result.capability_status or (
            CapabilityStatus.VALID
            if result.success
            else CapabilityStatus.COLLECTION_FAILED
        )
        is_valid = status in (CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY)
        actual_source_kind = result.source_kind or source_tool
        command_results = (
            result.command_results if self._structured_command_result else ()
        )
        return EvidencePackage(
            capability_name=capability_name,
            evidence_name=evidence_name,
            data=(
                result.data
                if is_valid or status is CapabilityStatus.PARTIAL
                else None
            ),
            success=is_valid,
            error=result.error if not is_valid else None,
            source_tool=actual_source_kind,
            status=status,
            command_results=command_results,
            warnings=result.warnings,
            produced_fact_names=result.produced_fact_names,
            collection_failures=(
                (result.error,)
                if result.error is not None and not is_valid
                else ()
            ),
            capability_error=result.capability_error,
            facts=(
                self._normalizers.normalize(
                    source_kind=actual_source_kind,
                    capability=capability_name,
                    resource=result.resource,
                    data=result.data,
                    status=status,
                    target=target,
                    command_results=command_results,
                    parameters=result.parameters,
                    produced_fact_names=result.produced_fact_names,
                    schema_version=result.schema_version,
                )
                if self._canonical_facts
                else ()
            ),
            source=result.source,
            resource=result.resource,
            parameters=result.parameters,
            timeframe=timeframe,
            schema_version=result.schema_version,
            recovery_attempts=result.recovery_attempts,
            recovered_by=result.recovered_by,
        )
