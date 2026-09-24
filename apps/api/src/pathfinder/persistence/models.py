"""SQLAlchemy ORM models the science owns.

The declarative base, the thread, the turn rows and the chunk log belong to
the runtime package; the tables here map on the same base, so a foreign key
between them resolves.
"""

from datetime import datetime
from uuid import UUID, uuid4

from assistant_core.persistence.models import (
    GUID,
    Base,
    Conversation,
    application_id_column,
)
from assistant_core.platform.types import JSONArray, JSONObject
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from veupathdb.domain.strategy import StrategyAst
from veupathdb.model import CamelModel

from pathfinder.domain.message_rating import Rating, WithheldCase


class User(Base):
    """User model for tracking strategies."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    monthly_cost_limit_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Whether finished investigations of this user may be extracted for the
    # eval corpus. Default on; the notice offers the switch on first sight.
    eval_data_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # When the user saw the eval-data notice. Server side, so the notice does
    # not come back on another device.
    eval_notice_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # One-directional: the thread is the runtime's and names no owner back.
    # The relationship stays because it orders the flush and cascades a delete.
    conversations: Mapped[list[Conversation]] = relationship(
        cascade="all, delete-orphan"
    )


class ControlSet(Base):
    """Reusable control gene set with provenance metadata."""

    __tablename__ = "control_sets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[str] = application_id_column()
    name: Mapped[str] = mapped_column(String(255))
    site_id: Mapped[str] = mapped_column(String(100))
    record_type: Mapped[str] = mapped_column(String(100))
    positive_ids: Mapped[JSONArray] = mapped_column(JSON, default=list)
    negative_ids: Mapped[JSONArray] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[JSONArray] = mapped_column(JSON, default=list)
    provenance_notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_control_sets_site_app", "site_id", "application_id"),
        Index("ix_control_sets_user_id", "user_id"),
    )


class ExperimentRow(Base):
    """Persisted experiment with full JSON blob."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[str] = application_id_column()
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    data: Mapped[JSONObject] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_experiments_site_id", "site_id"),
        Index("ix_experiments_user_app", "user_id", "application_id"),
    )


class GeneSetRow(Base):
    """Persisted gene set."""

    __tablename__ = "gene_sets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[str] = application_id_column()
    site_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), default="")
    gene_ids: Mapped[JSONArray] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20), default="paste")
    wdk_strategy_id: Mapped[int | None] = mapped_column(nullable=True)
    wdk_step_id: Mapped[int | None] = mapped_column(nullable=True)
    search_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parameters: Mapped[JSONObject | None] = mapped_column(JSON, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=1)
    vdi_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_gene_sets_user_id", "user_id"),
        Index("ix_gene_sets_site_id", "site_id"),
        Index("ix_gene_sets_user_app_site", "user_id", "application_id", "site_id"),
    )


class ConversationStrategy(Base):
    """PathFinder's WDK strategy projection for one chat thread.

    The row exists only after the first strategy write. Ownership is the
    parent thread's, so this table carries no user or application of its own.
    """

    __tablename__ = "conversation_strategies"
    __table_args__ = (
        Index(
            "ix_conversation_strategies_wdk_strategy_id",
            "wdk_strategy_id",
            unique=True,
            postgresql_where="wdk_strategy_id IS NOT NULL",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    record_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wdk_strategy_id: Mapped[int | None] = mapped_column(nullable=True)
    # True when PathFinder created this strategy on VEuPathDB. A strategy the
    # user made on the website and opened here is not PathFinder's to delete.
    wdk_strategy_created_here: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    strategy_ast: Mapped[JSONObject] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    estimated_size: Mapped[int | None] = mapped_column(nullable=True)
    gene_set_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("gene_sets.id", ondelete="SET NULL"), nullable=True
    )
    gene_set_auto_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    # WDK ids of the saved strategies that this strategy embeds.
    # A saved strategy with at least one consumer cannot be deleted.
    imported_saved_strategy_ids: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )


class ConversationStrategyView(BaseModel):
    """Read shape of a conversation's strategy projection.

    The field defaults are the absent-row semantics: a thread with no side
    row reads exactly like one whose strategy was never built.
    """

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    record_type: str | None = None
    wdk_strategy_id: int | None = None
    wdk_strategy_created_here: bool = False
    is_saved: bool = False
    step_count: int = 0
    strategy_ast: JSONObject = Field(default_factory=dict)
    estimated_size: int | None = None
    gene_set_id: str | None = None
    gene_set_auto_imported: bool = False
    imported_saved_strategy_ids: list[int] = Field(default_factory=list)


class PersistedStrategyGraph(CamelModel):
    """Outer container for a strategy AST snapshot, parsed at the load boundary."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str | None = None
    strategy_ast: StrategyAst | None = None
    wdk_strategy_id: int | None = None


# A thread with no side row reads as a thread whose strategy was never built.
ABSENT_STRATEGY = ConversationStrategyView()


class StrategyRevision(Base):
    """One persisted state of a thread's strategy, in the order it was written.

    Fork and revert read a thread's strategy as it stood at a chosen message,
    so every write of ``conversation_strategies`` appends a row here. The row
    outlives the message it names, which is why ``message_id`` carries no
    foreign key.
    """

    __tablename__ = "strategy_revisions"
    __table_args__ = (
        Index(
            "ix_strategy_revisions_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    record_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    strategy_ast: Mapped[JSONObject] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wdk_strategy_id: Mapped[int | None] = mapped_column(nullable=True)
    # The provenance of the strategy id this snapshot names, so a restore
    # writes the id back with the record it had.
    wdk_strategy_created_here: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    # The saved mark of the strategy this snapshot names. A restore writes it
    # back, so the row never carries the mark of the strategy it left.
    is_saved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class StrategyRevisionView(BaseModel):
    """Read shape of one strategy revision."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    id: int
    conversation_id: UUID
    revision: str
    record_type: str | None = None
    strategy_ast: JSONObject = Field(default_factory=dict)
    step_count: int = 0
    wdk_strategy_id: int | None = None
    wdk_strategy_created_here: bool = False
    is_saved: bool = False
    name: str | None = None
    message_id: UUID | None = None
    created_at: datetime


class ConversationAnalysis(Base):
    """The EDA analysis one chat thread has open.

    The EDA user service is the SSOT for the document; this row is the
    attachment. Ownership is the parent thread's, so there is no user column.
    """

    __tablename__ = "conversation_analyses"
    __table_args__ = (Index("ix_conversation_analyses_dataset_id", "dataset_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    site_id: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False)
    analysis_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Grows by one on every authoring mutation, so two surfaces editing the
    # same analysis always read a strictly increasing number.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # True once a preview has counted this analysis's subset. Binding another
    # analysis restarts it with the revision.
    subset_previewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ConversationAnalysisView(BaseModel):
    """Read shape of a thread's bound analysis."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    site_id: str
    dataset_id: str
    analysis_id: str
    revision: int
    subset_previewed: bool = False


class Export(Base):
    """Temporary download artifact with TTL."""

    __tablename__ = "exports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


STAGED = "staged"
PROMOTED = "promoted"

# A staged row names the user and the thread it came from, so an opt-out or a
# purge can delete it. A promoted row names neither, and holds no extract: the
# science moved into the corpus file. The constraint is the rule itself, so a
# promotion that kept the linkage cannot be written.
_LINKAGE_ENDS_AT_PROMOTION = (
    "(status = 'staged'"
    " AND user_id IS NOT NULL"
    " AND source_conversation_id IS NOT NULL"
    " AND extract IS NOT NULL)"
    " OR "
    "(status = 'promoted'"
    " AND user_id IS NULL"
    " AND source_conversation_id IS NULL"
    " AND extract IS NULL"
    " AND rated_message_id IS NULL)"
)


class EvalStagedCase(Base):
    """One candidate eval case, between extraction and curation.

    The row is the only place a candidate is associated with anybody, and the
    association ends when a curator promotes it.
    """

    __tablename__ = "eval_staged_cases"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    source_conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
    )
    application_id: Mapped[str] = application_id_column()
    site_id: Mapped[str] = mapped_column(String(50), nullable=False)
    assistant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # none_as_null: an absent extract is SQL NULL, which the linkage
    # constraint reads. A JSON null would satisfy IS NOT NULL.
    extract: Mapped[JSONObject | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STAGED, server_default=STAGED
    )
    corpus_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    staged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The disliked message this case was staged for. No foreign key: the case
    # outlives a revert of the message, and promotion ends the handle.
    rated_message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('staged', 'promoted')",
            name="ck_eval_staged_cases_status",
        ),
        CheckConstraint(
            _LINKAGE_ENDS_AT_PROMOTION,
            name="ck_eval_staged_cases_linkage_ends_at_promotion",
        ),
        UniqueConstraint("content_hash", name="uq_eval_staged_cases_content_hash"),
        # One extraction row per thread, and one rated row per disliked message.
        Index(
            "ix_eval_staged_cases_source_conversation",
            "source_conversation_id",
            unique=True,
            postgresql_where=(
                "rated_message_id IS NULL AND source_conversation_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_eval_staged_cases_rated_message",
            "rated_message_id",
            unique=True,
            postgresql_where="rated_message_id IS NOT NULL",
        ),
        Index("ix_eval_staged_cases_user_id", "user_id"),
        Index("ix_eval_staged_cases_status", "status"),
    )


class MessageRating(Base):
    """What one researcher said about one assistant message, and the cases it governs.

    The turn's finalize writes the case keys before any rating exists, so
    ``rating`` is NULL until the researcher rates. The row goes with its message.
    """

    __tablename__ = "message_ratings"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", name="uq_message_ratings_message_user"
        ),
        CheckConstraint(
            "rating IS NULL OR rating IN ('like', 'dislike')",
            name="ck_message_ratings_rating",
        ),
        Index("ix_message_ratings_user_rated", "user_id", "rating"),
        Index("ix_message_ratings_conversation", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str | None] = mapped_column(String(8), nullable=True)
    case_keys: Mapped[JSONArray] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # The case values a rating keeps out of the store, so a later rating can
    # put them back.
    withheld_cases: Mapped[JSONArray] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    rated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MessageRatingView(BaseModel):
    """Read shape of one rating row."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    message_id: UUID
    conversation_id: UUID
    user_id: UUID
    rating: Rating | None = None
    case_keys: list[str] = Field(default_factory=list)
    withheld_cases: list[WithheldCase] = Field(default_factory=list)
    rated_at: datetime | None = None
    updated_at: datetime


class UserProviderKey(Base):
    """A researcher's key for one model provider, sealed under the server secret.

    One live row per user, application and provider. A revoked row keeps its
    hint and holds no ciphertext, so it has nothing to open.
    """

    __tablename__ = "user_provider_keys"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google')",
            name="ck_user_provider_keys_provider",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (ciphertext IS NOT NULL)",
            name="ck_user_provider_keys_live_holds_the_key",
        ),
        CheckConstraint(
            "(refused_at IS NULL) = (refusal IS NULL)",
            name="ck_user_provider_keys_refusal_has_a_time",
        ),
        CheckConstraint(
            "refusal IS NULL OR refusal IN ('invalid', 'unreadable')",
            name="ck_user_provider_keys_refusal",
        ),
        Index(
            "uq_user_provider_keys_live",
            "user_id",
            "application_id",
            "provider",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[str] = application_id_column()
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    hint: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refusal: Mapped[str | None] = mapped_column(String(16), nullable=True)
