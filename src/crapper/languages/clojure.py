"""Clojure cyclomatic complexity, ported from crap4clj.

Decision points are the same forms crap4clj counts: `if` / `when` and their
variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`,
`case`, `cond->`, `cond->>`, `some->`, and `some->>`.
"""

import re

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
_TYPE_HEADS = ("defrecord", "deftype")
_DEF_HEADS = ("def", "defonce")
_ANON_HEADS = ("reify", "proxy")
_PREFIXES = ("#?@", "~@", "#?", "#'", "#=", "'", "`", "~", "@")


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
    return _end_of_one_form(text, index)


def _dispatch_end(text: str, index: int) -> int:
    """End of a `#`-dispatch form: set, anonymous fn, regex, namespaced map, conditional."""

    if text.startswith("#{", index) or text.startswith("#(", index):
        return _balanced_end(text, index + 1)
    if text.startswith('#"', index):
        return _consume_string(text, index + 1, 1)[0]
    if text.startswith("#:", index) or text.startswith("#?", index):
        return _child_end(text, _end_of_atom(text, index + 1))
    return _end_of_one_form(text, index)


def _children(form: str, start: int = 0) -> list[tuple[int, int]]:
    """Spans of the forms directly inside the list that opens at `start`."""

    spans = []
    index = start + 1
    while True:
        index = _skip_gap(form, index)
        if index >= len(form) or form[index] in ")]}":
            return spans
        end = _child_end(form, index)
        if end <= index:
            return spans
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


def _unit(form: str, base_line: int, span: tuple[int, int], name: str) -> dict:
    start, end = span
    first = base_line + form.count("\n", 0, start)
    last = first + form.count("\n", start, end)
    return {"name": name, "start_line": first, "end_line": last, "text": form[start:end]}


def _method_units(form, base_line, spans, type_name, protocols_are_types=False):
    """`Type.method` units for the method lists among `spans`.

    In `extend-protocol` the bare symbols name the type that the following
    methods extend; elsewhere they name a protocol or interface and the type
    stays `type_name`. A repeated name gets `#2`, `#3`, as overloads do.
    """

    units = []
    current = type_name
    seen: dict[str, int] = {}
    for span in spans:
        if _is_list(form, span):
            if current is None:
                continue
            method = _head(form, _children(form, _strip_meta(form, *span)[0]))
            if method is None:
                continue
            name = f"{current}.{method}"
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = f"{name}#{seen[name]}"
            units.append(_unit(form, base_line, span, name))
        elif protocols_are_types:
            symbol = _symbol(form, span)
            if symbol is not None:
                current = symbol
    return units


def _first_symbol_in_vector(form: str, span: tuple[int, int]) -> str | None:
    start, _end = _strip_meta(form, *span)
    if form[start] != "[":
        return None
    for child in _children(form, start):
        symbol = _symbol(form, child)
        if symbol is not None:
            return symbol
    return None


def _anonymous_units(form: str, base_line: int, span: tuple[int, int]) -> list[dict]:
    """Methods of a `reify` or `proxy` that is the value of a top-level `def`."""

    start, _end = _strip_meta(form, *span)
    if form[start] != "(":
        return []
    spans = _children(form, start)
    head = _head(form, spans)
    if head == "reify":
        return _reify_units(form, base_line, spans)
    if head == "proxy" and len(spans) >= 3:
        type_name = _first_symbol_in_vector(form, spans[1])
        if type_name is None:
            return []
        return _method_units(form, base_line, spans[3:], type_name)
    return []


def _reify_units(form: str, base_line: int, spans: list) -> list[dict]:
    units = []
    current = None
    for child in spans[1:]:
        if not _is_list(form, child):
            current = _symbol(form, child) or current
        elif current is not None:
            units.extend(_method_units(form, base_line, [child], current))
    return _renumber(units)


def _renumber(units: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    for unit in units:
        seen[unit["name"]] = seen.get(unit["name"], 0) + 1
        if seen[unit["name"]] > 1:
            unit["name"] = f"{unit['name']}#{seen[unit['name']]}"
    return units


def _dispatch_name(text: str, namespace: str | None) -> str:
    text = " ".join(text.split())
    if namespace and text.startswith("::") and "/" not in text:
        return f":{namespace}/{text[2:]}"
    return text


def _defmethod_unit(form, base_line, spans, namespace):
    if len(spans) < 3:
        return []
    multi = _symbol(form, spans[1])
    if multi is None:
        return []
    start, end = _strip_meta(form, *spans[2])
    dispatch = _dispatch_name(form[start:end], namespace)
    return [_unit(form, base_line, (0, len(form)), f"{multi} {dispatch}")]


def _form_units(form: str, base_line: int, namespace: str | None = None) -> list[dict]:
    """The scored units in one top-level form.

    `defn`, `defn-`, guardrails `>defn` / `>defn-`, and `defmacro` are one unit
    named for the var. `defmethod` is one unit named `multi dispatch-value`.
    The methods of `defrecord`, `deftype`, `extend-type`, `extend-protocol`,
    and of a `reify` or `proxy` that is a top-level `def` value, are one unit
    each, named `Type.method`. A `reify` or `proxy` inside a function stays
    part of that function.
    """

    if not form.startswith("("):
        return []
    name = _defn_name(form)
    if name is not None:
        return [{"name": name, "start_line": base_line,
                 "end_line": base_line + form.count("\n"), "text": form}]
    spans = _children(form)
    head = _head(form, spans)
    if head == "defmethod":
        return _defmethod_unit(form, base_line, spans, namespace)
    if head in _DEF_HEADS and len(spans) >= 3:
        return _anonymous_units(form, base_line, spans[-1])
    return _type_units(form, base_line, head, spans)


def _type_units(form: str, base_line: int, head: str | None, spans: list) -> list[dict]:
    """Method units of a type-defining form, or none for any other form."""

    if head in _TYPE_HEADS and len(spans) >= 3:
        return _method_units(form, base_line, spans[3:], _symbol(form, spans[1]))
    if head == "extend-type" and len(spans) >= 2:
        return _method_units(form, base_line, spans[2:], _symbol(form, spans[1]))
    if head == "extend-protocol" and len(spans) >= 2:
        return _method_units(form, base_line, spans[2:], None, protocols_are_types=True)
    return []


def _remember_form(
    forms: list[dict], source: str, start: int, start_line: int, end: int, line: int
) -> None:
    namespace = getattr(forms, "namespace", None)
    forms.extend(_form_units(source[start : end + 1], start_line, namespace))


class _Units(list):
    """The unit list, carrying the namespace that resolves `::keyword` dispatch values."""

    namespace: str | None = None


def _close_form(forms, source, depth, form_start, form_line, index, line):
    if depth == 1 and form_start is not None and form_line is not None:
        _remember_form(forms, source, form_start, form_line, index, line)
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


def _extract_top_level_defns(source: str, namespace: str | None = None) -> list[dict]:
    forms = _Units()
    forms.namespace = namespace
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
                forms, source, depth, form_start, form_line, index, line
            )
        if ch == "\n":
            line += 1
        index += 1
    return forms


def extract_functions(source: str, namespace: str | None = None) -> list[dict]:
    found = []
    for form in _extract_top_level_defns(source, namespace):
        found.append(
            {
                "name": form["name"],
                "start_line": form["start_line"],
                "end_line": form["end_line"],
                "complexity": cyclomatic_complexity(form["text"]),
            }
        )
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
        )
        for item in extract_functions(source, namespace)
    ]
