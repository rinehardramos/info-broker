from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from neo4j import GraphDatabase

_LABEL_MAP: dict[str, str] = {
    "person": "Person",
    "organization": "Organization",
    "location": "Location",
    "document": "Document",
    "technology": "Technology",
    "service": "Service",
    "event": "Event",
    "asset": "Asset",
    "financial_entity": "FinancialEntity",
    "transaction": "Transaction",
    "contract": "Contract",
    "market_signal": "MarketSignal",
    "threat_actor": "ThreatActor",
    "vulnerability": "Vulnerability",
    "campaign": "Campaign",
    "indicator": "Indicator",
    "malware": "Malware",
    "political_entity": "PoliticalEntity",
    "policy": "Policy",
    "geopolitical_event": "GeopoliticalEvent",
    "sanction": "Sanction",
    "infrastructure": "Infrastructure",
    "social_account": "SocialAccount",
    "credential": "Credential",
    "communication": "Communication",
}

_REL_MAP: dict[str, str] = {
    "works_at": "WORKS_AT",
    "founded": "FOUNDED",
    "subsidiary_of": "SUBSIDIARY_OF",
    "competes_with": "COMPETES_WITH",
    "partners_with": "PARTNERS_WITH",
    "supplies_to": "SUPPLIES_TO",
    "client_of": "CLIENT_OF",
    "invested_in": "INVESTED_IN",
    "acquired": "ACQUIRED",
    "transacted_with": "TRANSACTED_WITH",
    "funds": "FUNDS",
    "located_in": "LOCATED_IN",
    "uses_technology": "USES_TECHNOLOGY",
    "provides_service": "PROVIDES_SERVICE",
    "owns_domain": "OWNS_DOMAIN",
    "operates_infrastructure": "OPERATES_INFRASTRUCTURE",
    "attributed_to": "ATTRIBUTED_TO",
    "exploits": "EXPLOITS",
    "targets": "TARGETS",
    "sanctioned_by": "SANCTIONED_BY",
    "governed_by": "GOVERNED_BY",
    "linked_to_breach": "LINKED_TO_BREACH",
    "controls": "CONTROLS",
    "mentioned_in": "MENTIONED_IN",
    "participated_in": "PARTICIPATED_IN",
}


class Neo4jClient:
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        _uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        _user = user or os.environ.get("NEO4J_USER", "neo4j")
        _password = password or os.environ.get("NEO4J_PASSWORD", "changeme")
        self._driver = GraphDatabase.driver(_uri, auth=(_user, _password))

    def close(self) -> None:
        self._driver.close()

    def ensure_constraints(self) -> None:
        with self._driver.session() as session:
            for label in _LABEL_MAP.values():
                session.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.ref IS UNIQUE"
                )
                session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.name)"
                )

    def upsert_entity(
        self,
        ref: str,
        entity_type: str,
        name: str,
        attributes: Optional[dict] = None,
        confidence: int = 50,
        first_seen: Optional[datetime] = None,
        last_seen: Optional[datetime] = None,
        observation_count: int = 1,
        aliases: Optional[list[str]] = None,
    ) -> None:
        label = _LABEL_MAP.get(entity_type, "Entity")
        attrs = attributes or {}
        _aliases = aliases or []
        _first_seen = first_seen.isoformat() if first_seen else None
        _last_seen = last_seen.isoformat() if last_seen else None

        cypher = f"""
MERGE (n:{label} {{ref: $ref}})
ON CREATE SET
    n.name = $name,
    n.entity_type = $entity_type,
    n.confidence = $confidence,
    n.first_seen = $first_seen,
    n.last_seen = $last_seen,
    n.observation_count = $observation_count,
    n.aliases = $aliases,
    n.attributes = $attributes
ON MATCH SET
    n.name = CASE WHEN $confidence > n.confidence THEN $name ELSE n.name END,
    n.confidence = CASE WHEN $confidence > n.confidence THEN $confidence ELSE n.confidence END,
    n.first_seen = CASE
        WHEN $first_seen IS NOT NULL AND (n.first_seen IS NULL OR $first_seen < n.first_seen)
        THEN $first_seen ELSE n.first_seen END,
    n.last_seen = CASE
        WHEN $last_seen IS NOT NULL AND (n.last_seen IS NULL OR $last_seen > n.last_seen)
        THEN $last_seen ELSE n.last_seen END,
    n.observation_count = n.observation_count + $observation_count,
    n.aliases = apoc.coll.toSet(n.aliases + $aliases),
    n.attributes = $attributes
RETURN n
"""
        params = dict(
            ref=ref, name=name, entity_type=entity_type,
            confidence=confidence, first_seen=_first_seen,
            last_seen=_last_seen, observation_count=observation_count,
            aliases=_aliases, attributes=json.dumps(attrs) if attrs else "{}",
        )
        with self._driver.session() as session:
            session.execute_write(lambda tx: tx.run(cypher, **params).consume())

    def upsert_relationship(
        self,
        from_ref: str,
        to_ref: str,
        rel_type: str,
        confidence: int = 50,
        evidence: Optional[str] = None,
        first_seen: Optional[datetime] = None,
        last_seen: Optional[datetime] = None,
    ) -> None:
        neo4j_rel = _REL_MAP.get(rel_type, rel_type.upper())
        _first_seen = first_seen.isoformat() if first_seen else None
        _last_seen = last_seen.isoformat() if last_seen else None

        cypher = f"""
MATCH (a {{ref: $from_ref}})
MATCH (b {{ref: $to_ref}})
MERGE (a)-[r:{neo4j_rel}]->(b)
ON CREATE SET
    r.confidence = $confidence,
    r.evidence = $evidence,
    r.first_seen = $first_seen,
    r.last_seen = $last_seen,
    r.observation_count = 1
ON MATCH SET
    r.confidence = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END,
    r.evidence = CASE WHEN $evidence IS NOT NULL THEN $evidence ELSE r.evidence END,
    r.first_seen = CASE
        WHEN $first_seen IS NOT NULL AND (r.first_seen IS NULL OR $first_seen < r.first_seen)
        THEN $first_seen ELSE r.first_seen END,
    r.last_seen = CASE
        WHEN $last_seen IS NOT NULL AND (r.last_seen IS NULL OR $last_seen > r.last_seen)
        THEN $last_seen ELSE r.last_seen END,
    r.observation_count = r.observation_count + 1
RETURN r
"""
        params = dict(
            from_ref=from_ref, to_ref=to_ref, confidence=confidence,
            evidence=evidence, first_seen=_first_seen, last_seen=_last_seen,
        )
        with self._driver.session() as session:
            session.execute_write(lambda tx: tx.run(cypher, **params).consume())

    def get_subgraph(self, ref: str, hops: int = 2) -> list[dict[str, Any]]:
        max_hops = min(hops, 5)
        cypher = f"""
MATCH path = (n {{ref: $ref}})-[*1..{max_hops}]-(m)
WITH relationships(path) AS rels, nodes(path) AS nds
LIMIT 200
RETURN nds, rels
"""
        with self._driver.session() as session:
            result = session.run(cypher, ref=ref)
            return [dict(record) for record in result]

    def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if entity_type:
            label = _LABEL_MAP.get(entity_type, "Entity")
            cypher = f"""
MATCH (n:{label})
WHERE toLower(n.name) CONTAINS toLower($search_term)
RETURN n
LIMIT $max_results
"""
        else:
            cypher = """
MATCH (n)
WHERE toLower(n.name) CONTAINS toLower($search_term)
RETURN n
LIMIT $max_results
"""
        with self._driver.session() as session:
            result = session.run(cypher, search_term=query, max_results=limit)
            return [dict(record) for record in result]

    def get_entity(self, ref: str) -> Optional[dict[str, Any]]:
        cypher = """
MATCH (n {ref: $ref})
RETURN n
"""
        with self._driver.session() as session:
            result = session.run(cypher, ref=ref)
            record = result.single()
            return dict(record) if record else None

    def get_entity_relationships(self, ref: str) -> list[dict[str, Any]]:
        cypher = """
MATCH (n {ref: $ref})-[r]-(m)
RETURN
    n.ref AS from_ref,
    m.ref AS to_ref,
    type(r) AS rel_type,
    r AS relationship,
    startNode(r).ref AS start_ref,
    endNode(r).ref AS end_ref
"""
        with self._driver.session() as session:
            result = session.run(cypher, ref=ref)
            return [dict(record) for record in result]
