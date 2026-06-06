import re

INVALID_MANIM_METHODS = [
    "add_coordinate_labels",
    "move_arrow_to",
    "highlight_segment",
    "draw_text_box",
    "make_axis_grid",
    "mark_origin",
    "animate_point_path",
    "get_graph",
    "ShowCreation",
    "TexMobject",
    "TextMobject",
    "CircleGraph",
    "GraphScene",
    "always_redraw",
    "add_labels",
    "plot_function",
]


def check_for_invalid_manim_methods(script_code: str) -> list:
    """Scan the script for known invalid or hallucinated Manim methods."""
    violations = []
    for method in INVALID_MANIM_METHODS:
        pattern = rf"\b{re.escape(method)}\b"
        if re.search(pattern, script_code):
            violations.append(method)
    return violations


def check_layout_risk(script_code: str) -> tuple[bool, str]:
    """Flag scripts likely to produce overlapping labels."""
    text_count = len(re.findall(r"\bText\s*\(", script_code))
    arrange_count = len(re.findall(r"\.arrange\s*\(", script_code))
    next_to_count = len(re.findall(r"\.next_to\s*\(", script_code))
    vgroup_count = len(re.findall(r"\bVGroup\s*\(", script_code))

    if text_count >= 3 and arrange_count + next_to_count < 2:
        return (
            False,
            "Layout risk: use VGroup(...).arrange(DOWN/RIGHT, buff=0.6) and .next_to() "
            "for labels — do not stack Text objects at the same position",
        )
    if text_count >= 4 and vgroup_count == 0:
        return (
            False,
            "Layout risk: group related objects with VGroup before positioning",
        )
    return True, ""


def validate_script(script_code: str) -> tuple[bool, str]:
    """Validate Manim script syntax and API usage."""
    import ast

    if not script_code.strip():
        return False, "Empty script"

    if "class" not in script_code or "Scene" not in script_code:
        return False, "Script must define a Scene subclass"

    if "def construct" not in script_code:
        return False, "Scene must implement construct()"

    try:
        ast.parse(script_code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    invalids = check_for_invalid_manim_methods(script_code)
    if invalids:
        return False, f"Invalid Manim methods: {', '.join(invalids)}"

    layout_ok, layout_err = check_layout_risk(script_code)
    if not layout_ok:
        return False, layout_err

    return True, ""
