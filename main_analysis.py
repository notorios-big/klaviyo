#!/usr/bin/env python3
"""
AI-Powered Email Campaign Analysis

Analyzes stored campaigns using AI to identify:
- What subject lines drive engagement
- What content sells (and why)
- What DOESN'T work (and why) - most important!
- Patterns in top vs bottom performers

Usage:
    python main_analysis.py --model opus       # Use Claude Opus
    python main_analysis.py --model gemini     # Use Gemini 1.5 Pro
    python main_analysis.py --model gpt4o      # Use GPT-4o
    python main_analysis.py --model opus --with-images  # Include image analysis
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import Config
from src.storage import CampaignStorage
from src.ai_client import get_ai_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def prepare_campaign_summary(campaign: dict, include_content: bool = True) -> dict:
    """
    Prepare a token-optimized summary of a campaign.

    Focuses on data relevant for analysis, strips unnecessary details.
    """
    metrics = campaign.get("metrics", {})

    summary = {
        "id": campaign["campaign_id"][:8],  # Short ID
        "name": campaign["name"][:80],
        "subject": campaign["subject"],
        "preview": campaign.get("preview_text", "")[:100],
        "date": campaign.get("send_time", "")[:10] if campaign.get("send_time") else "N/A",
        "sends": metrics.get("recipients", 0),
        "open_rate": f"{metrics.get('open_rate', 0):.1%}",
        "click_rate": f"{metrics.get('click_rate', 0):.1%}",
        "conversions": metrics.get("conversions", 0),
        "revenue": f"${metrics.get('conversion_value', 0):.0f}" if metrics.get("conversion_value") else "$0",
    }

    if include_content:
        # Compact content representation
        blocks = campaign.get("blocks", [])
        content_summary = []
        for b in blocks[:8]:  # Limit blocks
            block_type = b.get("type", "unknown")
            if block_type == "text":
                text = b.get("content", "")[:200]
                content_summary.append(f"[TEXT] {text}")
            elif block_type == "button":
                content_summary.append(f"[CTA] {b.get('text', 'Button')} → {b.get('url', '')[:50]}")
            elif block_type == "image":
                alt = b.get("alt", "imagen")
                content_summary.append(f"[IMG] {alt}")
            elif block_type == "social":
                content_summary.append(f"[SOCIAL] {b.get('platform', '')}")

        summary["content"] = "\n".join(content_summary) if content_summary else "No content"

        # CTAs summary
        ctas = campaign.get("ctas", [])
        if ctas:
            summary["main_ctas"] = [{"text": c.get("text", "")[:50], "url": c.get("url", "")[:80]} for c in ctas[:3]]

    return summary


def categorize_campaigns(campaigns: list[dict]) -> dict:
    """
    Categorize campaigns by performance.

    Returns dict with 'top', 'bottom', 'middle' performers.
    """
    # Filter campaigns with enough data
    valid = [c for c in campaigns if c.get("metrics", {}).get("recipients", 0) >= 100]

    if not valid:
        return {"top": [], "bottom": [], "middle": [], "all": []}

    # Sort by open rate (primary) and click rate (secondary)
    sorted_by_open = sorted(
        valid,
        key=lambda x: (
            x.get("metrics", {}).get("open_rate", 0),
            x.get("metrics", {}).get("click_rate", 0)
        ),
        reverse=True
    )

    # Sort by conversions/revenue for sales analysis
    sorted_by_sales = sorted(
        valid,
        key=lambda x: (
            x.get("metrics", {}).get("conversions", 0),
            x.get("metrics", {}).get("conversion_value", 0)
        ),
        reverse=True
    )

    n = len(sorted_by_open)
    top_n = max(5, n // 5)  # Top 20% or at least 5
    bottom_n = max(5, n // 5)

    return {
        "top_engagement": sorted_by_open[:top_n],
        "bottom_engagement": sorted_by_open[-bottom_n:],
        "top_sales": sorted_by_sales[:top_n],
        "bottom_sales": sorted_by_sales[-bottom_n:],
        "all": valid,
        "total_count": len(valid),
    }


def build_analysis_prompt(categorized: dict, include_full_content: bool = False) -> str:
    """
    Build the analysis prompt optimized for token usage.
    """

    # Prepare summaries
    top_engagement = [prepare_campaign_summary(c, include_full_content) for c in categorized["top_engagement"]]
    bottom_engagement = [prepare_campaign_summary(c, include_full_content) for c in categorized["bottom_engagement"]]
    top_sales = [prepare_campaign_summary(c, include_full_content) for c in categorized["top_sales"]]
    bottom_sales = [prepare_campaign_summary(c, include_full_content) for c in categorized["bottom_sales"]]

    prompt = f"""# ANÁLISIS DE CAMPAÑAS DE EMAIL MARKETING

Eres un experto en email marketing y copywriting. Analiza estas campañas de email para identificar patrones de éxito y fracaso.

## DATOS A ANALIZAR

**Total de campañas:** {categorized["total_count"]}

---

### TOP PERFORMERS - ENGAGEMENT (mejores open/click rates)

```json
{json.dumps(top_engagement, indent=2, ensure_ascii=False)}
```

---

### PEORES PERFORMERS - ENGAGEMENT (peores open/click rates)

```json
{json.dumps(bottom_engagement, indent=2, ensure_ascii=False)}
```

---

### TOP PERFORMERS - VENTAS (más conversiones/revenue)

```json
{json.dumps(top_sales, indent=2, ensure_ascii=False)}
```

---

### PEORES PERFORMERS - VENTAS (menos conversiones)

```json
{json.dumps(bottom_sales, indent=2, ensure_ascii=False)}
```

---

## TU ANÁLISIS DEBE RESPONDER:

### 1. ASUNTOS QUE GENERAN APERTURA
- ¿Qué patrones tienen los asuntos con mejor open rate?
- ¿Qué palabras, estructuras o técnicas usan?
- Ejemplos específicos de los mejores asuntos

### 2. ASUNTOS QUE NO FUNCIONAN (CRÍTICO)
- ¿Por qué los peores asuntos fallan?
- ¿Qué errores comunes cometen?
- Ejemplos específicos de qué evitar

### 3. CONTENIDO QUE VENDE
- ¿Qué estructura de email genera más conversiones?
- ¿Qué tipo de CTAs funcionan mejor?
- ¿Qué longitud/formato es más efectivo?

### 4. CONTENIDO QUE NO CONVIERTE (CRÍTICO)
- ¿Por qué ciertos emails no venden aunque tengan aperturas?
- ¿Qué desconecta al lector del call-to-action?
- Errores específicos en los emails de bajo rendimiento

### 5. RECOMENDACIONES ACCIONABLES
- Top 5 cosas que HACER basado en lo que funciona
- Top 5 cosas que NO HACER basado en lo que falla
- Template/estructura sugerida para futuros emails

### 6. PATRONES OCULTOS
- ¿Hay correlación entre día/hora y performance?
- ¿Ciertos temas funcionan mejor que otros?
- ¿Hay fatiga de audiencia o patrones temporales?

---

**IMPORTANTE:** Sé específico con ejemplos reales de las campañas. No des consejos genéricos. Basa todo en los datos proporcionados.

**FORMATO:** Usa markdown con headers claros, bullets, y ejemplos específicos citando los nombres/asuntos de las campañas.
"""

    return prompt


def get_image_urls(categorized: dict, limit: int = 20) -> list[str]:
    """Extract unique image URLs from top campaigns for vision analysis."""
    urls = []
    seen = set()

    for campaign in categorized.get("top_engagement", []) + categorized.get("top_sales", []):
        for img in campaign.get("all_images", []):
            url = img.get("src", "")
            if url and url not in seen and url.startswith("http"):
                urls.append(url)
                seen.add(url)
                if len(urls) >= limit:
                    return urls

    return urls


def run_analysis(
    storage: CampaignStorage,
    model: str,
    with_images: bool = False,
    output_dir: Path = None,
) -> Path:
    """
    Run AI analysis on stored campaigns.

    Returns path to analysis output file.
    """
    # Load campaigns
    campaigns = storage.get_all_campaigns()
    if not campaigns:
        raise ValueError("No campaigns in storage. Run main.py first.")

    logger.info(f"Loaded {len(campaigns)} campaigns from storage")

    # Categorize by performance
    categorized = categorize_campaigns(campaigns)
    logger.info(
        f"Categorized: {len(categorized['top_engagement'])} top, "
        f"{len(categorized['bottom_engagement'])} bottom performers"
    )

    # Build prompt
    prompt = build_analysis_prompt(categorized, include_full_content=True)
    logger.info(f"Prompt size: ~{len(prompt)} characters")

    # Get AI client
    logger.info(f"Initializing AI client: {model}")
    client = get_ai_client(model)

    # Get images if requested and supported
    images = None
    if with_images and client.supports_vision:
        images = get_image_urls(categorized, limit=15)
        if images:
            logger.info(f"Including {len(images)} images for visual analysis")
            prompt += "\n\n### IMÁGENES DE LAS CAMPAÑAS TOP\nAnaliza también las imágenes adjuntas para identificar patrones visuales."

    # Run analysis
    logger.info("Running AI analysis... (this may take a minute)")
    try:
        response = client.analyze(prompt, images=images)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        raise

    # Save output
    output_dir = output_dir or Config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = output_dir / f"analysis_{model}_{timestamp}.md"

    # Build full output
    output_content = f"""# Análisis de Campañas de Email Marketing
**Modelo:** {model}
**Fecha:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Campañas analizadas:** {categorized['total_count']}

---

{response}

---

## Metadata del Análisis

- Top performers (engagement): {len(categorized['top_engagement'])}
- Bottom performers (engagement): {len(categorized['bottom_engagement'])}
- Top performers (ventas): {len(categorized['top_sales'])}
- Bottom performers (ventas): {len(categorized['bottom_sales'])}
- Imágenes analizadas: {len(images) if images else 0}
"""

    output_file.write_text(output_content, encoding="utf-8")
    logger.info(f"Analysis saved to: {output_file}")

    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI-powered analysis of email campaigns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Models available:
  opus          Claude Opus (best quality, Anthropic)
  sonnet        Claude Sonnet (faster, Anthropic)
  gpt4o         GPT-4o (OpenAI)
  gpt4-turbo    GPT-4 Turbo (OpenAI)
  gemini        Gemini 1.5 Pro (Google)
  gemini-flash  Gemini 1.5 Flash (faster, Google)

Examples:
  python main_analysis.py --model opus
  python main_analysis.py --model gemini --with-images
  python main_analysis.py --model gpt4o --output ./reports
        """
    )

    parser.add_argument(
        "--model", "-m",
        required=True,
        help="AI model to use (opus, sonnet, gpt4o, gemini, etc.)"
    )

    parser.add_argument(
        "--with-images",
        action="store_true",
        help="Include image analysis (requires vision-capable model)"
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory for analysis"
    )

    parser.add_argument(
        "--storage",
        type=Path,
        default=None,
        help="Path to campaigns_data.json"
    )

    args = parser.parse_args()

    # Load storage
    storage_path = args.storage or (Config.OUTPUT_DIR / "campaigns_data.json")
    storage = CampaignStorage(storage_path)

    stats = storage.get_stats()
    if stats["total"] == 0:
        logger.error("No campaigns in storage. Run 'python main.py' first to fetch campaigns.")
        return 1

    logger.info(f"Storage: {stats['total']} campaigns, avg open rate: {stats['avg_open_rate']:.1%}")

    try:
        output_file = run_analysis(
            storage=storage,
            model=args.model,
            with_images=args.with_images,
            output_dir=args.output,
        )
        print(f"\n✓ Analysis complete: {output_file}")
        return 0
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
