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


def test_record_and_type_methods_are_type_dot_method():
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
        ("Doc.render", 3, 5, 7),
        ("Doc.title", 1, 8, 8),
        ("Doc.close", 1, 10, 10),
        ("Box.deref", 2, 13, 13),
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
        "String.area": (2, 3),
        "nil.area": (1, 6),
        "java.util.List.area": (1, 8),
        "java.util.List.perimeter": (2, 9),
    }


def test_reify_and_proxy_methods_count_where_they_live():
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
        "Drawable.draw": (2, 3),
        "Drawable.draw#2": (1, 4),
        "JPanel.paintComponent": (2, 7),
        "make": (2, 8),
    }
