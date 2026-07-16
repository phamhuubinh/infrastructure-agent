from __future__ import annotations

from src.pipeline.evidence_package import EvidencePackage


class TestEvidencePackage:
    def test_defaults(self) -> None:
        pkg = EvidencePackage(capability_name="CPU", evidence_name="CPU Info")
        assert pkg.capability_name == "CPU"
        assert pkg.evidence_name == "CPU Info"
        assert pkg.data is None
        assert pkg.success is True
        assert pkg.error is None

    def test_successful_package(self) -> None:
        pkg = EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU",
            data={"cores": 4},
            success=True,
        )
        assert pkg.data == {"cores": 4}
        assert pkg.success is True
        assert pkg.error is None

    def test_failed_package(self) -> None:
        pkg = EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU",
            data=None,
            success=False,
            error="Connection refused",
        )
        assert pkg.data is None
        assert pkg.success is False
        assert pkg.error == "Connection refused"

    def test_is_frozen(self) -> None:
        pkg = EvidencePackage(capability_name="A", evidence_name="B")
        try:
            pkg.capability_name = "C"  # type: ignore[misc]
            assert False, "should have raised"
        except AttributeError:
            pass

    def test_str_representation(self) -> None:
        pkg = EvidencePackage(capability_name="Services", evidence_name="System")
        s = repr(pkg)
        assert "Services" in s
        assert "System" in s
        assert "EvidencePackage" in s

    def test_two_packages_equal_when_values_match(self) -> None:
        a = EvidencePackage(capability_name="CPU", evidence_name="CPU", data={"x": 1})
        b = EvidencePackage(capability_name="CPU", evidence_name="CPU", data={"x": 1})
        assert a == b

    def test_not_hashable_when_data_is_dict(self) -> None:
        pkg = EvidencePackage(capability_name="CPU", evidence_name="CPU", data={"x": 1})
        try:
            hash(pkg)
            assert False, "should have raised"
        except TypeError:
            pass
