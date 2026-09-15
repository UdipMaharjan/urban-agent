from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import date
from threading import Lock
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .agents.classifier import ClassificationAgent, StructuredLLM
from .agents.recommender import RecommendationAgent
from .agents.validator import ValidationAgent
from .config import Settings
from .database import Base, create_session_factory
from .models import (
    Feedback,
    FeedbackAnalysis,
    FeedbackAspect,
    FeedbackValidation,
)
from .reference import ReferenceData, ReferenceDataError, load_reference_data
from .schemas import (
    AnalyticsOverview,
    BatchClassificationError,
    BatchClassificationSummary,
    BatchValidationError,
    BatchValidationSummary,
    BusinessRecommendationRead,
    CategoryAnalytics,
    EmergingIssuesAnalytics,
    FeedbackAnalysisRead,
    FeedbackCreate,
    FeedbackRead,
    FeedbackValidationRead,
    ImportSummary,
    PipelineBatchSummary,
    PipelineResult,
    PipelineState,
    RecommendationApprovalStatus,
    RecommendationApprovalUpdate,
    RecommendationGenerationSummary,
    RecommendationPriority,
    RecoveryBatchSummary,
    RecoveryCaseRead,
    RecoveryRiskLevel,
    RecoveryStatus,
    RecoveryStatusUpdate,
    Sentiment,
    SentimentAnalytics,
    Severity,
    SeverityAnalytics,
    TimelineAnalytics,
    TimelinePeriod,
    TrendAnalytics,
    ValidationStatus,
)
from .services.analysis import analysis_response, classify_and_save, get_analysis
from .services.analytics import AnalyticsFilters, AnalyticsService
from .services.excel import InvalidWorkbook, import_excel
from .services.feedback import store_feedback
from .services.llm import LLMInvalidResponseError, LLMServiceError, LLMTimeoutError, OpenAIService
from .services.pipeline import AnalysisPipeline, pending_ids
from .services.recommendations import (
    RecommendationService,
    decide_recommendation,
    get_recommendation,
    list_recommendations,
    recommendation_response,
)
from .services.recovery import (
    AmbiguousFeedbackIdError,
    RecoveryNotTrustedError,
    RecoveryService,
    get_recovery_case,
    list_recovery_cases,
    recovery_case_response,
    update_recovery_status,
)
from .services.validation import (
    get_validation,
    validate_and_save,
    validation_response,
)


def create_app(
    settings: Settings | None = None,
    *,
    llm_service: StructuredLLM | None = None,
    reference_data: ReferenceData | None = None,
) -> FastAPI:
    settings = settings or Settings()
    engine, session_factory = create_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="UrbanAgent", version="0.5.0", lifespan=lifespan)
    app.state.llm_service = llm_service
    app.state.reference_data = reference_data
    app.state.classification_agent = None
    app.state.validation_agent = None
    app.state.recommendation_agent = None
    # Synchronous local deployment: reject overlapping analysis requests, not queue them.
    app.state.analysis_lock = Lock()

    def get_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    DatabaseSession = Annotated[Session, Depends(get_session)]

    def get_references() -> ReferenceData:
        try:
            if app.state.reference_data is None:
                app.state.reference_data = load_reference_data(
                    settings.categories_path, settings.business_rules_path
                )
            return app.state.reference_data
        except ReferenceDataError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def get_llm_service() -> StructuredLLM:
        try:
            if app.state.llm_service is None:
                app.state.llm_service = OpenAIService(settings)
            return app.state.llm_service
        except LLMServiceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def get_classification_agent() -> ClassificationAgent:
        if app.state.classification_agent is not None:
            return app.state.classification_agent
        references = get_references()
        app.state.classification_agent = ClassificationAgent(
            get_llm_service(),
            references,
            settings.classification_review_threshold,
        )
        return app.state.classification_agent

    def get_validation_agent() -> ValidationAgent:
        if app.state.validation_agent is not None:
            return app.state.validation_agent
        references = get_references()
        app.state.validation_agent = ValidationAgent(
            get_llm_service(),
            references,
            settings.validation_review_threshold,
        )
        return app.state.validation_agent

    def get_recommendation_agent() -> RecommendationAgent:
        if app.state.recommendation_agent is None:
            app.state.recommendation_agent = RecommendationAgent(get_llm_service())
        return app.state.recommendation_agent

    def get_analytics_filters(
        start_date: date | None = None,
        end_date: date | None = None,
        source: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
        category: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    ) -> AnalyticsFilters:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
        if category is not None and category not in get_references().category_names:
            raise HTTPException(
                status_code=422,
                detail="category is not an approved UrbanMart category.",
            )
        return AnalyticsFilters(
            start_date=start_date,
            end_date=end_date,
            source=source,
            category=category,
        )

    AnalyticsQuery = Annotated[AnalyticsFilters, Depends(get_analytics_filters)]

    def analytics_service(session: Session) -> AnalyticsService:
        references = get_references()
        return AnalyticsService(
            session,
            [category.name for category in references.categories.categories],
            trend_min_feedback=settings.trend_min_feedback,
            spike_min_current_count=settings.spike_min_current_count,
            spike_percent_increase=settings.spike_percent_increase,
        )

    def recommendation_service(session: Session) -> RecommendationService:
        return RecommendationService(
            session,
            analytics_service(session),
            get_references(),
        )

    def recovery_service(session: Session) -> RecoveryService:
        try:
            return RecoveryService(
                session,
                high_score=settings.recovery_high_score,
                critical_score=settings.recovery_critical_score,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def mark_classification_failed(session: Session, feedback_db_id: int) -> None:
        session.rollback()
        feedback = session.get(Feedback, feedback_db_id)
        if feedback is not None and get_analysis(session, feedback_db_id) is None:
            feedback.processing_status = "classification_failed"
            session.commit()

    def mark_validation_failed(session: Session, feedback_db_id: int) -> None:
        session.rollback()
        feedback = session.get(Feedback, feedback_db_id)
        if feedback is not None and get_validation(session, feedback_db_id) is None:
            feedback.processing_status = "validation_failed"
            session.commit()

    def pipeline(session: Session) -> AnalysisPipeline:
        return AnalysisPipeline(
            session, get_classification_agent, get_validation_agent, recovery_service(session)
        )

    @app.get("/api/feedback/analysis-state", response_model=PipelineState)
    def analysis_state(session: DatabaseSession):
        records = session.scalars(
            select(Feedback).options(
                selectinload(Feedback.analysis).selectinload(FeedbackAnalysis.validation)
            )
        ).all()
        review = sum(
            bool(
                record.analysis
                and (
                    record.analysis.requires_review
                    or (
                        record.analysis.validation
                        and (
                            record.analysis.validation.requires_human_review
                            or record.analysis.validation.validation_status
                            in {"needs_review", "rejected"}
                        )
                    )
                )
            )
            for record in records
        )
        return PipelineState(
            total=len(records),
            pending=len(pending_ids(session)),
            requires_review=review,
            is_running=app.state.analysis_lock.locked(),
        )

    @app.post("/api/feedback/analyze-pending", response_model=PipelineBatchSummary)
    def analyze_pending_feedback(session: DatabaseSession):
        if not app.state.analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "Feedback analysis is already running. Please wait.")
        try:
            return pipeline(session).analyze_pending()
        finally:
            app.state.analysis_lock.release()

    @app.post("/api/feedback/{id}/analyze", response_model=PipelineResult)
    def analyze_feedback(id: int, session: DatabaseSession, force: bool = False):
        if session.get(Feedback, id) is None:
            raise HTTPException(404, "Feedback not found.")
        if not app.state.analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "Feedback analysis is already running. Please wait.")
        try:
            return pipeline(session).analyze(id, force=force)
        finally:
            app.state.analysis_lock.release()

    @app.get("/health")
    def health(session: DatabaseSession):
        session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/feedback", response_model=list[FeedbackRead])
    def list_feedback(
        session: DatabaseSession,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return session.scalars(
            select(Feedback).order_by(Feedback.id).offset(offset).limit(limit)
        ).all()

    @app.get("/api/feedback/analyses", response_model=list[FeedbackAnalysisRead])
    def list_analyses(
        session: DatabaseSession,
        sentiment: Sentiment | None = None,
        severity: Severity | None = None,
        category: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
        requires_review: bool | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        statement = select(FeedbackAnalysis).options(
            selectinload(FeedbackAnalysis.aspects), selectinload(FeedbackAnalysis.feedback)
        )
        if sentiment is not None:
            statement = statement.where(FeedbackAnalysis.sentiment == sentiment.value)
        if severity is not None:
            statement = statement.where(FeedbackAnalysis.severity == severity.value)
        if category is not None:
            statement = statement.where(
                FeedbackAnalysis.aspects.any(FeedbackAspect.category == category)
            )
        if requires_review is not None:
            statement = statement.where(FeedbackAnalysis.requires_review == requires_review)
        analyses = session.scalars(
            statement.order_by(FeedbackAnalysis.id).offset(offset).limit(limit)
        ).all()
        return [analysis_response(analysis) for analysis in analyses]

    @app.get("/api/feedback/validations", response_model=list[FeedbackValidationRead])
    def list_validations(
        session: DatabaseSession,
        validation_status: ValidationStatus | None = None,
        requires_human_review: bool | None = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        statement = select(FeedbackValidation).options(
            selectinload(FeedbackValidation.analysis).selectinload(FeedbackAnalysis.feedback),
            selectinload(FeedbackValidation.categories),
            selectinload(FeedbackValidation.issues),
        )
        if validation_status is not None:
            statement = statement.where(
                FeedbackValidation.validation_status == validation_status.value
            )
        if requires_human_review is not None:
            statement = statement.where(
                FeedbackValidation.requires_human_review == requires_human_review
            )
        validations = session.scalars(
            statement.order_by(FeedbackValidation.id).offset(offset).limit(limit)
        ).all()
        return [validation_response(validation) for validation in validations]

    @app.get("/api/analytics/overview", response_model=AnalyticsOverview)
    def analytics_overview(session: DatabaseSession, filters: AnalyticsQuery):
        return analytics_service(session).overview(filters)

    @app.get("/api/analytics/sentiment", response_model=SentimentAnalytics)
    def analytics_sentiment(session: DatabaseSession, filters: AnalyticsQuery):
        return analytics_service(session).sentiment(filters)

    @app.get("/api/analytics/categories", response_model=CategoryAnalytics)
    def analytics_categories(session: DatabaseSession, filters: AnalyticsQuery):
        return analytics_service(session).categories(filters)

    @app.get("/api/analytics/severity", response_model=SeverityAnalytics)
    def analytics_severity(session: DatabaseSession, filters: AnalyticsQuery):
        return analytics_service(session).severity(filters)

    @app.get("/api/analytics/trends", response_model=TrendAnalytics)
    def analytics_trends(session: DatabaseSession, filters: AnalyticsQuery):
        return analytics_service(session).trends(filters)

    @app.get("/api/analytics/timeline", response_model=TimelineAnalytics)
    def analytics_timeline(
        session: DatabaseSession,
        filters: AnalyticsQuery,
        period: TimelinePeriod = TimelinePeriod.DAILY,
    ):
        return analytics_service(session).timeline(filters, period)

    @app.get("/api/analytics/emerging-issues", response_model=EmergingIssuesAnalytics)
    def analytics_emerging_issues(
        session: DatabaseSession,
        filters: AnalyticsQuery,
        period: TimelinePeriod = TimelinePeriod.WEEKLY,
        as_of: date | None = None,
    ):
        return analytics_service(session).emerging_issues(filters, period, as_of)

    @app.post(
        "/api/recommendations/generate",
        response_model=RecommendationGenerationSummary,
    )
    def generate_recommendations(
        session: DatabaseSession,
        filters: AnalyticsQuery,
        period: TimelinePeriod = TimelinePeriod.WEEKLY,
        as_of: date | None = None,
    ):
        service = recommendation_service(session)
        trend_inputs = service.trend_inputs(filters, period=period, as_of=as_of)
        if not trend_inputs:
            return RecommendationGenerationSummary(
                eligible_trends=0,
                generated=0,
                skipped_duplicates=0,
                failed=0,
            )
        return service.generate(
            get_recommendation_agent(),
            filters,
            period=period,
            as_of=as_of,
            trend_inputs=trend_inputs,
        )

    @app.get("/api/recommendations", response_model=list[BusinessRecommendationRead])
    def retrieve_recommendations(
        session: DatabaseSession,
        priority: RecommendationPriority | None = None,
        category: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
        approval_status: RecommendationApprovalStatus | None = None,
    ):
        recommendations = list_recommendations(
            session,
            priority=priority.value if priority else None,
            category=category,
            approval_status=approval_status.value if approval_status else None,
        )
        return [recommendation_response(item) for item in recommendations]

    @app.get("/api/recommendations/{id}", response_model=BusinessRecommendationRead)
    def retrieve_recommendation(id: int, session: DatabaseSession):
        recommendation = get_recommendation(session, id)
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        return recommendation_response(recommendation)

    @app.patch(
        "/api/recommendations/{id}/approval",
        response_model=BusinessRecommendationRead,
    )
    def update_recommendation_approval(
        id: int,
        update: RecommendationApprovalUpdate,
        session: DatabaseSession,
    ):
        recommendation = get_recommendation(session, id)
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        return recommendation_response(
            decide_recommendation(session, recommendation, update.approval_status)
        )

    @app.post("/api/recovery/evaluate/{feedback_id}", response_model=RecoveryCaseRead)
    def evaluate_recovery(
        feedback_id: str,
        session: DatabaseSession,
        source: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    ):
        statement = select(Feedback).where(Feedback.feedback_id == feedback_id)
        if source is not None:
            statement = statement.where(Feedback.source == source)
        matches = session.scalars(statement).all()
        if not matches:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail="More than one source uses this feedback_id; provide source.",
            )
        try:
            case = recovery_service(session).evaluate_feedback(feedback_id, source)
        except RecoveryNotTrustedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except AmbiguousFeedbackIdError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return recovery_case_response(case)

    @app.post("/api/recovery/evaluate-all", response_model=RecoveryBatchSummary)
    def evaluate_all_recovery(session: DatabaseSession):
        return recovery_service(session).evaluate_all()

    @app.get("/api/recovery/cases", response_model=list[RecoveryCaseRead])
    def retrieve_recovery_cases(
        session: DatabaseSession,
        risk_level: RecoveryRiskLevel | None = None,
        status: RecoveryStatus | None = None,
    ):
        cases = list_recovery_cases(
            session,
            risk_level=risk_level.value if risk_level else None,
            status=status.value if status else None,
        )
        return [recovery_case_response(case) for case in cases]

    @app.get("/api/recovery/cases/{id}", response_model=RecoveryCaseRead)
    def retrieve_recovery_case(id: int, session: DatabaseSession):
        case = get_recovery_case(session, id)
        if case is None:
            raise HTTPException(status_code=404, detail="Recovery case not found.")
        return recovery_case_response(case)

    @app.patch("/api/recovery/cases/{id}/status", response_model=RecoveryCaseRead)
    def change_recovery_status(
        id: int,
        update: RecoveryStatusUpdate,
        session: DatabaseSession,
    ):
        case = get_recovery_case(session, id)
        if case is None:
            raise HTTPException(status_code=404, detail="Recovery case not found.")
        return recovery_case_response(update_recovery_status(session, case, update))

    @app.get("/api/feedback/{id}", response_model=FeedbackRead)
    def get_feedback(id: int, session: DatabaseSession):
        feedback = session.get(Feedback, id)
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        return feedback

    @app.get("/api/feedback/{id}/analysis", response_model=FeedbackAnalysisRead)
    def retrieve_analysis(id: int, session: DatabaseSession):
        if session.get(Feedback, id) is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        analysis = get_analysis(session, id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Feedback has no completed analysis.")
        return analysis_response(analysis)

    @app.get("/api/feedback/{id}/validation", response_model=FeedbackValidationRead)
    def retrieve_validation(id: int, session: DatabaseSession):
        if session.get(Feedback, id) is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        validation = get_validation(session, id)
        if validation is None:
            raise HTTPException(status_code=404, detail="Feedback has no completed validation.")
        return validation_response(validation)

    @app.post("/api/feedback", response_model=FeedbackRead, status_code=201)
    def create_feedback(payload: FeedbackCreate, session: DatabaseSession):
        feedback, outcome = store_feedback(session, payload)
        if outcome != "created":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": outcome,
                    "message": "Feedback with this source and feedback_id already exists.",
                    "id": feedback.id,
                },
            )
        session.commit()
        return feedback

    @app.post("/api/feedback/{id}/classify", response_model=FeedbackAnalysisRead)
    def classify_feedback(
        id: int,
        session: DatabaseSession,
        force: bool = False,
    ):
        feedback = session.get(Feedback, id)
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        existing = get_analysis(session, id)
        if existing is not None and not force:
            return analysis_response(existing)
        agent = get_classification_agent()
        try:
            return analysis_response(classify_and_save(session, feedback, agent))
        except LLMTimeoutError as exc:
            mark_classification_failed(session, id)
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except (LLMInvalidResponseError, LLMServiceError) as exc:
            mark_classification_failed(session, id)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/feedback/classify-all", response_model=BatchClassificationSummary)
    def classify_all_feedback(
        session: DatabaseSession,
        force: bool = False,
    ):
        statement = select(Feedback).order_by(Feedback.id)
        if not force:
            statement = statement.where(~Feedback.analysis.has())
        feedback_records = session.scalars(statement).all()
        summary = BatchClassificationSummary(
            total=len(feedback_records), processed=0, failed=0, requires_review=0
        )
        if not feedback_records:
            return summary
        agent = get_classification_agent()
        for feedback in feedback_records:
            try:
                analysis = classify_and_save(session, feedback, agent)
                summary.processed += 1
                summary.requires_review += int(analysis.requires_review)
            except (LLMInvalidResponseError, LLMServiceError) as exc:
                mark_classification_failed(session, feedback.id)
                summary.failed += 1
                summary.errors.append(
                    BatchClassificationError(
                        feedback_db_id=feedback.id,
                        feedback_id=feedback.feedback_id,
                        message=str(exc),
                    )
                )
        return summary

    @app.post("/api/feedback/{id}/validate", response_model=FeedbackValidationRead)
    def validate_feedback(
        id: int,
        session: DatabaseSession,
        force: bool = False,
    ):
        feedback = session.get(Feedback, id)
        if feedback is None:
            raise HTTPException(status_code=404, detail="Feedback not found.")
        analysis = get_analysis(session, id)
        if analysis is None:
            raise HTTPException(
                status_code=409,
                detail="Feedback must have a completed classification before validation.",
            )
        existing = get_validation(session, id)
        if existing is not None and not force:
            return validation_response(existing)
        agent = get_validation_agent()
        try:
            return validation_response(validate_and_save(session, analysis, agent))
        except LLMTimeoutError as exc:
            mark_validation_failed(session, id)
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except (LLMInvalidResponseError, LLMServiceError) as exc:
            mark_validation_failed(session, id)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/feedback/validate-all", response_model=BatchValidationSummary)
    def validate_all_feedback(
        session: DatabaseSession,
        force: bool = False,
    ):
        statement = (
            select(FeedbackAnalysis)
            .where(FeedbackAnalysis.analysis_status == "completed")
            .options(
                selectinload(FeedbackAnalysis.feedback),
                selectinload(FeedbackAnalysis.aspects),
                selectinload(FeedbackAnalysis.validation),
            )
            .order_by(FeedbackAnalysis.id)
        )
        if not force:
            statement = statement.where(~FeedbackAnalysis.validation.has())
        analyses = session.scalars(statement).all()
        summary = BatchValidationSummary(
            total=len(analyses), validated=0, needs_review=0, rejected=0, failed=0
        )
        if not analyses:
            return summary
        agent = get_validation_agent()
        for analysis in analyses:
            feedback_db_id = analysis.feedback_id
            external_id = analysis.feedback.feedback_id
            try:
                validation = validate_and_save(session, analysis, agent)
                if validation.validation_status == ValidationStatus.NEEDS_REVIEW.value:
                    summary.needs_review += 1
                elif validation.validation_status == ValidationStatus.REJECTED.value:
                    summary.rejected += 1
                else:
                    summary.validated += 1
            except (LLMInvalidResponseError, LLMServiceError) as exc:
                mark_validation_failed(session, feedback_db_id)
                summary.failed += 1
                summary.errors.append(
                    BatchValidationError(
                        feedback_db_id=feedback_db_id,
                        feedback_id=external_id,
                        message=str(exc),
                    )
                )
        return summary

    @app.post("/api/import/excel", response_model=ImportSummary)
    def upload_excel(session: DatabaseSession, file: Annotated[UploadFile, File()]):
        try:
            if not file.filename or not file.filename.lower().endswith(".xlsx"):
                raise HTTPException(status_code=400, detail="Only .xlsx files are accepted.")
            content = file.file.read(settings.max_upload_bytes + 1)
            if len(content) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail="Upload exceeds configured size limit.")
            try:
                return import_excel(content, session, settings)
            except InvalidWorkbook as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            file.file.close()

    return app


app = create_app()
