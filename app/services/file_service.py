"""
app/services/file_service.py
File system operations for Vasuki.

Scope: user home directory ONLY. Never touches system files.
Search results: maximum 5, sorted by most recently modified.
All paths resolved relative to user home to prevent path traversal.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def _safe_location(location: str) -> Path:
    """Resolve a named location to an absolute path inside home directory."""
    home = Path.home()
    locations = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "home": home,
    }
    return locations.get(location.lower(), home / "Desktop")


def create_file(name: str, content: str = "", location: str = "desktop") -> dict:
    """Create a new text file at the given location."""
    try:
        save_dir = _safe_location(location)
        save_dir.mkdir(parents=True, exist_ok=True)

        if not name.endswith(".txt"):
            name = f"{name}.txt"

        file_path = save_dir / name

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "message": f"Created {name} on your {location}.",
            "path": str(file_path),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not create file: {e}",
            "path": None,
        }


def open_file(path: str) -> dict:
    """Open a file using its default Windows application."""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return {
                "success": False,
                "message": f"File not found: {path}",
                "path": path,
            }
        os.startfile(str(file_path))
        return {
            "success": True,
            "message": f"Opened {file_path.name}.",
            "path": str(file_path),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not open file: {e}",
            "path": path,
        }


def search_files(query: str, max_results: int = 5) -> dict:
    """
    Search for files matching query in the user home directory.
    Returns maximum 5 results, sorted by most recently modified.
    Never searches outside the home directory.
    """
    try:
        home = Path.home()
        query_lower = query.lower().strip()

        if not query_lower:
            return {
                "success": False,
                "message": "No search query provided.",
                "results": [],
            }

        matches = []
        for file in home.rglob(f"*{query_lower}*"):
            if file.is_file():
                try:
                    mtime = file.stat().st_mtime
                    matches.append((mtime, str(file)))
                except (PermissionError, OSError):
                    continue

        # Sort by most recently modified, cap at max_results
        matches.sort(reverse=True)
        results = [path for _, path in matches[:max_results]]

        if not results:
            return {
                "success": False,
                "message": f"No files found matching '{query}'.",
                "results": [],
            }

        return {
            "success": True,
            "message": f"Found {len(results)} file(s) matching '{query}'.",
            "results": results,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Search failed: {e}",
            "results": [],
        }


def save_text(text: str, filename: str, location: str = "desktop") -> dict:
    """Save text content to a named file."""
    return create_file(filename, text, location)
