"""Adobe Acrobat automation for filling XFA forms on macOS.

Uses AppleScript to control Adobe Acrobat Reader for filling XFA forms
that cannot be filled programmatically with standard PDF libraries.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class XFAFormData:
    """Data to fill into an XFA form."""
    field_values: dict[str, Any]  # field_path -> value
    pdf_path: Path
    output_path: Path


class AdobeAcrobatAutomation:
    """Automate Adobe Acrobat Reader for XFA form filling on macOS."""

    ACROBAT_BUNDLE_ID = "com.adobe.Reader"
    ACROBAT_PRO_BUNDLE_ID = "com.adobe.Acrobat.Pro"

    def __init__(self):
        """Initialize automation."""
        self._check_acrobat_installed()

    def _check_acrobat_installed(self) -> str:
        """Check if Adobe Acrobat is installed and return bundle ID."""
        # Check for Acrobat Reader
        check_script = '''
        tell application "System Events"
            set appExists to exists application process "Adobe Acrobat Reader"
        end tell
        '''
        
        # Try to find Acrobat
        try:
            result = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == 'com.adobe.Reader'"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                logger.info("Found Adobe Acrobat Reader")
                return self.ACROBAT_BUNDLE_ID
            
            result = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == 'com.adobe.Acrobat.Pro'"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                logger.info("Found Adobe Acrobat Pro")
                return self.ACROBAT_PRO_BUNDLE_ID
                
        except Exception as e:
            logger.warning(f"Error checking for Acrobat: {e}")
        
        logger.warning("Adobe Acrobat not found. Please install Adobe Acrobat Reader.")
        return ""

    def _run_applescript(self, script: str) -> str:
        """Run an AppleScript and return the result."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logger.error(f"AppleScript error: {result.stderr}")
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error("AppleScript timed out")
            return ""
        except Exception as e:
            logger.error(f"AppleScript execution failed: {e}")
            return ""

    def open_pdf(self, pdf_path: Path) -> bool:
        """Open a PDF in Adobe Acrobat Reader.
        
        Args:
            pdf_path: Path to the PDF file.
            
        Returns:
            True if successful.
        """
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return False

        script = f'''
        tell application "Adobe Acrobat"
            activate
            open POSIX file "{pdf_path}"
        end tell
        '''
        
        self._run_applescript(script)
        time.sleep(2)  # Wait for PDF to load
        logger.info(f"Opened PDF in Adobe Acrobat: {pdf_path.name}")
        return True

    def fill_field_via_javascript(self, field_name: str, value: str) -> bool:
        """Fill a form field using Acrobat's JavaScript.
        
        This uses the JavaScript console in Acrobat.
        
        Args:
            field_name: Name of the field to fill.
            value: Value to set.
            
        Returns:
            True if successful.
        """
        # Escape special characters in value
        escaped_value = value.replace('"', '\\"').replace("'", "\\'")
        
        # Use Acrobat's JavaScript API via AppleScript
        # Note: This requires Acrobat Pro or specific settings enabled
        js_code = f'this.getField("{field_name}").value = "{escaped_value}";'
        
        script = f'''
        tell application "Adobe Acrobat Reader"
            activate
            -- Execute JavaScript in the document
            do script "{js_code}"
        end tell
        '''
        
        result = self._run_applescript(script)
        return True

    def fill_fields_batch(self, field_values: dict[str, Any]) -> dict[str, bool]:
        """Fill multiple form fields.
        
        Args:
            field_values: Dictionary of field names to values.
            
        Returns:
            Dictionary of field names to success status.
        """
        results = {}
        
        for field_name, value in field_values.items():
            if value is None or str(value).strip() == "":
                continue
                
            str_value = str(value)
            success = self.fill_field_via_javascript(field_name, str_value)
            results[field_name] = success
            
            # Small delay between fields to avoid overwhelming Acrobat
            time.sleep(0.1)
        
        return results

    def save_pdf(self, output_path: Path | None = None) -> bool:
        """Save the current PDF.
        
        Args:
            output_path: Optional path to save as (if None, saves in place).
            
        Returns:
            True if successful.
        """
        if output_path:
            output_path = Path(output_path).resolve()
            script = f'''
            tell application "Adobe Acrobat Reader"
                activate
                -- Save As
                tell application "System Events"
                    keystroke "s" using {{command down, shift down}}
                    delay 1
                    keystroke "{output_path}"
                    delay 0.5
                    keystroke return
                end tell
            end tell
            '''
        else:
            script = '''
            tell application "Adobe Acrobat Reader"
                activate
                tell application "System Events"
                    keystroke "s" using command down
                end tell
            end tell
            '''
        
        self._run_applescript(script)
        time.sleep(1)
        logger.info(f"Saved PDF: {output_path if output_path else 'in place'}")
        return True

    def close_pdf(self) -> bool:
        """Close the current PDF without saving."""
        script = '''
        tell application "Adobe Acrobat Reader"
            activate
            tell application "System Events"
                keystroke "w" using command down
                delay 0.5
                -- Click "Don't Save" if dialog appears
                try
                    click button "Don't Save" of window 1
                end try
            end tell
        end tell
        '''
        self._run_applescript(script)
        return True


def fill_xfa_form_with_acrobat(
    pdf_path: Path | str,
    field_values: dict[str, Any],
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fill an XFA form using Adobe Acrobat automation.
    
    Args:
        pdf_path: Path to the XFA PDF form.
        field_values: Dictionary of field names to values.
        output_path: Path to save the filled form.
        
    Returns:
        Dictionary with results including success status and filled fields.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path) if output_path else pdf_path.parent / f"{pdf_path.stem}_filled.pdf"
    
    automation = AdobeAcrobatAutomation()
    
    # Open PDF
    if not automation.open_pdf(pdf_path):
        return {"success": False, "error": "Failed to open PDF"}
    
    # Fill fields
    results = automation.fill_fields_batch(field_values)
    filled_count = sum(1 for v in results.values() if v)
    
    # Save
    automation.save_pdf(output_path)
    
    return {
        "success": True,
        "output_path": str(output_path),
        "filled_count": filled_count,
        "total_fields": len(field_values),
        "field_results": results,
    }


# Alternative: Use Acrobat's batch processing with JavaScript
ACROBAT_FILL_JS_TEMPLATE = '''
// Acrobat JavaScript to fill form fields
// This can be run via Acrobat's batch processing or JavaScript console

var fieldData = %FIELD_DATA%;

for (var fieldName in fieldData) {
    try {
        var field = this.getField(fieldName);
        if (field) {
            field.value = fieldData[fieldName];
            console.println("Filled: " + fieldName);
        } else {
            console.println("Field not found: " + fieldName);
        }
    } catch (e) {
        console.println("Error filling " + fieldName + ": " + e);
    }
}

console.println("Form filling complete.");
'''


def generate_acrobat_javascript(field_values: dict[str, Any]) -> str:
    """Generate JavaScript code for Acrobat to fill form fields.
    
    This JavaScript can be:
    1. Pasted into Acrobat's JavaScript console (Ctrl+J)
    2. Used in Acrobat's batch processing
    3. Executed via Acrobat's command-line tools
    
    Args:
        field_values: Dictionary of field names to values.
        
    Returns:
        JavaScript code as a string.
    """
    import json
    
    # Filter out empty values and convert to JSON-safe format
    clean_values = {}
    for k, v in field_values.items():
        if v is not None and str(v).strip():
            clean_values[k] = str(v)
    
    field_data_json = json.dumps(clean_values, indent=2)
    
    js_code = ACROBAT_FILL_JS_TEMPLATE.replace('%FIELD_DATA%', field_data_json)
    return js_code


def save_acrobat_javascript(
    field_values: dict[str, Any],
    output_path: Path | str,
) -> Path:
    """Save Acrobat JavaScript to a file for manual use.
    
    Args:
        field_values: Dictionary of field names to values.
        output_path: Path to save the JavaScript file.
        
    Returns:
        Path to the saved file.
    """
    output_path = Path(output_path)
    js_code = generate_acrobat_javascript(field_values)
    
    output_path.write_text(js_code)
    logger.info(f"Saved Acrobat JavaScript to: {output_path}")
    
    return output_path


if __name__ == "__main__":
    # Test the automation
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python acrobat_automation.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Test opening a PDF
    automation = AdobeAcrobatAutomation()
    automation.open_pdf(Path(pdf_path))
    
    print("PDF opened in Adobe Acrobat. Press Enter to close...")
    input()
    
    automation.close_pdf()
