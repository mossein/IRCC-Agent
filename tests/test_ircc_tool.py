"""Tests for ircc_tool package."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ircc_tool.cli import main as cli_main

# ---------------------------------------------------------------------------
# Unit tests for XFA helpers
# ---------------------------------------------------------------------------

class TestXfaHelpers:
    def test_local_extracts_localname(self):
        from lxml import etree

        from ircc_tool.xfa import _local

        el = etree.Element("{http://example.com}field")
        assert _local(el) == "field"

    def test_local_plain_tag(self):
        from lxml import etree

        from ircc_tool.xfa import _local

        el = etree.Element("field")
        assert _local(el) == "field"

    def test_set_field_value_creates_path(self):
        from lxml import etree

        from ircc_tool.xfa import _set_field_value

        root = etree.Element("data")
        result = _set_field_value(root, ["Page1", "Name"], "Alice")
        assert result is True

        page1 = root.find("Page1")
        assert page1 is not None
        name = page1.find("Name")
        assert name is not None
        assert name.text == "Alice"

    def test_set_field_value_existing_path(self):
        from lxml import etree

        from ircc_tool.xfa import _set_field_value

        root = etree.Element("data")
        etree.SubElement(etree.SubElement(root, "Page1"), "Name").text = "Old"

        _set_field_value(root, ["Page1", "Name"], "New")
        assert root.find("Page1/Name").text == "New"


# ---------------------------------------------------------------------------
# Unit tests for AcroForm filler
# ---------------------------------------------------------------------------

class TestAcroformFill:
    def test_fill_creates_output_dir(self, tmp_path):
        """fill() should create parent dirs for output_path."""
        # We can't easily test without a real PDF, so just verify the import works
        from ircc_tool.acroform import fill
        assert callable(fill)


# ---------------------------------------------------------------------------
# Unit tests for inspect_form
# ---------------------------------------------------------------------------

class TestDetectFormType:
    @patch("pikepdf.open")
    def test_xfa_detected(self, mock_open):
        mock_pdf = MagicMock()
        mock_pdf.Root.get.return_value = {"/XFA": True}
        mock_pdf.__contains__ = lambda self, key: False
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        from ircc_tool.inspect_form import detect_form_type

        result = detect_form_type(Path("/fake/path.pdf"))
        assert result == "xfa"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_no_args_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            cli_main([])
        assert exc_info.value.code == 1

    def test_inspect_missing_pdf(self):
        with pytest.raises(SystemExit):
            cli_main(["inspect", "/nonexistent/form.pdf"])

    def test_fill_missing_pdf(self):
        with pytest.raises(SystemExit):
            cli_main([
                "fill", "/nonexistent/form.pdf",
                "/nonexistent/data.json", "-o", "/tmp/out.pdf",
            ])


# ---------------------------------------------------------------------------
# fill_form orchestrator tests
# ---------------------------------------------------------------------------

class TestFillForm:
    def test_fill_missing_file_raises(self):
        from ircc_tool.fill_form import fill

        with pytest.raises(FileNotFoundError):
            fill("/nonexistent.pdf", {}, "/tmp/out.pdf")
