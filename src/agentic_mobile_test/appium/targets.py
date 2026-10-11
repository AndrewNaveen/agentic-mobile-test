"""Version-controlled semantic targets and deterministic Appium resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from .actions import AppiumActions
from .models import CapturedState, Locator

TargetState = Literal["present", "visible", "clickable"]
_TARGET_STATES = frozenset({"present", "visible", "clickable"})
_SUPPORTED_STRATEGIES = frozenset(
    {
        "accessibility id",
        "id",
        "-android uiautomator",
        "-ios class chain",
        "-ios predicate string",
        "xpath",
    }
)


class TargetCatalogError(ValueError):
    """A version-controlled target catalog is invalid."""


class LocatorResolutionError(LookupError):
    """No reviewed locator resolved to exactly one eligible UI element."""

    def __init__(
        self,
        target_id: str,
        state: TargetState,
        attempts: tuple["LocatorAttempt", ...],
        *,
        evidence: CapturedState | None = None,
    ) -> None:
        summary = "; ".join(
            f"#{attempt.rank} {attempt.outcome} "
            f"({attempt.eligible_matches}/{attempt.total_matches} eligible/total)"
            for attempt in attempts
        ) or "no locator attempts"
        suffix = f" Evidence: {evidence.screenshot.parent}" if evidence else ""
        super().__init__(
            f"Target {target_id!r} did not resolve as {state}: {summary}.{suffix}"
        )
        self.target_id = target_id
        self.state = state
        self.attempts = attempts
        self.evidence = evidence


@dataclass(frozen=True)
class LocatorCandidate:
    """One reviewed Appium locator, ordered by preference in its catalog."""

    strategy: str
    value: str
    description: str = ""

    def __post_init__(self) -> None:
        if self.strategy not in _SUPPORTED_STRATEGIES:
            raise TargetCatalogError(
                f"Unsupported locator strategy {self.strategy!r}; "
                f"expected one of {sorted(_SUPPORTED_STRATEGIES)}"
            )
        if not self.value.strip():
            raise TargetCatalogError("Locator values cannot be empty")

    @property
    def locator(self) -> Locator:
        return self.strategy, self.value


@dataclass(frozen=True)
class SemanticTarget:
    """A durable name mapped to ranked, reviewed locator candidates."""

    target_id: str
    screen: str
    locators: tuple[LocatorCandidate, ...]
    source: Path

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.screen.strip():
            raise TargetCatalogError("Targets require non-empty id and screen values")
        if not self.locators:
            raise TargetCatalogError(f"Target {self.target_id!r} has no locators")
        locator_values = [candidate.locator for candidate in self.locators]
        if len(locator_values) != len(set(locator_values)):
            raise TargetCatalogError(
                f"Target {self.target_id!r} contains duplicate locators"
            )

    @property
    def preferred_locator(self) -> Locator:
        """Return the reviewed first choice for operations that search while scrolling."""

        return self.locators[0].locator


class TargetCatalog:
    """Read-only target definitions loaded from a strict JSON document."""

    def __init__(self, targets: tuple[SemanticTarget, ...], *, source: Path) -> None:
        ids = [target.target_id for target in targets]
        if len(ids) != len(set(ids)):
            duplicates = sorted({target_id for target_id in ids if ids.count(target_id) > 1})
            raise TargetCatalogError(f"Duplicate target ids: {duplicates}")
        self.source = source
        self._targets = {target.target_id: target for target in targets}

    @classmethod
    def load(cls, path: Path) -> "TargetCatalog":
        source = Path(path).resolve()
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise TargetCatalogError(f"Unable to read target catalog {source}: {error}") from error
        except json.JSONDecodeError as error:
            raise TargetCatalogError(f"Invalid JSON in target catalog {source}: {error}") from error

        if not isinstance(document, dict):
            raise TargetCatalogError("A target catalog must be a JSON object")
        _require_keys(document, required={"schema_version", "targets"})
        if document["schema_version"] != 1:
            raise TargetCatalogError("Only target catalog schema_version 1 is supported")
        raw_targets = document["targets"]
        if not isinstance(raw_targets, list) or not raw_targets:
            raise TargetCatalogError("A target catalog requires a non-empty targets list")

        targets = tuple(_parse_target(value, source) for value in raw_targets)
        return cls(targets, source=source)

    def require(self, target_id: str) -> SemanticTarget:
        try:
            return self._targets[target_id]
        except KeyError as error:
            raise TargetCatalogError(
                f"Unknown semantic target {target_id!r} in {self.source}"
            ) from error


@dataclass(frozen=True)
class LocatorAttempt:
    rank: int
    strategy: str
    value: str
    description: str
    total_matches: int
    eligible_matches: int
    outcome: str
    error: str | None = None

    @property
    def locator(self) -> Locator:
        return self.strategy, self.value


@dataclass(frozen=True)
class ResolvedTarget:
    target_id: str
    screen: str
    locator: Locator
    rank: int
    source: Path
    elapsed_seconds: float
    attempts: tuple[LocatorAttempt, ...]


class AppiumTargetResolver:
    """Resolve semantic targets with bounded waits and auditable decisions."""

    def __init__(
        self,
        actions: AppiumActions,
        *,
        trace_path: Path,
        poll_seconds: float | None = None,
    ) -> None:
        self.actions = actions
        self.trace_path = Path(trace_path)
        self.poll_seconds = poll_seconds or actions.poll_seconds
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be greater than zero")

    def resolve(
        self,
        target: SemanticTarget,
        *,
        state: TargetState = "visible",
        timeout_seconds: float | None = None,
    ) -> ResolvedTarget:
        if state not in _TARGET_STATES:
            raise ValueError(f"Unsupported target state: {state}")
        timeout = (
            self.actions.default_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        if timeout < 0:
            raise ValueError("timeout_seconds cannot be negative")

        started = monotonic()
        latest_attempts: tuple[LocatorAttempt, ...] = ()

        def probe(_: Any = None) -> ResolvedTarget | bool:
            nonlocal latest_attempts
            selected, latest_attempts = self._probe(target, state)
            if selected is None:
                return False
            return ResolvedTarget(
                target_id=target.target_id,
                screen=target.screen,
                locator=selected.locator,
                rank=selected.rank,
                source=target.source,
                elapsed_seconds=monotonic() - started,
                attempts=latest_attempts,
            )

        resolved: ResolvedTarget | None = None
        if timeout == 0:
            immediate = probe()
            resolved = immediate if isinstance(immediate, ResolvedTarget) else None
        else:
            try:
                resolved = WebDriverWait(
                    self.actions.driver,
                    timeout,
                    poll_frequency=self.poll_seconds,
                ).until(probe)
            except TimeoutException:
                resolved = None

        if resolved is not None:
            self._record(
                target=target,
                state=state,
                outcome="resolved",
                elapsed_seconds=resolved.elapsed_seconds,
                attempts=resolved.attempts,
                selected_rank=resolved.rank,
                evidence=None,
            )
            return resolved

        evidence = self.actions.capture_state(f"locator-failure-{target.target_id}")
        elapsed = monotonic() - started
        self._record(
            target=target,
            state=state,
            outcome="not_resolved",
            elapsed_seconds=elapsed,
            attempts=latest_attempts,
            selected_rank=None,
            evidence=evidence,
        )
        raise LocatorResolutionError(
            target.target_id,
            state,
            latest_attempts,
            evidence=evidence,
        )

    def is_available(
        self,
        target: SemanticTarget,
        *,
        state: TargetState = "visible",
    ) -> bool:
        """Check a postcondition immediately without logging or failure evidence."""

        if state not in _TARGET_STATES:
            raise ValueError(f"Unsupported target state: {state}")
        selected, _ = self._probe(target, state)
        return selected is not None

    def _probe(
        self,
        target: SemanticTarget,
        state: TargetState,
    ) -> tuple[LocatorAttempt | None, tuple[LocatorAttempt, ...]]:
        attempts: list[LocatorAttempt] = []
        selected: LocatorAttempt | None = None
        for rank, candidate in enumerate(target.locators, start=1):
            try:
                matches = list(self.actions.driver.find_elements(*candidate.locator))
                eligible = [element for element in matches if _is_eligible(element, state)]
                outcome = _attempt_outcome(len(matches), len(eligible))
                attempt = LocatorAttempt(
                    rank=rank,
                    strategy=candidate.strategy,
                    value=candidate.value,
                    description=candidate.description,
                    total_matches=len(matches),
                    eligible_matches=len(eligible),
                    outcome=outcome,
                )
            except Exception as error:
                attempt = LocatorAttempt(
                    rank=rank,
                    strategy=candidate.strategy,
                    value=candidate.value,
                    description=candidate.description,
                    total_matches=0,
                    eligible_matches=0,
                    outcome="query_error",
                    error=f"{type(error).__name__}: {error}",
                )
            attempts.append(attempt)
            if attempt.eligible_matches == 1:
                selected = attempt
                break
        return selected, tuple(attempts)

    def _record(
        self,
        *,
        target: SemanticTarget,
        state: TargetState,
        outcome: str,
        elapsed_seconds: float,
        attempts: tuple[LocatorAttempt, ...],
        selected_rank: int | None,
        evidence: CapturedState | None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "target_id": target.target_id,
            "screen": target.screen,
            "catalog": str(target.source),
            "required_state": state,
            "outcome": outcome,
            "selected_rank": selected_rank,
            "elapsed_seconds": round(elapsed_seconds, 6),
            "app_package": _driver_value(self.actions.driver, "current_package"),
            "activity": _driver_value(self.actions.driver, "current_activity"),
            "attempts": [asdict(attempt) for attempt in attempts],
            "evidence": _evidence_value(evidence),
        }
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _parse_target(value: object, source: Path) -> SemanticTarget:
    if not isinstance(value, dict):
        raise TargetCatalogError("Each target must be a JSON object")
    _require_keys(value, required={"id", "screen", "locators"})
    raw_locators = value["locators"]
    if not isinstance(raw_locators, list) or not raw_locators:
        raise TargetCatalogError(f"Target {value['id']!r} requires locators")
    locators = tuple(_parse_locator(candidate) for candidate in raw_locators)
    return SemanticTarget(
        target_id=_string(value["id"], "target id"),
        screen=_string(value["screen"], "screen"),
        locators=locators,
        source=source,
    )


def _parse_locator(value: object) -> LocatorCandidate:
    if not isinstance(value, dict):
        raise TargetCatalogError("Each locator must be a JSON object")
    _require_keys(value, required={"strategy", "value"}, optional={"description"})
    return LocatorCandidate(
        strategy=_string(value["strategy"], "locator strategy"),
        value=_string(value["value"], "locator value"),
        description=_string(value.get("description", ""), "locator description", empty=True),
    )


def _require_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise TargetCatalogError(f"Missing catalog fields: {sorted(missing)}")
    if unknown:
        raise TargetCatalogError(f"Unknown catalog fields: {sorted(unknown)}")


def _string(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise TargetCatalogError(f"{name} must be a string")
    return value.strip()


def _is_eligible(element: Any, state: TargetState) -> bool:
    if state == "present":
        return True
    try:
        visible = bool(element.is_displayed())
        if state == "visible":
            return visible
        return visible and bool(element.is_enabled())
    except Exception:
        return False


def _attempt_outcome(total: int, eligible: int) -> str:
    if eligible == 1:
        return "unique"
    if eligible > 1:
        return "ambiguous"
    if total > 0:
        return "ineligible"
    return "not_found"


def _driver_value(driver: Any, name: str) -> str | None:
    try:
        value = getattr(driver, name)
    except Exception:
        return None
    return str(value) if value else None


def _evidence_value(evidence: CapturedState | None) -> dict[str, str] | None:
    if evidence is None:
        return None
    return {
        "screenshot": str(evidence.screenshot),
        "ui_source": str(evidence.ui_source),
    }
