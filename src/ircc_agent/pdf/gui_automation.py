"""Smart GUI automation for XFA forms with field awareness.

Uses XFA field metadata to:
1. Detect field types (text, dropdown, checkbox)
2. Only select valid dropdown options
3. Skip low-confidence fields
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True


@dataclass
class FieldToFill:
    """A field to fill with its metadata."""
    name: str
    value: str
    field_type: str  # "text", "dropdown", "checkbox", "date"
    options: list[str] | None = None
    confidence: str = "high"  # "high", "medium", "low"
    tab_position: int = 0


class SmartFormFiller:
    """Fill XFA forms intelligently using GUI automation."""

    def __init__(self):
        self.current_position = 0

    def _run_applescript(self, script: str) -> str:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"AppleScript error: {e}")
            return ""

    def open_pdf(self, pdf_path: Path | str) -> bool:
        """Open PDF in Adobe Acrobat."""
        pdf_path = Path(pdf_path).resolve()
        
        script = f'''
        tell application "Adobe Acrobat"
            activate
            open POSIX file "{pdf_path}"
        end tell
        '''
        self._run_applescript(script)
        time.sleep(3)
        
        # Click to focus document
        pyautogui.click(600, 400)
        time.sleep(0.5)
        
        print(f"Opened: {pdf_path.name}")
        return True

    def go_to_first_field(self):
        """Navigate to first form field."""
        pyautogui.press('escape')
        time.sleep(0.3)
        pyautogui.press('tab')
        time.sleep(0.5)
        self.current_position = 1

    def next_field(self):
        """Move to next field."""
        pyautogui.press('tab')
        self.current_position += 1
        time.sleep(0.3)

    def skip_field(self):
        """Skip current field without filling."""
        self.next_field()

    def fill_text_field(self, value: str):
        """Fill a text field."""
        pyautogui.hotkey('command', 'a')
        time.sleep(0.1)
        pyperclip.copy(value)
        pyautogui.hotkey('command', 'v')
        time.sleep(0.2)

    def fill_dropdown(self, value: str, options: list[str] | None = None):
        """Fill a dropdown by selecting from options.
        
        Args:
            value: The value to select.
            options: Available options. If provided, validates value.
        """
        # If options are provided, find the best match
        if options:
            value_lower = value.lower()
            matched = None
            
            for opt in options:
                if opt.lower() == value_lower:
                    matched = opt
                    break
                elif value_lower in opt.lower():
                    matched = opt
                    break
            
            if not matched:
                print(f"  ⚠️  '{value}' not in dropdown options, skipping")
                return False
            
            value = matched

        # Open dropdown with down arrow
        pyautogui.press('down')
        time.sleep(0.3)
        
        # Type first few chars to filter
        if len(value) > 0:
            pyautogui.typewrite(value[:3].lower(), interval=0.1)
            time.sleep(0.3)
        
        # Press enter to select  
        pyautogui.press('return')
        time.sleep(0.2)
        
        return True

    def fill_checkbox(self, value: bool | str):
        """Fill a checkbox."""
        should_check = str(value).lower() in ['true', 'yes', '1', 'checked']
        
        # Press space to toggle
        if should_check:
            pyautogui.press('space')
            time.sleep(0.2)

    def fill_field(self, field: FieldToFill) -> bool:
        """Fill a single field based on its type.
        
        Args:
            field: The field to fill.
            
        Returns:
            True if field was filled, False if skipped.
        """
        # Skip low-confidence fields
        if field.confidence == "low":
            print(f"  ⏭️  Skipping (low confidence): {field.name}")
            return False

        # Fill based on type
        if field.field_type == "dropdown":
            success = self.fill_dropdown(field.value, field.options)
            if not success:
                return False
        elif field.field_type == "checkbox":
            self.fill_checkbox(field.value)
        else:  # text, date, number
            self.fill_text_field(field.value)

        print(f"  ✓ Filled: {field.name} = {field.value[:30]}")
        return True

    def save_pdf(self, output_path: Path | str | None = None):
        """Save the PDF."""
        if output_path:
            pyautogui.hotkey('command', 'shift', 's')
        else:
            pyautogui.hotkey('command', 's')
        time.sleep(1)


def fill_form_smart(
    pdf_path: Path | str,
    fields_to_fill: list[FieldToFill],
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fill form intelligently with field awareness.
    
    Args:
        pdf_path: Path to the PDF form.
        fields_to_fill: List of fields with metadata.
        output_path: Optional save path.
        
    Returns:
        Result dictionary.
    """
    filler = SmartFormFiller()
    
    print("\n" + "="*50)
    print("SMART FORM FILLING")
    print("="*50)
    print("⚠️  DO NOT MOVE MOUSE - Move to corner to abort")
    print("="*50 + "\n")
    
    time.sleep(2)
    
    filler.open_pdf(pdf_path)
    time.sleep(3)  # Wait for XFA to load
    
    filler.go_to_first_field()
    
    filled = 0
    skipped = 0
    
    for field in fields_to_fill:
        if filler.fill_field(field):
            filled += 1
        else:
            skipped += 1
        
        filler.next_field()
        time.sleep(0.3)
    
    print(f"\n✅ Done! Filled: {filled}, Skipped: {skipped}")
    
    if output_path:
        filler.save_pdf(output_path)
    
    return {
        "success": True,
        "filled": filled,
        "skipped": skipped,
    }


if __name__ == "__main__":
    # Test with sample fields
    test_fields = [
        FieldToFill(
            name="FamilyName",
            value="MAZYAKI",
            field_type="text",
            confidence="high",
        ),
        FieldToFill(
            name="GivenName", 
            value="Azam",
            field_type="text",
            confidence="high",
        ),
        FieldToFill(
            name="VisaType",
            value="Visitor",
            field_type="dropdown",
            options=["", "Visitor Visa", "Work Permit", "Study Permit"],
            confidence="high",
        ),
        FieldToFill(
            name="UnknownField",
            value="Maybe",
            field_type="text",
            confidence="low",  # Will be skipped
        ),
    ]
    
    result = fill_form_smart(
        "/Users/mo/IRCC-Agent/TEST/2026 Super Visa/IRCC forms/Mansour/imm5257e.pdf",
        test_fields,
    )
    print(f"\nResult: {result}")
