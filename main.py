#!/usr/bin/env python3
"""
Klaviyo Email Campaign Repository

Main script for extracting email campaigns from Klaviyo and generating
AI-readable reports.

Usage:
    python main.py                    # Process all campaigns
    python main.py --test             # Process only first few campaigns (test mode)
    python main.py --campaign-id XYZ  # Process specific campaign
    python main.py --help             # Show help
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.config import Config
from src.klaviyo_client import KlaviyoClient
from src.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract Klaviyo email campaigns and generate AI-readable reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                         # Process all sent campaigns
    python main.py --test                  # Process first 5 campaigns only
    python main.py --limit 10              # Process first 10 campaigns
    python main.py --min-sends 500         # Only include campaigns with 500+ sends
    python main.py --campaign-id abc123    # Process a specific campaign
    python main.py --output ./reports      # Save to custom directory
        """,
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: process only first 5 campaigns",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of campaigns to process (0 = all)",
    )

    parser.add_argument(
        "--min-sends",
        type=int,
        default=None,
        help=f"Minimum sends to include (default: {Config.MIN_SENDS_THRESHOLD})",
    )

    parser.add_argument(
        "--campaign-id",
        type=str,
        help="Process a specific campaign by ID",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for reports",
    )

    parser.add_argument(
        "--individual",
        action="store_true",
        help="Save individual report files per campaign",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine limit
    limit = args.limit
    if args.test:
        limit = 5
    elif Config.TEST_MODE_LIMIT > 0 and limit == 0:
        limit = Config.TEST_MODE_LIMIT

    # Determine minimum sends threshold
    min_sends = args.min_sends or Config.MIN_SENDS_THRESHOLD

    # Initialize components
    try:
        client = KlaviyoClient()
        generator = ReportGenerator(output_dir=args.output)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    logger.info("Starting Klaviyo campaign extraction...")

    # Fetch campaigns
    if args.campaign_id:
        # Single campaign mode
        logger.info(f"Fetching campaign: {args.campaign_id}")
        campaign_data = {
            "campaign_id": args.campaign_id,
            "name": "",
            "subject": "",
            "send_time": None,
        }
        campaign = client.get_full_campaign(campaign_data)
        campaigns = [campaign]
    else:
        # Batch mode
        campaigns = []
        logger.info(f"Fetching campaigns (limit: {limit or 'all'}, min_sends: {min_sends})...")

        for campaign_data in client.get_campaigns(limit=limit):
            logger.info(f"Processing: {campaign_data['name']}")

            campaign = client.get_full_campaign(campaign_data)

            # Apply minimum sends filter
            if campaign.metrics.recipients < min_sends:
                logger.debug(
                    f"Skipping {campaign.name}: "
                    f"{campaign.metrics.recipients} sends < {min_sends} threshold"
                )
                continue

            # Process HTML
            campaign = generator.process_campaign(campaign)
            campaigns.append(campaign)

            logger.info(
                f"  - {campaign.metrics.recipients:,} sends, "
                f"{campaign.metrics.open_rate:.1%} open rate, "
                f"{len(campaign.blocks)} blocks extracted"
            )

    if not campaigns:
        logger.warning("No campaigns found matching criteria.")
        return 0

    logger.info(f"Processed {len(campaigns)} campaigns")

    # Generate reports
    if args.individual:
        # Save individual files
        for campaign in campaigns:
            filepath = generator.save_campaign_report(campaign)
            logger.info(f"Saved: {filepath}")
    else:
        # Save combined report
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"campaigns_report_{date_str}"
        report = generator.generate_batch_report(
            campaigns,
            title=f"Reporte de Campañas - {datetime.now().strftime('%d/%m/%Y')}",
        )
        filepath = generator.save_report(report, filename)
        logger.info(f"Combined report saved to: {filepath}")

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
