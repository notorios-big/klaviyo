"""
Configuration module for Klaviyo Email Campaign Repository.
Loads settings from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration settings for the application."""

    # Klaviyo API
    KLAVIYO_API_KEY: str = os.getenv("KLAVIYO_API_KEY", "")
    KLAVIYO_API_BASE_URL: str = "https://a.klaviyo.com/api"
    KLAVIYO_API_REVISION: str = os.getenv("KLAVIYO_API_REVISION", "2024-02-15")

    # Processing
    MIN_SENDS_THRESHOLD: int = int(os.getenv("MIN_SENDS_THRESHOLD", "100"))
    TEST_MODE_LIMIT: int = int(os.getenv("TEST_MODE_LIMIT", "0"))

    # Conversion metric for Klaviyo reports
    CONVERSION_METRIC_ID: str = os.getenv("CONVERSION_METRIC_ID", "TKuEA4")

    # Output
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    OUTPUT_FORMAT: str = os.getenv("OUTPUT_FORMAT", "markdown")

    # Rate limiting - Klaviyo has strict limits, use 3s minimum
    RATE_LIMIT_DELAY: float = float(os.getenv("RATE_LIMIT_DELAY", "3.0"))

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        if not cls.KLAVIYO_API_KEY:
            raise ValueError(
                "KLAVIYO_API_KEY is required. "
                "Set it in your .env file or environment variables."
            )
        return True

    @classmethod
    def get_headers(cls) -> dict:
        """Get headers for Klaviyo API requests."""
        return {
            "Authorization": f"Klaviyo-API-Key {cls.KLAVIYO_API_KEY}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/json",
            "revision": cls.KLAVIYO_API_REVISION,
        }
