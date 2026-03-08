"""Sales Pipeline Orchestrator.

Coordinates all agents in sequence:

  CompanyInput
      ↓
  DomainAgent         → CompanyAnalysis
      ↓
  CompetitorAgent     → [CompetitorDiscovered]
      ↓
  WebAgent            → [CompetitorWebData]       (scrapping_module)
      ↓
  CleaningAgent       → [CompetitorCleanData]
      ↓
  GapAnalysisAgent    → [MarketGap]               (RAG)
      ↓
  ICPAgent            → [ICPProfile]
      ↓
  PersonaAgent        → [BuyerPersona]            (RAG)
      ↓
  OutreachAgent       → [OutreachAsset]           (RAG)

Each stage is logged. Results are persisted via repositories.
The final output is the enterprise EnterpriseOutput format.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import (
    CleaningAgent,
    CompetitorAgent,
    DomainAgent,
    GapAnalysisAgent,
    ICPAgent,
    OutreachAgent,
    PersonaAgent,
    WebAgent,
)
from app.config import get_settings
from app.core.logging import get_logger
from app.db.repositories import (
    CompanyRepository,
    CompetitorRepository,
    ICPRepository,
    MarketGapRepository,
    OutreachRepository,
    PersonaRepository,
)
from app.schemas.company import CompanyAnalysis, CompanyInput
from app.schemas.competitor import CompetitorCleanData, CompetitorDiscovered, CompetitorWebData
from app.schemas.gap_analysis import MarketGap
from app.schemas.icp import ICPProfile
from app.schemas.outreach import OutreachAsset
from app.schemas.persona import BuyerPersona

logger = get_logger(__name__)
_settings = get_settings()


# ---------------------------------------------------------------------------
# Pipeline output contract
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Enterprise output format — returned by the pipeline orchestrator."""

    company_id: UUID
    company_analysis: CompanyAnalysis
    competitors: list[CompetitorDiscovered] = field(default_factory=list)
    market_gaps: list[MarketGap] = field(default_factory=list)
    icps: list[ICPProfile] = field(default_factory=list)
    personas: list[BuyerPersona] = field(default_factory=list)
    outreach_assets: list[OutreachAsset] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "company_id": str(self.company_id),
            "icps": [icp.model_dump() for icp in self.icps],
            "personas": [p.model_dump() for p in self.personas],
            "outreach_assets": [a.model_dump() for a in self.outreach_assets],
            "market_gaps": [g.model_dump() for g in self.market_gaps],
            "competitors": [c.model_dump() for c in self.competitors],
            "duration_seconds": round(self.duration_seconds, 2),
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class SalesPipeline:
    """Async pipeline orchestrator. Stateless — creates new agents per run."""

    def __init__(
        self,
        db: AsyncSession,
        proxy: str | None = None,
        render_js: bool = False,
        num_icps: int = 3,
        num_personas_per_icp: int = 2,
    ) -> None:
        self._db = db
        self._proxy = proxy
        self._render_js = render_js
        self._num_icps = num_icps
        self._num_personas = num_personas_per_icp

    async def run(self, company_input: CompanyInput) -> PipelineResult:
        """Execute the full sales intelligence pipeline."""
        t0 = time.perf_counter()
        errors: list[str] = []

        logger.info(
            "pipeline.start",
            company=company_input.company_name,
            stages="domain→competitor→web→clean→gap→icp→persona→outreach",
        )

        # ------------------------------------------------------------------
        # Stage 1: Domain Intelligence
        # ------------------------------------------------------------------
        company_analysis = await self._run_stage(
            "domain_intelligence",
            DomainAgent().run,
            company_input,
            errors,
        )
        if company_analysis is None:
            return PipelineResult(
                company_id=uuid.uuid4(),
                company_analysis=None,  # type: ignore
                errors=errors,
                duration_seconds=time.perf_counter() - t0,
            )

        company_id = company_analysis.company_id

        # Persist company
        repo = CompanyRepository(self._db)
        company_record = await repo.create(
            name=company_input.company_name,
            industry=company_input.industry,
            input_data=company_input.model_dump(mode="json"),
        )
        await repo.update_analysis(company_record.id, company_analysis.model_dump(mode="json"))

        # ------------------------------------------------------------------
        # Stage 2: Competitor Discovery
        # ------------------------------------------------------------------
        competitors: list[CompetitorDiscovered] = await self._run_stage(
            "competitor_discovery",
            CompetitorAgent().run,
            company_analysis,
            errors,
        ) or []

        # Persist competitors
        comp_repo = CompetitorRepository(self._db)
        if competitors:
            await comp_repo.bulk_create(
                company_id=company_record.id,
                competitors=[
                    {
                        "name": c.name,
                        "website": c.website,
                        "category": c.category,
                        "positioning": c.positioning,
                        "relevance_score": c.relevance_score,
                    }
                    for c in competitors
                ],
            )

        # ------------------------------------------------------------------
        # Stage 3: Web Intelligence (scrapping_module integration)
        # ------------------------------------------------------------------
        web_data: list[CompetitorWebData] = await self._run_stage(
            "web_intelligence",
            WebAgent(proxy=self._proxy, render_js=self._render_js).run,
            competitors,
            errors,
        ) or []

        # ------------------------------------------------------------------
        # Stage 4: Data Cleaning
        # ------------------------------------------------------------------
        clean_data: list[CompetitorCleanData] = await self._run_stage(
            "data_cleaning",
            CleaningAgent().run,
            web_data,
            errors,
        ) or []

        # ------------------------------------------------------------------
        # Stage 5: Gap Analysis (RAG)
        # ------------------------------------------------------------------
        gaps: list[MarketGap] = await self._run_stage(
            "gap_analysis",
            lambda: GapAnalysisAgent().run(company_analysis, clean_data),
            None,
            errors,
            no_arg=True,
        ) or []

        # Persist gaps
        gap_repo = MarketGapRepository(self._db)
        for gap in gaps:
            await gap_repo.create(
                company_id=company_record.id,
                gap_type=gap.gap_type,
                gap_data=gap.model_dump(mode="json"),
                confidence=gap.confidence_score,
            )

        # ------------------------------------------------------------------
        # Stage 6: ICP Generation
        # ------------------------------------------------------------------
        icps: list[ICPProfile] = await self._run_stage(
            "icp_generation",
            lambda: ICPAgent().run(company_analysis, gaps, self._num_icps),
            None,
            errors,
            no_arg=True,
        ) or []

        # Persist ICPs
        icp_repo = ICPRepository(self._db)
        for icp in icps:
            await icp_repo.create(
                company_id=company_record.id,
                profile_data=icp.model_dump(mode="json"),
            )

        # ------------------------------------------------------------------
        # Stage 7: Persona Generation (RAG-enriched)
        # ------------------------------------------------------------------
        rag_collection = f"gap_{company_id}"
        personas: list[BuyerPersona] = await self._run_stage(
            "persona_generation",
            lambda: PersonaAgent().run(
                company_analysis, icps, self._num_personas, rag_collection=rag_collection
            ),
            None,
            errors,
            no_arg=True,
        ) or []

        # Persist personas
        persona_repo = PersonaRepository(self._db)
        for p in personas:
            await persona_repo.create(
                icp_id=p.icp_id,
                company_id=company_record.id,
                persona_data=p.model_dump(mode="json"),
            )

        # ------------------------------------------------------------------
        # Stage 8: Outreach Generation (RAG-enriched, per persona async)
        # ------------------------------------------------------------------
        outreach_assets: list[OutreachAsset] = []
        outreach_agent = OutreachAgent()
        outreach_repo = OutreachRepository(self._db)

        async def gen_outreach(persona: BuyerPersona) -> list[OutreachAsset]:
            assets = await outreach_agent.run(
                persona=persona,
                analysis=company_analysis,
                rag_collection=rag_collection,
            )
            for a in assets:
                await outreach_repo.create(
                    persona_id=persona.persona_id,
                    company_id=company_record.id,
                    channel=a.channel,
                    content=a.model_dump(mode="json"),
                )
            return assets

        outreach_tasks = [gen_outreach(p) for p in personas]
        outreach_batches = await asyncio.gather(*outreach_tasks, return_exceptions=True)
        for batch in outreach_batches:
            if isinstance(batch, list):
                outreach_assets.extend(batch)
            elif isinstance(batch, Exception):
                errors.append(f"Outreach error: {batch}")

        # ------------------------------------------------------------------
        # Done
        # ------------------------------------------------------------------
        duration = time.perf_counter() - t0
        logger.info(
            "pipeline.complete",
            company=company_input.company_name,
            competitors=len(competitors),
            gaps=len(gaps),
            icps=len(icps),
            personas=len(personas),
            outreach_assets=len(outreach_assets),
            duration_seconds=round(duration, 2),
            errors=len(errors),
        )

        return PipelineResult(
            company_id=company_id,
            company_analysis=company_analysis,
            competitors=competitors,
            market_gaps=gaps,
            icps=icps,
            personas=personas,
            outreach_assets=outreach_assets,
            duration_seconds=duration,
            errors=errors,
        )

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    async def _run_stage(
        self,
        stage_name: str,
        fn,  # callable
        arg,
        errors: list[str],
        *,
        no_arg: bool = False,
    ):
        """Run a pipeline stage with timeout, logging, and error recovery."""
        try:
            logger.info("pipeline.stage.start", stage=stage_name)
            t = time.perf_counter()
            if no_arg:
                result = await asyncio.wait_for(fn(), timeout=_settings.pipeline_timeout_seconds)
            else:
                result = await asyncio.wait_for(fn(arg), timeout=_settings.pipeline_timeout_seconds)
            logger.info(
                "pipeline.stage.done",
                stage=stage_name,
                elapsed=round(time.perf_counter() - t, 2),
            )
            return result
        except asyncio.TimeoutError:
            msg = f"Stage '{stage_name}' timed out after {_settings.pipeline_timeout_seconds}s"
            logger.error("pipeline.stage.timeout", stage=stage_name)
            errors.append(msg)
            return None
        except Exception as exc:
            msg = f"Stage '{stage_name}' failed: {exc}"
            logger.error("pipeline.stage.error", stage=stage_name, error=str(exc))
            errors.append(msg)
            return None
