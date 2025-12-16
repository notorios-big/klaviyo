"""
HTML Parser for Email Campaigns.

Converts HTML email content into structured blocks that are AI-readable.
Handles Klaviyo-specific markup and common email patterns.
"""

import re
import logging
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import (
    EmailBlock,
    ImageBlock,
    TextBlock,
    ButtonBlock,
    SocialBlock,
    SeparatorBlock,
    FooterBlock,
)

logger = logging.getLogger(__name__)

# Social media patterns
SOCIAL_PATTERNS = {
    "facebook": re.compile(r"facebook", re.I),
    "instagram": re.compile(r"instagram", re.I),
    "twitter": re.compile(r"twitter|x\.com", re.I),
    "linkedin": re.compile(r"linkedin", re.I),
    "youtube": re.compile(r"youtube", re.I),
    "tiktok": re.compile(r"tiktok", re.I),
    "pinterest": re.compile(r"pinterest", re.I),
}

# Footer/legal content patterns
FOOTER_PATTERNS = [
    re.compile(r"unsubscribe", re.I),
    re.compile(r"privacy\s*policy", re.I),
    re.compile(r"terms\s*(of\s*service|&\s*conditions)", re.I),
    re.compile(r"©\s*\d{4}", re.I),
    re.compile(r"all\s*rights\s*reserved", re.I),
    re.compile(r"email\s*preferences", re.I),
    re.compile(r"update.*profile", re.I),
]

# Tracking/junk link patterns to ignore
TRACKING_PATTERNS = [
    re.compile(r"trk\.klaviyo\.com", re.I),
    re.compile(r"tracking", re.I),
    re.compile(r"pixel", re.I),
    re.compile(r"beacon", re.I),
]


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Decode common HTML entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("'", "'")
    )
    return text.strip()


def is_social_link(url: str, alt_text: str = "") -> Optional[str]:
    """Check if a URL or alt text indicates a social media link."""
    check_text = f"{url} {alt_text}"
    for platform, pattern in SOCIAL_PATTERNS.items():
        if pattern.search(check_text):
            return platform
    return None


def is_footer_content(text: str) -> bool:
    """Check if text appears to be footer/legal content."""
    for pattern in FOOTER_PATTERNS:
        if pattern.search(text):
            return True
    return False


def is_tracking_url(url: str) -> bool:
    """Check if URL is a tracking pixel or similar."""
    for pattern in TRACKING_PATTERNS:
        if pattern.search(url):
            return True
    return False


def extract_color_from_style(style: str, property_name: str) -> Optional[str]:
    """Extract a color value from inline style."""
    if not style:
        return None
    pattern = rf"{property_name}\s*:\s*([^;]+)"
    match = re.search(pattern, style, re.I)
    if match:
        return match.group(1).strip()
    return None


class EmailHtmlParser:
    """Parser for converting HTML emails to structured blocks."""

    def __init__(self, html: str):
        """
        Initialize the parser.

        Args:
            html: The HTML content to parse
        """
        self.html = html
        self.soup = BeautifulSoup(html, "lxml") if html else None
        self.blocks: list[EmailBlock] = []
        self.all_links: list[dict] = []
        self.all_images: list[dict] = []
        self.ctas: list[dict] = []
        self._processed_texts: set[str] = set()  # Avoid duplicates

    def parse(self) -> list[EmailBlock]:
        """
        Parse the HTML and return structured blocks.

        Returns:
            List of EmailBlock objects in order of appearance
        """
        if not self.soup:
            return []

        # Remove script, style, and head elements
        for element in self.soup(["script", "style", "head", "title", "meta", "link"]):
            element.decompose()

        # Process the body
        body = self.soup.find("body") or self.soup
        self._process_element(body)

        return self.blocks

    def _process_element(self, element: Tag, in_footer: bool = False) -> None:
        """
        Recursively process an HTML element and extract blocks.

        Args:
            element: The BeautifulSoup element to process
            in_footer: Whether we're currently in footer content
        """
        if isinstance(element, NavigableString):
            return

        # Check for Klaviyo-specific classes
        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        # Handle Klaviyo button
        if "kl-button" in classes:
            self._process_button(element)
            return

        # Handle Klaviyo text block
        if "kl-text" in classes:
            self._process_text_block(element)
            return

        # Handle images
        if element.name == "img":
            self._process_image(element)
            return

        # Handle links (might contain buttons or social icons)
        if element.name == "a":
            self._process_link(element)
            return

        # Handle horizontal rules
        if element.name == "hr":
            self.blocks.append(SeparatorBlock(style="line"))
            return

        # Process children
        for child in element.children:
            if isinstance(child, Tag):
                # Check if entering footer section
                child_classes = child.get("class", [])
                if isinstance(child_classes, str):
                    child_classes = child_classes.split()

                is_footer = in_footer or "footer" in child_classes or child.name == "footer"
                self._process_element(child, in_footer=is_footer)

    def _process_image(self, img: Tag) -> None:
        """Process an image element."""
        src = img.get("src", "")
        if not src or is_tracking_url(src):
            return

        alt = clean_text(img.get("alt", ""))

        # Check if it's a social icon
        social = is_social_link(src, alt)
        if social:
            # Will be handled by parent link
            return

        # Get dimensions if available
        width = img.get("width")
        height = img.get("height")

        # Check for parent link
        link_url = None
        parent = img.find_parent("a")
        if parent:
            link_url = parent.get("href", "")

        image_block = ImageBlock(
            src=src,
            alt=alt if alt else None,
            width=int(width) if width and width.isdigit() else None,
            height=int(height) if height and height.isdigit() else None,
            link_url=link_url if link_url and not is_tracking_url(link_url) else None,
        )

        self.blocks.append(image_block)
        self.all_images.append({"src": src, "alt": alt, "link_url": link_url})

    def _process_button(self, element: Tag) -> None:
        """Process a Klaviyo button element."""
        link = element.find("a")
        if not link:
            return

        href = link.get("href", "")
        text = clean_text(link.get_text())

        if not text or not href:
            return

        # Try to get colors from style
        style = element.get("style", "") or link.get("style", "")
        bg_color = extract_color_from_style(style, "background-color")
        text_color = extract_color_from_style(style, "color")

        button_block = ButtonBlock(
            text=text,
            url=href,
            background_color=bg_color,
            color=text_color,
        )

        self.blocks.append(button_block)
        self.ctas.append({"text": text, "url": href})

    def _process_text_block(self, element: Tag) -> None:
        """Process a Klaviyo text block."""
        # Extract text content preserving some structure
        text = self._extract_formatted_text(element)

        if not text:
            return

        # Check if already processed (avoid duplicates)
        text_key = text[:100]  # Use first 100 chars as key
        if text_key in self._processed_texts:
            return
        self._processed_texts.add(text_key)

        # Determine style
        style = None
        if element.find("h1"):
            style = "heading"
        elif element.find("h2") or element.find("h3"):
            style = "subheading"

        # Check if footer content
        if is_footer_content(text):
            self.blocks.append(FooterBlock(content=text, is_legal=True))
        else:
            self.blocks.append(TextBlock(content=text, style=style))

    def _process_link(self, element: Tag) -> None:
        """Process a link element."""
        href = element.get("href", "")
        if not href or is_tracking_url(href):
            return

        # Check for social icon inside
        img = element.find("img")
        if img:
            alt = clean_text(img.get("alt", ""))
            src = img.get("src", "")
            social = is_social_link(href, f"{alt} {src}")

            if social:
                self.blocks.append(SocialBlock(platform=social, url=href))
                return

        # Regular link - store for reference
        text = clean_text(element.get_text())
        if text and len(text) < 200:  # Ignore very long text links
            self.all_links.append({"text": text, "url": href})

        # Process children (might contain images, etc.)
        for child in element.children:
            if isinstance(child, Tag):
                self._process_element(child)

    def _extract_formatted_text(self, element: Tag) -> str:
        """
        Extract text from an element, preserving basic formatting.

        Args:
            element: The element to extract text from

        Returns:
            Cleaned and formatted text
        """
        parts = []

        for item in element.descendants:
            if isinstance(item, NavigableString):
                text = clean_text(str(item))
                if text:
                    parts.append(text)
            elif isinstance(item, Tag):
                if item.name in ("br", "p", "div"):
                    parts.append("\n")
                elif item.name == "hr":
                    parts.append("\n---\n")

        text = " ".join(parts)
        # Clean up multiple newlines/spaces
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = re.sub(r" +", " ", text)
        return text.strip()

    def get_results(self) -> dict:
        """
        Get parsing results.

        Returns:
            Dictionary with blocks, links, images, and CTAs
        """
        return {
            "blocks": self.blocks,
            "all_links": self.all_links,
            "all_images": self.all_images,
            "ctas": self.ctas,
        }


def parse_email_html(html: str) -> dict:
    """
    Parse email HTML and return structured content.

    Args:
        html: The HTML content to parse

    Returns:
        Dictionary with:
        - blocks: List of EmailBlock objects
        - all_links: List of detected links
        - all_images: List of images
        - ctas: List of call-to-action buttons
    """
    if not html:
        return {
            "blocks": [],
            "all_links": [],
            "all_images": [],
            "ctas": [],
        }

    parser = EmailHtmlParser(html)
    parser.parse()
    return parser.get_results()
