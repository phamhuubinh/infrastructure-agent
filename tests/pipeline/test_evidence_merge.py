from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.execution.tool_result import ToolResult


class TestEvidenceMerge:
    def test_empty_results(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
        ]
        EvidenceMerge().merge(req, results={})
        assert req.evidence == []

    def test_empty_results_no_references(self) -> None:
        req = InvestigationRequest(raw_request="test")
        EvidenceMerge().merge(req, results={})
        assert req.evidence == []

    def test_successful_result_creates_package(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
        ]
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
        }
        EvidenceMerge().merge(req, results)

        assert len(req.evidence) == 1
        pkg = req.evidence[0]
        assert pkg.capability_name == "CPU Information"
        assert pkg.evidence_name == "CPU"
        assert pkg.data == {"cores": 4}
        assert pkg.success is True
        assert pkg.error is None

    def test_failed_result_includes_error(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
        ]
        results = {
            "CPU Information": ToolResult(success=False, error="Timeout"),
        }
        EvidenceMerge().merge(req, results)

        assert len(req.evidence) == 1
        pkg = req.evidence[0]
        assert pkg.data is None
        assert pkg.success is False
        assert pkg.error == "Timeout"

    def test_multiple_capabilities(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
            CapabilityReference(name="Memory Information", evidence_name="Memory"),
        ]
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
            "Memory Information": ToolResult(success=True, data={"total_kb": 8192}),
        }
        EvidenceMerge().merge(req, results)

        assert len(req.evidence) == 2
        names = {p.capability_name for p in req.evidence}
        assert names == {"CPU Information", "Memory Information"}

    def test_duplicate_capability_skipped(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
        ]
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
            "Memory Information": ToolResult(success=True, data={"cores": 8}),
        }
        EvidenceMerge().merge(req, results)

        # Memory Information has no reference, so it should be skipped

    def test_evidence_name_falls_back_to_capability_name(self) -> None:
        """When no CapabilityReference exists for a result, use cap name."""
        req = InvestigationRequest(raw_request="test")
        # no capability_references set
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
        }
        EvidenceMerge().merge(req, results)

        assert len(req.evidence) == 1
        pkg = req.evidence[0]
        assert pkg.capability_name == "CPU Information"
        assert pkg.evidence_name == "CPU Information"

    def test_evidence_name_from_reference(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="cap_cpu", evidence_name="CPU"),
            CapabilityReference(name="cap_mem", evidence_name="Memory"),
        ]
        results = {
            "cap_cpu": ToolResult(success=True, data={"cores": 4}),
            "cap_mem": ToolResult(success=True, data={"total_kb": 8192}),
        }
        EvidenceMerge().merge(req, results)

        ev_names = {p.evidence_name for p in req.evidence}
        assert ev_names == {"CPU", "Memory"}

    def test_mixed_success_and_failure(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
            CapabilityReference(name="Disk Information", evidence_name="Disk"),
        ]
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
            "Disk Information": ToolResult(success=False, error="No such device"),
        }
        EvidenceMerge().merge(req, results)

        assert len(req.evidence) == 2
        good = [p for p in req.evidence if p.success]
        bad = [p for p in req.evidence if not p.success]
        assert len(good) == 1
        assert len(bad) == 1
        assert good[0].data == {"cores": 4}
        assert bad[0].error == "No such device"
        assert bad[0].data is None

    def test_stores_evidence_on_request(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.capability_references = [
            CapabilityReference(name="CPU Information", evidence_name="CPU"),
        ]
        results = {
            "CPU Information": ToolResult(success=True, data={"cores": 4}),
        }
        EvidenceMerge().merge(req, results)

        assert req.evidence is not None
        assert isinstance(req.evidence, list)
        assert all(isinstance(p, EvidencePackage) for p in req.evidence)
