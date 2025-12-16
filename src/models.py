"""
Data models for Klaviyo Email Campaign Repository.

These models define the structure for campaigns, metrics, and email content blocks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Union


class BlockType(str, Enum):
    """Types of content blocks in an email."""

    IMAGE = "image"
    TEXT = "text"
    BUTTON = "button"
    SEPARATOR = "separator"
    SOCIAL = "social"
    FOOTER = "footer"
    HEADER = "header"


@dataclass
class ImageBlock:
    """Represents an image block in an email."""

    block_type: BlockType = field(default=BlockType.IMAGE, init=False)
    src: str
    alt: Optional[str] = None
    description: Optional[str] = None  # AI-generated visual description
    width: Optional[int] = None
    height: Optional[int] = None
    link_url: Optional[str] = None

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        parts = ["[IMAGEN]"]
        if self.alt:
            parts.append(f"Alt: {self.alt}")
        if self.description:
            parts.append(f"Descripción visual: {self.description}")
        if self.link_url:
            parts.append(f"Enlace: {self.link_url}")
        parts.append(f"URL: {self.src}")
        return "\n".join(parts)


@dataclass
class TextBlock:
    """Represents a text block in an email."""

    block_type: BlockType = field(default=BlockType.TEXT, init=False)
    content: str
    style: Optional[str] = None  # heading, paragraph, caption, etc.
    emphasis: Optional[str] = None  # bold, italic, etc.

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        prefix = "[TEXTO"
        if self.style:
            prefix += f" - {self.style.upper()}"
        prefix += "]"
        return f"{prefix}\n{self.content}"


@dataclass
class ButtonBlock:
    """Represents a CTA button in an email."""

    block_type: BlockType = field(default=BlockType.BUTTON, init=False)
    text: str
    url: str
    color: Optional[str] = None
    background_color: Optional[str] = None
    style_notes: Optional[str] = None  # shape, contrast, etc.

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        parts = ["[BOTÓN / CTA]"]
        parts.append(f"Texto: {self.text}")
        parts.append(f"URL destino: {self.url}")
        if self.color or self.background_color:
            style_parts = []
            if self.background_color:
                style_parts.append(f"fondo: {self.background_color}")
            if self.color:
                style_parts.append(f"texto: {self.color}")
            parts.append(f"Estilo: {', '.join(style_parts)}")
        if self.style_notes:
            parts.append(f"Notas visuales: {self.style_notes}")
        return "\n".join(parts)


@dataclass
class SocialBlock:
    """Represents social media links."""

    block_type: BlockType = field(default=BlockType.SOCIAL, init=False)
    platform: str  # facebook, instagram, twitter, etc.
    url: str

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        return f"[SOCIAL] {self.platform.upper()}: {self.url}"


@dataclass
class SeparatorBlock:
    """Represents a visual separator/divider."""

    block_type: BlockType = field(default=BlockType.SEPARATOR, init=False)
    style: Optional[str] = None  # line, space, banner

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        return "[SEPARADOR]" + (f" ({self.style})" if self.style else "")


@dataclass
class FooterBlock:
    """Represents footer/disclaimer content."""

    block_type: BlockType = field(default=BlockType.FOOTER, init=False)
    content: str
    is_legal: bool = True

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        prefix = "[FOOTER - Legal]" if self.is_legal else "[FOOTER]"
        return f"{prefix}\n{self.content}"


# Union type for all block types
EmailBlock = Union[
    ImageBlock,
    TextBlock,
    ButtonBlock,
    SocialBlock,
    SeparatorBlock,
    FooterBlock,
]


@dataclass
class CampaignMetrics:
    """Metrics for an email campaign."""

    recipients: int = 0
    delivered: int = 0
    opens: int = 0
    opens_unique: int = 0
    open_rate: float = 0.0
    clicks: int = 0
    clicks_unique: int = 0
    click_rate: float = 0.0
    bounced: int = 0
    unsubscribes: int = 0
    spam_complaints: int = 0
    conversions: int = 0
    conversion_value: float = 0.0
    conversion_rate: float = 0.0

    def to_readable(self) -> str:
        """Convert to AI-readable format."""
        lines = [
            "## Métricas",
            "",
            f"- Enviados: {self.recipients:,}",
            f"- Entregados: {self.delivered:,}",
            f"- Open Rate: {self.open_rate:.2%} ({self.opens_unique:,} aperturas únicas)",
            f"- Click Rate: {self.click_rate:.2%} ({self.clicks_unique:,} clicks únicos)",
            f"- Unsubscribes: {self.unsubscribes:,}",
            f"- Bounces: {self.bounced:,}",
        ]
        if self.conversions > 0:
            lines.append(f"- Conversiones: {self.conversions:,}")
            lines.append(f"- Tasa de conversión: {self.conversion_rate:.2%}")
        if self.conversion_value > 0:
            lines.append(f"- Revenue: ${self.conversion_value:,.2f}")
        return "\n".join(lines)


@dataclass
class Campaign:
    """Represents a complete email campaign."""

    # Identification
    campaign_id: str
    message_id: Optional[str] = None
    name: str = ""

    # Metadata
    subject: str = ""
    preview_text: str = ""
    send_time: Optional[datetime] = None
    audience_segment: Optional[str] = None

    # Metrics
    metrics: CampaignMetrics = field(default_factory=CampaignMetrics)

    # Content
    blocks: list[EmailBlock] = field(default_factory=list)
    html_original: Optional[str] = None  # For reference/debug
    text_version: Optional[str] = None

    # Extracted elements
    all_links: list[dict] = field(default_factory=list)
    all_images: list[dict] = field(default_factory=list)
    ctas: list[dict] = field(default_factory=list)

    def to_readable_report(self) -> str:
        """Generate the full AI-readable report."""
        lines = []

        # Header
        lines.append("=" * 70)
        lines.append(f"# CAMPAÑA: {self.name}")
        lines.append("=" * 70)
        lines.append("")

        # Identification
        lines.append("## Identificación")
        lines.append("")
        lines.append(f"- ID Campaña: {self.campaign_id}")
        if self.message_id:
            lines.append(f"- ID Mensaje: {self.message_id}")
        lines.append(f"- Nombre: {self.name}")
        lines.append(f"- Asunto: {self.subject}")
        if self.preview_text:
            lines.append(f"- Preview Text: {self.preview_text}")
        if self.send_time:
            lines.append(f"- Fecha de Envío: {self.send_time.strftime('%Y-%m-%d %H:%M')}")
        if self.audience_segment:
            lines.append(f"- Audiencia/Segmento: {self.audience_segment}")
        lines.append("")

        # Metrics
        lines.append(self.metrics.to_readable())
        lines.append("")

        # Email structure (the critical section)
        lines.append("## Estructura del Correo (bloque por bloque)")
        lines.append("")
        for i, block in enumerate(self.blocks, 1):
            lines.append(f"### Bloque {i}")
            lines.append(block.to_readable())
            lines.append("")

        # Links detected
        if self.all_links:
            lines.append("## Links Detectados")
            lines.append("")
            for link in self.all_links:
                text = link.get("text", "Sin texto")
                url = link.get("url", "")
                lines.append(f"- [{text}]({url})")
            lines.append("")

        # CTAs summary
        if self.ctas:
            lines.append("## CTAs Principales")
            lines.append("")
            for cta in self.ctas:
                lines.append(f"- **{cta.get('text', '')}** → {cta.get('url', '')}")
            lines.append("")

        return "\n".join(lines)
