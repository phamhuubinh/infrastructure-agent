from __future__ import annotations

from src.pipeline.parameter_extractor import ExtractedParams, ParameterExtractor


def test_extract_service_nginx() -> None:
    pe = ParameterExtractor()
    params = pe.extract("kiểm tra service nginx")
    assert params.service_name == "nginx"


def test_extract_service_dich_vu() -> None:
    pe = ParameterExtractor()
    params = pe.extract("xem dịch vụ postgresql")
    assert params.service_name == "postgresql"


def test_extract_service_inline() -> None:
    pe = ParameterExtractor()
    params = pe.extract("nginx có chạy không")
    assert params.service_name == "nginx"


def test_extract_port() -> None:
    pe = ParameterExtractor()
    params = pe.extract("kiểm tra port 8080")
    assert params.port == "8080"


def test_extract_bare_port() -> None:
    pe = ParameterExtractor()
    params = pe.extract("on port 443")
    assert params.port == "443"


def test_extract_process() -> None:
    pe = ParameterExtractor()
    params = pe.extract("tiến trình kworker có vấn đề")
    assert params.process_name == "kworker"


def test_extract_path() -> None:
    pe = ParameterExtractor()
    params = pe.extract("kiểm tra /var/log/syslog")
    assert params.path == "/var/log/syslog"


def test_extract_time_range_hours() -> None:
    pe = ParameterExtractor()
    params = pe.extract("CPU 1 giờ qua")
    assert params.time_range == "1h"


def test_extract_time_range_today() -> None:
    pe = ParameterExtractor()
    params = pe.extract("memory hôm nay")
    assert params.time_range == "today"


def test_extract_time_range_days() -> None:
    pe = ParameterExtractor()
    params = pe.extract("disk 7 ngày")
    assert params.time_range == "7d"


def test_extract_no_params() -> None:
    pe = ParameterExtractor()
    params = pe.extract("cho tôi xem CPU")
    assert params.service_name is None
    assert params.port is None
    assert params.process_name is None
    assert params.path is None
    assert params.time_range is None


def test_extracted_params_bool() -> None:
    assert bool(ExtractedParams()) is False
    assert bool(ExtractedParams(service_name="nginx")) is True


def test_extracted_params_to_dict() -> None:
    p = ExtractedParams(service_name="nginx", port="80")
    d = p.to_dict()
    assert d == {"service_name": "nginx", "port": "80"}
