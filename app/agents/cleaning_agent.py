"""Data Cleaning Agent.

Normalizes and structures raw web-scraped competitor data:
- Removes HTML noise (already done by extractor, but further cleanup needed)
- Deduplicates features
- Normalizes pricing text
- Produces clean, LLM-ready text

This is intentionally lightweight: the heavy HTML stripping was already
done by extractor.py in the scrapping_module.
"""

from __future__ import annotations

import re
import time

from app.core.logging import get_logger
from app.schemas.competitor import CompetitorCleanData, CompetitorWebData
from app.utils.text_cleaning import (
    clean_text,
    deduplicate_list,
    normalize_whitespace,
)

logger = get_logger(__name__)


class CleaningAgent:
    """Stateless data cleaning / normalization agent."""

    async def run(self, web_data_list: list[CompetitorWebData]) -> list[CompetitorCleanData]:
        t0 = time.perf_counter()
        logger.info(
            "cleaning_agent.start",
            module_name="CleaningAgent",
            input_summary=f"items={len(web_data_list)}",
        )

        cleaned = [self._clean_one(wd) for wd in web_data_list]

        elapsed = time.perf_counter() - t0
        logger.info(
            "cleaning_agent.complete",
            module_name="CleaningAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"cleaned={len(cleaned)} records",
        )
        return cleaned

    @staticmethod
    def _clean_one(wd: CompetitorWebData) -> CompetitorCleanData:
        # Clean features
        clean_features = deduplicate_list([
            clean_text(f) for f in wd.features if clean_text(f)
        ])

        # Clean pricing
        pricing_raw = " | ".join(wd.pricing_tiers) if wd.pricing_tiers else ""
        clean_pricing = normalize_whitespace(clean_text(pricing_raw))

        # Clean positioning
        clean_positioning = normalize_whitespace(clean_text(wd.marketing_copy))

        # Clean value proposition
        clean_vp = normalize_whitespace(clean_text(wd.value_proposition))

        # Build full normalized text for embedding
        all_paragraphs = [clean_text(p) for p in wd.raw_paragraphs if clean_text(p)]
        normalized_text = "\n".join(
            [clean_vp, clean_positioning] + clean_features[:10] + all_paragraphs[:20]
        )
        normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text).strip()

        return CompetitorCleanData(
            competitor_id=wd.competitor_id,
            clean_features=clean_features,
            clean_pricing=clean_pricing,
            clean_positioning=clean_positioning,
            clean_value_proposition=clean_vp,
            normalized_text=normalized_text[:8000],  # cap for embedding/LLM
        )
