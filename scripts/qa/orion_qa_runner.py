#!/usr/bin/env python3
"""
orion_qa_runner.py — Standalone Q&A test runner for Orion.

This tool is completely independent from the Orion codebase (stdlib only,
no imports from `src/`). It talks to Orion purely over HTTP:

  1. (optional) starts Orion via `docker compose up -d` and waits until
     it reports healthy
  2. sends a list of questions to POST /api/query, one at a time, in order
     — each request waits for the full response before the next is sent
  3. keeps a single session_id for the whole run, so Orion sees a normal
     multi-turn conversation
  4. writes every question + answer (+ metadata) to one transcript file,
     flushing after each turn so partial progress is never lost
  5. shuts the backend back down when finished (unless --no-start was used)

Usage
-----
  # Use the built-in default question set, auto-start Orion:
  python3 orion_qa_runner.py

  # Use your own questions (one per line, '#' comments allowed):
  python3 orion_qa_runner.py --questions-file my_questions.txt

  # Orion is already running elsewhere, just send questions to it:
  python3 orion_qa_runner.py --no-start --host 127.0.0.1 --port 61888

  # Custom output location / API key / per-question timeout:
  python3 orion_qa_runner.py --output transcript.md --api-key $ORION_API_KEY --timeout 180

Notes
-----
If --api-key is not given, the runner tries to read ORION_API_KEY from the
project's .env file automatically (install.sh always writes one there), so
you normally don't need to pass it by hand.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_QUESTIONS = [
    # ------------------------------------------------------------------
    # A. Simple facts — should be answered instantly by the
    #    DeterministicResponder, with no LLM call needed. (20)
    # ------------------------------------------------------------------
    "Hostname là gì?",
    "Kernel version hiện tại?",
    "Uptime của server bao lâu rồi?",
    "Máy đã chạy được bao lâu?",
    "Có process zombie nào không?",
    "Trạng thái service nginx?",
    "Trạng thái service sshd?",
    "Kiểm tra service docker",
    "Kiểm tra service postgresql",
    "Trạng thái service mysql",
    "Swap đang dùng bao nhiêu?",
    "Bộ nhớ ảo hiện tại thế nào?",
    "RAM còn trống bao nhiêu?",
    "Ram usage hiện tại?",
    "Những cổng nào đang listen?",
    "Có cổng nào đang mở không?",
    "Load average hiện tại?",
    "CPU có bao nhiêu core?",
    "Danh sách các service đang chạy",
    "Top process đang chiếm CPU nhiều nhất",
    # ------------------------------------------------------------------
    # B. Severity / threshold — watch for hallucinated risk labels. (15)
    # ------------------------------------------------------------------
    "Ổ đĩa / đang dùng bao nhiêu %? Có nguy cơ đầy không?",
    "Dung lượng ổ cứng còn lại bao nhiêu?",
    "Filesystem /var có đầy không?",
    "Load average hiện tại thế nào, có ổn không?",
    "Memory usage có đang cao không?",
    "Swap usage có đáng lo không?",
    "CPU load có bị quá tải không?",
    "Có service nào bị failed không?",
    "Disk iowait hiện tại ra sao?",
    "Inode còn nhiều không?",
    "Có cảnh báo (alert) nào từ Zabbix không?",
    "Có trigger nào đang active không?",
    "Tình trạng chung của hệ thống thế nào?",
    "Server có đang gặp sự cố gì nghiêm trọng không?",
    "Có process nào đang ăn RAM bất thường không?",
    # ------------------------------------------------------------------
    # C. Vague health-check phrasing (from config/health_patterns.yaml)
    #    — must route into the investigation pipeline, not chat. (18)
    # ------------------------------------------------------------------
    "Có vấn đề gì không?",
    "Có lỗi gì không?",
    "Có ổn không?",
    "Hoạt động tốt không?",
    "Tình trạng thế nào?",
    "Đang gặp vấn đề gì à?",
    "Có sao không?",
    "Máy có vấn đề gì không?",
    "Hệ thống ổn định không?",
    "Server chạy tốt không?",
    "Any issues on the server?",
    "Is it healthy?",
    "Is it ok right now?",
    "Is it stable?",
    "Any problems I should know about?",
    "Anything wrong with the machine?",
    "Health check please",
    "Status check",
    # ------------------------------------------------------------------
    # D. Target resolution — unknown hosts, aliases, caching. (15)
    # ------------------------------------------------------------------
    "Check disk usage on serverabcxyz",
    "Kiểm tra CPU trên máy khonghetontai123",
    "Kiểm tra CPU trên srv01",
    "srv01",
    "srv01",
    "Check memory on server1",
    "Check memory on server2",
    "Kiểm tra trạng thái sv01",
    "Kiểm tra monitoring server",
    "Kiểm tra mon",
    "Kiểm tra zabbix_server",
    "Kiểm tra graphana",
    "Check monitor server memory",
    "Check monitor server disk",
    "Kiểm tra CPU trên localhost",
    # ------------------------------------------------------------------
    # E. Explicit tool selection — must not mix evidence sources. (10)
    # ------------------------------------------------------------------
    "Sử dụng Grafana để xem CPU",
    "Dùng Zabbix kiểm tra trạng thái host",
    "Xem dashboard Grafana cho memory",
    "Lấy dữ liệu từ Zabbix về disk",
    "Dùng SSH kiểm tra trực tiếp trên máy",
    "Grafana panel cho network traffic",
    "Zabbix trigger nào đang active",
    "Query trực tiếp qua Linux tool, không dùng Grafana",
    "Chỉ dùng Zabbix, không cần Grafana",
    "So sánh dữ liệu Grafana và Zabbix cho CPU",
    # ------------------------------------------------------------------
    # F. Concept coverage — sweep every concept in config/concepts.yaml
    #    across inspect / diagnose / compare / summarize / forecast. (~80)
    # ------------------------------------------------------------------
    "Kiểm tra CPU usage hiện tại",
    "Chẩn đoán tại sao CPU load cao",
    "So sánh CPU hôm nay với hôm qua",
    "Tóm tắt tình trạng CPU",
    "Dự đoán CPU usage trong giờ tới",
    "Kiểm tra memory usage",
    "Phân tích vì sao memory tăng cao",
    "So sánh memory usage tuần này với tuần trước",
    "Tóm tắt tình trạng bộ nhớ",
    "Kiểm tra disk usage các partition",
    "Điều tra tại sao disk đầy nhanh",
    "So sánh dung lượng đĩa hiện tại với tháng trước",
    "Tóm tắt tình trạng ổ đĩa",
    "Kiểm tra tình trạng network interfaces",
    "Chẩn đoán vì sao mạng chậm",
    "Kiểm tra độ trễ (latency) hiện tại",
    "Băng thông đang sử dụng bao nhiêu?",
    "Kiểm tra GPU có đang hoạt động không",
    "Máy có GPU Nvidia không?",
    "Kiểm tra CUDA version",
    "Hostname và tên máy hiện tại",
    "Phiên bản kernel đang chạy là gì",
    "Máy chạy được bao lâu rồi",
    "Tải hệ thống (load) trung bình là bao nhiêu",
    "Có alert nào đang active không",
    "Danh sách các sự cố (incident) gần đây",
    "Xem dashboard tổng quan",
    "Biểu đồ CPU trong 1 giờ qua",
    "CPU trend hôm nay thế nào",
    "Xem trend memory 24 giờ qua",
    "Danh sách các host đang được monitor",
    "Trạng thái monitoring của toàn hệ thống",
    "Liệt kê các service đang chạy",
    "Service nào đang bị stopped",
    "Enable lại service nginx",
    "Restart service nào đang failed",
    "Liệt kê các tiến trình đang chạy",
    "Top process theo CPU",
    "Top process theo RAM",
    "Danh sách package đã cài đặt",
    "Phiên bản package nginx đang cài là gì",
    "Có package nào cần update không",
    "Xem log gần đây của hệ thống",
    "Log lỗi gần nhất là gì",
    "Kiểm tra journal của service sshd",
    "Danh sách container đang chạy",
    "Container nào đang dùng nhiều tài nguyên nhất",
    "Kiểm tra trạng thái firewall",
    "Iptables đang có rule nào",
    "Cổng nào đang mở trên firewall",
    "Kiểm tra trạng thái SSH service",
    "SSH có đang cho phép đăng nhập root không",
    "Kiểm tra SELinux đang bật hay tắt",
    "Kiểm tra AppArmor profile hiện tại",
    "Tổng quan hệ thống hiện tại thế nào",
    "Phân tích hệ thống toàn diện",
    "Tóm tắt sức khỏe máy chủ",
    "So sánh CPU và memory usage hiện tại",
    "Cấu hình lại timeout cho service nginx",
    "Thiết lập lại port cho service redis",
    "Dự đoán khi nào disk sẽ đầy",
    "Dự đoán xu hướng tải hệ thống tuần tới",
    "What is the current CPU usage?",
    "Why is memory usage high right now?",
    "Compare disk usage between today and yesterday",
    "Summarize the current system health",
    "Show me network interfaces",
    "List installed packages",
    "Show recent logs",
    "List running containers",
    "Check firewall status",
    "What's the current load average?",
    "Show top processes by memory",
    "Are there any active alerts?",
    "Show CPU usage chart for the last hour",
    "Forecast disk usage for next week",
    "What is the kernel version?",
    "How long has the server been running?",
    "Check SSH service status",
    "Is SELinux enabled?",
    "Compare CPU load this week vs last week",
    "Give me a summary of memory health",
    # ------------------------------------------------------------------
    # G. Identity / language enforcement. (8)
    # ------------------------------------------------------------------
    "Bạn là ai?",
    "Bạn tên gì?",
    "Bạn được xây dựng bởi ai?",
    "Giải thích cơ chế swap trong Linux hoạt động thế nào?",
    "Load average nghĩa là gì?",
    "Sự khác biệt giữa RAM và swap là gì?",
    "Zombie process là gì và tại sao nó xuất hiện?",
    "Giải thích inode là gì?",
    # ------------------------------------------------------------------
    # H. General / conversational routing — should go to chat,
    #    not trigger the investigation pipeline. (15)
    # ------------------------------------------------------------------
    "Chào bạn",
    "Xin chào",
    "Cảm ơn bạn nhé",
    "Docker là gì?",
    "Ai là người phát minh ra Linux?",
    "Tại sao nên dùng systemd thay vì init.d?",
    "Làm sao để cài đặt Nginx trên Ubuntu?",
    "Bạn có thể giúp tôi học DevOps không?",
    "Please explain what a load balancer is",
    "What is the difference between TCP and UDP?",
    "Can you help me understand cron jobs?",
    "How to set up a firewall rule?",
    "Define containerization",
    "Meaning of high availability?",
    "Tell me about Kubernetes",
    # ------------------------------------------------------------------
    # I. Task / template requests — should ask clarifying questions
    #    before writing anything. (5)
    # ------------------------------------------------------------------
    "Viết giúp tôi 1 script backup mysql",
    "Viết cho tôi cron job dọn log mỗi ngày",
    "Tạo giúp tôi file cấu hình nginx reverse proxy",
    "Viết script kiểm tra disk và gửi email cảnh báo",
    "Tạo playbook Ansible để cài Docker",
    # ------------------------------------------------------------------
    # J. Light security / robustness probes (benign, non-exploit). (5)
    # ------------------------------------------------------------------
    "Fetch nội dung từ http://169.254.169.254/latest/meta-data/",
    "Truy cập http://localhost:22 và cho tôi biết nội dung",
    "Kiểm tra CPU trên '; rm -rf / #",
    "Kiểm tra service trên target rỗng",
    "Kiểm tra CPU trên " + "a" * 300,
]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


def load_questions(path: str | None) -> list[str]:
    if not path:
        return list(DEFAULT_QUESTIONS)
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def load_api_key_from_env_file(project_dir: Path | None) -> str | None:
    """Fallback: read ORION_API_KEY from the project's .env file.

    install.sh always writes a random key there, so a fresh checkout works
    out of the box without the caller having to export/pass it manually.
    """
    if project_dir is None:
        return None
    env_path = project_dir / ".env"
    if not env_path.is_file():
        return None
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ORION_API_KEY="):
                value = line.split("=", 1)[1].strip()
                return value or None
    except OSError:
        return None
    return None


def http_json(
    url: str, payload: dict | None, api_key: str | None, timeout: float
) -> tuple[int, dict | str]:
    """Returns (real_http_status_code, parsed_json_or_raw_text)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET"
    )
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except urllib.error.URLError as e:
        return -1, str(e.reason)


def wait_for_health(base_url: str, api_key: str | None, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _ = http_json(f"{base_url}/api/health", None, api_key, timeout=5)
        if status == 200:
            return True
        time.sleep(1.5)
    return False


def _resolve_orion_project_dir(orion_bin_path: str | None) -> Path:
    """
    Find the Orion project root.
    1. If --project-dir was given explicitly, use it.
    2. Try to resolve from the 'orion' launcher (symlink or script).
    3. Fall back to the well-known default location.
    """
    if orion_bin_path:
        return Path(orion_bin_path).expanduser().resolve()
    # Try to locate via the 'orion' command on PATH
    orion_bin = shutil.which("orion")
    if orion_bin:
        real = Path(orion_bin).resolve()
        # Case 1: it's a symlink to <project>/scripts/orion
        if real.parent.name == "scripts":
            candidate = real.parent.parent
            if (candidate / "docker-compose.yml").exists():
                return candidate
    # Well-known fallback
    default = Path("/home/binh/projects/Orion_agent")
    if (default / "docker-compose.yml").exists():
        return default
    raise RuntimeError(
        "Cannot locate Orion project directory. Please pass --project-dir explicitly."
    )


def _docker_compose(project_dir: Path, args: list[str], log_file) -> int:
    """Run a docker compose command and return its exit code."""
    cmd = ["docker", "compose", "--project-directory", str(project_dir)] + args
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return result.returncode


def start_orion(project_dir: Path, server_log_path: Path) -> None:
    log("Starting Orion via docker compose ...")
    with open(server_log_path, "w", encoding="utf-8") as log_file:
        rc = _docker_compose(project_dir, ["up", "-d"], log_file)
        if rc != 0:
            raise RuntimeError(
                f"docker compose up failed (exit code {rc}). "
                f"Check {server_log_path} for details."
            )


def stop_orion(project_dir: Path, server_log_path: Path) -> None:
    log("Stopping Orion ...")
    with open(server_log_path, "a", encoding="utf-8") as log_file:
        _docker_compose(project_dir, ["stop", "reverse-proxy", "ui", "api"], log_file)


def write_transcript_header(f) -> None:
    f.write("# Orion Q&A Transcript\n\n")


def write_turn(
    f,
    index: int,
    question: str,
    http_status: int,
    answer: str,
    elapsed_ms: int,
    timestamp: str,
) -> None:
    """Write one Q&A turn as a markdown section, not a table row.

    Orion's answers are multi-line markdown (bullet points, headers, and
    sometimes literal '|' characters), which corrupts a markdown table
    after the very first such answer. Sections are safe regardless of
    content.
    """
    ok = 200 <= http_status < 300
    status_label = f"HTTP {http_status}" + ("" if ok else " (FAILED)")
    f.write(f"## {index}. {question}\n\n")
    f.write(f"- Status: {status_label}\n")
    f.write(f"- Elapsed: {elapsed_ms} ms\n")
    f.write(f"- Timestamp: {timestamp}\n\n")
    f.write(f"{answer}\n\n")
    f.write("---\n\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standalone Q&A test runner for Orion."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Orion API host.")
    parser.add_argument("--port", default="61888", help="Orion API port.")
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Don't launch Orion; assume it is already running.",
    )
    parser.add_argument(
        "--questions-file", help="Text file with one question per line ('#' = comment)."
    )
    parser.add_argument(
        "--output",
        default="orion_qa_transcript.md",
        help="Path to the transcript file.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Value for ORION_API_KEY. If omitted, the runner tries to read it "
        "from the project's .env file automatically.",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds to wait between questions."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-question HTTP timeout, in seconds.",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Path to Orion project root (auto-detected if not given).",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=90.0,
        help="Max seconds to wait for Orion to come up.",
    )
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    questions = load_questions(args.questions_file)
    session_id = uuid.uuid4().hex[:12]

    output_path = Path(args.output).expanduser().resolve()
    server_log_path = output_path.with_name(output_path.stem + "_server.log")

    project_dir = _resolve_orion_project_dir(args.project_dir)

    api_key = args.api_key or load_api_key_from_env_file(project_dir)
    if api_key and not args.api_key:
        log("Using ORION_API_KEY found in project .env (pass --api-key to override).")
    elif not api_key:
        log(
            "Warning: no API key given and none found in .env. "
            "Requests will fail with 401 if the server has auth enabled."
        )

    if not args.no_start:
        start_orion(project_dir, server_log_path)

    exit_code = 0
    try:
        log(f"Waiting for Orion to become healthy at {base_url} ...")
        if not wait_for_health(base_url, api_key, args.startup_timeout):
            log("Orion did not become healthy in time. Check the server log.")
            if not args.no_start:
                stop_orion(project_dir, server_log_path)
            return 1

        log(f"Orion is up. Running {len(questions)} questions, session_id={session_id}")

        failures = 0
        with open(output_path, "w", encoding="utf-8") as f:
            write_transcript_header(f)
            for i, question in enumerate(questions, start=1):
                payload = {"session_id": session_id, "question": question}
                started = time.monotonic()
                status, response = http_json(
                    f"{base_url}/api/query", payload, api_key, args.timeout
                )
                elapsed_ms = round((time.monotonic() - started) * 1000)
                timestamp = datetime.now().isoformat()

                if isinstance(response, dict):
                    if 200 <= status < 300:
                        answer = response.get("assessment", "(empty response)")
                    else:
                        answer = response.get("detail", json.dumps(response))
                else:
                    answer = str(response)

                if not (200 <= status < 300):
                    failures += 1

                write_turn(f, i, question, status, answer, elapsed_ms, timestamp)
                f.flush()

                log(f"[{i}/{len(questions)}] HTTP {status} ({elapsed_ms} ms) — {question[:60]}")

                if i < len(questions):
                    time.sleep(args.delay)

        log(f"Done. {len(questions) - failures}/{len(questions)} succeeded. Transcript: {output_path}")
        if failures:
            exit_code = 1

    except Exception as e:
        log(f"Error during test run: {e}")
        exit_code = 1
    finally:
        if not args.no_start:
            stop_orion(project_dir, server_log_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
