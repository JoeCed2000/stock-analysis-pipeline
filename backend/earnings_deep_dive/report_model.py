"""Structured render model for earnings deep-dive reports."""
from typing import Literal

from pydantic import BaseModel, Field


ReportLanguage = Literal["en", "jp"]


class SourceRef(BaseModel):
    label: str
    url: str | None = None
    note: str | None = None


class RenderedTableRow(BaseModel):
    label: str
    cells: list[str]


class RenderedTable(BaseModel):
    columns: list[str]
    rows: list[RenderedTableRow] = Field(default_factory=list)


class RenderedSection(BaseModel):
    key: str
    title: str
    question: str
    table: RenderedTable
    analysis: list[str] = Field(default_factory=list)
    summary_label: str
    summary: str


class EarningsDeepDiveReport(BaseModel):
    ticker: str
    company: str
    quarter: str
    language: ReportLanguage
    generated_at: str
    title: str
    sections: list[RenderedSection]
    sources: list[SourceRef] = Field(default_factory=list)
