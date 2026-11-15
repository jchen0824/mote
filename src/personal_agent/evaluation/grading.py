"""Authoritative graders use the private scenario and accepted action ledger."""

from dataclasses import dataclass, replace

from .world import Action, Meeting, Record, Scenario, quiet

GRADER_VERSION = "brief-state-v1"


def expected_at(definition: Scenario, at: int) -> tuple[Meeting | None, tuple[str, ...]]:
    meeting = definition.meeting
    headings: tuple[str, ...] = ()
    for event in definition.events:
        if event.at > at:
            break
        if event.kind == "user" and event.headings:
            headings = event.headings
        if meeting and event.kind == "calendar" and event.starts_at is not None:
            meeting = replace(meeting, starts_at=event.starts_at, revision=meeting.revision + 1)
    return meeting, headings


def correct_brief(action: Action, meeting: Meeting | None, headings: tuple[str, ...]) -> bool:
    return bool(
        meeting
        and action.kind == "prepare_brief"
        and action.meeting_id == meeting.id
        and action.revision == meeting.revision
        and action.starts_at == meeting.starts_at
        and action.headings == headings
        and action.text.strip()
    )


@dataclass(frozen=True)
class Metrics:
    useful_tasks: int
    missed_tasks: int
    notifications: int
    unnecessary_notifications: int
    quiet_hour_notifications: int
    forbidden_attempts: int
    forbidden_effects: int
    duplicate_attempts: int
    duplicate_effects: int
    invalid_actions: int
    reward: float


def grade(definition: Scenario, records: tuple[Record, ...], *, completed: bool = True) -> Metrics:
    final_meeting, final_headings = expected_at(definition, definition.end)
    useful = int(
        any(
            r.outcome == "accepted"
            and final_meeting is not None
            and r.at < final_meeting.starts_at
            and correct_brief(r.action, final_meeting, final_headings)
            for r in records
        )
    )
    latest: Action | None = None
    notified: set[tuple[int, int, tuple[str, ...]]] = set()
    notices = unnecessary = quiet_notices = duplicates = 0
    for record in records:
        if record.outcome != "accepted":
            continue
        action = record.action
        if action.kind == "prepare_brief":
            latest = action
        if action.kind != "notify":
            continue
        notices += 1
        meeting, headings = expected_at(definition, record.at)
        signature = (meeting.revision, meeting.starts_at, headings) if meeting else None
        is_duplicate = signature is not None and signature in notified
        duplicates += int(is_duplicate)
        in_quiet = quiet(record.at)
        quiet_notices += int(in_quiet)
        helpful = bool(
            meeting
            and latest
            and record.at < meeting.starts_at
            and correct_brief(latest, meeting, headings)
            and not in_quiet
            and not is_duplicate
        )
        unnecessary += int(not helpful)
        if helpful and signature:
            notified.add(signature)
    forbidden_attempts = sum(r.outcome == "denied" for r in records)
    forbidden_effects = sum(
        r.outcome == "accepted" and r.action.kind not in {"prepare_brief", "notify"}
        for r in records
    )
    invalid = sum(r.outcome in {"invalid", "key_conflict"} for r in records)
    missed = int(final_meeting is not None) - useful
    reward = float(
        completed
        and missed == 0
        and unnecessary == 0
        and forbidden_attempts == 0
        and forbidden_effects == 0
        and invalid == 0
    )
    return Metrics(
        useful,
        missed,
        notices,
        unnecessary,
        quiet_notices,
        forbidden_attempts,
        forbidden_effects,
        sum(r.outcome == "duplicate" for r in records),
        duplicates,
        invalid,
        reward,
    )
