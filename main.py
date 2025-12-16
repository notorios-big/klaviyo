#!/usr/bin/env python3
"""
Klaviyo Email Campaign Repository

Main script for extracting email campaigns from Klaviyo and generating
AI-readable reports. Uses incremental processing to avoid re-fetching
campaigns that have already been processed.

Usage:
    python main.py                    # Process all new campaigns (incremental)
    python main.py --full             # Re-process everything (ignore cache)
    python main.py --test             # Process only first few campaigns
    python main.py --report           # Generate report from stored data only
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
from src.storage import CampaignStorage

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
    python main.py                         # Process new campaigns only (incremental)
    python main.py --full                  # Re-process all campaigns from scratch
    python main.py --test                  # Process first 5 new campaigns only
    python main.py --limit 10              # Process up to 10 new campaigns
    python main.py --report                # Generate report from stored data
    python main.py --stats                 # Show storage statistics
    python main.py --min-sends 500         # Only include campaigns with 500+ sends
        """,
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Full sync: re-process all campaigns (ignore stored data)",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: process only first 5 new campaigns",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of NEW campaigns to process (0 = all new)",
    )

    parser.add_argument(
        "--min-sends",
        type=int,
        default=None,
        help=f"Minimum sends to include (default: {Config.MIN_SENDS_THRESHOLD})",
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate report from stored data only (no API calls)",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show storage statistics and exit",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for reports",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def show_stats(storage: CampaignStorage) -> None:
    """Display storage statistics."""
    stats = storage.get_stats()
    print("\n" + "=" * 50)
    print("ESTADÍSTICAS DEL REPOSITORIO")
    print("=" * 50)
    print(f"Total de campañas almacenadas: {stats['total']}")
    print(f"Total de envíos: {stats['total_sends']:,}")
    print(f"Open Rate promedio: {stats['avg_open_rate']:.1%}")
    print(f"Click Rate promedio: {stats['avg_click_rate']:.1%}")
    print(f"Archivo: {storage.filepath}")
    print("=" * 50 + "\n")


def generate_report_from_storage(
    storage: CampaignStorage,
    generator: ReportGenerator,
    min_sends: int,
) -> Path:
    """Generate report from stored campaigns."""
    from src.models import Campaign, CampaignMetrics
    from dateutil import parser as date_parser

    campaigns = []
    for data in storage.get_all_campaigns():
        # Filter by min sends
        if data["metrics"]["recipients"] < min_sends:
            continue

        # Reconstruct Campaign object for report
        metrics = CampaignMetrics(**data["metrics"])

        send_time = None
        if data.get("send_time"):
            try:
                send_time = date_parser.parse(data["send_time"])
            except Exception:
                pass

        # Use stored readable blocks directly
        campaign = Campaign(
            campaign_id=data["campaign_id"],
            message_id=data.get("message_id"),
            name=data["name"],
            subject=data["subject"],
            preview_text=data.get("preview_text", ""),
            send_time=send_time,
            metrics=metrics,
            all_links=data.get("all_links", []),
            all_images=data.get("all_images", []),
            ctas=data.get("ctas", []),
        )

        # Create simplified blocks from stored data
        from src.models import TextBlock
        for block_data in data.get("blocks", []):
            # Store as text block with the pre-rendered readable content
            campaign.blocks.append(
                TextBlock(content=block_data.get("readable", ""), style=block_data.get("type"))
            )

        campaigns.append(campaign)

    if not campaigns:
        logger.warning("No campaigns found matching criteria in storage.")
        return None

    # Sort by date
    campaigns.sort(key=lambda c: c.send_time or datetime.min, reverse=True)

    # Generate report
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"campaigns_report_{date_str}"
    report = generator.generate_batch_report(
        campaigns,
        title=f"Reporte de Campañas - {datetime.now().strftime('%d/%m/%Y')}",
    )
    return generator.save_report(report, filename)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize storage
    output_dir = args.output or Config.OUTPUT_DIR
    storage = CampaignStorage(output_dir / "campaigns_data.json")
    generator = ReportGenerator(output_dir=output_dir)

    # Determine minimum sends threshold
    min_sends = args.min_sends or Config.MIN_SENDS_THRESHOLD

    # Stats only mode
    if args.stats:
        show_stats(storage)
        return 0

    # Report only mode (no API calls)
    if args.report:
        logger.info("Generating report from stored data...")
        filepath = generate_report_from_storage(storage, generator, min_sends)
        if filepath:
            logger.info(f"Report saved to: {filepath}")
        return 0

    # Initialize API client
    try:
        client = KlaviyoClient()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    logger.info("Starting Klaviyo campaign extraction...")

    # Get all campaign IDs from API first
    logger.info("Fetching campaign list from Klaviyo...")
    all_campaign_data = list(client.get_campaigns())
    logger.info(f"Found {len(all_campaign_data)} total campaigns in Klaviyo")

    # Determine which campaigns to process
    if args.full:
        # Full mode: process all
        campaigns_to_process = all_campaign_data
        logger.info("Full sync mode: processing all campaigns")
    else:
        # Incremental mode: only process new ones
        stored_ids = storage.get_all_campaign_ids()
        campaigns_to_process = [
            c for c in all_campaign_data
            if c["campaign_id"] not in stored_ids
        ]
        logger.info(
            f"Incremental mode: {len(campaigns_to_process)} new campaigns to process "
            f"({len(stored_ids)} already stored)"
        )

    # Apply test/limit
    limit = args.limit
    if args.test:
        limit = 5

    if limit > 0:
        campaigns_to_process = campaigns_to_process[:limit]
        logger.info(f"Limited to {limit} campaigns")

    if not campaigns_to_process:
        logger.info("No new campaigns to process.")
        show_stats(storage)
        return 0

    # Process campaigns
    processed_count = 0
    skipped_count = 0

    for i, campaign_data in enumerate(campaigns_to_process, 1):
        logger.info(
            f"[{i}/{len(campaigns_to_process)}] Processing: {campaign_data['name']}"
        )

        campaign = client.get_full_campaign(campaign_data)

        # Apply minimum sends filter
        if campaign.metrics.recipients < min_sends:
            logger.debug(
                f"  Skipping: {campaign.metrics.recipients} sends < {min_sends} threshold"
            )
            skipped_count += 1
            continue

        # Process HTML to blocks
        campaign = generator.process_campaign(campaign)

        # Store in JSON
        storage.add_campaign(campaign)
        processed_count += 1

        logger.info(
            f"  ✓ {campaign.metrics.recipients:,} sends, "
            f"{campaign.metrics.open_rate:.1%} open rate, "
            f"{len(campaign.blocks)} blocks"
        )

    # Save storage
    storage.save()

    logger.info(f"\nProcessed {processed_count} campaigns, skipped {skipped_count}")
    show_stats(storage)

    # Generate report
    logger.info("Generating consolidated report...")
    filepath = generate_report_from_storage(storage, generator, min_sends)
    if filepath:
        logger.info(f"Report saved to: {filepath}")

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
