"""XFA parsing and filling using pikepdf + lxml for proper XML handling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pikepdf
from lxml import etree

# Common XFA namespaces
_XFA_NS = {
    "xfa": "http://www.xfa.org/schema/xfa-data/1.0/",
    "xdp": "http://ns.adobe.com/xdp/",
    "tpl": "http://www.xfa.org/schema/xfa-template/2.8/",
}


# ---------------------------------------------------------------------------
# Parsing (inspect)
# ---------------------------------------------------------------------------

def _get_xfa_streams(pdf: pikepdf.Pdf) -> dict[str, bytes]:
    """Extract named XFA streams from the PDF catalog."""
    acroform = pdf.Root.get("/AcroForm")
    if not acroform or "/XFA" not in acroform:
        return {}

    xfa = acroform["/XFA"]
    streams: dict[str, bytes] = {}
    current_name: str | None = None

    for item in xfa:
        if isinstance(item, pikepdf.String) or isinstance(item, pikepdf.Name):
            current_name = str(item)
        elif isinstance(item, pikepdf.Object):
            resolved = item
            if isinstance(resolved, pikepdf.Stream):
                if current_name:
                    streams[current_name] = resolved.read_bytes()
                    current_name = None
    return streams


def _walk_template_fields(
    element: etree._Element,
    path_prefix: str,
    fields: list[dict[str, Any]],
) -> None:
    """Recursively walk XFA template XML to extract field definitions."""
    tag = etree.QName(element.tag).localname if isinstance(element.tag, str) else ""
    name = element.get("name", "")

    current_path = f"{path_prefix}.{name}" if path_prefix and name else (path_prefix or name)

    if tag == "field":
        field_type = _detect_field_type(element)
        tooltip = _get_tooltip(element)
        options = _get_options(element)
        value = _get_value(element)

        fields.append({
            "name": name,
            "path": current_path,
            "type": field_type,
            "value": value,
            "options": options,
            "tooltip": tooltip or "",
            "required": False,
        })

    for child in element:
        _walk_template_fields(child, current_path, fields)


def _detect_field_type(element: etree._Element) -> str:
    """Determine XFA field type from <ui> children."""
    ui_tag_map = {
        "textEdit": "text",
        "checkButton": "checkbox",
        "choiceList": "dropdown",
        "dateTimeEdit": "date",
        "numericEdit": "number",
        "signature": "signature",
        "imageEdit": "image",
    }
    for child in element:
        if _local(child) == "ui":
            for ui_child in child:
                local = _local(ui_child)
                if local in ui_tag_map:
                    return ui_tag_map[local]
    return "text"


def _get_tooltip(element: etree._Element) -> str | None:
    for child in element:
        if _local(child) == "assist":
            for ac in child:
                if _local(ac) == "toolTip" and ac.text:
                    return ac.text
    return None


def _get_options(element: etree._Element) -> list[str]:
    options: list[str] = []
    for child in element:
        if _local(child) == "items":
            for item in child:
                if _local(item) == "text" and item.text:
                    options.append(item.text)
    return options


def _get_value(element: etree._Element) -> Any:
    for child in element:
        if _local(child) == "value":
            for vc in child:
                if vc.text:
                    return vc.text
    return None


def _local(el: etree._Element) -> str:
    return etree.QName(el.tag).localname if isinstance(el.tag, str) else ""


def parse_xfa_fields(pdf_path: Path) -> list[dict[str, Any]]:
    """Parse XFA template from a PDF and return a list of field dicts."""
    with pikepdf.open(pdf_path) as pdf:
        streams = _get_xfa_streams(pdf)

    if "template" not in streams:
        print("Warning: no XFA template stream found", file=sys.stderr)
        return []

    root = etree.fromstring(streams["template"])
    fields: list[dict[str, Any]] = []
    _walk_template_fields(root, "", fields)
    return fields


# ---------------------------------------------------------------------------
# Filling (write)
# ---------------------------------------------------------------------------

def fill(
    pdf_path: str | Path,
    field_values: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    """Fill an XFA PDF by modifying the datasets XML with proper lxml parsing.

    Returns a result dict: {filled_count, skipped, output_path}.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)

    acroform = pdf.Root.get("/AcroForm")
    if not acroform or "/XFA" not in acroform:
        pdf.close()
        raise ValueError("PDF does not contain an XFA form")

    xfa = acroform["/XFA"]

    # Locate the datasets stream object
    datasets_stream: pikepdf.Stream | None = None
    for i in range(0, len(xfa), 2):
        key = str(xfa[i])
        if key == "datasets":
            datasets_stream = xfa[i + 1]
            break

    if datasets_stream is None:
        pdf.close()
        raise ValueError("datasets stream not found in XFA array")

    # Read and parse XML
    xml_bytes = datasets_stream.read_bytes()
    root = etree.fromstring(xml_bytes)

    # The datasets element usually contains a <data> child.
    # Fields live inside <data> using a hierarchy matching the form structure.
    # We need to handle the namespace: the data element often has the xfa:datasets ns
    # but child data elements may be un-namespaced.
    data_el = _find_data_element(root)
    if data_el is None:
        pdf.close()
        raise ValueError("Could not locate <data> element inside datasets XML")

    filled = 0
    skipped: list[str] = []

    for field_path, value in field_values.items():
        if value is None or str(value).strip() == "":
            skipped.append(field_path)
            continue

        str_value = str(value)

        # field_path is like "form1.Page1.Section.FieldName"
        parts = field_path.split(".")

        if _set_field_value(data_el, parts, str_value):
            filled += 1
        else:
            skipped.append(field_path)

    # Write modified XML back to the stream.
    # Do NOT add an xml_declaration — this is an embedded stream inside the PDF,
    # not a standalone XML document. Adding <?xml?> causes Acrobat parse errors.
    new_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=False)
    datasets_stream.write(new_xml)

    pdf.save(output_path)
    pdf.close()

    return {
        "filled_count": filled,
        "skipped": skipped,
        "output_path": str(output_path),
    }


def _find_data_element(root: etree._Element) -> etree._Element | None:
    """Find the <data> element inside <datasets>, namespace-aware."""
    # Try common patterns
    for child in root:
        local = _local(child)
        if local == "data":
            return child

    # If root itself is <data> (unlikely but handle)
    if _local(root) == "data":
        return root

    return None


def _set_field_value(
    data_el: etree._Element,
    path_parts: list[str],
    value: str,
) -> bool:
    """Navigate path_parts inside data_el and set the leaf element's text.

    Creates intermediate elements if they don't exist.
    Returns True if the value was set.
    """
    current = data_el

    for part in path_parts:
        found = None
        for child in current:
            if _local(child) == part:
                found = child
                break

        if found is None:
            # Create missing element (unnamespaced, as XFA data children are)
            found = etree.SubElement(current, part)

        current = found

    current.text = value
    return True
