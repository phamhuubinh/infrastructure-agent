"""Closed, bounded scheduler inputs shared by API and canonical tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orion.scheduler.schedules import CronSchedule, parse_instant, utc_text

MAX_PROMPT = 16_000
MAX_RESULTS = 100


class SchedulerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskInput(SchedulerInput):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT)
    schedule_kind: Literal["once", "recurring"]
    run_at: str | None = Field(default=None, max_length=64)
    cron: str | None = Field(default=None, max_length=256)
    timezone: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_schedule(self) -> TaskInput:
        if not self.prompt.strip():
            raise ValueError("Task prompt cannot be blank.")
        if self.schedule_kind == "once":
            if self.run_at is None or self.cron is not None or self.timezone is not None:
                raise ValueError("One-time schedules require only run_at.")
            self.run_at = utc_text(parse_instant(self.run_at))
        else:
            if self.run_at is not None or self.cron is None or self.timezone is None:
                raise ValueError("Recurring schedules require only cron and timezone.")
            self.cron = CronSchedule.parse(self.cron, self.timezone).text
        return self


class TaskLookup(SchedulerInput):
    task_id: str = Field(min_length=1, max_length=64)


class TaskList(SchedulerInput):
    limit: int = Field(default=50, ge=1, le=MAX_RESULTS)


class TaskHistory(TaskLookup):
    limit: int = Field(default=50, ge=1, le=MAX_RESULTS)
