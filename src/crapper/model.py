from dataclasses import dataclass


@dataclass(frozen=True)
class Function:
    """One scored unit: a function or method."""

    name: str
    namespace: str
    complexity: int
    start_line: int
    end_line: int
    path: str
    language: str
    jacoco_class: str | None = None
    # UTF-8 byte span of the function. -1 when the language does not record it.
    # Mutator uses the span to give a nested handler the sites inside it.
    start_byte: int = -1
    end_byte: int = -1
    # Lines whose coverage counts belong to this unit, when that is narrower
    # than start_line..end_line: a Clojure method that shares its first or last
    # line with other code leaves that line out. -1 means use the line range.
    cover_start: int = -1
    cover_end: int = -1


@dataclass(frozen=True)
class Entry:
    """One row of the CRAP report and of `.metrics/crap.edn`."""

    name: str
    namespace: str
    complexity: int
    coverage: float | None
    crap: float | None
    path: str
    language: str
