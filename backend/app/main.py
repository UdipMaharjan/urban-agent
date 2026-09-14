from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .agents.classifier import ClassificationAgent, StructuredLLM
from .config import Settings
from .database import Base, create_session_factory
from .models import Feedback, FeedbackAnalysis, FeedbackAspect
from .reference import ReferenceData, ReferenceDataError, load_reference_data
from .schemas import (
    BatchClassificationError,
    BatchClassificationSummary,
    FeedbackAnalysisRead,
    FeedbackCreate,
    FeedbackRead,
    ImportSummary,
    Sentiment,
    Severity,
)
from .services.analysis import analysis_response, classify_and_save, get_analysis
from .services.excel import InvalidWorkbook, import_excel
from .services.feedback import store_feedback
from .services.llm import LLMInvalidResponseError, LLMServiceError, LLMTimeoutError, OpenAIService


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

    app = FastAPI(title="UrbanAgent", version="0.2.0", lifespan=lifespan)
    app.state.llm_service = llm_service
    app.state.reference_data = reference_data
    app.state.classification_agent = None

    def get_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    DatabaseSession = Annotated[Session, Depends(get_session)]

    def get_classification_agent() -> ClassificationAgent:
        if app.state.classification_agent is not None:
            return app.state.classification_agent
        try:
            references = app.state.reference_data or load_reference_data(
                settings.categories_path, settings.business_rules_path
            )
            llm = app.state.llm_service or OpenAIService(settings)
        except (ReferenceDataError, LLMServiceError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        app.state.classification_agent = ClassificationAgent(
            llm, references, settings.classification_review_threshold
        )
        return app.state.classification_agent

    def mark_classification_failed(session: Session, feedback_db_id: int) -> None:
        session.rollback()
        feedback = session.get(Feedback, feedback_db_id)
        if feedback is not None and get_analysis(session, feedback_db_id) is None:
            feedback.processing_status = "classification_failed"
            session.commit()

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
