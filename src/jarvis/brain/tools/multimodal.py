"""T6 multi-modal tools — laptop-side screenshot + OCR (precursor to glasses camera + display).

For "what's on my screen" / "read this menu" / "what does this say" queries. Takes a fresh
screenshot of the laptop display via the pc_agent executor and (if pytesseract is installed)
runs OCR on it. Falls back to returning the screenshot path so a vision-capable LLM can read
it on the next turn.

When Mentra OS glasses integration lands (separate module), this same surface should accept a
frame from the glasses camera instead of the laptop screen — the schema stays the same.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from jarvis.brain.tools.base import tool_error


_DEFAULT_SHOT = Path.home() / ".jarvis" / "screenshots" / "latest.png"


async def screenshot_screen(args: dict) -> str:
    """Capture a screenshot of the laptop screen via the pc_agent executor.

    The LLM can then call ``read_screen_text`` (OCR) or read the image directly. Returns the
    saved PNG path so the next turn can attach it to a vision-capable model."""
    path = (args.get("path") or str(_DEFAULT_SHOT)).strip() or str(_DEFAULT_SHOT)
    try:
        from jarvis.brain.tools.system import run_powershell
        # PowerShell: System.Drawing.Bitmap of the primary screen, save as PNG.
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png);"
            "Write-Output $bmp.Width;Write-Output $bmp.Height"
        )
        res = await run_powershell({"command": ps})
        # run_powershell forwards to laptop; if it ran there, we'll get a string with width/height
        if "didn't run" in (res or "").lower() or "no laptop" in (res or "").lower():
            return f"Laptop executor isn't connected, sir — I can't capture the screen right now."
        return f"Screenshot captured at {path}, sir — {res.strip().splitlines()[-2:]}"
    except Exception as e:  # noqa: BLE001
        return tool_error("screenshot", e)


async def read_screen_text(args: dict) -> str:
    """OCR the most recent screenshot. Returns up to ~2000 chars of extracted text.

    If pytesseract isn't installed, falls back to the screenshot path so a vision LLM can read it.
    """
    path = (args.get("path") or str(_DEFAULT_SHOT)).strip() or str(_DEFAULT_SHOT)
    p = Path(path)
    if not p.exists():
        return f"No screenshot at {path}, sir — run screenshot_screen first."
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return (f"Screenshot at {path}, sir — pytesseract / Pillow aren't installed, so I can't "
                "OCR it here. The image is on disk for me to read on the next turn.")
    try:
        img = Image.open(p)
        text = pytesseract.image_to_string(img)
        text = (text or "").strip()
        if not text:
            return f"No readable text found in {path}, sir."
        if len(text) > 2000:
            text = text[:1997].rstrip() + "…"
        return f"On screen:\n{text}"
    except Exception as e:  # noqa: BLE001
        return tool_error("OCR", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "screenshot_screen",
            "description": (
                "Take a screenshot of the laptop screen and save it to a PNG path. Use for "
                "'what's on my screen', 'show me what you see', 'capture this', or as a precursor "
                "to reading screen text via OCR. The image is on disk for the next turn."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description":
                             "Where to save the PNG (default ~/.jarvis/screenshots/latest.png)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen_text",
            "description": (
                "OCR the most recent laptop screenshot and return extracted text. Use for "
                "'read the screen', 'what does this say', 'read this menu', 'transcribe what's "
                "on my monitor'. Requires pytesseract + Pillow on the laptop; falls back to the "
                "screenshot path when missing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description":
                             "Screenshot path (default ~/.jarvis/screenshots/latest.png)."},
                },
            },
        },
    },
]

HANDLERS = {"screenshot_screen": screenshot_screen, "read_screen_text": read_screen_text}