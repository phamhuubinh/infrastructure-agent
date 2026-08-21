from __future__ import annotations

from dataclasses import replace

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact_normalizers import FactNormalizerRegistry
from src.pipeline.fact_reconciler import FactReconciler, MetricTolerance
from src.pipeline.fact_set import FactSet
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus


class EvidenceMerge:
    """Merge collected evidence into normalized EvidencePackages.

    Responsibilities:
    - combine individual capability results
    - normalize results into EvidencePackage objects
    - detect missing or failed evidence
    - store merged evidence on the InvestigationRequest

    Never performs assessment or reasoning.
    """

    def __init__(
        self,
        normalizers: FactNormalizerRegistry | None = None,
        reconciler: FactReconciler | None = None,
        *,
        canonical_facts: bool = True,
        structured_command_result: bool = True,
    ) -> None:
        self._normalizers = normalizers or FactNormalizerRegistry()
        self._reconciler = reconciler or FactReconciler(
            tolerances={
                "cpu.usage": MetricTolerance(absolute=5.0),
                "memory.usage": MetricTolerance(absolute=2.0),
                "filesystem.usage": MetricTolerance(absolute=1.0),
                "network.latency": MetricTolerance(relative=0.1),
            }
        )
        self._canonical_facts = canonical_facts
        self._structured_command_result = structured_command_result

    def merge(
        self,
        request: InvestigationRequest,
        results: dict[str, ToolResult],
        source_tool: str | None = None,
    ) -> None:
        """Merge capability results into normalized evidence packages.

        Each ToolResult is wrapped in an EvidencePackage with the
        capability name and evidence name preserved.

        Failed results are included with success=False and error set.
        Normalization of data content is minimal — raw tool output
        is preserved for assessment consumption.

        Args:
            request: The InvestigationRequest with capability_references
                     populated. Mutates evidence.
            results: Raw capability_name → ToolResult mapping from Runtime.
        """
        packages: list[EvidencePackage] = []
        seen: set[str] = set()

        # Build evidence name lookup from capability references.
        ev_name_by_cap: dict[str, str] = {}
        for ref in request.capability_references:
            ev_name_by_cap[ref.name] = ref.evidence_name

        for cap_name, result in results.items():
            if cap_name in seen:
                continue
            seen.add(cap_name)

            # Explicit source-comparison nodes are suffixed at runtime solely
            # to keep their ToolResults distinct.  They still fulfill the
            # original evidence requirement and keep their own source receipt.
            base_capability = cap_name.partition("::")[0]
            ev_name = ev_name_by_cap.get(base_capability, cap_name)
            packages.append(
                self.package_from_result(
                    capability_name=cap_name,
                    evidence_name=ev_name,
                    result=result,
                    target=request.target or result.source or "localhost",
                    source_tool=source_tool,
                    timeframe=getattr(request.request_frame, "timeframe", None),
                )
            )

        request.evidence = packages
        self.rebuild_fact_set(request)

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

    def rebuild_fact_set(self, request: InvestigationRequest) -> None:
        """Reconcile all packages after cached and newly collected evidence merge."""

        fact_set = FactSet.merge(*(package.facts for package in request.evidence))
        reconciliation = self._reconciler.reconcile(fact_set)
        reconciled_by_id = {fact.id: fact for fact in reconciliation.fact_set}
        request.evidence = [
            replace(
                package,
                facts=tuple(
                    reconciled_by_id.get(fact.id, fact) for fact in package.facts
                ),
            )
            for package in request.evidence
        ]
        request.fact_set = reconciliation.fact_set
        request.contradictions = reconciliation.contradictions
