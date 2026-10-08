from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    system_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    user_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    language: Mapped[str] = mapped_column(
        String(50),
        default="nigerian_english",
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        default="N-ATLAS",
        nullable=False,
    )

    request_payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    response_payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    latency_ms: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship(
        "Project",
        back_populates="experiments",
    )