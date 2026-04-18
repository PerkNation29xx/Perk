from __future__ import annotations
import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    consumer = "consumer"
    merchant = "merchant"
    admin = "admin"


class UserStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class RewardPreference(str, enum.Enum):
    cash = "cash"
    stock = "stock"


class OfferStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class TransactionStatus(str, enum.Enum):
    authorized = "authorized"
    settled = "settled"
    refunded = "refunded"
    reversed = "reversed"


class RewardState(str, enum.Enum):
    pending = "pending"
    available = "available"
    paid = "paid"
    reversed = "reversed"


class TicketStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class DisputeStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    denied = "denied"


class ReferralAttributionStatus(str, enum.Enum):
    linked = "linked"
    qualified = "qualified"


class ReferralEventType(str, enum.Enum):
    share = "share"
    redeem = "redeem"
    qualify = "qualify"


class PrivateAssistantAuthor(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, unique=True)
    # When using Supabase Auth, the password is managed by Supabase and this is null.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supabase_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.consumer, nullable=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active, nullable=False)
    reward_preference: Mapped[RewardPreference] = mapped_column(
        Enum(RewardPreference), default=RewardPreference.cash, nullable=False
    )

    notifications_enabled: Mapped[bool] = mapped_column(default=True)
    location_consent: Mapped[bool] = mapped_column(default=True)
    # Consumer push/geo preferences.
    # Allowed distances (enforced by API): 2, 5, 10 miles.
    alert_radius_miles: Mapped[int] = mapped_column(default=5, nullable=False)
    # Comma-separated category keys (e.g. "restaurant,gas,retail").
    notification_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # SMS consent and delivery telemetry.
    sms_opt_in: Mapped[bool] = mapped_column(default=False, nullable=False)
    sms_opt_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_opt_in_source: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    sms_opt_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sms_welcome_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    email_verification_code_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email_verification_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    merchant_profile: Mapped[Optional["MerchantProfile"]] = relationship(back_populates="owner", uselist=False)
    activations: Mapped[list["OfferActivation"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    rewards: Mapped[list["RewardLedgerEntry"]] = relationship(back_populates="user")
    tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="user")
    referral_profile: Mapped[Optional["ReferralProfile"]] = relationship(back_populates="owner", uselist=False)
    referrals_sent: Mapped[list["ReferralAttribution"]] = relationship(
        back_populates="referrer",
        foreign_keys="ReferralAttribution.referrer_user_id",
    )
    referral_attribution: Mapped[Optional["ReferralAttribution"]] = relationship(
        back_populates="referred_user",
        uselist=False,
        foreign_keys="ReferralAttribution.referred_user_id",
    )
    reviews: Mapped[list["RestaurantReview"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    private_assistant_messages: Mapped[list["PrivateAssistantMessage"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ReferralProfile(Base):
    __tablename__ = "referral_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    invites_sent: Mapped[int] = mapped_column(default=0, nullable=False)
    successful_referrals: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="referral_profile")
    events: Mapped[list["ReferralEvent"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class ReferralAttribution(Base):
    __tablename__ = "referral_attributions"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referral_referred_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referral_code_used: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[ReferralAttributionStatus] = mapped_column(
        Enum(ReferralAttributionStatus),
        default=ReferralAttributionStatus.linked,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    qualified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    referrer: Mapped[User] = relationship(
        back_populates="referrals_sent",
        foreign_keys=[referrer_user_id],
    )
    referred_user: Mapped[User] = relationship(
        back_populates="referral_attribution",
        foreign_keys=[referred_user_id],
    )


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("referral_profiles.id"), index=True)
    event_type: Mapped[ReferralEventType] = mapped_column(
        Enum(ReferralEventType),
        default=ReferralEventType.share,
        nullable=False,
    )
    channel: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    metadata_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped[ReferralProfile] = relationship(back_populates="events")


class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    legal_name: Mapped[str] = mapped_column(String(160))
    dba_name: Mapped[str] = mapped_column(String(160))
    # Optional merchant logo URL for client display (e.g. favicon/service URL).
    logo_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(80))
    subscription_tier: Mapped[str] = mapped_column(String(40), default="starter")
    billing_customer_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    owner: Mapped[User] = relationship(back_populates="merchant_profile")
    locations: Mapped[list["Location"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")
    offers: Mapped[list["Offer"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")
    reviews: Mapped[list["RestaurantReview"]] = relationship(back_populates="merchant")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchant_profiles.id"), index=True)

    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")

    merchant: Mapped[MerchantProfile] = relationship(back_populates="locations")
    offers: Mapped[list["Offer"]] = relationship(back_populates="location")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchant_profiles.id"), index=True)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(140))
    offer_type: Mapped[str] = mapped_column(String(40), default="boost")
    terms_text: Mapped[str] = mapped_column(Text)

    reward_rate_cash: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.01"))
    reward_rate_stock: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.01"))

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schedule_rules: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    daily_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    per_user_limit: Mapped[Optional[int]] = mapped_column(nullable=True)

    approval_status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus), default=OfferStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    merchant: Mapped[MerchantProfile] = relationship(back_populates="offers")
    location: Mapped[Optional[Location]] = relationship(back_populates="offers")
    activations: Mapped[list["OfferActivation"]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="offer")
    reviews: Mapped[list["RestaurantReview"]] = relationship(back_populates="offer")

    @property
    def merchant_name(self) -> str:
        """
        Convenience for API clients: expose the merchant DBA name alongside the offer.
        """
        try:
            return self.merchant.dba_name
        except Exception:
            return f"Merchant #{self.merchant_id}"

    @property
    def merchant_logo_url(self) -> Optional[str]:
        """
        Convenience for API clients: expose a merchant logo URL alongside the offer.
        """
        try:
            return self.merchant.logo_url
        except Exception:
            return None

    @property
    def location_name(self) -> Optional[str]:
        """
        Convenience for API clients: expose location details alongside the offer.
        """
        try:
            return self.location.name if self.location else None
        except Exception:
            return None

    @property
    def location_address(self) -> Optional[str]:
        try:
            return self.location.address if self.location else None
        except Exception:
            return None

    @property
    def location_latitude(self) -> Optional[Decimal]:
        try:
            return self.location.latitude if self.location else None
        except Exception:
            return None

    @property
    def location_longitude(self) -> Optional[Decimal]:
        try:
            return self.location.longitude if self.location else None
        except Exception:
            return None


class RestaurantReview(Base):
    """
    Consumer-authored restaurant feedback.

    One review per user + merchant, with optional offer linkage.
    """

    __tablename__ = "restaurant_reviews"
    __table_args__ = (UniqueConstraint("user_id", "merchant_id", name="uq_review_user_merchant"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchant_profiles.id"), index=True)
    offer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("offers.id"), nullable=True, index=True)

    overall_hearts: Mapped[int] = mapped_column(nullable=False)
    plates_hearts: Mapped[int] = mapped_column(nullable=False)
    sides_hearts: Mapped[int] = mapped_column(nullable=False)
    umami_hearts: Mapped[int] = mapped_column(nullable=False)
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="reviews")
    merchant: Mapped[MerchantProfile] = relationship(back_populates="reviews")
    offer: Mapped[Optional[Offer]] = relationship(back_populates="reviews")

    @property
    def merchant_name(self) -> str:
        try:
            return self.merchant.dba_name
        except Exception:
            return f"Merchant #{self.merchant_id}"


class OfferActivation(Base):
    __tablename__ = "offer_activations"
    __table_args__ = (UniqueConstraint("offer_id", "user_id", name="uq_offer_user_activation"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    offer: Mapped[Offer] = relationship(back_populates="activations")
    user: Mapped[User] = relationship(back_populates="activations")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("merchant_profiles.id"), nullable=True, index=True)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    offer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("offers.id"), nullable=True, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    rail_type: Mapped[str] = mapped_column(String(40), default="card_linked")
    processor_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    status: Mapped[TransactionStatus] = mapped_column(Enum(TransactionStatus), default=TransactionStatus.authorized)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="transactions")
    offer: Mapped[Optional[Offer]] = relationship(back_populates="transactions")
    reward_entries: Mapped[list["RewardLedgerEntry"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")

    @property
    def merchant_name(self) -> Optional[str]:
        try:
            return self.offer.merchant.dba_name if self.offer else None
        except Exception:
            return None

    @property
    def merchant_logo_url(self) -> Optional[str]:
        try:
            return self.offer.merchant.logo_url if self.offer else None
        except Exception:
            return None


class RewardLedgerEntry(Base):
    __tablename__ = "reward_ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("merchant_profiles.id"), nullable=True, index=True)
    offer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("offers.id"), nullable=True, index=True)

    reward_type: Mapped[RewardPreference] = mapped_column(Enum(RewardPreference), nullable=False)
    rate_applied: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    funding_source: Mapped[str] = mapped_column(String(64), default="merchant_promo")

    state: Mapped[RewardState] = mapped_column(Enum(RewardState), default=RewardState.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="reward_entries")
    user: Mapped[User] = relationship(back_populates="rewards")

    @property
    def merchant_name(self) -> Optional[str]:
        try:
            return self.transaction.offer.merchant.dba_name if self.transaction and self.transaction.offer else None
        except Exception:
            return None

    @property
    def merchant_logo_url(self) -> Optional[str]:
        try:
            return self.transaction.offer.merchant.logo_url if self.transaction and self.transaction.offer else None
        except Exception:
            return None


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    txn_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"), nullable=True, index=True)

    category: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(140))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.open)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="tickets")


class DisputeCase(Base):
    __tablename__ = "dispute_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    reason: Mapped[str] = mapped_column(String(160))
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[DisputeStatus] = mapped_column(Enum(DisputeStatus), default=DisputeStatus.open)

    resolution_action: Mapped[Optional[str]] = mapped_column(String(140), nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StockConversion(Base):
    """
    Consumer action: convert available cash rewards into a "Stock Vault" balance.

    This is a demo/MVP representation of investing; it records the USD amount
    converted. Real brokerage execution is out of scope for this project.
    """

    __tablename__ = "stock_conversions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebLeadSubmission(Base):
    """
    Public marketing website form submissions (guest/merchant/contact).
    """

    __tablename__ = "web_lead_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    form_type: Mapped[str] = mapped_column(String(40), index=True)
    source_page: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dob: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    inquiry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)

    payload_json: Mapped[str] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[str] = mapped_column(String(32))

    action: Mapped[str] = mapped_column(String(120))
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(64))

    before_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuntimeSetting(Base):
    """
    Persisted runtime configuration key/value pairs editable from admin UI.

    Values are restricted to admin-only APIs; public APIs never expose them.
    """

    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PrivateAssistantMessage(Base):
    __tablename__ = "private_assistant_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    user_email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    author: Mapped[PrivateAssistantAuthor] = mapped_column(Enum(PrivateAssistantAuthor), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="private_assistant_messages")
