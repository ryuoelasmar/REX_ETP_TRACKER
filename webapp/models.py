"""
SQLAlchemy ORM models for the ETP Filing Tracker database.

Tables mirror the CSV pipeline output with added relational integrity.
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.database import Base


class Trust(Base):
    __tablename__ = "trusts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    is_rex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    filings: Mapped[list[Filing]] = relationship(back_populates="trust", cascade="all, delete-orphan")
    fund_statuses: Mapped[list[FundStatus]] = relationship(back_populates="trust", cascade="all, delete-orphan")


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trust_id: Mapped[int] = mapped_column(Integer, ForeignKey("trusts.id"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    form: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date)
    primary_document: Mapped[str | None] = mapped_column(String(200))
    primary_link: Mapped[str | None] = mapped_column(Text)
    submission_txt_link: Mapped[str | None] = mapped_column(Text)
    cik: Mapped[str] = mapped_column(String(20), nullable=False)
    registrant: Mapped[str | None] = mapped_column(String(200))
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    trust: Mapped[Trust] = relationship(back_populates="filings")
    extractions: Mapped[list[FundExtraction]] = relationship(back_populates="filing", cascade="all, delete-orphan")
    analyses: Mapped[list[AnalysisResult]] = relationship(back_populates="filing")

    __table_args__ = (
        Index("idx_filings_trust", "trust_id"),
        Index("idx_filings_form", "form"),
        Index("idx_filings_date", "filing_date"),
    )


class FundExtraction(Base):
    __tablename__ = "fund_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[int] = mapped_column(Integer, ForeignKey("filings.id"), nullable=False)
    series_id: Mapped[str | None] = mapped_column(String(30))
    series_name: Mapped[str | None] = mapped_column(String(300))
    class_contract_id: Mapped[str | None] = mapped_column(String(30))
    class_contract_name: Mapped[str | None] = mapped_column(String(300))
    class_symbol: Mapped[str | None] = mapped_column(String(20))
    extracted_from: Mapped[str | None] = mapped_column(String(50))
    effective_date: Mapped[date | None] = mapped_column(Date)
    effective_date_confidence: Mapped[str | None] = mapped_column(String(20))
    delaying_amendment: Mapped[bool] = mapped_column(Boolean, default=False)
    prospectus_name: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    filing: Mapped[Filing] = relationship(back_populates="extractions")

    __table_args__ = (
        Index("idx_extractions_series", "series_id"),
        Index("idx_extractions_filing", "filing_id"),
    )


class FundStatus(Base):
    __tablename__ = "fund_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trust_id: Mapped[int] = mapped_column(Integer, ForeignKey("trusts.id"), nullable=False)
    series_id: Mapped[str | None] = mapped_column(String(30))
    class_contract_id: Mapped[str | None] = mapped_column(String(30))
    fund_name: Mapped[str] = mapped_column(String(300), nullable=False)
    sgml_name: Mapped[str | None] = mapped_column(String(300))
    prospectus_name: Mapped[str | None] = mapped_column(String(300))
    ticker: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    effective_date_confidence: Mapped[str | None] = mapped_column(String(20))
    latest_form: Mapped[str | None] = mapped_column(String(20))
    latest_filing_date: Mapped[date | None] = mapped_column(Date)
    prospectus_link: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    trust: Mapped[Trust] = relationship(back_populates="fund_statuses")

    __table_args__ = (
        UniqueConstraint("trust_id", "series_id", "class_contract_id", name="uq_fund_status"),
        Index("idx_fund_status_trust", "trust_id"),
        Index("idx_fund_status_status", "status"),
        Index("idx_fund_status_ticker", "ticker"),
    )


class NameHistory(Base):
    __tablename__ = "name_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_clean: Mapped[str | None] = mapped_column(String(300))
    first_seen_date: Mapped[date | None] = mapped_column(Date)
    last_seen_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_form: Mapped[str | None] = mapped_column(String(20))
    source_accession: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_name_history_series", "series_id"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("filings.id"))
    fund_status_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fund_status.id"))
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_used: Mapped[str | None] = mapped_column(Text)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_html: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    filing: Mapped[Filing | None] = relationship(back_populates="analyses")

    __table_args__ = (
        Index("idx_analysis_filing", "filing_id"),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    trusts_processed: Mapped[int] = mapped_column(Integer, default=0)
    filings_found: Mapped[int] = mapped_column(Integer, default=0)
    funds_extracted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(100))


# --- Screener Models ---

class ScreenerUpload(Base):
    __tablename__ = "screener_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stock_rows: Mapped[int] = mapped_column(Integer, default=0)
    etp_rows: Mapped[int] = mapped_column(Integer, default=0)
    filing_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    model_type: Mapped[str | None] = mapped_column(String(50))
    model_r_squared: Mapped[float | None] = mapped_column(Float)

    results: Mapped[list[ScreenerResult]] = relationship(back_populates="upload", cascade="all, delete-orphan")


class ScreenerResult(Base):
    __tablename__ = "screener_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("screener_uploads.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_aum: Mapped[float | None] = mapped_column(Float)
    predicted_aum_low: Mapped[float | None] = mapped_column(Float)
    predicted_aum_high: Mapped[float | None] = mapped_column(Float)
    mkt_cap: Mapped[float | None] = mapped_column(Float)
    call_oi_pctl: Mapped[float | None] = mapped_column(Float)
    total_oi_pctl: Mapped[float | None] = mapped_column(Float)
    volume_pctl: Mapped[float | None] = mapped_column(Float)
    passes_filters: Mapped[bool] = mapped_column(Boolean, default=False)
    filing_status: Mapped[str | None] = mapped_column(String(100))
    competitive_density: Mapped[str | None] = mapped_column(String(50))
    competitor_count: Mapped[int | None] = mapped_column(Integer)
    total_competitor_aum: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    upload: Mapped[ScreenerUpload] = relationship(back_populates="results")

    __table_args__ = (
        Index("idx_screener_upload", "upload_id"),
        Index("idx_screener_score", "composite_score"),
        Index("idx_screener_ticker", "ticker"),
    )
