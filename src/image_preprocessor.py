"""
Image preprocessing helpers.

Goal: convert email images into Spanish paragraphs (cached) so reports and analysis
can work from text even without re-fetching images.
"""

import logging
from typing import Optional

from .ai_client import AIClient
from .models import Campaign, ImageBlock, TextBlock
from .storage import ImageDescriptionStorage

logger = logging.getLogger(__name__)

_DECORATIVE_KEYWORDS = (
    "facebook",
    "instagram",
    "whatsapp",
    "tiktok",
    "youtube",
    "linkedin",
    "twitter",
    "x.com",
    "pinterest",
    "icon",
    "icons",
    "social",
    "logo",
    "logos",
    "badge",
    "spacer",
    "pixel",
    "transparent",
)


def should_skip_image(block: ImageBlock) -> bool:
    """Heuristic filter for decorative images (logos, social icons, tiny assets)."""
    src = (block.src or "").lower()
    alt = (block.alt or "").lower()
    link = (block.link_url or "").lower()

    # Very small images are almost always icons/logos/spacers.
    if block.width and block.height and (block.width * block.height) <= 80 * 80:
        return True
    if (block.width and block.width <= 60) or (block.height and block.height <= 60):
        return True

    haystack = " ".join([src, alt, link])
    if any(k in haystack for k in _DECORATIVE_KEYWORDS):
        return True

    # Common social domains in links
    if any(d in link for d in ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "linkedin.com", "twitter.com", "x.com")):
        return True

    return False


def _build_image_prompt(*, alt: Optional[str] = None) -> str:
    alt_line = f"Alt/Texto alternativo: {alt}\n" if alt else ""
    return (
        "Describe esta imagen de email marketing en español en 1 solo párrafo.\n"
        "Enfócate en: producto/escena, estilo visual, colores, jerarquía, "
        "y cualquier texto visible (si se distingue).\n"
        "No inventes detalles: si no estás seguro, dilo.\n"
        f"{alt_line}"
    )


def preprocess_campaign_images(
    campaign: Campaign,
    *,
    client: Optional[AIClient],
    cache: ImageDescriptionStorage,
    max_images: int = 10,
) -> Campaign:
    """
    Replace ImageBlocks with TextBlocks containing an AI-generated paragraph.

    Notes:
    - Uses a URL->description cache to avoid repeated model calls.
    - If no client is available, falls back to alt text + URL.
    """
    new_blocks = []
    described = 0

    for block in campaign.blocks:
        if isinstance(block, ImageBlock):
            if should_skip_image(block):
                continue

            src = (block.src or "").strip()
            alt = (block.alt or "").strip() or None

            description = None
            if src and src.startswith("http"):
                description = cache.get(src)

            if not description:
                if client and src and src.startswith("http") and described < max_images:
                    try:
                        prompt = _build_image_prompt(alt=alt)
                        description = (client.analyze(prompt, images=[src]) or "").strip()
                        if description:
                            cache.set(src, description)
                        described += 1
                    except Exception as e:
                        logger.warning(f"Failed to describe image {src}: {e}")

            if not description:
                # Safe fallback: keep useful context without hallucinating.
                if alt:
                    description = f"Imagen (alt: {alt})."
                else:
                    description = "Imagen del email (sin alt disponible)."

            paragraph = description
            if src:
                paragraph += f"\nURL: {src}"

            new_blocks.append(TextBlock(content=paragraph, style="imagen"))
            continue

        new_blocks.append(block)

    campaign.blocks = new_blocks
    return campaign
