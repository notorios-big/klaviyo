"""
Klaviyo API Client.

Handles all interactions with the Klaviyo API for fetching campaigns,
metrics, and email content.
"""

import time
import logging
from datetime import datetime
from typing import Optional, Iterator
from dateutil import parser as date_parser

import requests

from .config import Config
from .models import Campaign, CampaignMetrics

logger = logging.getLogger(__name__)


class KlaviyoClient:
    """Client for interacting with Klaviyo API."""

    # Retry settings for rate limiting
    MAX_RETRIES = 4
    BASE_BACKOFF = 2  # seconds

    def __init__(self):
        """Initialize the Klaviyo client."""
        Config.validate()
        self.base_url = Config.KLAVIYO_API_BASE_URL
        self.headers = Config.get_headers()
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Make an API request with rate limiting and retry logic."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(self.MAX_RETRIES + 1):
            # Rate limiting delay (increases with retries)
            delay = Config.RATE_LIMIT_DELAY * (attempt + 1)
            time.sleep(delay)

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )

                # Handle rate limiting with retry
                if response.status_code == 429:
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BASE_BACKOFF * (2 ** attempt)  # 2, 4, 8, 16 seconds
                        logger.warning(
                            f"Rate limited (429). Retrying in {backoff}s... "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                if attempt < self.MAX_RETRIES and "429" in str(e):
                    backoff = self.BASE_BACKOFF * (2 ** attempt)
                    logger.warning(f"Request failed, retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                logger.error(f"API request failed: {e}")
                raise

        raise requests.exceptions.RequestException(f"Max retries exceeded for {url}")

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, json_data: dict) -> dict:
        """Make a POST request."""
        return self._request("POST", endpoint, json_data=json_data)

    def get_campaigns(
        self,
        status: str = "Sent",
        channel: str = "email",
        limit: Optional[int] = None,
    ) -> Iterator[dict]:
        """
        Fetch all email campaigns with pagination.

        Args:
            status: Campaign status filter (default: "Sent")
            channel: Channel filter (default: "email")
            limit: Maximum number of campaigns to return (for testing)

        Yields:
            Campaign data dictionaries
        """
        params = {
            "filter": f"equals(messages.channel,'{channel}'),equals(status,'{status}')",
            "fields[campaign]": "name,status,created_at,send_time,archived",
            "include": "campaign-messages",
        }

        count = 0
        next_url = None

        while True:
            if next_url:
                # For pagination, use the full URL
                time.sleep(Config.RATE_LIMIT_DELAY)
                response = self.session.get(next_url)
                response.raise_for_status()
                data = response.json()
            else:
                data = self._get("campaigns/", params=params)

            campaigns = data.get("data", [])
            included = data.get("included", [])

            # Create a map of included messages
            messages_map = {
                item["id"]: item
                for item in included
                if item.get("type") == "campaign-message"
            }

            for campaign in campaigns:
                if limit and count >= limit:
                    return

                # Find associated message
                msg_rel = (
                    campaign.get("relationships", {})
                    .get("campaign-messages", {})
                    .get("data", [])
                )
                message_id = msg_rel[0]["id"] if msg_rel else None
                message = messages_map.get(message_id, {}) if message_id else {}
                message_attrs = message.get("attributes", {})

                attrs = campaign.get("attributes", {})

                yield {
                    "campaign_id": campaign["id"],
                    "name": attrs.get("name", "Sin nombre"),
                    "subject": message_attrs.get("label", attrs.get("name", "Sin asunto")),
                    "status": attrs.get("status"),
                    "send_time": attrs.get("send_time") or attrs.get("created_at"),
                    "message_id": message_id,
                }
                count += 1

            # Check for next page
            next_url = data.get("links", {}).get("next")
            if not next_url:
                break

    def get_campaign_metrics(self, campaign_id: str) -> CampaignMetrics:
        """
        Get metrics for a specific campaign.

        Args:
            campaign_id: The campaign ID

        Returns:
            CampaignMetrics object with campaign statistics
        """
        payload = {
            "data": {
                "type": "campaign-values-report",
                "attributes": {
                    "timeframe": {"key": "last_365_days"},
                    "conversion_metric_id": Config.CONVERSION_METRIC_ID,
                    "filter": f'equals(campaign_id,"{campaign_id}")',
                    "statistics": [
                        "opens",
                        "opens_unique",
                        "open_rate",
                        "clicks",
                        "clicks_unique",
                        "click_rate",
                        "recipients",
                        "delivered",
                        "bounced",
                        "unsubscribes",
                        "spam_complaints",
                        "conversions",
                        "conversion_value",
                    ],
                },
            }
        }

        try:
            data = self._post("campaign-values-reports/", json_data=payload)
            results = data.get("data", {}).get("attributes", {}).get("results", [])

            if not results:
                return CampaignMetrics()

            stats = results[0].get("statistics", {})
            recipients = int(stats.get("recipients", 0) or stats.get("delivered", 0) or 0)

            return CampaignMetrics(
                recipients=recipients,
                delivered=int(stats.get("delivered", 0) or 0),
                opens=int(stats.get("opens", 0) or 0),
                opens_unique=int(stats.get("opens_unique", 0) or 0),
                open_rate=float(stats.get("open_rate", 0) or 0),
                clicks=int(stats.get("clicks", 0) or 0),
                clicks_unique=int(stats.get("clicks_unique", 0) or 0),
                click_rate=float(stats.get("click_rate", 0) or 0),
                bounced=int(stats.get("bounced", 0) or 0),
                unsubscribes=int(stats.get("unsubscribes", 0) or 0),
                spam_complaints=int(stats.get("spam_complaints", 0) or 0),
                conversions=int(stats.get("conversions", 0) or 0),
                conversion_value=float(stats.get("conversion_value", 0) or 0),
                conversion_rate=(
                    int(stats.get("conversions", 0) or 0) / recipients
                    if recipients > 0
                    else 0
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to get metrics for campaign {campaign_id}: {e}")
            return CampaignMetrics()

    def get_campaign_content(self, campaign_id: str) -> dict:
        """
        Get the email content for a campaign.

        Args:
            campaign_id: The campaign ID

        Returns:
            Dictionary with subject, preview_text, and message details
        """
        try:
            params = {
                "fields[campaign-message]": "label,content",
            }
            data = self._get(f"campaigns/{campaign_id}/campaign-messages/", params=params)

            messages = data.get("data", [])
            if not messages:
                return {}

            msg = messages[0]
            attrs = msg.get("attributes", {})
            content = attrs.get("content", {})

            return {
                "message_id": msg.get("id"),
                "subject": content.get("subject", ""),
                "preview_text": content.get("preview_text", ""),
                "label": attrs.get("label", ""),
            }
        except Exception as e:
            logger.warning(f"Failed to get content for campaign {campaign_id}: {e}")
            return {}

    def get_message_template(self, message_id: str) -> dict:
        """
        Get the template HTML for a message.

        Args:
            message_id: The campaign message ID

        Returns:
            Dictionary with template details including HTML
        """
        try:
            data = self._get(f"campaign-messages/{message_id}/template/")

            template = data.get("data", {})
            attrs = template.get("attributes", {})

            return {
                "template_id": template.get("id"),
                "name": attrs.get("name"),
                "html": attrs.get("html", ""),
                "editor_type": attrs.get("editor_type"),
            }
        except Exception as e:
            logger.warning(f"Failed to get template for message {message_id}: {e}")
            return {}

    def get_full_campaign(self, campaign_data: dict) -> Campaign:
        """
        Get complete campaign data including metrics and content.

        Args:
            campaign_data: Basic campaign data from get_campaigns()

        Returns:
            Complete Campaign object
        """
        campaign_id = campaign_data["campaign_id"]
        message_id = campaign_data.get("message_id")

        # Get metrics
        metrics = self.get_campaign_metrics(campaign_id)

        # Get content details
        content = self.get_campaign_content(campaign_id)
        if content.get("message_id"):
            message_id = content["message_id"]

        # Get template HTML
        html = ""
        if message_id:
            template = self.get_message_template(message_id)
            html = template.get("html", "")

        # Parse send time
        send_time = None
        if campaign_data.get("send_time"):
            try:
                send_time = date_parser.parse(campaign_data["send_time"])
            except Exception:
                pass

        return Campaign(
            campaign_id=campaign_id,
            message_id=message_id,
            name=campaign_data.get("name", ""),
            subject=content.get("subject") or campaign_data.get("subject", ""),
            preview_text=content.get("preview_text", ""),
            send_time=send_time,
            metrics=metrics,
            html_original=html,
        )
