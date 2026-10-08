from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProjectFile(Base):
    __tablename__ = "project_files"

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

    path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    language: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="text",
    )

    size: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    is_binary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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