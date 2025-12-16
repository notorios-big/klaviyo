"""
Storage module for persisting campaign data.

Provides JSON-based storage to avoid re-fetching campaigns that have
already been processed.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Config
from .models import Campaign, CampaignMetrics

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_FILE = "campaigns_data.json"


class CampaignStorage:
    """JSON-based storage for campaign data."""

    def __init__(self, filepath: Optional[Path] = None):
        """
        Initialize storage.

        Args:
            filepath: Path to JSON file (default: output/campaigns_data.json)
        """
        self.filepath = filepath or (Config.OUTPUT_DIR / DEFAULT_STORAGE_FILE)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        """Load data from JSON file."""
        if not self.filepath.exists():
            return {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "total_campaigns": 0,
                },
                "campaigns": {},
            }

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(
                    f"Loaded {len(data.get('campaigns', {}))} campaigns from storage"
                )
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load storage file: {e}. Starting fresh.")
            return {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "total_campaigns": 0,
                },
                "campaigns": {},
            }

    def save(self) -> None:
        """Save data to JSON file."""
        self._data["metadata"]["last_updated"] = datetime.now().isoformat()
        self._data["metadata"]["total_campaigns"] = len(self._data["campaigns"])

        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(self._data['campaigns'])} campaigns to {self.filepath}")

    def has_campaign(self, campaign_id: str) -> bool:
        """Check if a campaign is already stored."""
        return campaign_id in self._data["campaigns"]

    def get_campaign(self, campaign_id: str) -> Optional[dict]:
        """Get a stored campaign by ID."""
        return self._data["campaigns"].get(campaign_id)

    def get_all_campaign_ids(self) -> set[str]:
        """Get all stored campaign IDs."""
        return set(self._data["campaigns"].keys())

    def get_missing_ids(self, all_ids: list[str]) -> list[str]:
        """
        Get campaign IDs that are not yet stored.

        Args:
            all_ids: List of all campaign IDs from API

        Returns:
            List of IDs not in storage
        """
        stored = self.get_all_campaign_ids()
        return [cid for cid in all_ids if cid not in stored]

    def add_campaign(self, campaign: Campaign) -> None:
        """
        Add a campaign to storage.

        Args:
            campaign: Campaign object to store
        """
        self._data["campaigns"][campaign.campaign_id] = self._serialize_campaign(campaign)

    def _serialize_campaign(self, campaign: Campaign) -> dict:
        """Convert Campaign object to JSON-serializable dict."""
        return {
            "campaign_id": campaign.campaign_id,
            "message_id": campaign.message_id,
            "name": campaign.name,
            "subject": campaign.subject,
            "preview_text": campaign.preview_text,
            "send_time": campaign.send_time.isoformat() if campaign.send_time else None,
            "metrics": {
                "recipients": campaign.metrics.recipients,
                "delivered": campaign.metrics.delivered,
                "opens": campaign.metrics.opens,
                "opens_unique": campaign.metrics.opens_unique,
                "open_rate": campaign.metrics.open_rate,
                "clicks": campaign.metrics.clicks,
                "clicks_unique": campaign.metrics.clicks_unique,
                "click_rate": campaign.metrics.click_rate,
                "bounced": campaign.metrics.bounced,
                "unsubscribes": campaign.metrics.unsubscribes,
                "spam_complaints": campaign.metrics.spam_complaints,
                "conversions": campaign.metrics.conversions,
                "conversion_value": campaign.metrics.conversion_value,
                "conversion_rate": campaign.metrics.conversion_rate,
            },
            "blocks": [self._serialize_block(b) for b in campaign.blocks],
            "all_links": campaign.all_links,
            "all_images": campaign.all_images,
            "ctas": campaign.ctas,
            "processed_at": datetime.now().isoformat(),
        }

    def _serialize_block(self, block) -> dict:
        """Convert an EmailBlock to dict."""
        block_dict = {
            "type": block.block_type.value,
            "readable": block.to_readable(),
        }

        # Add type-specific fields
        if hasattr(block, "content"):
            block_dict["content"] = block.content
        if hasattr(block, "src"):
            block_dict["src"] = block.src
        if hasattr(block, "alt"):
            block_dict["alt"] = block.alt
        if hasattr(block, "text"):
            block_dict["text"] = block.text
        if hasattr(block, "url"):
            block_dict["url"] = block.url
        if hasattr(block, "platform"):
            block_dict["platform"] = block.platform

        return block_dict

    def get_all_campaigns(self) -> list[dict]:
        """Get all stored campaigns as list."""
        return list(self._data["campaigns"].values())

    def get_stats(self) -> dict:
        """Get storage statistics."""
        campaigns = self._data["campaigns"].values()
        total = len(campaigns)

        if total == 0:
            return {
                "total": 0,
                "avg_open_rate": 0,
                "avg_click_rate": 0,
                "total_sends": 0,
            }

        total_sends = sum(c["metrics"]["recipients"] for c in campaigns)
        avg_open = sum(c["metrics"]["open_rate"] for c in campaigns) / total
        avg_click = sum(c["metrics"]["click_rate"] for c in campaigns) / total

        return {
            "total": total,
            "avg_open_rate": avg_open,
            "avg_click_rate": avg_click,
            "total_sends": total_sends,
        }
