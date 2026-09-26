#!/usr/bin/env python3
"""按《星火之光AI 基础 VI 规范》生成 SparklightAIGEO 系统品牌资源。

源素材：星火之光AI 默认 VI 目录（靛蓝反白图标、透明底图标、横式标志）。
输出：
  public/icons/sparklightaigeo-app.svg            应用图标（矢量，内嵌 VI 位图）
  public/icons/sparklightaigeo-app-192.png
  public/icons/sparklightaigeo-app-512.png
  public/icons/sparklightaigeo-app-maskable-512.png
  public/icons/sparklightaigeo-app-maskable.svg
  public/favicon.ico                              16/32/48 多尺寸
  public/brand/sparklight-wordmark.svg            横式标志（透明底）
  public/brand/sparklight-wordmark-reversed.svg   横式标志（靛蓝底反白）
  public/brand/sparklight-wordmark.png            横式标志位图（宽 640）

色彩遵循 VI：主靛蓝 #2D326B、柔珊瑚 #FF6B5B、暖白 #FBF8F4、深墨 #1E2238。
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

VI_DIR = Path("D:/文档/关健文件/同步文件/AIFiles/WBPro/raw/星火之光AI/SparklightAI_默认VI")
REPO_ROOT = Path(__file__).resolve().parent.parent

PRIMARY = (45, 50, 107)  # #2D326B 主靛蓝

SRC_ICON_REVERSED = VI_DIR / "星火之光AI_logo_图标_靛蓝反白_1600x1600.png"
SRC_MARK_TRANSPARENT = VI_DIR / "星火之光AI_logo_横式_透明底_2480x800.png"
SRC_MARK_REVERSED = VI_DIR / "星火之光AI_logo_横式_靛蓝反白_2480x800.png"

ICONS_DIR = REPO_ROOT / "public" / "icons"
BRAND_DIR = REPO_ROOT / "public" / "brand"


def load(path: Path) -> Image.Image:
    if not path.exists():
        sys.exit("[brand-assets] 缺少 VI 素材：" + str(path))
    return Image.open(path).convert("RGBA")


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGBA").convert("P", palette=Image.ADAPTIVE, colors=32).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = png_bytes(image)
    path.write_bytes(data)
    print("[brand-assets] " + str(path.relative_to(REPO_ROOT)) + f" ({len(data) / 1024:.1f} KB)")


def contain(image: Image.Image, size: int, ratio: float, background) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), background)
    target = int(size * ratio)
    resized = image.resize((target, target), Image.LANCZOS)
    canvas.paste(resized, ((size - target) // 2, (size - target) // 2), resized)
    return canvas


def rounded(source: Image.Image, size: int, radius_ratio: float) -> Image.Image:
    source = source.resize((size, size), Image.LANCZOS)
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1), radius=int(size * scale * radius_ratio), fill=255
    )
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(source, (0, 0), mask)
    return out


def icon_svg(image: Image.Image, size: int, title: str, radius: int) -> str:
    data = base64.b64encode(png_bytes(image.resize((size, size), Image.LANCZOS))).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-labelledby="t">\n'
        f'  <title id="t">{title}</title>\n'
        f'  <defs><clipPath id="r"><rect width="{size}" height="{size}" rx="{radius}" ry="{radius}"/></clipPath></defs>\n'
        f'  <g clip-path="url(#r)"><image width="{size}" height="{size}" href="data:image/png;base64,{data}"/></g>\n'
        f'</svg>\n'
    )


def mark_svg(image: Image.Image, height: int, title: str) -> str:
    width = round(image.width * height / image.height)
    data = base64.b64encode(png_bytes(image.resize((width, height), Image.LANCZOS))).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">\n'
        f'  <title id="t">{title}</title>\n'
        f'  <image width="{width}" height="{height}" href="data:image/png;base64,{data}"/>\n'
        f'</svg>\n'
    )


def main() -> None:
    icon = load(SRC_ICON_REVERSED)
    mark = load(SRC_MARK_TRANSPARENT)
    mark_reversed = load(SRC_MARK_REVERSED)

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    # 1) PWA 应用图标：靛蓝底反白星火图形
    for size in (192, 512):
        save_png(icon.resize((size, size), Image.LANCZOS), ICONS_DIR / f"sparklightaigeo-app-{size}.png")

    # 2) maskable：图形收进 80% 安全区
    save_png(
        contain(icon, 512, ratio=0.8, background=PRIMARY + (255,)),
        ICONS_DIR / "sparklightaigeo-app-maskable-512.png",
    )

    # 3) SVG 图标
    svg_path = ICONS_DIR / "sparklightaigeo-app.svg"
    svg_path.write_text(icon_svg(icon, 512, "SparklightAIGEO · 星火之光AI", 112), encoding="utf-8")
    print(f"[brand-assets] public/icons/sparklightaigeo-app.svg ({svg_path.stat().st_size / 1024:.1f} KB)")
    (ICONS_DIR / "sparklightaigeo-app-maskable.svg").write_text(
        icon_svg(contain(icon, 512, ratio=0.8, background=PRIMARY + (255,)), 512, "SparklightAIGEO · 星火之光AI", 112),
        encoding="utf-8",
    )

    # 4) favicon.ico（16/32/48）
    favicon_path = REPO_ROOT / "public" / "favicon.ico"
    sizes = (16, 32, 48)
    images = [rounded(icon, s, radius_ratio=0.22 if s >= 32 else 0.12) for s in sizes]
    images[0].save(favicon_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    print(f"[brand-assets] public/favicon.ico ({favicon_path.stat().st_size / 1024:.1f} KB)")

    # 5) Chrome 协作扩展图标（16/32/48/128）
    ext_icons = REPO_ROOT / "browser-extension" / "icons"
    if ext_icons.exists():
        for size in (16, 32, 48, 128):
            save_png(icon.resize((size, size), Image.LANCZOS), ext_icons / f"icon{size}.png")

    # 6) 横式标志（后台品牌区、登录页使用）
    wordmark = mark.resize((640, round(mark.height * 640 / mark.width)), Image.LANCZOS)
    save_png(wordmark, BRAND_DIR / "sparklight-wordmark.png")
    (BRAND_DIR / "sparklight-wordmark.svg").write_text(
        mark_svg(mark, 96, "星火之光AI SparkLight AI"), encoding="utf-8"
    )
    (BRAND_DIR / "sparklight-wordmark-reversed.svg").write_text(
        mark_svg(mark_reversed, 96, "星火之光AI SparkLight AI"), encoding="utf-8"
    )
    print("[brand-assets] public/brand/ 横式标志已生成")


if __name__ == "__main__":
    main()
