"""Compact planner XML and conservative label-anchored Android button locators."""

from collections import Counter
from xml.etree import ElementTree as ET

from ..contracts import ObservedElement

SLIDER_CLASSES = {"android.widget.SeekBar", "XCUIElementTypeSlider"}


def scoped_slider_locator(node, parents, visible, counts: dict[str, Counter]) -> str | None:
    """Resolve sliders through unique identifiers or bounded container anchors.

    Duplicate IDs are common in WebViews. Keep uniqueness guards in the XPath;
    never fall back to an ordinal or a stored screen coordinate.
    """
    class_name = node.get("class") or node.get("type") or node.tag
    if class_name not in SLIDER_CLASSES:
        return None
    class_attribute = "class" if node.get("class") else "type"
    predicate = f"@{class_attribute}={xpath_literal(class_name)}"
    for attribute in ("resource-id", "content-desc", "text", "name"):
        value = node.get(attribute, "").strip()
        if value and counts[attribute][value] == 1:
            match = f"//*[{predicate} and @{attribute}={xpath_literal(value)}]"
            return f"{match}[count({match})=1]"

    container = parents.get(node)
    for _ in range(4):
        if container is None:
            break
        for anchor_node in [container, *list(container)]:
            if id(anchor_node) not in visible:
                continue
            for attribute in ("resource-id", "content-desc", "text", "name"):
                value = anchor_node.get(attribute, "").strip()
                if not value or counts[attribute][value] != 1:
                    continue
                anchor = f"//*[@{attribute}={xpath_literal(value)}]"
                scope = f"{anchor}[count({anchor})=1]"
                if anchor_node is not container:
                    scope += "/parent::*"
                for axis, path, candidates in (
                    (".//*", "//*", list(container.iter())[1:]),
                    ("./*", "/*", list(container)),
                ):
                    matches = [x for x in candidates
                               if (x.get("class") or x.get("type") or x.tag) == class_name]
                    if len(matches) == 1 and matches[0] is node:
                        return f"{scope}[count({axis}[{predicate}])=1]{path}[{predicate}]"
        container = parents.get(container)
    return None


def scoped_button_locator(node, parents, visible, text_counts: Counter) -> str | None:
    """Disambiguate a named button using a unique direct label on its card.

    Bound ancestor search to four levels. Require one matching button within the
    container, and retain both uniqueness guards in the executable XPath.
    """
    if node.get("class") != "android.widget.Button" or node.get("clickable") != "true":
        return None
    attribute = "content-desc" if node.get("content-desc") else "text"
    name = node.get(attribute)
    if not name:
        return None
    predicate = (f"@class='android.widget.Button' and @{attribute}={xpath_literal(name)}"
                 " and @clickable='true' and @enabled='true'")
    container = parents.get(node)
    for _ in range(4):
        if container is None:
            break
        matches = [x for x in container.iter()
                   if x.get("class") == "android.widget.Button" and x.get(attribute) == name
                   and x.get("clickable") == "true" and x.get("enabled") == "true"]
        if len(matches) == 1 and matches[0] is node:
            for label in container:
                text = label.get("text", "")
                if (id(label) in visible and text.strip() and text_counts[text.strip()] == 1
                        and label.get("clickable") != "true"):
                    anchor = f"//*[@text={xpath_literal(text)}]"
                    return (f"{anchor}[count({anchor})=1]/parent::*"
                            f"[count(.//*[{predicate}])=1]//*[{predicate}]")
        container = parents.get(container)
    return None


def structural_button_locator(node, parents, visible, text_counts: Counter) -> str | None:
    """Only an unlabeled direct button in a single-control, labeled container.

    No nearest-neighbor geometry or absolute indexes. The generated XPath keeps
    label uniqueness and single-control guards when Appium evaluates it again.
    """
    if (node.get("clickable") != "true" or node.get("class") != "android.widget.Button"
            or node.get("text") or node.get("content-desc") or node.get("resource-id")):
        return None
    container = parents.get(node)
    if container is None:
        return None
    controls = [item for item in container.iter() if item.get("clickable") == "true"]
    if len(controls) != 1 or controls[0] is not node:
        return None
    # Search only this immediate container, not arbitrary ancestors of the page.
    for label in container.iter():
        text = label.get("text", "").strip()
        if id(label) not in visible or not text or text_counts[text] != 1:
            continue
        hops = 0
        current = label
        while current is not container and current in parents:
            hops += 1
            current = parents[current]
        if current is not container or not 1 <= hops <= 6:
            continue
        anchor = f"//*[@text={xpath_literal(label.get('text'))}]"
        return (
            f"{anchor}[count({anchor})=1]" + "/parent::*" * hops
            + "[count(.//*[@clickable='true'])=1]"
            + "/*[@class='android.widget.Button' and @clickable='true' and @enabled='true']"
        )
    return None


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in value.split("'")) + ")"


def compact_xml(root, visible: set[int], targets: dict[int, ObservedElement]) -> str:
    """Drop unused metadata and unary wrappers, but retain branching structure."""
    def visit(node):
        if id(node) not in visible:
            return None
        children = [result for child in node if (result := visit(child)) is not None]
        target = targets.get(id(node))
        if target is None and len(children) == 1:
            return children[0]
        if target is None and not children:
            return None
        result = ET.Element("container" if target is None else "element")
        if target:
            result.attrib.update({
                "ref": target.ref, "class": target.class_name.rsplit(".", 1)[-1],
                "clickable": str(target.clickable).lower(),
                "executable": str(target.executable).lower(),
                "enabled": str(target.enabled).lower(),
            })
            for key, value in (("text", target.text), ("description", target.accessibility_id),
                               ("bounds", node.get("bounds", ""))):
                if value:
                    result.set(key, value)
            if target.checked is not None:
                result.set("checked", str(target.checked).lower())
            if target.toggles_state:
                result.set("toggles_state", "true")
            if target.is_slider:
                result.set("slider", "true")
                if target.slider_value_hint:
                    result.set("value_hint", target.slider_value_hint)
        result.extend(children)
        return result

    tree = visit(root)
    return ET.tostring(tree, encoding="unicode") if tree is not None else "<container />"
