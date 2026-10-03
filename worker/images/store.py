"""이미지 파일 저장. 원본은 받은 그대로 두고, 표시용은 비율을 유지한 축소본만 만든다(자르지 않는다).

경로는 IMAGE_DIR 기준 상대 경로로 기록한다. 웹(/img/[id])이 같은 디렉터리에서 읽는다.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import httpx

from ..settings import ROOT

ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


class ImageError(Exception):
    pass


def image_dir() -> Path:
    return Path(os.environ.get("IMAGE_DIR") or ROOT / "var" / "images")


def download(client: httpx.Client, url: str, max_bytes: int) -> tuple[bytes, str]:
    with client.stream("GET", url, follow_redirects=True, timeout=30) as r:
        if r.status_code != 200:
            raise ImageError(f"원본을 받지 못함 (HTTP {r.status_code})")
        mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if mime not in ALLOWED:
            raise ImageError(f"이미지 형식이 아님 ({mime or '알 수 없음'})")
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise ImageError("파일이 너무 큼")
    return bytes(buf), mime


def save(content: bytes, mime: str, render_width: int, prefer_png: bool = False) -> dict:
    """원본과 표시용 파일을 쓰고 크기 정보를 돌려준다. 글자 위주의 자체 그래픽은 PNG로 둔다(prefer_png)."""
    from PIL import Image, ImageOps

    if mime not in ALLOWED:
        raise ImageError(f"이미지 형식이 아님 ({mime})")
    sha = hashlib.sha256(content).hexdigest()
    root = image_dir()
    orig_rel = f"o/{sha[:2]}/{sha}.{ALLOWED[mime]}"
    (root / orig_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / orig_rel).write_bytes(content)
    try:
        im = Image.open(io.BytesIO(content))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"이미지를 열지 못함: {e}") from e
    im = ImageOps.exif_transpose(im)        # 촬영 방향 정보대로 세우기만 한다
    w, h = im.size
    if w > render_width:
        im = im.resize((render_width, round(h * render_width / w)), Image.LANCZOS)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if alpha or prefer_png:
        im.convert("RGBA").save(out, "PNG", optimize=True)
        ext, out_mime = "png", "image/png"
    else:
        im.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
        ext, out_mime = "jpg", "image/jpeg"
    rel = f"r/{sha[:2]}/{sha}.{ext}"
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(out.getvalue())
    return {"sha256": sha, "original_path": orig_rel, "stored_path": rel, "mime": out_mime,
            "width": im.size[0], "height": im.size[1], "original_width": w, "original_height": h}
