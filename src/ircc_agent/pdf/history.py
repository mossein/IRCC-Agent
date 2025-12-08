"""Parser for extracting data from previously filled PDF forms."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from pypdf import PdfReader

from ircc_agent.pdf.extractor import FieldType, FormField, FormFieldExtractor, FormType

logger = logging.getLogger(__name__)


@dataclass
class FilledFormData:
    """Data extracted from a previously filled form."""

    form_path: Path
    form_type: FormType
    form_name: str  # e.g., "IMM5257" extracted from filename
    fields: dict[str, Any]  # field_name -> value
    field_metadata: dict[str, FormField]  # field_name -> full field info
    confidence: float = 1.0  # Historical forms are high confidence

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "form_path": str(self.form_path),
            "form_name": self.form_name,
            "form_type": self.form_type.value,
            "field_count": len(self.fields),
            "fields": self.fields,
        }


class FilledFormParser:
    """Parse previously filled PDF forms to extract field values."""

    def __init__(self, forms_directory: Path | str | None = None):
        """Initialize parser.

        Args:
            forms_directory: Directory containing historical filled forms.
        """
        self.forms_directory = Path(forms_directory) if forms_directory else None
        self._cache: dict[str, FilledFormData] = {}

    def parse_filled_form(self, pdf_path: Path | str) -> FilledFormData:
        """Extract all field values from a filled PDF form.

        Args:
            pdf_path: Path to the filled PDF form.

        Returns:
            FilledFormData with extracted values.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Check cache
        cache_key = str(pdf_path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Extract form name from filename (e.g., "IMM5257" from "imm5257e_filled.pdf")
        form_name = self._extract_form_name(pdf_path.name)

        # Use extractor to get field info
        extractor = FormFieldExtractor(pdf_path)
        fields = extractor.extract_fields()

        # Build field values dict
        field_values = {}
        field_metadata = {}

        for field in fields:
            if field.value is not None and str(field.value).strip():
                field_values[field.name] = field.value
                field_metadata[field.name] = field

        result = FilledFormData(
            form_path=pdf_path,
            form_type=extractor.form_type,
            form_name=form_name,
            fields=field_values,
            field_metadata=field_metadata,
        )

        self._cache[cache_key] = result
        logger.info(
            f"Parsed filled form '{form_name}': {len(field_values)} fields with values"
        )
        return result

    def _extract_form_name(self, filename: str) -> str:
        """Extract form identifier from filename.

        Examples:
            "imm5257e_filled.pdf" -> "IMM5257"
            "IMM_5257_application.pdf" -> "IMM5257"
            "visitor_visa_form.pdf" -> "VISITOR_VISA_FORM"
        """
        import re

        # Remove extension
        name = Path(filename).stem.upper()

        # Try to match IMM form pattern
        imm_match = re.search(r"IMM\s*_?\s*(\d+)", name)
        if imm_match:
            return f"IMM{imm_match.group(1)}"

        # Remove common suffixes
        for suffix in ["_FILLED", "_COMPLETE", "_SIGNED", "_FINAL"]:
            name = name.replace(suffix, "")

        return name.strip("_- ")

    def find_similar_forms(
        self,
        target_form: Path | str,
        search_directory: Path | str | None = None,
    ) -> list[FilledFormData]:
        """Find previously filled forms that match the target form.

        Args:
            target_form: Path to the form to be filled.
            search_directory: Directory to search for historical forms.

        Returns:
            List of matching filled forms, ordered by relevance.
        """
        target_form = Path(target_form)
        search_dir = Path(search_directory) if search_directory else self.forms_directory

        if not search_dir or not search_dir.exists():
            logger.warning("No search directory specified for historical forms")
            return []

        target_name = self._extract_form_name(target_form.name)
        matching_forms = []

        # Search for PDF files
        for pdf_file in search_dir.glob("**/*.pdf"):
            # Skip the target form itself
            if pdf_file.resolve() == target_form.resolve():
                continue

            try:
                form_name = self._extract_form_name(pdf_file.name)

                # Check if form names match
                if self._forms_match(target_name, form_name):
                    filled_data = self.parse_filled_form(pdf_file)

                    # Only include if it has filled values
                    if filled_data.fields:
                        matching_forms.append(filled_data)
                        logger.info(f"Found matching historical form: {pdf_file.name}")

            except Exception as e:
                logger.debug(f"Error parsing {pdf_file}: {e}")
                continue

        # Sort by number of filled fields (more is better)
        matching_forms.sort(key=lambda f: len(f.fields), reverse=True)

        return matching_forms

    def _forms_match(self, name1: str, name2: str) -> bool:
        """Check if two form names refer to the same form type."""
        # Direct match
        if name1 == name2:
            return True

        # Extract just the core form number
        import re

        def get_core(name: str) -> str:
            # Get numbers from IMM forms
            match = re.search(r"IMM(\d+)", name)
            if match:
                return match.group(1)
            return name

        return get_core(name1) == get_core(name2)

    def merge_historical_data(
        self,
        historical_forms: list[FilledFormData],
        target_fields: list[str],
    ) -> dict[str, Any]:
        """Merge data from multiple historical forms.

        Uses most recent form's data, with fallback to older forms.

        Args:
            historical_forms: List of historical form data (ordered by preference).
            target_fields: List of field names we need values for.

        Returns:
            Dictionary mapping field names to values from historical forms.
        """
        merged = {}

        # Process forms in order (first = highest priority)
        for form_data in historical_forms:
            for field_name in target_fields:
                if field_name not in merged and field_name in form_data.fields:
                    value = form_data.fields[field_name]
                    if value is not None and str(value).strip():
                        merged[field_name] = value

        logger.info(f"Merged {len(merged)} field values from historical forms")
        return merged


def find_historical_form_data(
    target_form: Path | str,
    search_directories: list[Path | str],
) -> dict[str, Any]:
    """Convenience function to find and merge historical form data.

    Args:
        target_form: The form to be filled.
        search_directories: Directories to search for historical forms.

    Returns:
        Dictionary of field values from historical forms.
    """
    parser = FilledFormParser()
    all_historical = []

    for directory in search_directories:
        directory = Path(directory)
        if directory.exists():
            historical = parser.find_similar_forms(target_form, directory)
            all_historical.extend(historical)

    if not all_historical:
        return {}

    # Get all unique field names
    all_fields = set()
    for form_data in all_historical:
        all_fields.update(form_data.fields.keys())

    return parser.merge_historical_data(all_historical, list(all_fields))
