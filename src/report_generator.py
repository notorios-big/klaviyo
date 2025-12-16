"""
Report Generator for Email Campaigns.

Generates AI-readable reports in Markdown format from parsed campaign data.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Config
from .models import Campaign, EmailBlock
from .html_parser import parse_email_html

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates AI-readable reports for email campaigns."""

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize the report generator.

        Args:
            output_dir: Directory to save reports (default: from config)
        """
        self.output_dir = output_dir or Config.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_campaign(self, campaign: Campaign) -> Campaign:
        """
        Process a campaign's HTML and populate its blocks.

        Args:
            campaign: Campaign with HTML content

        Returns:
            Campaign with parsed blocks
        """
        if not campaign.html_original:
            return campaign

        result = parse_email_html(campaign.html_original)
        campaign.blocks = result["blocks"]
        campaign.all_links = result["all_links"]
        campaign.all_images = result["all_images"]
        campaign.ctas = result["ctas"]

        return campaign

    def generate_report(self, campaign: Campaign) -> str:
        """
        Generate a full AI-readable report for a campaign.

        Args:
            campaign: The campaign to report on

        Returns:
            Markdown-formatted report string
        """
        # Ensure campaign is processed
        if not campaign.blocks and campaign.html_original:
            campaign = self.process_campaign(campaign)

        return campaign.to_readable_report()

    def generate_batch_report(
        self,
        campaigns: list[Campaign],
        title: Optional[str] = None,
    ) -> str:
        """
        Generate a combined report for multiple campaigns.

        Args:
            campaigns: List of campaigns to include
            title: Optional title for the report

        Returns:
            Markdown-formatted report string
        """
        lines = []

        # Header
        report_title = title or f"Reporte de Campañas de Email"
        lines.append(f"# {report_title}")
        lines.append("")
        lines.append(f"**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Total de campañas:** {len(campaigns)}")
        lines.append("")

        # Summary table
        lines.append("## Resumen")
        lines.append("")
        lines.append("| Campaña | Fecha | Envíos | Open Rate | Click Rate |")
        lines.append("|---------|-------|--------|-----------|------------|")

        for c in campaigns:
            date_str = c.send_time.strftime("%Y-%m-%d") if c.send_time else "N/A"
            lines.append(
                f"| {c.name[:40]}{'...' if len(c.name) > 40 else ''} | "
                f"{date_str} | "
                f"{c.metrics.recipients:,} | "
                f"{c.metrics.open_rate:.1%} | "
                f"{c.metrics.click_rate:.1%} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

        # Individual campaign reports
        for campaign in campaigns:
            lines.append(self.generate_report(campaign))
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def save_report(
        self,
        report: str,
        filename: str,
    ) -> Path:
        """
        Save a report to a file.

        Args:
            report: The report content
            filename: Name for the file (without extension)

        Returns:
            Path to the saved file
        """
        filepath = self.output_dir / f"{filename}.md"
        filepath.write_text(report, encoding="utf-8")
        logger.info(f"Report saved to: {filepath}")
        return filepath

    def save_campaign_report(self, campaign: Campaign) -> Path:
        """
        Save an individual campaign report.

        Args:
            campaign: The campaign to save

        Returns:
            Path to the saved file
        """
        report = self.generate_report(campaign)

        # Create filename from campaign name/date
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in campaign.name[:50]
        )
        date_str = (
            campaign.send_time.strftime("%Y%m%d")
            if campaign.send_time
            else "unknown"
        )
        filename = f"campaign_{date_str}_{safe_name}"

        return self.save_report(report, filename)


def generate_ai_readable_email(html: str) -> str:
    """
    Quick function to convert HTML email to AI-readable format.

    Args:
        html: The email HTML content

    Returns:
        AI-readable text representation
    """
    result = parse_email_html(html)
    blocks = result["blocks"]

    lines = []
    for i, block in enumerate(blocks, 1):
        lines.append(f"### Bloque {i}")
        lines.append(block.to_readable())
        lines.append("")

    return "\n".join(lines)
