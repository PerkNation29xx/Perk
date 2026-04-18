from __future__ import annotations
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal, Optional

from app.db.models import (
    DisputeStatus,
    OfferStatus,
    RewardPreference,
    RewardState,
    TicketStatus,
    TransactionStatus,
    UserRole,
    UserStatus,
)


class APIMessage(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=32)
    password: str = Field(min_length=8)
    role: UserRole = UserRole.consumer
    reward_preference: RewardPreference = RewardPreference.cash
    notifications_enabled: bool = True
    location_consent: bool = True
    alert_radius_miles: int = 5
    notification_categories: Optional[str] = None
    sms_opt_in: bool = False
    sms_opt_in_source: Optional[str] = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str]
    role: UserRole
    reward_preference: RewardPreference
    notifications_enabled: bool
    location_consent: bool
    alert_radius_miles: int
    notification_categories: Optional[str]
    sms_opt_in: bool
    sms_opt_in_at: Optional[datetime]
    sms_opt_in_source: Optional[str]
    sms_opt_out_at: Optional[datetime]
    sms_welcome_sent_at: Optional[datetime]
    email_verified: bool


class UserPreferencesUpdate(BaseModel):
    """
    Partial update for user preferences.

    Used by mobile clients after login (e.g. changing consumer reward preference).
    """

    reward_preference: Optional[RewardPreference] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    notifications_enabled: Optional[bool] = None
    location_consent: Optional[bool] = None
    alert_radius_miles: Optional[int] = None
    notification_categories: Optional[str] = None
    sms_opt_in: Optional[bool] = None
    sms_opt_in_source: Optional[str] = Field(default=None, max_length=80)


class RegisterResponse(BaseModel):
    user: UserOut
    verification_required: bool = True
    verification_code: Optional[str] = None


class MerchantProfileCreate(BaseModel):
    legal_name: str
    dba_name: str
    category: str


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class EmailVerificationRequestResponse(BaseModel):
    message: str
    verification_code: Optional[str] = None


class LocationCreate(BaseModel):
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    hours: Optional[str] = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    hours: Optional[str]
    status: str


class OfferCreate(BaseModel):
    title: str
    offer_type: str = "boost"
    terms_text: str
    reward_rate_cash: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reward_rate_stock: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    starts_at: datetime
    ends_at: datetime
    location_id: Optional[int] = None
    schedule_rules: Optional[str] = None
    daily_cap: Optional[Decimal] = None
    total_cap: Optional[Decimal] = None
    per_user_limit: Optional[int] = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: int
    merchant_name: str
    merchant_logo_url: Optional[str] = None
    merchant_category: Optional[str] = None
    location_id: Optional[int]
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    location_latitude: Optional[Decimal] = None
    location_longitude: Optional[Decimal] = None
    title: str
    offer_type: str
    terms_text: str
    reward_rate_cash: Decimal
    reward_rate_stock: Decimal
    starts_at: datetime
    ends_at: datetime
    schedule_rules: Optional[str]
    daily_cap: Optional[Decimal]
    total_cap: Optional[Decimal]
    per_user_limit: Optional[int]
    approval_status: OfferStatus
    is_activated: bool = False
    is_live_offer: bool = False
    is_coming_soon: bool = False
    is_early_bird_opted_in: bool = False
    early_bird_count: int = 0
    is_popular: bool = False
    activation_count: int = 0
    area_activation_count: int = 0
    rank_score: float = 0.0
    review_avg_hearts: float = 0.0
    review_count: int = 0
    my_review_hearts: Optional[int] = None


class RestaurantReviewCreate(BaseModel):
    """
    Consumer review payload.

    Quick-rating: set `overall_hearts` only.
    Detailed rating: also set `plates_hearts`, `sides_hearts`, `umami_hearts`,
    plus optional `review_text`.
    """

    offer_id: Optional[int] = None
    merchant_id: Optional[int] = None
    overall_hearts: int = Field(ge=1, le=5)
    plates_hearts: Optional[int] = Field(default=None, ge=1, le=5)
    sides_hearts: Optional[int] = Field(default=None, ge=1, le=5)
    umami_hearts: Optional[int] = Field(default=None, ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)


class RestaurantReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    merchant_id: int
    merchant_name: str
    offer_id: Optional[int]
    overall_hearts: int
    plates_hearts: int
    sides_hearts: int
    umami_hearts: int
    review_text: Optional[str]
    created_at: datetime
    updated_at: datetime


class RestaurantReviewSummaryOut(BaseModel):
    merchant_id: int
    merchant_name: str
    review_count: int
    avg_overall_hearts: float
    my_review_hearts: Optional[int] = None


class OfferActivationCreate(BaseModel):
    offer_id: int


class TransactionCreate(BaseModel):
    offer_id: Optional[int] = None
    merchant_id: Optional[int] = None
    location_id: Optional[int] = None
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    rail_type: str = "card_linked"


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    merchant_id: Optional[int]
    merchant_name: Optional[str] = None
    merchant_logo_url: Optional[str] = None
    location_id: Optional[int]
    offer_id: Optional[int]
    amount: Decimal
    currency: str
    rail_type: str
    status: TransactionStatus
    occurred_at: datetime


class RewardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_id: int
    user_id: int
    merchant_id: Optional[int]
    merchant_name: Optional[str] = None
    merchant_logo_url: Optional[str] = None
    offer_id: Optional[int]
    reward_type: RewardPreference
    rate_applied: Decimal
    reward_amount: Decimal
    state: RewardState
    created_at: datetime


class RedeemRequest(BaseModel):
    reward_ids: list[int] = Field(min_length=1)


class SupportTicketCreate(BaseModel):
    txn_id: Optional[int] = None
    category: str
    subject: str
    message: str


class SupportTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    txn_id: Optional[int]
    category: str
    subject: str
    message: str
    status: TicketStatus
    created_at: datetime


class DisputeCreate(BaseModel):
    txn_id: int
    reason: str
    evidence: Optional[str] = None


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_id: int
    user_id: int
    reason: str
    evidence: Optional[str]
    status: DisputeStatus
    resolution_action: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]


class OfferDecision(BaseModel):
    status: OfferStatus


class RewardAdjustRequest(BaseModel):
    state: RewardState
    reason: str


class InvestmentSummaryOut(BaseModel):
    """
    Consumer investing summary (MVP).

    - cash_available: available cash rewards that can be redeemed or converted.
    - convertible_now: how much can be converted right now in $25 increments.
    - until_next_unlock: how much more cash is needed to unlock the next $25 increment.
    - stock_balance_usd: total converted USD stored in the Stock Vault.
    """

    cash_available: Decimal
    convertible_now: Decimal
    until_next_unlock: Decimal
    stock_balance_usd: Decimal


class StockConversionCreate(BaseModel):
    amount_usd: Decimal = Field(gt=Decimal("0"))


class ReferralShareRequest(BaseModel):
    channel: Optional[str] = Field(default="link", max_length=40)


class ReferralRedeemRequest(BaseModel):
    referral_code: str = Field(min_length=4, max_length=32)


class ReferralEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    channel: Optional[str] = None
    metadata_text: Optional[str] = None
    created_at: datetime


class ReferralProfileOut(BaseModel):
    referral_code: str
    invite_url: str
    qr_payload: str
    invites_sent: int
    pending_referrals: int
    successful_referrals: int
    recent_events: list[ReferralEventOut] = []


class WebFormSubmitRequest(BaseModel):
    source_page: Optional[str] = Field(default=None, max_length=255)
    data: dict[str, str] = Field(default_factory=dict)


class AIChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: Optional[str] = Field(default=None, max_length=32)
    history: list[AIChatTurn] = Field(default_factory=list, max_length=12)


class AIChatResponse(BaseModel):
    answer: str
    model: str
    role_context: str


class PrivateAssistantMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PrivateAssistantMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: Literal["user", "assistant"]
    message: str
    model: Optional[str] = None
    created_at: datetime


class PrivateAssistantMessageSendResponse(BaseModel):
    user_message: PrivateAssistantMessageOut
    assistant_message: PrivateAssistantMessageOut
    model: str


class WebFormSubmitResponse(BaseModel):
    message: str
    submission_id: int
    mirrored_to_backup: bool = False
    emailed_to_support: bool = False
    sms_acknowledged: bool = False


# Admin portal schemas


class AdminSeriesPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    value: Decimal


class AdminSeriesPointInt(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    value: int


class AdminOverviewOut(BaseModel):
    days: int

    users_total: int
    users_new: int
    users_consumers: int
    users_merchants: int
    users_admins: int

    offers_total: int
    offers_pending: int
    offers_approved: int
    offers_active: int

    transactions_total: int
    transactions_volume_usd: Decimal
    transactions_volume_window_usd: Decimal

    rewards_pending_usd: Decimal
    rewards_available_usd: Decimal
    rewards_paid_usd: Decimal

    stock_converted_total_usd: Decimal

    tickets_open: int
    disputes_open: int

    volume_by_day: list[AdminSeriesPoint]
    new_users_by_day: list[AdminSeriesPointInt]


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime
    supabase_user_id: Optional[str] = None


class AdminMerchantRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_name: str
    dba_name: str
    category: str
    status: str
    logo_url: Optional[str] = None
    created_at: datetime
    locations_count: int
    offers_count: int


class AdminTransactionRow(BaseModel):
    id: int
    user_id: int
    user_email: Optional[EmailStr] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None
    offer_id: Optional[int] = None
    amount: Decimal
    currency: str
    status: TransactionStatus
    occurred_at: datetime


class AdminRewardRow(BaseModel):
    id: int
    user_id: int
    user_email: Optional[EmailStr] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None
    reward_type: RewardPreference
    reward_amount: Decimal
    state: RewardState
    created_at: datetime


class AdminStockConversionRow(BaseModel):
    id: int
    user_id: int
    user_email: Optional[EmailStr] = None
    amount_usd: Decimal
    created_at: datetime


class AdminSupportTicketRow(BaseModel):
    id: int
    user_id: int
    user_email: Optional[EmailStr] = None
    category: str
    subject: str
    status: TicketStatus
    created_at: datetime


class AdminContactInboxRow(BaseModel):
    id: int
    form_type: str
    source_page: Optional[str] = None
    name: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    inquiry: Optional[str] = None
    created_at: datetime


class AdminOrderRow(BaseModel):
    id: int
    created_at: datetime
    source_page: Optional[str] = None
    customer_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    offer_choice: Optional[str] = None
    selected_park: Optional[str] = None
    package_quantity: Optional[str] = None
    payment_option: Optional[str] = None
    payment_status: Optional[str] = None
    payment_provider: Optional[str] = None
    stripe_mode: Optional[str] = None
    payment_amount_usd: Optional[Decimal] = None
    stripe_checkout_session_id: Optional[str] = None
    summary: Optional[str] = None


class AdminAuditLogRow(BaseModel):
    id: int
    actor_user_id: Optional[int] = None
    actor_email: Optional[EmailStr] = None
    actor_role: str
    action: str
    object_type: str
    object_id: str
    created_at: datetime
