"""Clojure cyclomatic complexity, ported from crap4clj.

Decision points are the same forms crap4clj counts: `if` / `when` and their
variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`,
`case`, `cond->`, `cond->>`, `some->`, and `some->>`.
"""

import re
from dataclasses import dataclass, field

from crapper.model import Function

_DECISION = re.compile(
    r"\((if-not|if-let|if-some|when-not|when-let|when-some|when-first|if|when|and|or|loop|catch)[\s\)]"
)
_COND = re.compile(r"\((some->>|some->|cond->>|cond->|cond|condp|case)[\s\)]")
_NS = re.compile(r"\(\s*ns\s+([A-Za-z0-9*+!_?.\-/]+)")
_IN_NS = re.compile(r"\(\s*in-ns\s+'([A-Za-z0-9*+!_?.\-/]+)\s*\)")
_IN_NS_QUOTE = re.compile(
    r"\(\s*in-ns\s+\(quote\s+([A-Za-z0-9*+!_?.\-/]+)\)\s*\)"
)

_FORM_SKIP = {
    "condp": 2,
    "case": 1,
    "cond->": 1,
    "cond->>": 1,
    "some->": 1,
    "some->>": 1,
}
_THREAD_FORMS = {"some->", "some->>"}
_CHAR_DELIMITERS = set("()[]{}\";,")


def _blank_span(source: str, start: int, end: int, out: list[str]) -> None:
    for ch in source[start:end]:
        out.append("\n" if ch == "\n" else " ")


def _advance_past_reader_token(source: str, index: int) -> int | None:
    """Index after a string, character, or comment, or None when `index` is code."""

    ch = source[index]
    if ch == '"':
        return _consume_string(source, index, 1)[0]
    if ch == "\\":
        return _char_literal_end(source, index)
    if ch != ";":
        return None
    while index < len(source) and source[index] != "\n":
        index += 1
    return index


def _balanced_end(source: str, index: int) -> int:
    opener = source[index]
    closer = {"(": ")", "[": "]", "{": "}"}[opener]
    depth = 0
    while index < len(source):
        nxt = _advance_past_reader_token(source, index)
        if nxt is not None:
            index = nxt
            continue
        ch = source[index]
        index += 1
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return index
    return index


def _skip_space_and_comment(source: str, index: int) -> int:
    while index < len(source) and source[index].isspace():
        index += 1
    if index < len(source) and source[index] == ";":
        while index < len(source) and source[index] != "\n":
            index += 1
    return index


def _skip_ignorable(source: str, index: int) -> int:
    while True:
        nxt = _skip_space_and_comment(source, index)
        if nxt == index:
            return index
        index = nxt


def _end_of_atom(source: str, index: int) -> int:
    while index < len(source) and not source[index].isspace() and source[index] not in "()[]{}\";":
        index += 1
    return index


def _end_of_one_form(source: str, index: int) -> int:
    ch = source[index]
    if ch in "([{":
        return _balanced_end(source, index)
    if ch == '"':
        return _consume_string(source, index, 1)[0]
    if ch == "\\":
        return _char_literal_end(source, index)
    if source.startswith("#_", index):
        return _form_end(source, index + 2)
    return _end_of_atom(source, index)


def _form_end(source: str, index: int) -> int:
    """Index just after the next form. `index` may sit on whitespace before it."""

    index = _skip_ignorable(source, index)
    if index >= len(source):
        return index
    return _end_of_one_form(source, index)


def without_strings_and_comments(source: str) -> str:
    """Blank strings, comments, character literals, and `#_` discarded forms.

    Character literals are blanked before `"` or `;` can be read, so `\\"` does
    not open a string and `\\;` does not open a comment.
    """

    out: list[str] = []
    index = 0
    while index < len(source):
        if source.startswith("#_", index):
            end = _form_end(source, index + 2)
            _blank_span(source, index, end, out)
            index = end
            continue
        ch = source[index]
        if ch == '"':
            end = _consume_string(source, index, 1)[0]
            _blank_span(source, index, end, out)
            index = end
            continue
        if ch == "\\":
            end = _char_literal_end(source, index)
            _blank_span(source, index, end, out)
            index = end
            continue
        if ch == ";":
            while index < len(source) and source[index] != "\n":
                out.append(" ")
                index += 1
            continue
        out.append(ch)
        index += 1
    return "".join(out)


def _open_bracket(ch: str) -> bool:
    return ch in "({["


def _close_bracket(ch: str) -> bool:
    return ch in ")}]"


def _on_open_bracket(depth: int, in_form: bool, forms: int) -> tuple[int, bool, int]:
    if depth == 1 and not in_form:
        forms += 1
    return depth + 1, True, forms


def _on_close_bracket(depth: int, in_form: bool, forms: int) -> tuple[int, bool, int]:
    if depth == 1:
        in_form = False
    return depth - 1, in_form, forms


def _on_atom(depth: int, in_form: bool, forms: int) -> tuple[int, bool, int]:
    if depth == 1 and not in_form:
        forms += 1
    return depth, True, forms


def _count_top_level_forms(text: str, start: int) -> int:
    depth = 1
    forms = 0
    in_form = False
    i = start
    n = len(text)
    while i < n and depth != 0:
        ch = text[i]
        if _open_bracket(ch):
            depth, in_form, forms = _on_open_bracket(depth, in_form, forms)
        elif _close_bracket(ch):
            depth, in_form, forms = _on_close_bracket(depth, in_form, forms)
        elif ch.isspace():
            in_form = depth != 1
        else:
            depth, in_form, forms = _on_atom(depth, in_form, forms)
        i += 1
    return forms


def _skip_to_body(text: str, match_start: int) -> int:
    i = match_start + 1
    while i < len(text) and not text[i].isspace() and text[i] != ")":
        i += 1
    return i


def _pairwise_clause_count(form_type: str, remaining: int) -> int:
    base = remaining // 2
    if form_type == "case" and remaining % 2 == 1:
        return base + 1
    return base


def _count_clauses(text: str, form_type: str, match_start: int) -> int:
    body_start = _skip_to_body(text, match_start)
    total_forms = _count_top_level_forms(text, body_start)
    remaining = total_forms - _FORM_SKIP.get(form_type, 0)
    if form_type in _THREAD_FORMS:
        return remaining
    return _pairwise_clause_count(form_type, remaining)


def _count_cond_decisions(clean: str) -> int:
    total = 0
    for match in _COND.finditer(clean):
        form_type = match.group(1)
        total += _count_clauses(clean, form_type, match.start())
    return total


def cyclomatic_complexity(fn_text: str) -> int:
    clean = without_strings_and_comments(fn_text)
    simple = len(_DECISION.findall(clean))
    return 1 + simple + _count_cond_decisions(clean)


def _char_literal_end(source: str, index: int) -> int:
    first = index + 1
    if first >= len(source):
        return len(source)
    i = first + 1
    while i < len(source):
        ch = source[i]
        if ch.isspace() or ch in _CHAR_DELIMITERS:
            return i
        i += 1
    return len(source)


def _consume_comment(source: str, index: int, line: int) -> tuple[int, int]:
    index += 1
    while index < len(source) and source[index] != "\n":
        index += 1
    if index < len(source):
        return index + 1, line + 1
    return index, line


def _consume_string(source: str, index: int, line: int) -> tuple[int, int]:
    index += 1
    escaped = False
    while index < len(source):
        ch = source[index]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return index + 1, line
        if ch == "\n":
            line += 1
        index += 1
    return index, line


_NAME_STOP = " \t\n\r()[]{}\""


def _skip_space(form: str, index: int) -> int:
    while index < len(form) and form[index].isspace():
        index += 1
    return index


def _keyword_ends(form: str, after: int) -> bool:
    return after >= len(form) or form[after] in _NAME_STOP


_DEFN_HEADS = ("defn", "defn-", ">defn", ">defn-", "defmacro")
_DEF_HEADS = ("def", "defonce")
_BODY_START = {"defrecord": 3, "deftype": 3, "extend-type": 2, "extend-protocol": 2}
_PREFIXES = ("#?@", "~@", "#?", "#'", "#=", "'", "`", "~", "@")
_ATOM = re.compile(r'[^\s,()\[\]{}";]*')


def _defn_keyword_end(form: str, index: int) -> int | None:
    for candidate in sorted(_DEFN_HEADS, key=len, reverse=True):
        after = index + len(candidate)
        if form.startswith(candidate, index) and _keyword_ends(form, after):
            return after
    return None


def _skip_metadata(form: str, index: int) -> int:
    index += 1
    if index < len(form) and form[index] == "{":
        return _balanced_end(form, index)
    while index < len(form) and form[index] not in _NAME_STOP:
        index += 1
    return index


def _skip_leading_metadata(form: str, index: int) -> int:
    while True:
        index = _skip_space(form, index)
        if index < len(form) and form[index] == "^":
            index = _skip_metadata(form, index)
            continue
        return index


def _read_name(form: str, index: int) -> str | None:
    if index >= len(form) or form[index] in "()[]{}\";":
        return None
    start = index
    while index < len(form) and form[index] not in _NAME_STOP:
        index += 1
    return form[start:index]


def _defn_name(form: str) -> str | None:
    if not form.startswith("("):
        return None
    keyword_at = _defn_keyword_end(form, _skip_space(form, 1))
    if keyword_at is None:
        return None
    return _read_name(form, _skip_leading_metadata(form, keyword_at))


def _skip_gap(text: str, index: int) -> int:
    """Skip whitespace, commas, comments, and `#_` discarded forms."""

    while index < len(text):
        ch = text[index]
        if ch.isspace() or ch == ",":
            index += 1
        elif ch == ";":
            while index < len(text) and text[index] != "\n":
                index += 1
        elif text.startswith("#_", index):
            index = _child_end(text, _skip_gap(text, index + 2))
        else:
            return index
    return index


def _atom_end(text: str, index: int) -> int:
    """End of a symbol, keyword, or number. A comma ends it, as whitespace does."""

    return _ATOM.match(text, index).end()


def _child_end(text: str, index: int) -> int:
    """End of one reader form, including reader prefixes and `^meta`."""

    if index >= len(text):
        return index
    if text[index] == "^":
        return _child_end(text, _skip_gap(text, _child_end(text, index + 1)))
    for prefix in _PREFIXES:
        if text.startswith(prefix, index):
            return _child_end(text, _skip_gap(text, index + len(prefix)))
    if text[index] == "#":
        return _dispatch_end(text, index)
    if text[index] in "([{\"\\":
        return _end_of_one_form(text, index)
    return _atom_end(text, index)


def _dispatch_end(text: str, index: int) -> int:
    """End of a `#`-dispatch form. `_child_end` reads `#?`, `#'`, and `#=` as prefixes.

    A set or anonymous fn ends at its closing bracket, a regex at its closing
    quote, and `##Inf` at the end of its token. A namespaced map (`#:ns{...}`)
    or a tagged literal (`#inst "..."`) is its tag and the form after the tag.
    """

    if text.startswith(("#{", "#("), index):
        return _balanced_end(text, index + 1)
    if text.startswith('#"', index):
        return _consume_string(text, index + 1, 1)[0]
    tag_end = _atom_end(text, index + 1)
    if text.startswith("##", index):
        return tag_end
    return _child_end(text, _skip_gap(text, tag_end))


def _children(form: str, start: int = 0) -> list[tuple[int, int]]:
    """Spans of the forms directly inside the list that opens at `start`."""

    spans = []
    index = start + 1
    while True:
        index = _skip_gap(form, index)
        if index >= len(form) or form[index] in ")]}":
            return spans
        end = _child_end(form, index)
        spans.append((index, end))
        index = end


def _head(form: str, spans: list[tuple[int, int]]) -> str | None:
    if not spans:
        return None
    start, end = spans[0]
    return form[start:end]


def _strip_meta(form: str, start: int, end: int) -> tuple[int, int]:
    while start < end and form[start] == "^":
        start = _skip_gap(form, _child_end(form, start + 1))
    return start, end


def _symbol(form: str, span: tuple[int, int]) -> str | None:
    start, end = _strip_meta(form, *span)
    text = form[start:end]
    if not text or text[0] in "([{\"\\:#'`~@^":
        return None
    return text


def _is_list(form: str, span: tuple[int, int]) -> bool:
    start, end = _strip_meta(form, *span)
    return start < end and form[start] == "("


@dataclass
class _Reading:
    """What naming needs from the whole file.

    The namespace and its `:as` aliases resolve `::keyword` dispatch values.
    `seen` counts each name, so a repeated method or `defmethod` gets `#2`, `#3`.
    """

    namespace: str | None = None
    aliases: dict[str, str] = field(default_factory=dict)
    seen: dict[str, int] = field(default_factory=dict)

    def claim(self, name: str) -> str:
        count = self.seen.get(name, 0) + 1
        self.seen[name] = count
        if count == 1:
            return name
        return f"{name}#{count}"


def _libspec_aliases(source: str, start: int, prefix: str, out: dict[str, str]) -> None:
    """Record `alias -> lib` for a libspec, and for the libspecs of a prefix list."""

    if source[start] not in "([":
        return
    spans = _children(source, start)
    texts = [source[s:e] for s, e in spans]
    if not texts:
        return
    lib = prefix + texts[0]
    for key, value in zip(texts[1:], texts[2:]):
        if key in (":as", ":as-alias"):
            out[value] = lib
    for child_start, _end in spans[1:]:
        _libspec_aliases(source, child_start, lib + ".", out)


def _ns_aliases(source: str) -> dict[str, str]:
    """The `:as` / `:as-alias` aliases of the `(:require ...)` clauses of the `ns` form."""

    aliases: dict[str, str] = {}
    match = _NS.search(without_strings_and_comments(source))
    if match is None:
        return aliases
    for start, _end in _children(source, match.start()):
        clause = _children(source, start) if source[start] == "(" else []
        if _head(source, clause) == ":require":
            for libspec_start, _libspec_end in clause[1:]:
                _libspec_aliases(source, libspec_start, "", aliases)
    return aliases


def _resolve_keyword(body: str, reading: _Reading) -> str:
    """`::kw` as `:ns/kw`; `::alias/kw` as `:lib/kw` when the alias is known."""

    alias, slash, name = body.partition("/")
    namespace = reading.aliases.get(alias) if slash else reading.namespace
    if namespace is None:
        return f"::{body}"
    return f":{namespace}/{name if slash else alias}"


def _spelling(token: str, reading: _Reading) -> str:
    if token.startswith('"'):
        return token.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if token.startswith("::"):
        return _resolve_keyword(token[2:], reading)
    return token


def _token_end(text: str, index: int) -> int:
    if text[index] in "()[]{}":
        return index + 1
    if text[index] in "\"\\":
        return _end_of_one_form(text, index)
    return _atom_end(text, index)


def _dispatch_name(text: str, reading: _Reading) -> str:
    """The dispatch value as written, with only insignificant whitespace normalized.

    Outside string literals, each run of whitespace, commas, comments, and `#_`
    discards becomes one space, and none is kept just inside a bracket. A
    string keeps its contents; a raw newline, return, or tab in it is written as
    its escape, which reads as the same string. `::kw` and `::alias/kw` resolve
    through `reading`, so one keyword gets one name however it is spelled.
    """

    out: list[str] = []
    index = 0
    gap = False
    while index < len(text):
        after_gap = _skip_gap(text, index)
        if after_gap > index:
            gap, index = True, after_gap
            continue
        end = _token_end(text, index)
        token = text[index:end]
        if gap and out[-1][-1] not in "([{" and token not in ")]}":
            out.append(" ")
        out.append(_spelling(token, reading))
        gap, index = False, end
    return "".join(out)


def _unit(form: str, base_line: int, span: tuple[int, int], name: str) -> dict:
    start, end = span
    first = base_line + form.count("\n", 0, start)
    last = first + form.count("\n", start, end)
    return {"name": name, "start_line": first, "end_line": last,
            "text": form[start:end], "span": span}


def _conditional_branches(form: str, span: tuple[int, int]) -> list[tuple[int, int]] | None:
    """The forms of every branch of a reader conditional, or None for any other form.

    `#?(:clj a :cljs b)` gives `a` and `b`; `#?@(:clj [a b])` splices `a` and `b`.
    """

    splice = form.startswith("#?@", span[0])
    if not splice and not form.startswith("#?", span[0]):
        return None
    opener = _skip_gap(form, span[0] + (3 if splice else 2))
    if form[opener] != "(":
        return []
    branches = _children(form, opener)[1::2]
    if not splice:
        return branches
    return [child for start, _end in branches if form[start] in "([" for child in _children(form, start)]


def _expanded(form: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """`spans` with each reader conditional replaced by the forms of all its branches.

    Branches are read in source order, so a method that two branches define is
    numbered like a repeated method.
    """

    out = []
    for span in spans:
        branches = _conditional_branches(form, span)
        if branches is None:
            out.append(span)
        else:
            out.extend(_expanded(form, branches))
    return out


def _method_name(form: str, span: tuple[int, int]) -> tuple[str, tuple[int, int]] | None:
    """The method symbol of a method list, without `^hint` metadata, and its span."""

    children = _children(form, _strip_meta(form, *span)[0])
    if not children:
        return None
    name = _symbol(form, children[0])
    if name is None:
        return None
    return name, children[0]


def _method_unit(form, base_line, span, found, prefix, reading):
    """One method. Its name is blanked from the scored text, so `(when [x] ...)`
    is not counted as a `when` decision."""

    method, (name_start, name_end) = found
    unit = _unit(form, base_line, span, reading.claim(f"{prefix}.{method}"))
    left, right = name_start - span[0], name_end - span[0]
    unit["text"] = unit["text"][:left] + " " * (right - left) + unit["text"][right:]
    return unit


def _method_units(form, base_line, spans, label, reading, group=None):
    """A unit for each method list among `spans`, named `label(group).method`.

    A bare symbol starts a new group: the protocol or interface in a type
    body, or the type in `extend-protocol`. Methods before any group are
    skipped. Reader conditionals contribute the forms of all their branches.
    """

    units = []
    for span in _expanded(form, spans):
        if not _is_list(form, span):
            group = _symbol(form, span) or group
            continue
        found = _method_name(form, span)
        if group is not None and found is not None:
            units.append(_method_unit(form, base_line, span, found, label(group), reading))
    return _with_coverage_lines(form, base_line, units)


def _foreign_lines(form: str, base_line: int, units: list[dict]) -> set[int]:
    """Lines where the form has code outside every unit, such as `(defrecord R [x] P`."""

    inside = [False] * len(form)
    for unit in units:
        start, end = unit["span"]
        inside[start:end] = [True] * (end - start)
    lines = set()
    line = base_line
    for index, ch in enumerate(without_strings_and_comments(form)):
        if ch == "\n":
            line += 1
        elif not inside[index] and not ch.isspace() and ch not in ",)]}":
            lines.add(line)
    return lines


def _with_coverage_lines(form: str, base_line: int, units: list[dict]) -> list[dict]:
    """Give each method the lines whose coverage counts are its own.

    Cloverage and LCOV count per line, so a line that a method shares with
    another method, or with the form's own code, cannot be split between
    them. Such a shared first or last line is left out of the method's
    coverage. A method with no line of its own (a one-line `deftype`, say)
    falls back to its whole line range and shares those counts.
    """

    foreign = _foreign_lines(form, base_line, units)

    def shared(line: int, unit: dict) -> bool:
        return line in foreign or any(
            other is not unit and other["start_line"] <= line <= other["end_line"]
            for other in units
        )

    for unit in units:
        first, last = unit["start_line"], unit["end_line"]
        start = first + 1 if shared(first, unit) else first
        end = last - 1 if shared(last, unit) else last
        if start > end:
            start, end = first, last
        unit["cover_start"], unit["cover_end"] = start, end
    return units


def _anonymous_units(form: str, base_line: int, spans: list, reading: _Reading) -> list[dict]:
    """Methods of a `reify` or `proxy` that is the value of a top-level `def`.

    The def's var stands for the anonymous type: `var.Interface.method` for a
    `reify`, `var.method` for a `proxy`, whose methods do not name an interface.
    """

    var = _symbol(form, spans[1])
    start, _end = _strip_meta(form, *spans[-1])
    if var is None or form[start] != "(":
        return []
    value = _children(form, start)
    head = _head(form, value)
    if head == "reify":
        return _method_units(form, base_line, value[1:], lambda face: f"{var}.{face}", reading)
    if head == "proxy":
        return _method_units(form, base_line, value[3:], lambda _: var, reading, group="")
    return []


def _defmethod_unit(form, base_line, spans, reading):
    if len(spans) < 3:
        return []
    multi = _symbol(form, spans[1])
    if multi is None:
        return []
    start, end = _strip_meta(form, *spans[2])
    name = reading.claim(f"{multi} {_dispatch_name(form[start:end], reading)}")
    return [_unit(form, base_line, (0, len(form)), name)]


def _form_units(form: str, base_line: int, reading: _Reading) -> list[dict]:
    """The scored units in one top-level form.

    `defn`, `defn-`, guardrails `>defn` / `>defn-`, and `defmacro` are one unit
    named for the var. `defmethod` is one unit named `multi dispatch-value`.
    The methods of `defrecord`, `deftype`, `extend-type`, and `extend-protocol`
    are one unit each, named `Type.Protocol.method`; those of a `reify` or
    `proxy` that is a top-level `def` value are named for the var. A `reify`
    or `proxy` inside a function stays part of that function.
    """

    name = _defn_name(form)
    if name is not None:
        return [{"name": name, "start_line": base_line,
                 "end_line": base_line + form.count("\n"), "text": form}]
    spans = _children(form)
    head = _head(form, spans)
    if head == "defmethod":
        return _defmethod_unit(form, base_line, spans, reading)
    if head in _DEF_HEADS and len(spans) >= 3:
        return _anonymous_units(form, base_line, spans, reading)
    return _type_units(form, base_line, head, spans, reading)


def _type_units(form: str, base_line: int, head: str | None, spans: list, reading) -> list[dict]:
    """`Type.Protocol.method` units of a type-defining form, or none for any other form."""

    body = _BODY_START.get(head)
    owner = _symbol(form, spans[1]) if body is not None and len(spans) >= 2 else None
    if owner is None:
        return []
    if head == "extend-protocol":
        return _method_units(form, base_line, spans[body:], lambda kind: f"{kind}.{owner}", reading)
    return _method_units(form, base_line, spans[body:], lambda protocol: f"{owner}.{protocol}", reading)


def _remember_form(
    forms: list[dict], source: str, start: int, start_line: int, end: int, reading: _Reading
) -> None:
    forms.extend(_form_units(source[start : end + 1], start_line, reading))


def _close_form(forms, source, depth, form_start, form_line, index, reading):
    if depth == 1 and form_start is not None and form_line is not None:
        _remember_form(forms, source, form_start, form_line, index, reading)
        return 0, None, None
    return max(0, depth - 1), form_start, form_line


def _skip_reader(source: str, index: int, line: int) -> tuple[int, int] | None:
    ch = source[index]
    if ch == ";":
        return _consume_comment(source, index, line)
    if ch == '"':
        return _consume_string(source, index, line)
    if ch == "\\":
        return _char_literal_end(source, index), line
    if source.startswith("#_", index):
        end = _form_end(source, index + 2)
        return end, line + source[index:end].count("\n")
    return None


def _extract_top_level_defns(source: str, reading: _Reading | None = None) -> list[dict]:
    reading = reading or _Reading()
    forms: list[dict] = []
    index = 0
    line = 1
    depth = 0
    form_start = None
    form_line = None
    while index < len(source):
        skipped = _skip_reader(source, index, line)
        if skipped is not None:
            index, line = skipped
            continue
        ch = source[index]
        if ch == "(":
            if depth == 0:
                form_start = index
                form_line = line
            depth += 1
        elif ch == ")":
            depth, form_start, form_line = _close_form(
                forms, source, depth, form_start, form_line, index, reading
            )
        if ch == "\n":
            line += 1
        index += 1
    return forms


_COVER_KEYS = ("cover_start", "cover_end")


def extract_functions(source: str, namespace: str | None = None) -> list[dict]:
    """Units with name, lines, and complexity.

    A method unit also carries `cover_start` / `cover_end`, the lines whose
    coverage counts are its own (see `_with_coverage_lines`).
    """

    reading = _Reading(namespace, _ns_aliases(source))
    found = []
    for form in _extract_top_level_defns(source, reading):
        item = {
            "name": form["name"],
            "start_line": form["start_line"],
            "end_line": form["end_line"],
            "complexity": cyclomatic_complexity(form["text"]),
        }
        item.update({key: form[key] for key in _COVER_KEYS if key in form})
        found.append(item)
    return found


def declared_namespace(source: str) -> str | None:
    clean = without_strings_and_comments(source)
    for pattern in (_NS, _IN_NS, _IN_NS_QUOTE):
        match = pattern.search(clean)
        if match:
            return match.group(1)
    return None


def namespace_from_path(path: str, source_root: str | None) -> str:
    relative = path.replace("\\", "/")
    root = (source_root or "").replace("\\", "/").rstrip("/")
    if root and root not in {".", ""} and relative.startswith(root + "/"):
        relative = relative[len(root) + 1 :]
    if relative.startswith("src/"):
        relative = relative[4:]
    elif "/src/" in relative:
        relative = relative.split("/src/", 1)[1]
    relative = re.sub(r"\.(?:clj[cs]?|bb)$", "", relative)
    return relative.replace("/", ".").replace("_", "-")


def functions_in_source(
    source: str, path: str, source_root: str | None = None
) -> list[Function]:
    namespace = declared_namespace(source) or namespace_from_path(path, source_root)
    return [
        Function(
            name=item["name"],
            namespace=namespace,
            complexity=item["complexity"],
            start_line=item["start_line"],
            end_line=item["end_line"],
            path=path,
            language="clojure",
            cover_start=item.get("cover_start", -1),
            cover_end=item.get("cover_end", -1),
        )
        for item in extract_functions(source, namespace)
    ]
