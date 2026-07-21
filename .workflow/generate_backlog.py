#!/usr/bin/env python3
"""Generate BACKLOG.md from .workflow/state.json with standardized format."""

import json
from collections import OrderedDict, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / ".workflow" / "state.json"
BACKLOG_PATH = ROOT / "BACKLOG.md"

STATUS_EMOJI = {
    "completed": "✅",
    "in_progress": "🔄",
    "pending": "⬜",
    "blocked": "🔴",
}

PHASES = OrderedDict(
    [
        (0, "Diagnosis & Preparation"),
        (1, "Foundation (P0\u2013P1)"),
        (2, "Quality & Technical Debt (P2)"),
        (3, "Polish & Governance (P3)"),
    ]
)


def determine_phase(item):
    p = item["priority"]
    if p == "P0":
        epic = item["epic"]
        if epic == "Code Quality":
            return 0
        return 1
    elif p == "P1":
        return 1
    elif p == "P2":
        return 2
    else:
        return 3


EPIC_SORT = [
    "Code Quality",
    "Core Architecture",
    "Security",
    "DevOps & CI/CD",
    "Testing & Quality Assurance",
    "Documentation & Project Governance",
    "Code Quality, Refactoring & Technical Debt",
]


def generate():
    with open(STATE_PATH) as f:
        state = json.load(f)

    backlog = state["backlog"]

    # Group items by phase, then epic, then id
    phases = OrderedDict()
    for phase_id, phase_name in PHASES.items():
        phases[phase_id] = {
            "name": phase_name,
            "epics": OrderedDict(),
        }

    for item in backlog:
        phase = determine_phase(item)
        epic = item["epic"]
        if epic not in phases[phase]["epics"]:
            phases[phase]["epics"][epic] = []
        phases[phase]["epics"][epic].append(item)

    # Sort epics within each phase
    for phase_id in phases:
        epics = phases[phase_id]["epics"]
        sorted_epics = OrderedDict()
        for epic_name in EPIC_SORT:
            if epic_name in epics:
                sorted_epics[epic_name] = sorted(
                    epics[epic_name], key=lambda x: x["id"]
                )
        for epic_name, items in sorted(epics.items()):
            if epic_name not in sorted_epics:
                sorted_epics[epic_name] = sorted(items, key=lambda x: x["id"])
        phases[phase_id]["epics"] = sorted_epics

    lines = []
    lines.append("# Orion \u2014 Backlog")
    lines.append("")
    lines.append("> Consolidated backlog derived from `.workflow/state.json`.")
    lines.append("> Tasks are grouped by Epic, sorted by ID, then by Phase.")
    lines.append("")
    lines.append(f"Last updated: {date.today().isoformat()}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Legend")
    lines.append("")
    lines.append("| Column      | Meaning                                           |")
    lines.append("|-------------|---------------------------------------------------|")
    lines.append("| ID          | Unique task identifier                            |")
    lines.append("| Priority    | P0=Critical, P1=High, P2=Medium, P3=Low          |")
    lines.append(
        "| Status      | `✅ completed` / `🔄 in_progress` / `⬜ pending` / `🔴 blocked` |"
    )
    lines.append("| Title       | Short task name                                   |")
    lines.append("| Description | Brief description of the task                     |")
    lines.append("")
    lines.append("**Phases:**")
    for pid, pname in PHASES.items():
        lines.append(f"- **Phase {pid}**: {pname}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for phase_id, phase_data in phases.items():
        phase_name = phase_data["name"]
        lines.append(f"## Phase {phase_id} \u2014 {phase_name}")
        lines.append("")

        for epic_name, items in phase_data["epics"].items():
            if not items:
                continue
            lines.append(f"### {epic_name}")
            lines.append("")
            # Handle special case: duplicated IDs (like task 4 having two entries)
            # We need to group them: use ID as primary, but if there are duplicates,
            # append "a" and "b" suffixes
            display_items = []
            id_counts = defaultdict(int)
            for item in items:
                id_counts[item["id"]] += 1

            id_suffix = defaultdict(int)
            for item in items:
                item_id = item["id"]
                if id_counts[item_id] > 1:
                    suffix = chr(ord("a") + id_suffix[item_id])
                    id_suffix[item_id] += 1
                    display_id = f"{item_id}{suffix}"
                else:
                    display_id = str(item_id)
                display_items.append((display_id, item))

            lines.append("| ID  | Priority | Status | Title | Description |")
            lines.append("|-----|----------|--------|-------|-------------|")

            for display_id, item in display_items:
                status_str = STATUS_EMOJI.get(item["status"], "⬜")
                title = item["title"]
                desc = item.get("description", "")
                lines.append(
                    f"| {display_id:<3s} | {item['priority']:<8s} | {status_str:<6s} | {title:<44s} | {desc} |"
                )
            lines.append("")
        lines.append("---")
        lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Phase | Epic | Total | \u2705 Done | \U0001f504 In Progress | \u2b1c Pending | \U0001f534 Blocked |"
    )
    lines.append(
        "|-------|------|-------|--------|----------------|---------|----------|"
    )

    grand_total = 0
    grand_done = 0
    grand_in_progress = 0
    grand_pending = 0
    grand_blocked = 0

    for phase_id, phase_data in phases.items():
        for epic_name, items in phase_data["epics"].items():
            if not items:
                continue
            total = len(items)
            done = sum(1 for i in items if i["status"] == "completed")
            in_progress = sum(1 for i in items if i["status"] == "in_progress")
            pending = sum(1 for i in items if i["status"] == "pending")
            blocked = sum(1 for i in items if i["status"] == "blocked")
            grand_total += total
            grand_done += done
            grand_in_progress += in_progress
            grand_pending += pending
            grand_blocked += blocked
            lines.append(
                f"| {str(phase_id):<5s} | {epic_name:<44s} | {total:<5d} | {done:<6d} | {in_progress:<12d} | {pending:<7d} | {blocked:<8d} |"
            )

    lines.append(
        f"|       | **Total**{'':>36s} | **{grand_total}** | **{grand_done}** | **{grand_in_progress}** | **{grand_pending}** | **{grand_blocked}** |"
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Source: `.workflow/state.json` \u2014 this file is auto-generated for human readability.*"
    )
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    content = generate()
    with open(BACKLOG_PATH, "w") as f:
        f.write(content)
    print(f"Written {BACKLOG_PATH}")
