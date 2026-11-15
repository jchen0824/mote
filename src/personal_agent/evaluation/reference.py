"""Deterministic plumbing baseline, not a model or a measured personal agent."""

import hashlib

from .world import Action, Observation, quiet


class ReferenceActor:
    def __init__(self) -> None:
        self.headings: tuple[str, ...] = ()

    async def act(self, observation: Observation) -> list[Action]:
        for event in observation.events:
            if event.kind == "user" and event.headings:
                self.headings = event.headings
        meeting = observation.meeting
        if not meeting or observation.now >= meeting.starts_at:
            return []
        fingerprint = hashlib.sha256(repr((meeting, self.headings)).encode()).hexdigest()[:16]
        wanted = Action(
            "prepare_brief",
            f"brief-{fingerprint}",
            meeting.id,
            meeting.revision,
            meeting.starts_at,
            self.headings,
            f"Preparation for {meeting.title}",
        )
        actions = [wanted] if observation.brief != wanted else []
        if not quiet(observation.now) and not any(
            a.key == f"notify-{fingerprint}" for a in observation.notifications
        ):
            actions.append(Action("notify", f"notify-{fingerprint}", text="Your brief is ready."))
        return actions
