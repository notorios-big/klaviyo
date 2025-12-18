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
from typing import Optional

from src.config import Config
from src.klaviyo_client import KlaviyoClient
from src.report_generator import ReportGenerator
from src.storage import CampaignStorage, CampaignIgnoreStorage, ImageDescriptionStorage
from src.ai_client import get_ai_client
from src.image_preprocessor import preprocess_campaign_images, should_skip_image

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

    parser.add_argument(
        "--describe-images",
        action="store_true",
        help="Convert images into Spanish paragraphs (uses vision AI, cached)",
    )

    parser.add_argument(
        "--image-model",
        type=str,
        default="gpt-5.2",
        help="Vision model to use for image descriptions (e.g. gpt-5.2, opus, gemini)",
    )

    parser.add_argument(
        "--image-max",
        type=int,
        default=10,
        help="Max images to describe per campaign",
    )

    return parser.parse_args()


def show_stats(
    storage: CampaignStorage,
    ignored: Optional[CampaignIgnoreStorage] = None,
) -> None:
    """Display storage statistics."""
    stats = storage.get_stats()
    ignored_stats = ignored.get_stats() if ignored else {}
    print("\n" + "=" * 50)
    print("ESTADÍSTICAS DEL REPOSITORIO")
    print("=" * 50)
    print(f"Total de campañas almacenadas: {stats['total']}")
    if ignored:
        print(f"Total de campañas ignoradas: {ignored_stats.get('total_ignored', 0)}")
    print(f"Total de envíos: {stats['total_sends']:,}")
    print(f"Open Rate promedio: {stats['avg_open_rate']:.1%}")
    print(f"Click Rate promedio: {stats['avg_click_rate']:.1%}")
    print(f"Archivo: {storage.filepath}")
    if ignored:
        print(f"Archivo ignoradas: {ignored.filepath}")
    print("=" * 50 + "\n")


def generate_report_from_storage(
    storage: CampaignStorage,
    generator: ReportGenerator,
    min_sends: int,
) -> Path:
    """Generate report from stored campaigns."""
    from src.models import Campaign, CampaignMetrics
    from dateutil import parser as date_parser

    class StoredReadableBlock:
        def __init__(self, readable: str):
            self._readable = readable

        def to_readable(self) -> str:
            return self._readable

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

        # Use stored readable blocks directly (avoid double-wrapping)
        for block_data in data.get("blocks", []):
            readable = block_data.get("readable") or ""
            if readable:
                campaign.blocks.append(StoredReadableBlock(readable))

        campaigns.append(campaign)

    if not campaigns:
        logger.warning("No campaigns found matching criteria in storage.")
        return None

    # Sort by date
    campaigns.sort(key=lambda c: c.send_time or datetime.min, reverse=True)

    # Generate report
    filename = "campaigns_report"
    report = generator.generate_batch_report(
        campaigns,
        title=f"Reporte de Campañas - {datetime.now().strftime('%d/%m/%Y')}",
    )
    return generator.save_report(report, filename)


def describe_images_in_storage(
    storage: CampaignStorage,
    *,
    client,
    cache: ImageDescriptionStorage,
    max_images_per_campaign: int,
) -> int:
    """
    Backfill image descriptions inside campaigns_data.json without Klaviyo API calls.

    Converts stored image blocks into text blocks with a Spanish paragraph + URL.
    Returns number of converted image blocks.
    """
    from src.models import TextBlock

    converted = 0
    for campaign in storage._data.get("campaigns", {}).values():
        blocks = campaign.get("blocks", [])
        if not blocks:
            continue

        new_blocks = []
        described_this_campaign = 0
        for b in blocks:
            if b.get("type") != "image":
                new_blocks.append(b)
                continue

            src = (b.get("src") or "").strip()
            alt = (b.get("alt") or "").strip() or None
            width = b.get("width")
            height = b.get("height")
            link_url = b.get("link_url")

            # Filter decorative images (logos, social icons, tiny assets)
            try:
                from src.models import ImageBlock

                tmp = ImageBlock(
                    src=src,
                    alt=alt,
                    width=int(width) if isinstance(width, int) or (isinstance(width, str) and width.isdigit()) else None,
                    height=int(height) if isinstance(height, int) or (isinstance(height, str) and height.isdigit()) else None,
                    link_url=link_url,
                )
                if should_skip_image(tmp):
                    continue
            except Exception:
                pass

            # Skip if already converted previously
            if b.get("from_image") is True:
                new_blocks.append(b)
                continue

            description = cache.get(src) if src and src.startswith("http") else None
            if not description and client and src and src.startswith("http") and described_this_campaign < max_images_per_campaign:
                try:
                    prompt = (
                        "Describe esta imagen de email marketing en español en 1 solo párrafo.\n"
                        "Enfócate en: producto/escena, estilo visual, colores, jerarquía, "
                        "y cualquier texto visible (si se distingue).\n"
                        "No inventes detalles: si no estás seguro, dilo.\n"
                        + (f"Alt/Texto alternativo: {alt}\n" if alt else "")
                    )
                    description = (client.analyze(prompt, images=[src]) or "").strip()
                    if description:
                        cache.set(src, description)
                    described_this_campaign += 1
                except Exception as e:
                    logger.warning(f"Failed to describe image {src}: {e}")

            if not description:
                description = f"Imagen (alt: {alt})." if alt else "Imagen del email (sin alt disponible)."

            paragraph = description + (f"\nURL: {src}" if src else "")
            text_block = TextBlock(content=paragraph, style="imagen")
            new_b = {
                "type": text_block.block_type.value,
                "readable": text_block.to_readable(),
                "content": text_block.content,
                "style": text_block.style,
                "emphasis": text_block.emphasis,
                "from_image": True,
                "image_src": src,
                "image_alt": alt,
            }
            new_blocks.append(new_b)
            converted += 1

        campaign["blocks"] = new_blocks

    return converted


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize storage
    output_dir = args.output or Config.OUTPUT_DIR
    storage = CampaignStorage(output_dir / "campaigns_data.json")
    ignored = CampaignIgnoreStorage(output_dir / "campaigns_ignored.json")
    image_cache = ImageDescriptionStorage(output_dir / "image_descriptions.json")
    generator = ReportGenerator(output_dir=output_dir)

    # Determine minimum sends threshold
    min_sends = args.min_sends or Config.MIN_SENDS_THRESHOLD
    ignore_sends_threshold = Config.IGNORE_SENDS_THRESHOLD

    image_client = None
    if args.describe_images:
        try:
            image_client = get_ai_client(args.image_model)
        except Exception as e:
            logger.warning(
                f"Image preprocessing disabled (failed to init model '{args.image_model}'): {e}"
            )
            image_client = None

    # Stats only mode
    if args.stats:
        show_stats(storage, ignored)
        return 0

    # Report only mode (no API calls)
    if args.report:
        logger.info("Generating report from stored data...")
        if args.describe_images:
            converted = describe_images_in_storage(
                storage,
                client=image_client,
                cache=image_cache,
                max_images_per_campaign=args.image_max,
            )
            if converted:
                logger.info(
                    f"Backfilled {converted} images as paragraphs in storage (cached in {image_cache.filepath})"
                )
                storage.save()
                image_cache.save()
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
    ignored_ids = ignored.get_all_campaign_ids()
    if args.full:
        # Full mode: process all
        campaigns_to_process = [
            c for c in all_campaign_data if c["campaign_id"] not in ignored_ids
        ]
        logger.info(
            f"Full sync mode: processing all campaigns ({len(ignored_ids)} ignored)"
        )
    else:
        # Incremental mode: only process new ones
        stored_ids = storage.get_all_campaign_ids()
        excluded_ids = stored_ids | ignored_ids
        campaigns_to_process = [
            c for c in all_campaign_data
            if c["campaign_id"] not in excluded_ids
        ]
        logger.info(
            f"Incremental mode: {len(campaigns_to_process)} new campaigns to process "
            f"({len(stored_ids)} already stored, {len(ignored_ids)} ignored)"
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
        show_stats(storage, ignored)
        return 0

    # Process campaigns
    processed_count = 0
    skipped_count = 0

    for i, campaign_data in enumerate(campaigns_to_process, 1):
        logger.info(
            f"[{i}/{len(campaigns_to_process)}] Processing: {campaign_data['name']}"
        )

        campaign_id = campaign_data["campaign_id"]
        metrics, ok = client.try_get_campaign_metrics(campaign_id)
        if not ok:
            logger.warning("  Skipping: failed to fetch metrics (will retry next run)")
            skipped_count += 1
            continue

        # Apply minimum sends filter
        if metrics.recipients < ignore_sends_threshold:
            ignored.add_ignored(
                campaign_id,
                name=campaign_data.get("name", ""),
                recipients=metrics.recipients,
                reason=f"recipients<{ignore_sends_threshold}",
                send_time=campaign_data.get("send_time"),
            )
            logger.info(
                f"  Skipping: {metrics.recipients:,} sends < {ignore_sends_threshold} (ignored)"
            )
            skipped_count += 1
            continue

        if metrics.recipients < min_sends:
            logger.info(
                f"  Skipping: {metrics.recipients:,} sends < {min_sends} (min-sends)"
            )
            skipped_count += 1
            continue

        campaign = client.get_full_campaign(campaign_data, metrics=metrics)

        # Process HTML to blocks
        campaign = generator.process_campaign(campaign)

        if args.describe_images:
            campaign = preprocess_campaign_images(
                campaign,
                client=image_client,
                cache=image_cache,
                max_images=args.image_max,
            )

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
    ignored.save()
    image_cache.save()

    logger.info(f"\nProcessed {processed_count} campaigns, skipped {skipped_count}")
    show_stats(storage, ignored)

    # Generate report
    logger.info("Generating consolidated report...")
    filepath = generate_report_from_storage(storage, generator, min_sends)
    if filepath:
        logger.info(f"Report saved to: {filepath}")

    logger.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
