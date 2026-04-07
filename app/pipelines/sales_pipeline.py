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
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import (
    CleaningAgent,
    CompetitorAgent,
    DomainAgent,
    GapAnalysisAgent,
    ICPAgent,
    OptimizationAgent,
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
from app.schemas.outreach import OutreachAsset, OutreachFeedback
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
        num_icps: int = 1,
        num_personas_per_icp: int = 1,
        on_progress: Callable | None = None,
    ) -> None:
        self._db = db
        self._proxy = proxy
        self._render_js = render_js
        self._num_icps = num_icps
        self._num_personas = num_personas_per_icp
        self._on_progress = on_progress
        self._company_id: UUID | None = None

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
            company_id=company_analysis.company_id,
        )
        await repo.update_analysis(company_record.id, company_analysis.model_dump(mode="json"))
        await self._db.commit()
        self._company_id = company_record.id
        if self._on_progress:
            self._on_progress(status="Company analyzed", progress=self._get_stage_progress("domain_intelligence"), company_id=str(self._company_id))

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
                        "competitor_id": c.competitor_id,
                        "name": c.name,
                        "website": c.website,
                        "category": c.category,
                        "positioning": c.positioning,
                        "relevance_score": c.relevance_score,
                    }
                    for c in competitors
                ],
            )
            await self._db.commit()

        # Stage 3: Web Intelligence (scrapping_module integration)
        # ------------------------------------------------------------------
        web_agent = WebAgent(proxy=self._proxy, render_js=self._render_js)
        web_data: list[CompetitorWebData] = []
        
        if competitors:
            logger.info("pipeline.web_intel.start", count=len(competitors))
            tasks = [web_agent._scrape_one(c) for c in competitors]
            for future in asyncio.as_completed(tasks):
                try:
                    wd = await future
                    web_data.append(wd)
                    await comp_repo.update_web_data(wd.competitor_id, wd.model_dump(mode="json"))
                    await self._db.commit()
                    if self._on_progress:
                        self._on_progress(status=f"Scraped {wd.website}", progress=self._get_stage_progress("web_intelligence"), company_id=str(self._company_id))
                except Exception as e:
                    logger.error("pipeline.web_intel.error", error=str(e))
                    errors.append(f"Scrape failed: {e}")
                    
        # ------------------------------------------------------------------
        # Stage 4: Data Cleaning
        # ------------------------------------------------------------------
        clean_data: list[CompetitorCleanData] = await self._run_stage(
            "data_cleaning",
            CleaningAgent().run,
            web_data,
            errors,
        ) or []

        # Persist clean data
        for cd in clean_data:
            await comp_repo.update_clean_data(cd.competitor_id, cd.model_dump(mode="json"))
        await self._db.commit()

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
                gap_id=gap.gap_id,
            )
        await self._db.commit()

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
                icp_id=icp.icp_id,
            )
        await self._db.commit()

        # Stage 7: Persona Generation (RAG-enriched)
        # ------------------------------------------------------------------
        rag_collection = f"gap_{str(company_record.id)}"
        persona_agent = PersonaAgent()
        persona_repo = PersonaRepository(self._db)
        personas: list[BuyerPersona] = []
        
        if icps:
            logger.info("pipeline.persona_gen.start", count=len(icps))
            persona_tasks = [persona_agent._generate_for_icp(company_analysis, icp, self._num_personas, rag_collection) for icp in icps]
            for future in asyncio.as_completed(persona_tasks):
                try:
                    p_list = await future
                    for p in p_list:
                        personas.append(p)
                        await persona_repo.create(
                            icp_id=p.icp_id,
                            company_id=company_record.id,
                            persona_data=p.model_dump(mode="json"),
                            persona_id=p.persona_id,
                        )
                    await self._db.commit()
                    if self._on_progress:
                        self._on_progress(status=f"Generated {len(p_list)} personas", progress=self._get_stage_progress("persona_generation"), company_id=str(self._company_id))
                except Exception as e:
                    logger.error("pipeline.persona_gen.error", error=str(e))
                    errors.append(f"Persona generation failed: {e}")

        # ------------------------------------------------------------------
        # Stage 8: Outreach Generation (RAG-enriched, parallel per persona)
        # ------------------------------------------------------------------
        if self._on_progress:
            self._on_progress(status="Generating outreach assets...", progress=self._get_stage_progress("outreach_generation"), company_id=str(self._company_id))

        outreach_assets: list[OutreachAsset] = []
        outreach_agent = OutreachAgent()
        outreach_repo = OutreachRepository(self._db)

        async def gen_outreach(persona: BuyerPersona) -> list[OutreachAsset]:
            assets = await outreach_agent.run(
                persona=persona,
                analysis=company_analysis,
                rag_collection=rag_collection,
            )
            return assets

        outreach_tasks = [gen_outreach(p) for p in personas]
        outreach_batches = await asyncio.gather(*outreach_tasks, return_exceptions=True)
        
        for batch in outreach_batches:
            if isinstance(batch, list):
                outreach_assets.extend(batch)
                # Sequentially save to DB to avoid SQLAlchemy concurrent flush errors
                for a in batch:
                    await outreach_repo.create(
                        persona_id=a.persona_id,
                        company_id=company_record.id,
                        channel=a.channel,
                        content=a.model_dump(mode="json"),
                        asset_id=a.asset_id,
                    )
            elif isinstance(batch, Exception):
                msg = f"Outreach error: {batch}"
                logger.error("pipeline.outreach.error", error=str(batch))
                errors.append(msg)
        
        await self._db.commit()

        # ------------------------------------------------------------------
        # Stage 9: Optimization (Simulate & Analyze)
        # ------------------------------------------------------------------
        if self._on_progress:
            self._on_progress(status="Seeding initial performance data...", progress=self._get_stage_progress("optimization"), company_id=str(self._company_id))

        await outreach_repo.seed_feedback(company_record.id)
        await self._db.commit()

        # Run optimization analysis based on seeded data
        opt_agent = OptimizationAgent()
        # Mock feedback list for agent ingestion
        records = await outreach_repo.get_by_company(company_record.id)
        feedback_list = [
            OutreachFeedback(
                asset_id=r.id, 
                open_rate=r.open_rate, 
                reply_rate=r.reply_rate, 
                conversion_rate=r.conversion_rate
            ) 
            for r in records
        ]
        
        optimization_result = await self._run_stage(
            "optimization",
            lambda: opt_agent.run([OutreachAsset(**r.content, asset_id=r.id, persona_id=r.persona_id, company_id=r.company_id, channel=r.channel) for r in records], feedback_list),
            None,
            errors,
            no_arg=True
        )

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
            company_id=self._company_id,
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
            if self._on_progress:
                pct = self._get_stage_progress(stage_name)
                self._on_progress(
                    status=f"Executing {stage_name}...", 
                    progress=pct,
                    company_id=str(self._company_id) if self._company_id else None
                )

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
            
    def _get_stage_progress(self, stage_name: str) -> int:
        """Map stage name to approximate completion percentage."""
        stages = [
            "domain_intelligence",
            "competitor_discovery",
            "web_intelligence",
            "data_cleaning",
            "gap_analysis",
            "icp_generation",
            "persona_generation",
            "outreach_generation",
            "optimization"
        ]
        try:
            idx = stages.index(stage_name)
            return int(((idx + 1) / len(stages)) * 100)
        except ValueError:
            return 0
