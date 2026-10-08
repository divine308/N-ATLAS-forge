from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    default_language: Mapped[str] = mapped_column(
        String(50),
        default="nigerian_english",
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        default="N-ATLAS",
        nullable=False,
    )

    configuration: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
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

    owner = relationship(
        "User",
        back_populates="projects",
    )

    experiments = relationship(
        "Experiment",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    datasets = relationship(
        "Dataset",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    evaluation_suites = relationship(
        "EvaluationSuite",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    evaluation_runs = relationship(
        "EvaluationRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )