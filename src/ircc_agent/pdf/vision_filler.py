"""Vision-based form filling using screenshots and OCR.

Uses PyAutoGUI for screenshots/clicks and pytesseract for finding field labels.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyautogui
import pyperclip
from PIL import Image

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.2
pyautogui.FAILSAFE = True


@dataclass
class FieldLocation:
    """A field with its screen location."""
    name: str
    label: str
    value: str
    x: int  # Center X of field
    y: int  # Center Y of field
    field_type: str = "text"
    options: list[str] | None = None


class VisionFormFiller:
    """Fill forms using vision and OCR."""

    def __init__(self):
        self.screenshot: Image.Image | None = None
        self.ocr_data: dict | None = None
        self.animation_process = None

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

    def show_screen_border_animation(self):
        """Show animated border around screen to indicate automation is running."""
        # Create a simple overlay script that shows red corners
        script = '''
        tell application "System Events"
            display notification "🤖 Automation Active - Don't move mouse!" with title "IRCC Agent" sound name "Glass"
        end tell
        '''
        self._run_applescript(script)
        
        # Also speak to indicate automation is starting
        subprocess.Popen(["say", "-v", "Samantha", "Automation starting"], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def hide_screen_border_animation(self):
        """Hide the screen border animation."""
        # Play completion sound
        subprocess.Popen(["say", "-v", "Samantha", "Form filling complete"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
        return True

    def take_screenshot(self) -> Image.Image:
        """Take a screenshot of the current screen."""
        self.screenshot = pyautogui.screenshot()
        return self.screenshot

    def find_text_location(self, text: str) -> tuple[int, int] | None:
        """Find the screen location of text using OCR.
        
        Args:
            text: Text to find.
            
        Returns:
            (x, y) tuple of center point, or None if not found.
        """
        import pytesseract
        
        if self.screenshot is None:
            self.take_screenshot()
        
        # Get screen vs screenshot size for Retina scaling
        screen_w, screen_h = pyautogui.size()
        shot_w, shot_h = self.screenshot.size
        scale_x = screen_w / shot_w  # Usually 0.5 for Retina
        scale_y = screen_h / shot_h
        
        # Get OCR data with bounding boxes
        data = pytesseract.image_to_data(self.screenshot, output_type=pytesseract.Output.DICT)
        
        text_lower = text.lower().strip()
        words = text_lower.split()
        
        # First try exact match
        for i, word in enumerate(data['text']):
            if word and text_lower == word.lower():
                x = int((data['left'][i] + data['width'][i] // 2) * scale_x)
                y = int((data['top'][i] + data['height'][i] // 2) * scale_y)
                return (x, y)
        
        # Then try partial match (first word of label)
        if words:
            first_word = words[0]
            for i, word in enumerate(data['text']):
                if word and first_word in word.lower():
                    x = int((data['left'][i] + data['width'][i] // 2) * scale_x)
                    y = int((data['top'][i] + data['height'][i] // 2) * scale_y)
                    return (x, y)
        
        # Try substring match
        for i, word in enumerate(data['text']):
            if word and len(word) > 3 and word.lower() in text_lower:
                x = int((data['left'][i] + data['width'][i] // 2) * scale_x)
                y = int((data['top'][i] + data['height'][i] // 2) * scale_y)
                return (x, y)
        
        return None

    def find_field_input_area(self, label: str, offset_x: int = 50, offset_y: int = 25) -> tuple[int, int] | None:
        """Find the input area below a field label.
        
        Args:
            label: The field label text.
            offset_x: Horizontal offset from label to input (right).
            offset_y: Vertical offset from label to input (down).
            
        Returns:
            (x, y) of the input area.
        """
        label_pos = self.find_text_location(label)
        if label_pos:
            # Click below and slightly right of the label
            return (label_pos[0] + offset_x, label_pos[1] + offset_y)
        return None

    def click_at(self, x: int, y: int):
        """Click at screen coordinates with visual indicator."""
        # Move slowly so user can see what's happening
        pyautogui.moveTo(x, y, duration=0.5)  # Slower for visibility
        time.sleep(0.2)
        pyautogui.click(x, y)
        time.sleep(0.3)

    def type_text(self, text: str):
        """Type text at current position."""
        # Clear existing
        pyautogui.hotkey('command', 'a')
        time.sleep(0.1)
        
        # Paste text
        pyperclip.copy(text)
        pyautogui.hotkey('command', 'v')
        time.sleep(0.2)

    def toggle_checkbox(self, should_check: bool = True):
        """Toggle a checkbox.
        
        Args:
            should_check: True to check, False to uncheck.
        """
        # Click to toggle
        pyautogui.click()
        time.sleep(0.2)

    def select_dropdown(self, value: str, dropdown_x: int, dropdown_y: int):
        """Select a dropdown value by clicking the arrow on the far right.
        
        Args:
            value: Value to select.
            dropdown_x: X position of dropdown field.
            dropdown_y: Y position of dropdown field.
        """
        # Click on the dropdown arrow (far right side - about 200px from label)
        # The arrow is at the far right edge of the dropdown box
        arrow_x = dropdown_x + 250  # Go further right to hit the arrow
        
        # Move to arrow and click
        print(f"    → Clicking dropdown arrow at ({arrow_x}, {dropdown_y})")
        pyautogui.moveTo(arrow_x, dropdown_y, duration=0.3)
        time.sleep(0.2)
        pyautogui.click(arrow_x, dropdown_y)
        time.sleep(0.5)
        
        # Type to filter options
        pyautogui.typewrite(value[:5].lower(), interval=0.08)
        time.sleep(0.4)
        
        # Use down arrow to select and enter to confirm
        pyautogui.press('down')
        time.sleep(0.2)
        pyautogui.press('return')
        time.sleep(0.3)

    def fill_field_by_label(self, label: str, value: str, field_type: str = "text") -> bool:
        """Find a field by its label and fill it.
        
        Args:
            label: The field label to search for.
            value: The value to fill.
            field_type: Type of field ("text", "dropdown", "checkbox").
            
        Returns:
            True if field was found and filled.
        """
        print(f"🔍 Looking for: '{label}'...")
        
        # Take fresh screenshot
        self.take_screenshot()
        
        # Find input area (below the label)
        input_pos = self.find_field_input_area(label)
        
        if not input_pos:
            print(f"  ❌ Could not find: {label}")
            return False
        
        print(f"  📍 Found at ({input_pos[0]}, {input_pos[1]})")
        
        # Fill based on type
        if field_type == "dropdown":
            self.select_dropdown(value, input_pos[0], input_pos[1])
            print(f"  🔽 Selected: {label} = {value}")
        elif field_type == "checkbox":
            # Move mouse visually
            self.click_at(input_pos[0], input_pos[1])
            should_check = str(value).lower() in ['true', 'yes', '1', 'y']
            self.toggle_checkbox(should_check)
            print(f"  ☑️  Toggled: {label} = {value}")
        else:
            # Move mouse visually to show what's happening
            self.click_at(input_pos[0], input_pos[1])
            self.type_text(value)
            print(f"  ✏️  Typed: {label} = {value}")
        
        return True


def get_applicant_from_path(pdf_path: Path | str) -> str:
    """Extract the applicant name from the PDF path.
    
    The folder containing the PDF is assumed to be the applicant's name.
    E.g., /forms/Mansour/imm5257e.pdf -> "Mansour"
    
    Args:
        pdf_path: Path to the PDF.
        
    Returns:
        Applicant name (capitalized).
    """
    pdf_path = Path(pdf_path)
    folder_name = pdf_path.parent.name
    return folder_name.title()  # Capitalize properly


def fill_form_with_vision(
    pdf_path: Path | str,
    fields: list[dict[str, str]],
) -> dict[str, Any]:
    """Fill a form using vision-based field detection.
    
    Args:
        pdf_path: Path to the PDF.
        fields: List of {label, value, type} dicts.
        
    Returns:
        Result dictionary.
    """
    filler = VisionFormFiller()
    
    # Get applicant from path
    applicant = get_applicant_from_path(pdf_path)
    
    print("\n" + "="*60)
    print(f"🤖 VISION FORM FILLER - Applicant: {applicant}")
    print("="*60)
    print("⚠️  DO NOT MOVE MOUSE")
    print("="*60 + "\n")
    
    time.sleep(2)
    
    # Show automation indicator
    filler.show_screen_border_animation()
    
    # Open PDF
    filler.open_pdf(pdf_path)
    time.sleep(2)
    
    # Take initial screenshot
    filler.take_screenshot()
    
    filled = 0
    failed = 0
    
    for field in fields:
        label = field.get('label', '')
        value = field.get('value', '')
        field_type = field.get('type', 'text')
        
        if not label or not value:
            continue
        
        if filler.fill_field_by_label(label, value, field_type):
            filled += 1
        else:
            failed += 1
        
        time.sleep(0.5)
    
    # Hide animation and play completion sound
    filler.hide_screen_border_animation()
    
    print(f"\n✅ Done! Filled: {filled}, Failed: {failed}")
    print(f"📋 Applicant: {applicant}")
    
    return {
        "success": True,
        "filled": filled,
        "failed": failed,
        "applicant": applicant,
    }


if __name__ == "__main__":
    # Test with actual IRCC form labels including dropdown and checkbox
    test_fields = [
        {"label": "*Family name", "value": "MAZYAKI", "type": "text"},
        {"label": "Given name(s)", "value": "Azam", "type": "text"},
        {"label": "service in", "value": "English", "type": "dropdown"},  # I want service in
        {"label": "City/Town", "value": "TEHRAN", "type": "text"},
    ]
    
    result = fill_form_with_vision(
        "/Users/mo/IRCC-Agent/TEST/2026 Super Visa/IRCC forms/Mansour/imm5257e.pdf",
        test_fields,
    )
    print(f"\nResult: {result}")
