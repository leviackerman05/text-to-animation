"""
Persist rendered videos to Supabase Storage (preferred) or server stream URLs.
Local Manim artifacts are removed after upload so files stay off the user's disk
until they explicitly download from the app.
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple

from app.renderer import get_video_metadata
from app.supabase_client import supabase_admin

BUCKET = "videos"
LOCAL_VIDEO_DIR = Path("app/data/videos")
SUPABASE_PUBLIC_PREFIX = "/storage/v1/object/public/videos/"


def _client():
    return supabase_admin


def _safe_unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _cleanup_manim_tree(video_path: str) -> None:
    """Remove Manim media folders after the video has been persisted elsewhere."""
    try:
        outputs_root = Path("app/static/outputs").resolve()
        video_file = Path(video_path).resolve()
        if outputs_root not in video_file.parents:
            return
        # Remove the quality folder (e.g. .../videos/generated_scene/480p15/)
        quality_dir = video_file.parent
        scene_dir = quality_dir.parent
        videos_dir = scene_dir.parent
        if videos_dir.name == "videos" and scene_dir.is_dir():
            shutil.rmtree(scene_dir, ignore_errors=True)
    except Exception as e:
        print(f"Could not clean Manim artifacts: {e}")


def _upload_to_supabase(local_path: str, user_id: str, chat_id: str) -> Optional[str]:
    client = _client()
    if not client:
        return None

    storage_path = f"{user_id}/{chat_id}/{uuid.uuid4()}.mp4"
    try:
        with open(local_path, "rb") as f:
            client.storage.from_(BUCKET).upload(
                storage_path,
                f,
                file_options={"content-type": "video/mp4", "upsert": "true"},
            )
        base = os.getenv("SUPABASE_URL", "").rstrip("/")
        return f"{base}{SUPABASE_PUBLIC_PREFIX}{storage_path}"
    except Exception as e:
        print(f"Supabase video upload failed: {e}")
        return None


def _store_for_streaming(local_path: str) -> str:
    """Keep one server-side copy and expose a stream URL (inline, not attachment)."""
    LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    video_id = uuid.uuid4().hex
    dest = LOCAL_VIDEO_DIR / f"{video_id}.mp4"
    shutil.copy2(local_path, dest)
    return f"/videos/{video_id}/stream"


def persist_video(local_path: str, user_id: str, chat_id: str) -> Tuple[str, dict]:
    """
    Upload video to cloud storage when available, otherwise register for streaming.
    Removes local Manim render files afterward.
    """
    if not local_path or not os.path.exists(local_path):
        return "", get_video_metadata("")

    metadata = get_video_metadata_from_file(local_path)

    remote_url = _upload_to_supabase(local_path, user_id, chat_id)
    if remote_url:
        _safe_unlink(local_path)
        _cleanup_manim_tree(local_path)
        return remote_url, metadata

    stream_url = _store_for_streaming(local_path)
    _safe_unlink(local_path)
    _cleanup_manim_tree(local_path)
    return stream_url, metadata


def get_video_metadata_from_file(path: str) -> dict:
    rel = f"/static/outputs/{os.path.basename(path)}"
    meta = get_video_metadata(rel)
    if meta.get("size") == "unknown" and os.path.exists(path):
        size_bytes = os.path.getsize(path)
        meta["size"] = f"{size_bytes / (1024 * 1024):.1f} MB"
    return meta


def resolve_local_stream_path(video_id: str) -> Optional[Path]:
    if not video_id or not video_id.isalnum():
        return None
    path = LOCAL_VIDEO_DIR / f"{video_id}.mp4"
    return path if path.exists() else None
