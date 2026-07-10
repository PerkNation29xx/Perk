from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import BusinessDirectoryEntry
from app.services.business_directory import upsert_business_directory_entry


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def test_natural_dedupe_updates_existing_listing_when_source_row_moves() -> None:
    with _db_session() as db:
        existing = BusinessDirectoryEntry(
            slug="alhambra-heating-cooling-alhambra-hvac-contractor",
            source_file="sgv_cities_business_directory",
            source_sheet="Directory",
            source_row=99,
            business_name="Alhambra Heating & Cooling",
            business_name_normalized="alhambra heating & cooling",
            business_type="HVAC Contractor",
            business_type_slug="hvac-contractor",
            business_type_icon="🔧",
            requested_city="Alhambra",
            search_city="Alhambra",
            search_city_slug="alhambra",
            city="Alhambra",
            state="CA",
            zip_code="91801",
            address="89 E. Commonwealth Ave., Alhambra, CA 91801",
            phone_number="626-226-4982",
            description="Old description",
            is_active=True,
        )
        db.add(existing)
        db.flush()

        entry, created = upsert_business_directory_entry(
            db,
            source_file="sgv_cities_business_directory",
            source_sheet="Directory",
            source_row=3,
            raw_record={
                "requested_city": "Alhambra",
                "business_name": "Alhambra Heating & Cooling",
                "business_type": "HVAC Contractor",
                "phone_number": "626-226-4982",
                "address": "89 E. Commonwealth Ave., Alhambra, CA 91801",
                "city": "Alhambra",
                "state": "CA",
                "zip_code": "91801",
                "website": "https://choiceheatingcoolingco.store/",
                "data_source": "ChamberofCommerce.com",
            },
            dedupe_natural=True,
        )
        db.commit()

        rows = db.scalars(select(BusinessDirectoryEntry)).all()

    assert created is False
    assert entry.id == existing.id
    assert entry.website == "https://choiceheatingcoolingco.store/"
    assert entry.data_source == "ChamberofCommerce.com"
    assert len(rows) == 1
