"""Unit tests for the 8 new OSINT pipeline nodes.

Tests cover: field mapping, error handling, empty-input guards, and
key-resolution fallbacks — no network I/O, no real API keys.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

from app.pipeline.nodes.base import RunContext


def make_context() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def arun(coro):
    """Run an async coroutine synchronously — matches the pattern used by existing node tests."""
    return asyncio.run(coro)


def raise_runtime(msg: str):
    """Return a callable that raises RuntimeError — avoids inline side_effect= patterns."""
    def _raise(*_a, **_kw):
        raise RuntimeError(msg)
    return _raise


# ---------------------------------------------------------------------------
# facebook_pages
# ---------------------------------------------------------------------------

class TestFacebookPagesNode:
    def test_map_item_full(self):
        from app.pipeline.nodes.facebook_pages import _map_item
        raw = {
            "name": "Acme Corp",
            "followersCount": 12000,
            "about": "IT services company",
            "email": "hello@acme.ph",
            "phoneNumber": "+63 2 1234567",
        }
        result = _map_item(raw)
        assert result["name"] == "Acme Corp"
        assert result["followers"] == 12000
        assert result["email"] == "hello@acme.ph"
        assert result["source"] == "facebook"

    def test_map_item_sparse(self):
        from app.pipeline.nodes.facebook_pages import _map_item
        result = _map_item({})
        assert result["name"] == ""
        assert result["followers"] is None
        assert result["source"] == "facebook"

    def test_execute_no_api_key_returns_error(self):
        from app.pipeline.nodes.facebook_pages import FacebookPagesNode
        node = FacebookPagesNode()
        with patch(
            "app.pipeline.nodes.apify_actor._resolve_api_key",
            side_effect=raise_runtime("no key"),
        ):
            result = arun(node.execute({}, [], make_context()))
        assert len(result) == 1
        assert "error" in result[0]

    def test_execute_no_urls_returns_error(self):
        from app.pipeline.nodes.facebook_pages import FacebookPagesNode
        node = FacebookPagesNode()
        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"):
            result = arun(node.execute({"page_urls": []}, [], make_context()))
        assert result[0].get("error")

    def test_execute_returns_actor_results(self):
        from app.pipeline.nodes.facebook_pages import FacebookPagesNode
        node = FacebookPagesNode()
        mock_result = [{"name": "Test Page", "source": "facebook"}]
        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"), \
             patch.object(node, "_run_sync", return_value=mock_result):
            result = arun(node.execute({"page_urls": ["AcmePH"]}, [], make_context()))
        assert result == mock_result


# ---------------------------------------------------------------------------
# twitter_search
# ---------------------------------------------------------------------------

class TestTwitterSearchNode:
    def test_map_item_full(self):
        from app.pipeline.nodes.twitter_search import _map_item
        raw = {
            "author": {
                "userName": "acme_ceo",
                "name": "John Reyes",
                "description": "CEO @ Acme Corp",
                "followersCount": 3400,
            },
            "text": "Excited to announce our Series A!",
        }
        result = _map_item(raw)
        assert result["username"] == "acme_ceo"
        assert result["full_name"] == "John Reyes"
        assert result["followers"] == 3400
        assert result["tweet_text"] == "Excited to announce our Series A!"
        assert result["source"] == "twitter"

    def test_map_item_sparse(self):
        from app.pipeline.nodes.twitter_search import _map_item
        result = _map_item({})
        assert result["username"] == ""
        assert result["followers"] is None
        assert result["source"] == "twitter"

    def test_execute_no_api_key_returns_error(self):
        from app.pipeline.nodes.twitter_search import TwitterSearchNode
        node = TwitterSearchNode()
        with patch(
            "app.pipeline.nodes.apify_actor._resolve_api_key",
            side_effect=raise_runtime("no key"),
        ):
            result = arun(node.execute({}, [], make_context()))
        assert "error" in result[0]

    def test_execute_no_query_returns_error(self):
        from app.pipeline.nodes.twitter_search import TwitterSearchNode
        node = TwitterSearchNode()
        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"):
            result = arun(node.execute({}, [], make_context()))
        assert result[0].get("error")

    def test_execute_picks_query_from_input(self):
        from app.pipeline.nodes.twitter_search import TwitterSearchNode
        node = TwitterSearchNode()
        mock_result = [{"username": "x", "source": "twitter"}]
        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"), \
             patch.object(node, "_run_sync", return_value=mock_result):
            result = arun(node.execute(
                {}, [{"company": "Acme Corp"}], make_context())
            )
        assert result == mock_result


# ---------------------------------------------------------------------------
# opencorporates
# ---------------------------------------------------------------------------

class TestOpenCorporatesNode:
    def test_map_company_nested(self):
        from app.pipeline.nodes.opencorporates import _map_company
        raw = {
            "company": {
                "name": "Acme Inc",
                "company_number": "SEC123456",
                "jurisdiction_code": "ph",
                "incorporation_date": "2010-01-15",
                "current_status": "Active",
                "company_type": "Corporation",
                "registered_address": {"in_full": "Ayala Ave, Makati, Manila"},
            }
        }
        result = _map_company(raw)
        assert result["name"] == "Acme Inc"
        assert result["company_number"] == "SEC123456"
        assert result["jurisdiction_code"] == "ph"
        assert result["status"] == "Active"
        assert result["source"] == "opencorporates"

    def test_map_company_flat(self):
        from app.pipeline.nodes.opencorporates import _map_company
        raw = {"name": "Flat Corp", "company_number": "X1", "jurisdiction_code": "gb"}
        result = _map_company(raw)
        assert result["name"] == "Flat Corp"
        assert result["source"] == "opencorporates"

    def test_execute_skips_empty_query(self):
        from app.pipeline.nodes.opencorporates import OpenCorporatesNode
        node = OpenCorporatesNode()
        result = arun(node.execute({}, [{}], make_context()))
        assert result == []

    def test_execute_uses_company_field(self):
        from app.pipeline.nodes.opencorporates import OpenCorporatesNode, _map_company
        node = OpenCorporatesNode()
        fake_item = _map_company({"company": {"name": "Acme", "company_number": "C1"}})
        with patch(
            "app.pipeline.nodes.opencorporates._search_companies",
            return_value=[fake_item],
        ):
            result = arun(node.execute({}, [{"company": "Acme"}], make_context()))
        assert len(result) == 1
        assert result[0]["name"] == "Acme"


# ---------------------------------------------------------------------------
# instagram_profile
# ---------------------------------------------------------------------------

class TestInstagramProfileNode:
    def test_map_item_business(self):
        from app.pipeline.nodes.instagram_profile import _map_item
        raw = {
            "username": "acme_ph",
            "fullName": "Acme Philippines",
            "biography": "Tech company",
            "followersCount": 5000,
            "followsCount": 100,
            "isBusinessAccount": True,
            "businessCategoryName": "Technology",
            "businessEmail": "ig@acme.ph",
        }
        result = _map_item(raw)
        assert result["username"] == "acme_ph"
        assert result["followers"] == 5000
        assert result["is_business"] is True
        assert result["email"] == "ig@acme.ph"
        assert result["source"] == "instagram"

    def test_map_item_sparse(self):
        from app.pipeline.nodes.instagram_profile import _map_item
        result = _map_item({"username": "x"})
        assert result["followers"] is None
        assert result["source"] == "instagram"

    def test_execute_no_api_key_returns_error(self):
        from app.pipeline.nodes.instagram_profile import InstagramProfileNode
        node = InstagramProfileNode()
        with patch(
            "app.pipeline.nodes.apify_actor._resolve_api_key",
            side_effect=raise_runtime("no key"),
        ):
            result = arun(node.execute({}, [], make_context()))
        assert "error" in result[0]

    def test_execute_no_usernames_returns_error(self):
        from app.pipeline.nodes.instagram_profile import InstagramProfileNode
        node = InstagramProfileNode()
        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"):
            result = arun(node.execute({}, [], make_context()))
        assert result[0].get("error")

    def test_execute_normalises_at_handle(self):
        from app.pipeline.nodes.instagram_profile import InstagramProfileNode
        node = InstagramProfileNode()
        captured: dict = {}

        def mock_run_sync(api_key, actor_input):
            captured["input"] = actor_input
            return []

        with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake"), \
             patch.object(node, "_run_sync", side_effect=mock_run_sync):
            arun(node.execute({"usernames": ["@acme_ph"]}, [], make_context()))

        direct_urls = captured["input"]["directUrls"]
        assert len(direct_urls) == 1
        assert "acme_ph" in direct_urls[0]
        assert "instagram.com" in direct_urls[0]


# ---------------------------------------------------------------------------
# hunter_io
# ---------------------------------------------------------------------------

class TestHunterIoNode:
    def test_map_email_full(self):
        from app.pipeline.nodes.hunter_io import _map_email
        item = {
            "value": "jane@acme.ph",
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "CTO",
            "department": "Engineering",
            "confidence": 95,
        }
        result = _map_email(item, "acme.ph")
        assert result["email"] == "jane@acme.ph"
        assert result["first_name"] == "Jane"
        assert result["confidence"] == 95
        assert result["domain"] == "acme.ph"
        assert result["source"] == "hunter_io"

    def test_map_email_sparse(self):
        from app.pipeline.nodes.hunter_io import _map_email
        result = _map_email({}, "acme.ph")
        assert result["email"] == ""
        assert result["source"] == "hunter_io"

    def test_execute_no_api_key_returns_error(self):
        from app.pipeline.nodes.hunter_io import HunterIoNode
        node = HunterIoNode()
        with patch("app.pipeline.nodes.hunter_io._resolve_api_key", return_value=None):
            result = arun(node.execute({}, [], make_context()))
        assert "error" in result[0]

    def test_execute_domain_mode_uses_plain_domain(self):
        from app.pipeline.nodes.hunter_io import HunterIoNode
        node = HunterIoNode()
        expected = [{"email": "ceo@acme.ph", "source": "hunter_io"}]
        with patch("app.pipeline.nodes.hunter_io._resolve_api_key", return_value="fake"), \
             patch("app.pipeline.nodes.hunter_io._domain_search", return_value=expected):
            result = arun(node.execute(
                {"lookup_type": "domain"},
                [{"domain": "acme.ph"}],
                make_context()),
            )
        assert result == expected


# ---------------------------------------------------------------------------
# whois_lookup
# ---------------------------------------------------------------------------

class TestWhoisLookupNode:
    def test_extract_domain_strips_www(self):
        from app.pipeline.nodes.whois_lookup import _extract_domain
        assert _extract_domain({"domain": "acme.ph"}) == "acme.ph"
        assert _extract_domain({"domain": "www.acme.ph"}) == "acme.ph"
        assert _extract_domain({}) == ""

    def test_map_whois_full(self):
        from app.pipeline.nodes.whois_lookup import _map_whois
        record = {
            "registrarName": "GoDaddy",
            "createdDate": "2010-01-15",
            "expiresDate": "2026-01-15",
            "updatedDate": "2024-01-01",
            "nameServers": {"hostNames": ["ns1.godaddy.com", "ns2.godaddy.com"]},
            "status": "clientTransferProhibited",
        }
        registrant = {
            "name": "John Doe",
            "organization": "Acme Corp",
            "email": "admin@acme.ph",
            "country": "PH",
            "phone": "+63.1234567",
        }
        result = _map_whois("acme.ph", record, registrant)
        assert result["domain"] == "acme.ph"
        assert result["registrar"] == "GoDaddy"
        assert result["registrant_org"] == "Acme Corp"
        assert result["name_servers"] == ["ns1.godaddy.com", "ns2.godaddy.com"]
        assert result["source"] == "whois"

    def test_execute_skips_item_without_domain(self):
        from app.pipeline.nodes.whois_lookup import WhoisLookupNode
        node = WhoisLookupNode()
        result = arun(node.execute({}, [{"name": "no domain here"}], make_context()))
        assert result == []


# ---------------------------------------------------------------------------
# google_news
# ---------------------------------------------------------------------------

class TestGoogleNewsNode:
    def test_parse_rss_extracts_items(self):
        from app.pipeline.nodes.google_news import _parse_rss
        # No <link> tag to avoid URL patterns in literal strings
        xml = (
            '<?xml version="1.0"?><rss><channel>'
            "<item>"
            "<title><![CDATA[Acme Corp raises $10M]]></title>"
            "<pubDate>Mon, 06 May 2026 00:00:00 GMT</pubDate>"
            "<source>TechCrunch</source>"
            "</item>"
            "</channel></rss>"
        )
        results = _parse_rss(xml)
        assert len(results) == 1
        assert results[0]["title"] == "Acme Corp raises $10M"
        assert results[0]["news_source"] == "TechCrunch"
        assert results[0]["source"] == "google_news"

    def test_parse_rss_empty_returns_empty(self):
        from app.pipeline.nodes.google_news import _parse_rss
        assert _parse_rss("<rss><channel></channel></rss>") == []

    def test_strip_cdata(self):
        from app.pipeline.nodes.google_news import _strip_cdata
        assert _strip_cdata("<![CDATA[Hello & World]]>") == "Hello & World"
        assert _strip_cdata("plain text") == "plain text"

    def test_execute_no_query_returns_error(self):
        from app.pipeline.nodes.google_news import GoogleNewsNode
        node = GoogleNewsNode()
        result = arun(node.execute({}, [], make_context()))
        assert result[0].get("error")

    def test_execute_uses_company_from_input(self):
        from app.pipeline.nodes.google_news import GoogleNewsNode
        node = GoogleNewsNode()
        mock_items = [{"title": "Acme News", "source": "google_news"}]
        with patch("app.pipeline.nodes.google_news._fetch_news", return_value=mock_items):
            result = arun(node.execute(
                {}, [{"company": "Acme Corp"}], make_context())
            )
        assert result == mock_items

    def test_execute_config_query_takes_priority(self):
        from app.pipeline.nodes.google_news import GoogleNewsNode
        node = GoogleNewsNode()
        calls: list = []

        def capture_fetch(query, language, max_results):
            calls.append(query)
            return []

        with patch("app.pipeline.nodes.google_news._fetch_news", side_effect=capture_fetch):
            arun(node.execute(
                {"query": "configured query"},
                [{"company": "should be secondary"}],
                make_context()),
            )
        assert calls[0] == "configured query"


# ---------------------------------------------------------------------------
# shodan_search
# ---------------------------------------------------------------------------

class TestShodanSearchNode:
    def test_map_host_full(self):
        from app.pipeline.nodes.shodan_search import _map_host
        data = {
            "ip_str": "1.2.3.4",
            "org": "Acme Corp",
            "country_name": "Philippines",
            "city": "Manila",
            "isp": "PLDT Inc",
            "ports": [80, 443, 22],
            "hostnames": ["acme.ph"],
            "domains": ["acme.ph"],
            "os": "Linux",
            "vulns": {"CVE-2021-44228": {}},
            "last_update": "2024-01-01",
        }
        result = _map_host(data, "acme.ph")
        assert result["ip"] == "1.2.3.4"
        assert result["organization"] == "Acme Corp"
        assert result["country"] == "Philippines"
        assert result["open_ports"] == [80, 443, 22]
        assert "CVE-2021-44228" in result["vulnerabilities"]
        assert result["source"] == "shodan"

    def test_map_host_empty_vulns(self):
        from app.pipeline.nodes.shodan_search import _map_host
        result = _map_host({"ip_str": "1.1.1.1"}, "1.1.1.1")
        assert result["vulnerabilities"] == []

    def test_is_ip_true(self):
        from app.pipeline.nodes.shodan_search import _is_ip
        assert _is_ip("1.2.3.4") is True
        assert _is_ip("192.168.1.1") is True

    def test_is_ip_false(self):
        from app.pipeline.nodes.shodan_search import _is_ip
        assert _is_ip("acme.com") is False
        assert _is_ip("") is False

    def test_execute_no_api_key_returns_error(self):
        from app.pipeline.nodes.shodan_search import ShodanSearchNode
        node = ShodanSearchNode()
        with patch("app.pipeline.nodes.shodan_search._resolve_api_key", return_value=None):
            result = arun(node.execute({}, [], make_context()))
        assert result[0].get("error")

    def test_execute_host_mode_skips_empty_items(self):
        from app.pipeline.nodes.shodan_search import ShodanSearchNode
        node = ShodanSearchNode()
        with patch("app.pipeline.nodes.shodan_search._resolve_api_key", return_value="fake"):
            result = arun(node.execute(
                {"lookup_type": "host"},
                [{"name": "no ip or domain"}],
                make_context()),
            )
        assert result == []

    def test_execute_search_mode_builds_org_query(self):
        from app.pipeline.nodes.shodan_search import ShodanSearchNode
        node = ShodanSearchNode()
        calls: list = []

        def capture_search(api_key, query, max_results):
            calls.append(query)
            return [{"ip": "1.2.3.4", "source": "shodan"}]

        with patch("app.pipeline.nodes.shodan_search._resolve_api_key", return_value="fake"), \
             patch("app.pipeline.nodes.shodan_search._search_shodan", side_effect=capture_search):
            arun(node.execute(
                {"lookup_type": "search"},
                [{"company": "Acme Corp"}],
                make_context()),
            )
        assert len(calls) == 1
        assert "Acme Corp" in calls[0]


# ---------------------------------------------------------------------------
# Registry smoke tests
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_all_8_new_nodes_registered(self):
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        types = {n.node_type for n in NodeRegistry.all()}
        new_nodes = {
            "facebook_pages",
            "twitter_search",
            "opencorporates",
            "instagram_profile",
            "hunter_io",
            "whois_lookup",
            "google_news",
            "shodan_search",
        }
        assert new_nodes.issubset(types), f"Missing: {new_nodes - types}"

    def test_node_categories_are_valid(self):
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        valid_categories = {"source", "enrich", "score", "filter", "datastore"}
        new_node_types = {
            "facebook_pages", "twitter_search", "opencorporates",
            "instagram_profile", "hunter_io", "whois_lookup",
            "google_news", "shodan_search",
        }
        nodes = {n.node_type: n for n in NodeRegistry.all()}
        for nt in new_node_types:
            node = nodes[nt]
            assert node.category in valid_categories, (
                f"{nt}.category={node.category!r} not valid"
            )

    def test_node_config_schemas_are_valid_json_schema(self):
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        new_node_types = {
            "facebook_pages", "twitter_search", "opencorporates",
            "instagram_profile", "hunter_io", "whois_lookup",
            "google_news", "shodan_search",
        }
        nodes = {n.node_type: n for n in NodeRegistry.all()}
        for nt in new_node_types:
            schema = nodes[nt].config_schema
            assert schema.get("type") == "object", f"{nt}: schema missing type=object"
            assert "properties" in schema, f"{nt}: schema missing properties"
            assert isinstance(schema["properties"], dict), (
                f"{nt}: properties must be a dict"
            )


# ---------------------------------------------------------------------------
# apify_actor (base ApifyActorNode) — graceful missing-key degradation
# ---------------------------------------------------------------------------

class TestApifyActorNode:
    def test_execute_no_api_key_returns_error(self):
        """A missing Apify key must degrade to an error dict, never raise.

        Raising propagates out of execute() to the node route handler, which
        turns it into an HTTP 500 and can abort the pipeline run.
        """
        from app.pipeline.nodes.apify_actor import ApifyActorNode
        node = ApifyActorNode()
        with patch(
            "app.pipeline.nodes.apify_actor._resolve_api_key",
            side_effect=raise_runtime("Apify API key not found"),
        ):
            result = arun(node.execute({"searchUrl": "https://x"}, [], make_context()))
        assert len(result) == 1
        assert "error" in result[0]
        assert result[0].get("source") == "apify"
        assert "key" in result[0]["error"].lower()
