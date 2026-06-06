import glob
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RenderResult:
    success: bool
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    error_log: str = ""
    class_name: str = "GeneratedScene"


def extract_class_name(script_path: str) -> str:
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"class\s+(\w+)\s*\(\s*Scene\s*\)", content)
    return match.group(1) if match else "GeneratedScene"


def get_manim_quality_flag(hd: bool = False) -> str:
    """Return manim quality flag. Free plan uses 480p for speed."""
    return "-pqh" if hd else "-pql"


def render_manim_script(
    script_path: str,
    class_name: str = "GeneratedScene",
    hd: bool = False,
) -> RenderResult:
    output_dir = "app/static/outputs"
    quality = get_manim_quality_flag(hd)

    command = [
        "manim",
        quality,
        script_path,
        class_name,
        "--media_dir",
        output_dir,
        "--output_file",
        "scene.mp4",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return RenderResult(
            success=False,
            error_log="Manim render timed out after 5 minutes",
            class_name=class_name,
        )
    except Exception as e:
        return RenderResult(success=False, error_log=str(e), class_name=class_name)

    if result.returncode != 0:
        error_log = (result.stderr or result.stdout or "Unknown render error")[-4000:]
        return RenderResult(
            success=False,
            error_log=error_log,
            class_name=class_name,
        )

    pattern = os.path.join(output_dir, "videos", "**", "scene.mp4")
    matches = glob.glob(pattern, recursive=True)
    if not matches:
        return RenderResult(
            success=False,
            error_log="Render completed but no video file was found",
            class_name=class_name,
        )

    video_path = max(matches, key=os.path.getmtime)
    rel_path = os.path.relpath(video_path, output_dir)
    video_url = f"/static/outputs/{rel_path.replace(os.sep, '/')}"
    return RenderResult(
        success=True,
        video_url=video_url,
        local_path=video_path,
        class_name=class_name,
    )


def get_video_metadata(video_url: str) -> dict:
    """Extract basic metadata from a rendered video file."""
    if not video_url:
        return {"duration": "unknown", "resolution": "unknown", "format": "MP4", "size": "unknown"}

    rel = video_url.replace("/static/outputs/", "")
    path = os.path.join("app/static/outputs", rel)
    if not os.path.exists(path):
        return {"duration": "unknown", "resolution": "unknown", "format": "MP4", "size": "unknown"}

    size_bytes = os.path.getsize(path)
    size_mb = f"{size_bytes / (1024 * 1024):.1f} MB"

    resolution = "unknown"
    if "1080p" in path:
        resolution = "1080p"
    elif "480p" in path:
        resolution = "480p"
    elif "720p" in path:
        resolution = "720p"

    return {
        "duration": "unknown",
        "resolution": resolution,
        "format": "MP4",
        "size": size_mb,
    }
