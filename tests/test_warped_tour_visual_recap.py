from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "vans-warped-tour-long-beach-2026.html"


def test_warped_recap_has_artist_portraits_social_links_and_official_video() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert html.count('class="warpedArtistCard"') == 6
    assert html.count("official Vans Warped Tour lineup portrait") == 6
    assert html.count('class="warpedVideoGrid"') == 1
    assert html.count("instagram.com/vanswarpedtour/reel/") == 4
    assert "youtube-nocookie.com/embed/MnKtScnMTs8" in html
    assert "youtube-nocookie.com/embed/Pf1sWmhdrAM" in html
    assert "These official artist videos are not Long Beach set footage." in html
    for artist in (
        "Alemeda",
        "Good Terms",
        "Guilt Trip",
        "People R Ugly",
        "Winona Fighter",
        "Origami Angel",
    ):
        assert artist in html
    for social_url in (
        "instagram.com/alemeda",
        "instagram.com/goodtermsband",
        "instagram.com/guilttripmhc",
        "instagram.com/peoplerugly",
        "instagram.com/winonafighter",
        "instagram.com/gami.gang",
    ):
        assert social_url in html


def test_warped_recap_reads_as_editorial_not_a_content_assignment() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "The waterfront became a headliner" in html
    assert "Long Beach carried the festival beyond the gates" in html
    assert "What stayed after the stages went quiet" in html
    for forbidden in (
        "Food became part of the recap",
        "PerkNation view",
        "For PerkNation, the lesson is clear",
        "future content opportunity",
        "winning next guide",
        "For local coverage",
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_warped_visual_recap_is_public_and_current_on_both_homepages() -> None:
    client = TestClient(app)

    for route in (
        "/articles/vans-warped-tour-long-beach-2026",
        "/white/articles/vans-warped-tour-long-beach-2026",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert _PUBLIC_BUILD_ID in response.text
        assert 'id="recap"' in response.text
        assert 'id="artist-spotlights"' in response.text

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Visual Long Beach recap" in response.text
        assert "six emerging-artist portraits" in response.text
        assert _PUBLIC_BUILD_ID in response.text


def test_warped_recap_stays_in_sitemap_and_public_ai_context() -> None:
    client = TestClient(app)
    sitemap = client.get("/sitemap.xml")

    assert sitemap.status_code == 200
    assert "<loc>https://perknation.app/articles/vans-warped-tour-long-beach-2026</loc>" in sitemap.text

    answer = _public_review_live_query_response(
        "What concert and festival coverage is available for Long Beach?",
        "home_local_guide",
    )
    assert answer
    assert "emerging-artist portraits" in answer
    assert "/articles/vans-warped-tour-long-beach-2026" in answer
