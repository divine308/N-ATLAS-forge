from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suites"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str] = mapped_column(
        String(50),
        default="general",
        nullable=False,
    )

    # Optional dataset attached to this suite.
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Pinned dataset version. This prevents a suite from silently
    # changing when a new dataset version is uploaded.
    dataset_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    configuration: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship(
        "Project",
        back_populates="evaluation_suites",
    )

    dataset = relationship(
        "Dataset",
        foreign_keys=[dataset_id],
    )

    cases = relationship(
        "EvaluationCase",
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="EvaluationCase.position",
    )

    target_files = relationship(
        "EvaluationSuiteTarget",
        back_populates="suite",
        cascade="all, delete-orphan",
    )


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    suite_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    input: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    expected: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        default="general",
        nullable=False,
    )

    language: Mapped[str] = mapped_column(
        String(50),
        default="nigerian_english",
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # If the case originated from a Dataset record, retain its index.
    dataset_record_index: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    suite = relationship(
        "EvaluationSuite",
        back_populates="cases",
    )


class EvaluationSuiteTarget(Base):
    __tablename__ = "evaluation_suite_targets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    suite_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_file_id: Mapped[int] = mapped_column(
        ForeignKey("project_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    suite = relationship(
        "EvaluationSuite",
        back_populates="target_files",
    )

    project_file = relationship(
        "ProjectFile",
    )


class EvaluationRunTarget(Base):
    """
    Immutable snapshot of the files involved in an evaluation run.

    This is important because a ProjectFile can change after a run.
    The run therefore retains the path and content hash that existed
    when the evaluation was executed.
    """

    __tablename__ = "evaluation_run_targets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    project_file_id: Mapped[int] = mapped_column(
        ForeignKey("project_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    path_snapshot: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    language_snapshot: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    file_size_snapshot: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    run = relationship(
        "EvaluationRun",
        back_populates="target_snapshots",
    )

    project_file = relationship(
        "ProjectFile",
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    suite_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    dataset_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="completed",
        nullable=False,
    )

    total_tests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    passed_tests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    failed_tests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    score: Mapped[float] = mapped_column(
        default=0.0,
        nullable=False,
    )

    results: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    category_summary: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship(
        "Project",
        back_populates="evaluation_runs",
    )

    target_snapshots = relationship(
        "EvaluationRunTarget",
        back_populates="run",
        cascade="all, delete-orphan",
    )