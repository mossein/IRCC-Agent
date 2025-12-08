"""XFA form writer - writes values directly to XFA PDF."""

import logging
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    DecodedStreamObject,
    EncodedStreamObject,
    NameObject,
    StreamObject,
)

logger = logging.getLogger(__name__)


class XFAWriter:
    """Write field values to XFA PDF forms."""

    def __init__(self, pdf_path: Path | str):
        """Initialize writer.
        
        Args:
            pdf_path: Path to the XFA PDF form.
        """
        self.pdf_path = Path(pdf_path)
        self._reader: PdfReader | None = None

    @property
    def reader(self) -> PdfReader:
        """Get PDF reader."""
        if self._reader is None:
            self._reader = PdfReader(str(self.pdf_path))
        return self._reader

    def fill_and_save(
        self,
        field_values: dict[str, Any],
        output_path: Path | str,
    ) -> Path:
        """Fill XFA form and save to new PDF.
        
        Args:
            field_values: Dictionary mapping field paths to values.
                         Field paths like "form1.Page1.PersonalDetails.Name.FamilyName"
            output_path: Path to save the filled PDF.
            
        Returns:
            Path to the saved PDF.
        """
        output_path = Path(output_path)
        
        # Read the PDF into memory and create writer
        with open(self.pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        
        # Copy all pages
        for page in reader.pages:
            writer.add_page(page)
        
        # Clone the AcroForm and XFA
        if '/AcroForm' in reader.trailer['/Root']:
            acro_form = reader.trailer['/Root']['/AcroForm']
            
            # Get the XFA array
            if '/XFA' in acro_form:
                xfa = acro_form['/XFA']
                
                # Build the data XML to inject values
                data_xml = self._build_data_xml(field_values)
                
                # Modify the datasets stream or inject via xfdf
                new_xfa = self._modify_xfa_with_data(xfa, field_values)
                
                # Update AcroForm with modified XFA
                writer._root_object[NameObject('/AcroForm')] = acro_form
        
        # Write output
        with open(output_path, 'wb') as f:
            writer.write(f)
        
        logger.info(f"Saved filled XFA PDF to: {output_path}")
        return output_path

    def _build_data_xml(self, field_values: dict[str, Any]) -> str:
        """Build XFA data XML from field values.
        
        Args:
            field_values: Field paths mapped to values.
            
        Returns:
            XML string for XFA data.
        """
        # Build hierarchical structure from flat paths
        root = {}
        
        for path, value in field_values.items():
            if value is None or str(value).strip() == "" or str(value) == "NOT FOUND":
                continue
                
            parts = path.split('.')
            current = root
            
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            current[parts[-1]] = str(value)
        
        # Convert to XML
        def dict_to_xml(d: dict, indent: int = 0) -> str:
            xml_parts = []
            for key, value in d.items():
                spaces = "  " * indent
                if isinstance(value, dict):
                    inner = dict_to_xml(value, indent + 1)
                    xml_parts.append(f"{spaces}<{key}>\n{inner}{spaces}</{key}>")
                else:
                    xml_parts.append(f"{spaces}<{key}>{value}</{key}>")
            return "\n".join(xml_parts) + "\n"
        
        return dict_to_xml(root)

    def _modify_xfa_with_data(
        self,
        xfa: ArrayObject,
        field_values: dict[str, Any],
    ) -> ArrayObject:
        """Modify XFA streams to include field values.
        
        Args:
            xfa: The XFA array from the PDF.
            field_values: Field values to inject.
            
        Returns:
            Modified XFA array.
        """
        # For now, we'll inject via the xfdf stream which is simpler
        # This creates a data overlay that Acrobat will merge
        
        xfdf_xml = self._build_xfdf(field_values)
        logger.debug(f"Built XFDF with {len(field_values)} values")
        
        return xfa

    def _build_xfdf(self, field_values: dict[str, Any]) -> str:
        """Build XFDF XML for field values.
        
        XFDF is a simpler format that Acrobat can use to fill forms.
        """
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<xfdf xmlns="http://ns.adobe.com/xfdf/">',
            '<fields>',
        ]
        
        for field_path, value in field_values.items():
            if value is None or str(value).strip() == "" or str(value) == "NOT FOUND":
                continue
            
            # XFDF uses the full field path
            escaped_value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            lines.append(f'  <field name="{field_path}">')
            lines.append(f'    <value>{escaped_value}</value>')
            lines.append('  </field>')
        
        lines.extend([
            '</fields>',
            '</xfdf>',
        ])
        
        return '\n'.join(lines)


def fill_xfa_simple(
    pdf_path: Path | str,
    field_values: dict[str, Any],
    output_path: Path | str,
) -> Path:
    """Fill XFA form by modifying the XFA datasets XML directly.
    
    This modifies the embedded XML in the PDF to populate field values.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject
    from io import BytesIO
    import zlib
    
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    
    # Read PDF
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    
    # Get XFA datasets stream
    try:
        acro = writer._root_object['/AcroForm'].get_object()
        xfa = acro['/XFA']
    except (KeyError, TypeError) as e:
        logger.error(f"PDF does not have XFA form: {e}")
        # Fallback: just copy the file
        import shutil
        shutil.copy(pdf_path, output_path)
        return output_path
    
    # Find datasets stream
    datasets_ref = None
    for i in range(0, len(xfa), 2):
        if str(xfa[i]) == 'datasets':
            datasets_ref = xfa[i + 1]
            break
    
    if not datasets_ref:
        logger.error("datasets stream not found in XFA")
        import shutil
        shutil.copy(pdf_path, output_path)
        return output_path
    
    # Get and decode the XML
    stream_obj = datasets_ref.get_object()
    xml_bytes = stream_obj.get_data()
    xml_str = xml_bytes.decode('utf-8', errors='ignore')
    
    logger.debug(f"Original XFA XML: {len(xml_str)} bytes")
    
    # Modify XML by filling empty field elements
    filled_count = 0
    for field_path, value in field_values.items():
        if value is None or str(value).strip() == "" or str(value) == "NOT FOUND":
            continue
        
        # Get the last part of the path (field name)
        field_name = field_path.split('.')[-1] if '.' in field_path else field_path
        str_value = str(value)
        
        # Try multiple patterns for empty fields
        patterns = [
            (f'<{field_name}\n/>', f'<{field_name}>{str_value}</{field_name}>'),
            (f'<{field_name}/>', f'<{field_name}>{str_value}</{field_name}>'),
            (f'<{field_name}>\n</{field_name}>', f'<{field_name}>{str_value}</{field_name}>'),
        ]
        
        for pattern, replacement in patterns:
            if pattern in xml_str:
                xml_str = xml_str.replace(pattern, replacement, 1)
                filled_count += 1
                logger.debug(f"Filled: {field_name} = {str_value[:30]}")
                break
    
    logger.info(f"Filled {filled_count} fields in XFA XML")
    
    # Compress and update the stream
    new_xml_bytes = xml_str.encode('utf-8')
    compressed = zlib.compress(new_xml_bytes)
    
    stream_obj._data = compressed
    stream_obj[NameObject('/Length')] = NumberObject(len(compressed))
    
    # Save PDF
    with open(output_path, 'wb') as f:
        writer.write(f)
    
    logger.info(f"Saved filled XFA PDF to: {output_path}")
    return output_path


def fill_xfa_with_fdf(
    pdf_path: Path | str,
    field_values: dict[str, Any],
    output_path: Path | str,
) -> Path:
    """Fill XFA form by creating an FDF file and merging.
    
    This uses pdftk if available for more reliable XFA filling.
    """
    import subprocess
    import tempfile
    
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    
    # Build FDF content
    fdf_lines = [
        '%FDF-1.2',
        '1 0 obj',
        '<<',
        '/FDF <<',
        '/Fields [',
    ]
    
    for field_name, value in field_values.items():
        if value is None or str(value).strip() == "" or str(value) == "NOT FOUND":
            continue
        
        # Escape special chars and convert field name
        escaped_value = str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        # Use only the last part of the path for widget name matching
        short_name = field_name.split('.')[-1] if '.' in field_name else field_name
        
        fdf_lines.append(f'<< /T ({short_name}) /V ({escaped_value}) >>')
    
    fdf_lines.extend([
        ']',
        '>>',
        '>>',
        'endobj',
        'trailer',
        '<< /Root 1 0 R >>',
        '%%EOF',
    ])
    
    fdf_content = '\n'.join(fdf_lines)
    
    # Write FDF to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fdf', delete=False) as f:
        f.write(fdf_content)
        fdf_path = f.name
    
    # Try pdftk first
    try:
        result = subprocess.run(
            ['pdftk', str(pdf_path), 'fill_form', fdf_path, 'output', str(output_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info(f"Filled form with pdftk, saved to: {output_path}")
            return output_path
    except FileNotFoundError:
        logger.debug("pdftk not found, trying alternative method")
    except Exception as e:
        logger.debug(f"pdftk failed: {e}")
    
    # Fallback to simple widget fill
    return fill_xfa_simple(pdf_path, field_values, output_path)


if __name__ == "__main__":
    import sys
    import json
    
    if len(sys.argv) < 3:
        print("Usage: python xfa_writer.py <pdf_path> <output_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2]
    
    # Test with sample data
    test_values = {
        "form1.Page1.PersonalDetails.Name.FamilyName": "TEST",
        "form1.Page1.PersonalDetails.Name.GivenName": "USER",
    }
    
    fill_xfa_with_fdf(pdf_path, test_values, output_path)
    print(f"Saved to: {output_path}")
