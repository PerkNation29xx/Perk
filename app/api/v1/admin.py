from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_roles
from app.db.models import (
    AuditLog,
    DisputeCase,
    DisputeStatus,
    MerchantProfile,
    Offer,
    OfferStatus,
    RewardLedgerEntry,
    RewardState,
    StockConversion,
    SupportTicket,
    TicketStatus,
    Transaction,
    User,
    WebLeadSubmission,
    UserRole,
    UserStatus,
)
from app.schemas import (
    APIMessage,
    AdminContactInboxRow,
    AdminPaymentSettingsOut,
    AdminPaymentSettingsUpdate,
    AdminOrderRow,
    AdminAuditLogRow,
    AdminMerchantRow,
    AdminOverviewOut,
    AdminRewardRow,
    AdminSeriesPoint,
    AdminSeriesPointInt,
    AdminStockConversionRow,
    AdminSupportTicketRow,
    AdminTransactionRow,
    AdminUserRow,
    DisputeOut,
    OfferDecision,
    OfferOut,
    RewardAdjustRequest,
    RewardOut,
    TransactionStatus,
)
from app.services.audit import log_action
from app.services.runtime_settings import apply_payment_settings_updates, get_payment_settings_snapshot

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/approvals", response_model=list[OfferOut])
def approval_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[OfferOut]:
    del current_user
    offers = db.scalars(
        select(Offer)
        .options(selectinload(Offer.merchant), selectinload(Offer.location))
        .where(Offer.approval_status == OfferStatus.pending)
        .order_by(Offer.created_at.asc())
    ).all()
    return [OfferOut.model_validate(offer) for offer in offers]


@router.post("/approvals/{offer_id}", response_model=OfferOut)
def decide_offer(
    offer_id: int,
    payload: OfferDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> OfferOut:
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    before = offer.approval_status.value
    offer.approval_status = payload.status

    log_action(
        db,
        actor=current_user,
        action="admin.offer.decision",
        object_type="offer",
        object_id=str(offer.id),
        before_snapshot=f"status={before}",
        after_snapshot=f"status={payload.status.value}",
    )

    db.commit()
    db.refresh(offer)
    return OfferOut.model_validate(offer)


@router.get("/disputes", response_model=list[DisputeOut])
def list_disputes(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[DisputeOut]:
    del current_user
    disputes = db.scalars(select(DisputeCase).order_by(DisputeCase.created_at.desc())).all()
    return [DisputeOut.model_validate(d) for d in disputes]


@router.post("/rewards/{reward_id}/adjust", response_model=RewardOut)
def adjust_reward(
    reward_id: int,
    payload: RewardAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> RewardOut:
    reward = db.get(RewardLedgerEntry, reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="Reward entry not found")

    before_state = reward.state
    reward.state = payload.state

    if payload.state == RewardState.available:
        reward.settled_at = datetime.now(timezone.utc)

    log_action(
        db,
        actor=current_user,
        action="admin.reward.adjust",
        object_type="reward",
        object_id=str(reward.id),
        before_snapshot=f"state={before_state.value}",
        after_snapshot=f"state={payload.state.value};reason={payload.reason}",
    )

    db.commit()
    db.refresh(reward)
    return RewardOut.model_validate(reward)


@router.post("/disputes/{dispute_id}/resolve", response_model=APIMessage)
def resolve_dispute(
    dispute_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> APIMessage:
    dispute = db.get(DisputeCase, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    dispute.status = DisputeStatus.resolved
    dispute.resolution_action = "manual_review_credit"
    dispute.admin_notes = "Resolved by admin"
    dispute.resolved_at = datetime.now(timezone.utc)

    log_action(
        db,
        actor=current_user,
        action="admin.dispute.resolve",
        object_type="dispute",
        object_id=str(dispute.id),
    )

    db.commit()
    return APIMessage(message="Dispute resolved")


def _quantize_usd(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _parse_payload_json(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_payment_amount_usd(payload: dict) -> Optional[Decimal]:
    for key in ("payment_amount_cents", "amount_total_cents"):
        raw = payload.get(key)
        if raw in (None, ""):
            continue
        try:
            cents = int(str(raw).strip())
            return _quantize_usd(Decimal(cents) / Decimal("100"))
        except Exception:
            continue

    for key in ("payment_amount_usd", "amount_usd"):
        raw = payload.get(key)
        if raw in (None, ""):
            continue
        try:
            return _quantize_usd(Decimal(str(raw).strip()))
        except Exception:
            continue
    return None


@router.get("/overview", response_model=AdminOverviewOut)
def admin_overview(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> AdminOverviewOut:
    del current_user

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days - 1)
    window_start_date = window_start.date()

    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    users_consumers = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.consumer)) or 0
    users_merchants = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.merchant)) or 0
    users_admins = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin)) or 0
    users_new = (
        db.scalar(select(func.count()).select_from(User).where(User.created_at >= window_start)) or 0
    )

    offers_total = db.scalar(select(func.count()).select_from(Offer)) or 0
    offers_pending = (
        db.scalar(select(func.count()).select_from(Offer).where(Offer.approval_status == OfferStatus.pending)) or 0
    )
    offers_approved = (
        db.scalar(select(func.count()).select_from(Offer).where(Offer.approval_status == OfferStatus.approved)) or 0
    )
    offers_active = (
        db.scalar(
            select(func.count())
            .select_from(Offer)
            .where(
                Offer.approval_status == OfferStatus.approved,
                Offer.starts_at <= now,
                Offer.ends_at >= now,
            )
        )
        or 0
    )

    transactions_total = db.scalar(select(func.count()).select_from(Transaction)) or 0
    transactions_volume_usd = (
        db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(Transaction)) or Decimal("0")
    )
    transactions_volume_usd = _quantize_usd(Decimal(transactions_volume_usd))

    transactions_volume_window_usd = (
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).select_from(Transaction).where(
                Transaction.occurred_at >= window_start
            )
        )
        or Decimal("0")
    )
    transactions_volume_window_usd = _quantize_usd(Decimal(transactions_volume_window_usd))

    rewards_pending_usd = (
        db.scalar(
            select(func.coalesce(func.sum(RewardLedgerEntry.reward_amount), 0))
            .select_from(RewardLedgerEntry)
            .where(RewardLedgerEntry.state == RewardState.pending)
        )
        or Decimal("0")
    )
    rewards_pending_usd = _quantize_usd(Decimal(rewards_pending_usd))

    rewards_available_usd = (
        db.scalar(
            select(func.coalesce(func.sum(RewardLedgerEntry.reward_amount), 0))
            .select_from(RewardLedgerEntry)
            .where(RewardLedgerEntry.state == RewardState.available)
        )
        or Decimal("0")
    )
    rewards_available_usd = _quantize_usd(Decimal(rewards_available_usd))

    rewards_paid_usd = (
        db.scalar(
            select(func.coalesce(func.sum(RewardLedgerEntry.reward_amount), 0))
            .select_from(RewardLedgerEntry)
            .where(RewardLedgerEntry.state == RewardState.paid)
        )
        or Decimal("0")
    )
    rewards_paid_usd = _quantize_usd(Decimal(rewards_paid_usd))

    stock_converted_total_usd = (
        db.scalar(
            select(func.coalesce(func.sum(StockConversion.amount_usd), 0)).select_from(StockConversion)
        )
        or Decimal("0")
    )
    stock_converted_total_usd = _quantize_usd(Decimal(stock_converted_total_usd))

    tickets_open = (
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status == TicketStatus.open)
        )
        or 0
    )
    disputes_open = (
        db.scalar(
            select(func.count())
            .select_from(DisputeCase)
            .where(DisputeCase.status == DisputeStatus.open)
        )
        or 0
    )

    # Window series (UTC) for charts.
    # Use python grouping for cross-DB compatibility.
    window_days = [window_start_date + timedelta(days=i) for i in range(days)]
    day_labels = [d.isoformat() for d in window_days]

    tx_rows = db.execute(
        select(Transaction.occurred_at, Transaction.amount).where(Transaction.occurred_at >= window_start)
    ).all()
    volume_by_day_map: dict[str, Decimal] = {label: Decimal("0") for label in day_labels}
    for occurred_at, amount in tx_rows:
        dt = occurred_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        label = dt.date().isoformat()
        if label in volume_by_day_map:
            volume_by_day_map[label] = volume_by_day_map[label] + Decimal(str(amount))

    user_rows = db.execute(select(User.created_at).where(User.created_at >= window_start)).all()
    new_users_by_day_map: dict[str, int] = {label: 0 for label in day_labels}
    for (created_at,) in user_rows:
        dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        label = dt.date().isoformat()
        if label in new_users_by_day_map:
            new_users_by_day_map[label] += 1

    volume_by_day = [
        AdminSeriesPoint(date=label, value=_quantize_usd(volume_by_day_map[label])) for label in day_labels
    ]
    new_users_by_day = [AdminSeriesPointInt(date=label, value=new_users_by_day_map[label]) for label in day_labels]

    return AdminOverviewOut(
        days=days,
        users_total=users_total,
        users_new=users_new,
        users_consumers=users_consumers,
        users_merchants=users_merchants,
        users_admins=users_admins,
        offers_total=offers_total,
        offers_pending=offers_pending,
        offers_approved=offers_approved,
        offers_active=offers_active,
        transactions_total=transactions_total,
        transactions_volume_usd=transactions_volume_usd,
        transactions_volume_window_usd=transactions_volume_window_usd,
        rewards_pending_usd=rewards_pending_usd,
        rewards_available_usd=rewards_available_usd,
        rewards_paid_usd=rewards_paid_usd,
        stock_converted_total_usd=stock_converted_total_usd,
        tickets_open=tickets_open,
        disputes_open=disputes_open,
        volume_by_day=volume_by_day,
        new_users_by_day=new_users_by_day,
    )


@router.get("/users", response_model=list[AdminUserRow])
def admin_list_users(
    q: Optional[str] = None,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminUserRow]:
    del current_user

    query = select(User).order_by(User.created_at.desc(), User.id.desc())

    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)

    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(User.email.ilike(like), User.full_name.ilike(like)))

    users = db.scalars(query.limit(limit).offset(offset)).all()
    return [AdminUserRow.model_validate(u) for u in users]


@router.get("/merchants", response_model=list[AdminMerchantRow])
def admin_list_merchants(
    q: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminMerchantRow]:
    del current_user

    query = (
        select(MerchantProfile)
        .options(
            selectinload(MerchantProfile.owner),
            selectinload(MerchantProfile.locations),
            selectinload(MerchantProfile.offers),
        )
        .order_by(MerchantProfile.id.desc())
    )

    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(MerchantProfile.dba_name.ilike(like), MerchantProfile.legal_name.ilike(like)))

    merchants = db.scalars(query.limit(limit).offset(offset)).all()
    now = datetime.now(timezone.utc)
    return [
        AdminMerchantRow(
            id=m.id,
            legal_name=m.legal_name,
            dba_name=m.dba_name,
            category=m.category,
            status=m.status,
            logo_url=m.logo_url,
            created_at=(m.owner.created_at if getattr(m, "owner", None) is not None else now),
            locations_count=len(m.locations or []),
            offers_count=len(m.offers or []),
        )
        for m in merchants
    ]


@router.get("/offers", response_model=list[OfferOut])
def admin_list_offers(
    approval_status: Optional[OfferStatus] = None,
    active_only: bool = False,
    merchant_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[OfferOut]:
    del current_user

    now = datetime.now(timezone.utc)
    query = select(Offer).options(selectinload(Offer.merchant), selectinload(Offer.location))

    if approval_status:
        query = query.where(Offer.approval_status == approval_status)
    if merchant_id:
        query = query.where(Offer.merchant_id == merchant_id)
    if active_only:
        query = query.where(
            Offer.approval_status == OfferStatus.approved,
            Offer.starts_at <= now,
            Offer.ends_at >= now,
        )

    offers = db.scalars(query.order_by(Offer.created_at.desc(), Offer.id.desc()).limit(limit).offset(offset)).all()
    return [OfferOut.model_validate(o) for o in offers]


@router.get("/transactions", response_model=list[AdminTransactionRow])
def admin_list_transactions(
    status: Optional[TransactionStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminTransactionRow]:
    del current_user

    query = (
        select(Transaction)
        .options(
            selectinload(Transaction.user),
            selectinload(Transaction.offer).selectinload(Offer.merchant),
        )
        .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
    )

    if status:
        query = query.where(Transaction.status == status)

    txns = db.scalars(query.limit(limit).offset(offset)).all()
    rows: list[AdminTransactionRow] = []
    for txn in txns:
        user_email = None
        try:
            user_email = txn.user.email if txn.user else None
        except Exception:
            user_email = None

        rows.append(
            AdminTransactionRow(
                id=txn.id,
                user_id=txn.user_id,
                user_email=user_email,
                merchant_id=txn.merchant_id,
                merchant_name=txn.merchant_name,
                offer_id=txn.offer_id,
                amount=txn.amount,
                currency=txn.currency,
                status=txn.status,
                occurred_at=txn.occurred_at,
            )
        )

    return rows


@router.get("/rewards", response_model=list[AdminRewardRow])
def admin_list_rewards(
    state: Optional[RewardState] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminRewardRow]:
    del current_user

    query = (
        select(RewardLedgerEntry)
        .options(
            selectinload(RewardLedgerEntry.user),
            selectinload(RewardLedgerEntry.transaction)
            .selectinload(Transaction.offer)
            .selectinload(Offer.merchant),
        )
        .order_by(RewardLedgerEntry.created_at.desc(), RewardLedgerEntry.id.desc())
    )

    if state:
        query = query.where(RewardLedgerEntry.state == state)

    rewards = db.scalars(query.limit(limit).offset(offset)).all()
    rows: list[AdminRewardRow] = []
    for reward in rewards:
        user_email = None
        try:
            user_email = reward.user.email if reward.user else None
        except Exception:
            user_email = None

        rows.append(
            AdminRewardRow(
                id=reward.id,
                user_id=reward.user_id,
                user_email=user_email,
                merchant_id=reward.merchant_id,
                merchant_name=reward.merchant_name,
                reward_type=reward.reward_type,
                reward_amount=reward.reward_amount,
                state=reward.state,
                created_at=reward.created_at,
            )
        )

    return rows


@router.get("/stock_conversions", response_model=list[AdminStockConversionRow])
def admin_list_stock_conversions(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminStockConversionRow]:
    del current_user

    rows = db.execute(
        select(StockConversion, User.email)
        .join(User, User.id == StockConversion.user_id)
        .order_by(StockConversion.created_at.desc(), StockConversion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        AdminStockConversionRow(
            id=sc.id,
            user_id=sc.user_id,
            user_email=email,
            amount_usd=sc.amount_usd,
            created_at=sc.created_at,
        )
        for sc, email in rows
    ]


@router.get("/support/tickets", response_model=list[AdminSupportTicketRow])
def admin_list_support_tickets(
    status: Optional[TicketStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminSupportTicketRow]:
    del current_user

    query = (
        select(SupportTicket)
        .options(selectinload(SupportTicket.user))
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
    )
    if status:
        query = query.where(SupportTicket.status == status)

    tickets = db.scalars(query.limit(limit).offset(offset)).all()
    return [
        AdminSupportTicketRow(
            id=t.id,
            user_id=t.user_id,
            user_email=(t.user.email if t.user else None),
            category=t.category,
            subject=t.subject,
            status=t.status,
            created_at=t.created_at,
        )
        for t in tickets
    ]


@router.get("/contact-inbox", response_model=list[AdminContactInboxRow])
def admin_contact_inbox(
    q: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminContactInboxRow]:
    del current_user

    query = select(WebLeadSubmission).where(WebLeadSubmission.form_type.in_(("contact", "checkout")))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                WebLeadSubmission.email.ilike(like),
                WebLeadSubmission.name.ilike(like),
                WebLeadSubmission.contact_name.ilike(like),
                WebLeadSubmission.company.ilike(like),
                WebLeadSubmission.phone.ilike(like),
                WebLeadSubmission.inquiry.ilike(like),
            )
        )

    rows = db.scalars(
        query.order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        AdminContactInboxRow(
            id=r.id,
            form_type=r.form_type,
            source_page=r.source_page,
            name=r.name,
            contact_name=r.contact_name,
            company=r.company,
            email=r.email,
            phone=r.phone,
            inquiry=r.inquiry,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/orders", response_model=list[AdminOrderRow])
def admin_orders(
    q: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminOrderRow]:
    del current_user

    query = select(WebLeadSubmission).where(WebLeadSubmission.form_type == "checkout")
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                WebLeadSubmission.email.ilike(like),
                WebLeadSubmission.name.ilike(like),
                WebLeadSubmission.contact_name.ilike(like),
                WebLeadSubmission.phone.ilike(like),
                WebLeadSubmission.inquiry.ilike(like),
                WebLeadSubmission.source_page.ilike(like),
                WebLeadSubmission.payload_json.ilike(like),
            )
        )

    rows = db.scalars(
        query.order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    out: list[AdminOrderRow] = []
    for row in rows:
        payload = _parse_payload_json(row.payload_json)
        customer_name = _first_non_empty(
            row.name,
            row.contact_name,
            payload.get("full_name"),
            payload.get("name"),
            payload.get("contact_name"),
        )
        payment_option = _first_non_empty(payload.get("payment_option"))
        payment_status = _first_non_empty(payload.get("payment_status"))
        payment_provider = _first_non_empty(payload.get("payment_provider"))
        stripe_mode = _first_non_empty(payload.get("stripe_mode"))
        stripe_session_id = _first_non_empty(payload.get("stripe_checkout_session_id"))
        payment_amount_usd = _parse_payment_amount_usd(payload)

        out.append(
            AdminOrderRow(
                id=row.id,
                created_at=row.created_at,
                source_page=row.source_page,
                customer_name=customer_name,
                email=row.email,
                phone=_first_non_empty(row.phone, payload.get("phone")),
                offer_choice=_first_non_empty(payload.get("offer_choice"), payload.get("selected_offer")),
                selected_park=_first_non_empty(payload.get("selected_park"), payload.get("park")),
                package_quantity=_first_non_empty(payload.get("package_quantity")),
                payment_option=payment_option,
                payment_status=payment_status,
                payment_provider=payment_provider,
                stripe_mode=stripe_mode,
                payment_amount_usd=payment_amount_usd,
                stripe_checkout_session_id=stripe_session_id,
                summary=_first_non_empty(row.inquiry, payload.get("notes"), payload.get("inquiry")),
            )
        )

    return out


@router.get("/payments/settings", response_model=AdminPaymentSettingsOut)
def admin_payment_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> AdminPaymentSettingsOut:
    del current_user
    snapshot = get_payment_settings_snapshot(db)
    return AdminPaymentSettingsOut(**snapshot)


@router.put("/payments/settings", response_model=AdminPaymentSettingsOut)
def admin_update_payment_settings(
    payload: AdminPaymentSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> AdminPaymentSettingsOut:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        snapshot = get_payment_settings_snapshot(db)
        return AdminPaymentSettingsOut(**snapshot)

    before = get_payment_settings_snapshot(db)
    try:
        after = apply_payment_settings_updates(db, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    changed_keys = ",".join(sorted(updates.keys()))
    log_action(
        db,
        actor=current_user,
        action="admin.payment.settings.update",
        object_type="system",
        object_id="stripe",
        before_snapshot=(
            f"mode={before.get('stripe_mode')};"
            f"test_secret_set={bool(before.get('stripe_secret_key_test'))};"
            f"live_secret_set={bool(before.get('stripe_secret_key_live'))}"
        ),
        after_snapshot=(
            f"mode={after.get('stripe_mode')};"
            f"test_secret_set={bool(after.get('stripe_secret_key_test'))};"
            f"live_secret_set={bool(after.get('stripe_secret_key_live'))};"
            f"changed={changed_keys}"
        ),
    )
    db.commit()
    return AdminPaymentSettingsOut(**after)


@router.get("/audit", response_model=list[AdminAuditLogRow])
def admin_list_audit_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[AdminAuditLogRow]:
    del current_user

    rows = db.execute(
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        AdminAuditLogRow(
            id=log.id,
            actor_user_id=log.actor_user_id,
            actor_email=email,
            actor_role=log.actor_role,
            action=log.action,
            object_type=log.object_type,
            object_id=log.object_id,
            created_at=log.created_at,
        )
        for log, email in rows
    ]
