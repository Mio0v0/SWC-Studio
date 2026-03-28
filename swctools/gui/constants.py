from swctools.core.custom_types import get_custom_type_definition

APP_TITLE = "SWC Tools – Dendrogram Editor"

SWC_COLS = ["id", "type", "x", "y", "z", "radius", "parent"]

TYPE_LABEL = {
    0: "undefined",
    1: "soma",
    2: "axon",
    3: "basal dendrite",
    4: "apical dendrite",
}

DEFAULT_COLORS = {
    "undefined": "#636363",
    "soma": "#2ca02c",
    "axon": "#1a6ca7",
    "basal dendrite": "#ff0000",
    "apical dendrite": "#e377c2",
    "custom": "#ff7f0e",  # for types >= 5
}

# Distinct colors for identifying trees (up to 10)
TREE_COLORS = [
    "#5e353f", "#878714", "#6684f0", "#f58231", "#911eb4",
    "#00d0ff", "#e032f0", "#bfef45", "#fabed4", "#471212",
]

def label_for_type(t: int) -> str:
    t = int(t)
    if t in TYPE_LABEL:
        return TYPE_LABEL[t]
    if t < 0:
        return f"invalid type {t}"
    if t <= 4:
        return "custom"
    definition = get_custom_type_definition(t)
    if definition and str(definition.get("name", "")).strip():
        return str(definition["name"]).strip()
    return f"custom type {t}"

def color_for_type(t: int) -> str:
    t = int(t)
    if t <= 4:
        return DEFAULT_COLORS.get(label_for_type(t), DEFAULT_COLORS["custom"])
    definition = get_custom_type_definition(t)
    if definition and str(definition.get("color", "")).strip():
        return str(definition["color"]).strip()
    return DEFAULT_COLORS["custom"]
