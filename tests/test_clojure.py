from crapper.languages.clojure import (
    cyclomatic_complexity,
    extract_functions,
    functions_in_source,
    namespace_from_path,
)


def test_base_and_branch_forms():
    assert cyclomatic_complexity("(defn foo [])") == 1
    assert cyclomatic_complexity("(defn foo [x]\n  (+ x 1))") == 1
    assert cyclomatic_complexity("(defn foo [x]\n  (if x 1 0))") == 2
    assert cyclomatic_complexity("(defn foo [x]\n  (if-not x 1 0))") == 2
    assert cyclomatic_complexity("(defn foo [x]\n  (if-let [y x] y 0))") == 2
    assert cyclomatic_complexity("(defn foo [x]\n  (when x 1))") == 2
    assert cyclomatic_complexity("(defn foo [x]\n  (when-first [y x] y))") == 2
    assert cyclomatic_complexity("(defn foo [x y]\n  (and x y))") == 2
    assert cyclomatic_complexity("(defn foo [x y]\n  (or x y))") == 2
    assert cyclomatic_complexity("(defn foo [x]\n  (loop [i 0] (recur (inc i))))") == 2


def test_cond_case_and_threading():
    assert (
        cyclomatic_complexity("(defn foo [x]\n  (cond\n    (= x 1) :one\n    :else :other))")
        == 3
    )
    assert cyclomatic_complexity("(defn foo [x]\n  (condp = x\n    1 :one\n    2 :two))") == 3
    assert cyclomatic_complexity("(defn foo [x]\n  (case x\n    1 :one\n    :other))") == 3
    assert (
        cyclomatic_complexity(
            "(defn foo [x]\n  (cond-> x\n    (pos? x) inc\n    (even? x) (* 2)))"
        )
        == 3
    )
    assert cyclomatic_complexity("(defn foo [x]\n  (some-> x inc dec))") == 3
    assert (
        cyclomatic_complexity("(defn foo [x]\n  (some->> x (map inc) (filter pos?)))") == 3
    )


def test_ignores_decisions_in_strings_and_comments():
    assert cyclomatic_complexity('(defn foo [x]\n  "if when cond and or"\n  x)') == 1
    assert cyclomatic_complexity('(defn foo [x]\n  "(if true 1 0)"\n  x)') == 1
    assert cyclomatic_complexity('(defn foo [x]\n  ;; if when cond\n  x)') == 1
    assert cyclomatic_complexity('(defn foo [x]\n  (if x :yes :no) ; and or when cond)') == 2


def test_map_literals_inside_cond_are_not_extra_clauses():
    source = """(defn foo [cell]
  (let [contents (:contents cell)]
    (cond
      (pred-a? contents)
      {:type :army :mode :awake :owner (:owner contents) :aboard true}

      (pred-b? contents)
      {:type :fighter :mode :awake :owner (:owner contents) :fuel 20 :from-carrier true}

      (pred-c? contents) contents

      (pred-d? cell)
      {:type :fighter :mode :awake :owner :player :fuel 20 :from-airport true}

      :else nil)))"""
    assert cyclomatic_complexity(source) == 6


def test_extracts_defn_names_lines_and_namespace():
    source = "(ns demo.core)\n\n(defn choose [x]\n  (if x 1 0))\n\n(defn- hidden [y]\n  y)\n"
    found = functions_in_source(source, "src/demo/core.clj", "/proj")
    assert [(item.name, item.complexity, item.start_line) for item in found] == [
        ("choose", 2, 3),
        ("hidden", 1, 6),
    ]
    assert {item.namespace for item in found} == {"demo.core"}


def test_top_level_def_does_not_attach_to_the_previous_function():
    source = (
        "(defn alpha [x]\n"
        "  (if x 1 0))\n\n"
        "(def rules\n"
        "  [{:pred (fn [v]\n"
        "            (if v (when (pos? v) true) false))}])\n\n"
        "(defn omega [y]\n"
        "  y)"
    )
    found = {item["name"]: item["complexity"] for item in extract_functions(source)}
    assert found == {"alpha": 2, "omega": 1}


def test_namespace_falls_back_to_the_path():
    assert namespace_from_path("src/demo/core_extra.clj", None) == "demo.core-extra"
    assert namespace_from_path("/proj/src/demo/core.cljc", "/proj") == "demo.core"
    assert namespace_from_path("pkg/src/demo/core.bb", None) == "demo.core"
    found = functions_in_source("(defn foo [] 1)\n", "src/demo/core_extra.clj", "/proj")
    assert found[0].namespace == "demo.core-extra"


def test_strings_comments_and_character_literals_stay_inside_one_form():
    source = '(defn foo [x]\n  "say \\"hi\\"\n  (if x 1)"\n  \\space\n  ;; (defn hidden [])\n  x)\n'
    assert [item["name"] for item in extract_functions(source)] == ["foo"]


def test_discards_and_metadata_cover_each_reader_form():
    source = r"""
#_
; gone
(defn ghost [] (if x 1 0))
#_ "string"
#_ \x
#_ symbol
#_ #_(defn inner [] (if x 1 0))
#_(defn boxed []
  "str"
  \;
  ; comment
  (if x 1 0))
(defn ^{:doc "hi" :private true} kept [] 1)
(defn ^{:flag \; :private true} also [] 1)
(defn ^{:private true ; note
  } third [] 1)
( defn spaced [] 1)
(defn)
(defn ^)
"""
    assert [item["name"] for item in extract_functions(source)] == [
        "kept",
        "also",
        "third",
        "spaced",
    ]
    assert extract_functions("(defn ^{:private kept [] 1)") == []


def test_character_literals_do_not_swallow_the_next_defn():
    source = '(def x #{\\"})\n(defn foo [] 1)'
    assert [item["name"] for item in extract_functions(source)] == ["foo"]


def test_reader_keeps_the_real_namespace_name_and_decisions():
    source = r""";; (ns demo.wrong)
(ns demo.core)
#_(defn dropped [x]
  (if x 1 0))
(defn ^:private kept [x]
  #_(if x 1 0)
  1)
(defn ^{:private true} also [] 1)
(defn quoted []
  \"
  (if x 1 0))
(defn semi []
  \;
  (if true 1 2))
"""
    found = functions_in_source(source, "src/demo/core.clj", "/proj")
    assert [(item.name, item.complexity) for item in found] == [
        ("kept", 1),
        ("also", 1),
        ("quoted", 2),
        ("semi", 2),
    ]
    assert {item.namespace for item in found} == {"demo.core"}
    assert cyclomatic_complexity(r'(defn semi [] \; (if true 1 2))') == 2
    assert cyclomatic_complexity(r'(defn quoted [] \" (if x 1 0))') == 2
    assert extract_functions("#_(defn dropped [] (if x 1 0))\n(defn kept [] 1)\n") == [
        {"name": "kept", "start_line": 2, "end_line": 2, "complexity": 1}
    ]


def test_defmethod_is_one_unit_named_for_multi_and_dispatch_value():
    source = (
        "(ns demo.core)\n"
        "(defmulti handle-event :type)\n"
        "(defmethod handle-event ::render [e]\n"
        "  (if (:page e) (when (pos? (:page e)) 1) 0))\n"
        "(defmethod handle-event :default [_] nil)\n"
        "(defmethod ^:private other/area [:circle :big]\n"
        "  [s] (* 3 s))\n"
    )
    found = functions_in_source(source, "src/demo/core.clj", "/proj")
    assert [(f.name, f.complexity, f.start_line, f.end_line) for f in found] == [
        ("handle-event :demo.core/render", 3, 3, 4),
        ("handle-event :default", 1, 5, 5),
        ("other/area [:circle :big]", 1, 6, 7),
    ]


def test_guardrails_defn_and_defmacro_are_units():
    source = (
        "(>defn get-page [] [=> int?] (or (:page @s) 0))\n"
        "(>defn- hidden [x] [int? => int?]\n  (if x 1 0))\n"
        "(defmacro timed [& body]\n  `(let [t0# 1] ~@body))\n"
    )
    found = {item["name"]: item["complexity"] for item in extract_functions(source)}
    assert found == {"get-page": 2, "hidden": 2, "timed": 1}


def test_record_and_type_methods_are_type_protocol_method():
    source = (
        "(ns demo.render)\n"
        "(defrecord Doc [handle items]\n"
        "  ;; protocol\n"
        "  Renderer\n"
        "  (render [this n]\n"
        "    (when (< n (count items))\n"
        "      (if (pos? n) :a :b)))\n"
        "  (title [_ n] \"(if x)\")\n"
        "  java.io.Closeable\n"
        "  (close [_] (.close handle)))\n"
        "(deftype Box [v]\n"
        "  clojure.lang.IDeref\n"
        "  (deref [_] (or v 0)))\n"
    )
    found = functions_in_source(source, "src/demo/render.clj", "/proj")
    assert [(f.name, f.complexity, f.start_line, f.end_line) for f in found] == [
        ("Doc.Renderer.render", 3, 5, 7),
        ("Doc.Renderer.title", 1, 8, 8),
        ("Doc.java.io.Closeable.close", 1, 10, 10),
        ("Box.clojure.lang.IDeref.deref", 2, 13, 13),
    ]
    assert {f.namespace for f in found} == {"demo.render"}


def test_extend_type_and_extend_protocol_methods():
    source = (
        "(extend-type String\n"
        "  Shape\n"
        "  (area [s] (if (empty? s) 0 1)))\n"
        "(extend-protocol Shape\n"
        "  nil\n"
        "  (area [_] 0)\n"
        "  java.util.List\n"
        "  (area [xs] (count xs))\n"
        "  (perimeter [xs] (when (seq xs) 1)))\n"
    )
    found = {item["name"]: (item["complexity"], item["start_line"]) for item in extract_functions(source)}
    assert found == {
        "String.Shape.area": (2, 3),
        "nil.Shape.area": (1, 6),
        "java.util.List.Shape.area": (1, 8),
        "java.util.List.Shape.perimeter": (2, 9),
    }


def test_reify_and_proxy_methods_are_named_for_their_var():
    source = (
        "(def ^:private no-op\n"
        "  (reify Drawable\n"
        "    (draw [_ g] (when g 1))\n"
        "    (draw [_ g x] nil)))\n"
        "(defonce panel\n"
        "  (proxy [JPanel Runnable] []\n"
        "    (paintComponent [g] (if g 1 0))))\n"
        "(defn make []\n"
        "  (reify Runnable (run [_] (if a 1 0))))\n"
        "(def plain {:a 1})\n"
    )
    found = {item["name"]: (item["complexity"], item["start_line"]) for item in extract_functions(source)}
    assert found == {
        "no-op.Drawable.draw": (2, 3),
        "no-op.Drawable.draw#2": (1, 4),
        "panel.paintComponent": (2, 7),
        "make": (2, 8),
    }


def test_child_end_spans_each_dispatch_and_prefix_form():
    from crapper.languages.clojure import _child_end

    for form in ('#{1 2}', '#(inc %)', '#"a\\"b"', "#:ns{:a 1}", "#?(:clj 1)",
                 '#inst "2020"', "#my/tag [1 2]", "##Inf", "^:m [x]", "'(a b)",
                 "~@xs", "sym", ":k"):
        assert _child_end(f"{form} tail", 0) == len(form), form
        assert _child_end(f"{form}, tail", 0) == len(form), form
    assert _child_end("", 0) == 0


def _names(source, namespace=None):
    return {item["name"]: item["complexity"] for item in extract_functions(source, namespace)}


def test_discarded_and_empty_forms_inside_a_type_are_not_methods():
    source = (
        "(deftype T [] P\n"
        "  #_(skipped [x] (if x 1 0))\n"
        "  ()\n"
        "  (\"text\" [x] 1)\n"
        "  (kept [x] (when x 1)))\n"
        "()\n"
    )
    assert _names(source) == {"T.P.kept": 2}


def test_methods_before_any_protocol_or_type_are_skipped():
    source = (
        "(extend-protocol P\n"
        "  (orphan [x] 1)\n"
        '  "text"\n'
        "  (also-orphan [x] 2)\n"
        "  String\n"
        "  (m [x] 3))\n"
        "(defrecord R [] (orphan [_] 1) Q (m [_] 2))\n"
        "(def r (reify (orphan [x] 1) Foo (m [x] (if x 1 0))))\n"
    )
    assert _names(source) == {"String.P.m": 1, "R.Q.m": 1, "r.Foo.m": 2}


def test_type_forms_without_a_symbol_owner_have_no_units():
    for source in ('(defrecord "R" [] P (m [_] 1))', "(extend-type)",
                   "(extend-protocol :p String (m [_] 1))", "(deftype T)"):
        assert _names(source) == {}, source


def test_repeated_method_names_get_numbered_suffixes():
    source = "(extend-type String P (m [x] 1) (m [x y] (if x 1 0)))"
    assert _names(source) == {"String.P.m": 1, "String.P.m#2": 2}


def test_def_value_that_is_not_reify_or_proxy_has_no_units():
    assert _names("(def x (foo 1 2))") == {}
    assert _names("(def x :k)") == {}
    assert _names('(def "x" (reify P (m [_] 1)))') == {}
    assert _names("(def p (proxy [Foo]))") == {}
    assert _names("(def p (proxy Foo [] (m [x] 1)))") == {"p.m": 1}


def test_defmethod_needs_a_symbol_multimethod_and_a_dispatch_value():
    assert _names("(defmethod area)") == {}
    assert _names('(defmethod "area" :a [x] 1)') == {}


def test_string_dispatch_values_keep_their_contents():
    source = (
        '(defmethod m "a b" [_] 1)\n'
        '(defmethod m "a  b" [_] 2)\n'
        '(defmethod m "a\n  b" [_] 3)\n'
        '(defmethod m "a\\n  b" [_] 4)\n'
        '(defmethod m "x;y,z" [_] 5)\n'
    )
    assert list(_names(source)) == [
        'm "a b"', 'm "a  b"', 'm "a\\n  b"', 'm "a\\n  b"#2', 'm "x;y,z"',
    ]


def test_dispatch_whitespace_commas_and_comments_are_normalized_outside_strings():
    source = (
        "(defmethod m [:a, :b] [_] 1)\n"
        "(defmethod m [ :a\n   :b ] [_] 2)\n"
        "(defmethod m [:a ; note\n :b #_:c] [_] 3)\n"
        "(defmethod m #{\\a \\space} [_] 4)\n"
    )
    assert list(_names(source)) == [
        "m [:a :b]", "m [:a :b]#2", "m [:a :b]#3", "m #{\\a \\space}",
    ]


def test_tagged_literal_dispatch_keeps_its_payload():
    source = '(defmethod m #inst "2020" [_] 1)\n(defmethod m #my/tag [1  2] [x] (if x 1 0))\n'
    assert _names(source) == {'m #inst "2020"': 1, "m #my/tag [1 2]": 2}


def test_duplicate_defmethods_are_numbered_like_repeated_methods():
    assert _names("(defmethod m :a [_] 1)\n(defmethod m :a [_] 2)") == {"m :a": 1, "m :a#2": 1}


def test_auto_resolved_keywords_resolve_to_one_name():
    source = (
        "(ns demo.core\n"
        "  (:require [demo.other :as o]\n"
        "            [demo.spec :refer [x] :as-alias sp]\n"
        "            (demo [util :as u])\n"
        "            [plain.lib]\n"
        "            [] plain.sym))\n"
        "(defmethod m ::k [_] 1)\n"
        "(defmethod m :demo.core/k [_] 2)\n"
        "(defmethod m ::o/k [_] 3)\n"
        "(defmethod m [::sp/k ::u/k] [_] 4)\n"
        "(defmethod m ::nope/k [_] 5)\n"
    )
    assert list(_names(source, "demo.core")) == [
        "m :demo.core/k", "m :demo.core/k#2", "m :demo.other/k",
        "m [:demo.spec/k :demo.util/k]", "m ::nope/k",
    ]
    assert list(_names("(defmethod m ::k [_] 1)")) == ["m ::k"]
    assert list(_names("(ns a.b)\n(defmethod m ::o/k [_] 1)", "a.b")) == ["m ::o/k"]
    assert list(_names("(ns)\n(defmethod m :k [_] 1)")) == ["m :k"]


def test_top_level_reify_and_proxy_of_different_vars_do_not_collide():
    source = (
        "(def a (reify P (m [_] 1)))\n(def b (reify P (m [_] 2)))\n"
        "(def c (proxy [Foo] [] (m [] 1)))\n(def d (proxy [Foo] [] (m [] 2)))\n"
    )
    assert list(_names(source)) == ["a.P.m", "b.P.m", "c.m", "d.m"]


def test_same_method_of_different_protocols_does_not_collide():
    source = (
        "(defrecord R [] P (m [_] 1) Q (m [_] 2))\n"
        "(extend-type String P (m [_] 1))\n"
        "(extend-type String Q (m [_] 2))\n"
    )
    assert list(_names(source)) == ["R.P.m", "R.Q.m", "String.P.m", "String.Q.m"]


def test_type_hints_and_metadata_stay_out_of_method_names():
    source = (
        "(defrecord R [] P (^String m [_] 1))\n"
        "(deftype T [] P (^{:tag String} m [_] 1) ^:x (n [_] 2))\n"
    )
    assert list(_names(source)) == ["R.P.m", "T.P.m", "T.P.n"]


def test_method_names_are_not_counted_as_decisions():
    source = "(defrecord R [] P (when [_] 1) (or [_] (if x 1 2)) (catch [_] (and a b)))"
    assert _names(source) == {"R.P.when": 1, "R.P.or": 2, "R.P.catch": 2}


def test_methods_inside_reader_conditionals_are_units():
    source = (
        "(deftype T [] P\n"
        "  #?(:clj (m [_] 1))\n"
        "  #?@(:clj [Q (n [_] (if x 1 0))])\n"
        "  #?(:clj (o [_] 1) :cljs (o [_] 2))\n"
        "  #?@(:clj sym)\n"
        "  #?x)\n"
        "(def r (reify #?@(:clj [Runnable (run [_] 1)] :cljs [IFn (-invoke [_] 2)])))\n"
    )
    assert _names(source) == {
        "T.P.m": 1, "T.Q.n": 2, "T.Q.o": 1, "T.Q.o#2": 1,
        "r.Runnable.run": 1, "r.IFn.-invoke": 1,
    }


def test_methods_get_only_the_lines_they_do_not_share():
    source = (
        "(deftype T [x] P (a [_] 1)\n"
        "  (b [_]\n"
        "    (if x 1 2))\n"
        "  (c [_]\n"
        "    3) (d [_] 4))\n"
    )
    lines = {
        item["name"]: (item["start_line"], item["end_line"], item["cover_start"], item["cover_end"])
        for item in extract_functions(source)
    }
    assert lines == {
        "T.P.a": (1, 1, 1, 1),
        "T.P.b": (2, 3, 2, 3),
        "T.P.c": (4, 5, 4, 4),
        "T.P.d": (5, 5, 5, 5),
    }
    assert "cover_start" not in extract_functions("(defn f [] 1)")[0]
