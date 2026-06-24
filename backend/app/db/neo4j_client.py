"""Neo4j knowledge graph client — concepts, mastery, recommendations.

Follows the same pattern as supabase_client.py: module-level singleton via
@lru_cache, thin wrapper functions.

WHY Neo4j (Community Edition):
  1. Relationship-first queries — "what concepts does this student need to learn
     next?" requires traversing ENROLLED_IN → Course → COVERS → Subject →
     RELATED_TO → Concept chains. In SQL this is 4+ JOINs; in Cypher it's a
     single readable MATCH pattern.
  2. Recommendation engine — "students like you found X helpful" needs graph
     traversal (collaborative filtering over enrollment + mastery patterns).
  3. Prerequisite checking — Concept → DEPENDS_ON → Concept is a natural DAG
     that Neo4j can traverse in O(depth), not O(nodes).
  4. Cost: $0 — Community Edition is GPLv3, free forever.

For 500 users with ~10K concepts and ~50K relationships, Neo4j CE on a single
server is more than sufficient (it handles millions of nodes).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def _driver():
    """Lazy Neo4j driver. Returns None if not configured."""
    settings = get_settings()
    if not settings.neo4j_uri:
        return None
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=300,
        )
        # Verify connectivity
        driver.verify_connectivity()
        return driver
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Neo4j not available: {e}")
        return None


def available() -> bool:
    return _driver() is not None


def _run(query: str, params: dict | None = None) -> list[dict]:
    """Execute a Cypher query and return records as list of dicts."""
    d = _driver()
    if not d:
        return []
    try:
        with d.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]
    except Exception as e:
        print(f"[warn] Neo4j query failed: {e}")
        return []


def _write(query: str, params: dict | None = None) -> None:
    """Execute a write Cypher query."""
    d = _driver()
    if not d:
        return
    try:
        with d.session() as session:
            session.run(query, params or {})
    except Exception as e:
        print(f"[warn] Neo4j write failed: {e}")


# === Student Operations =====================================================

def upsert_student(student_id: str, name: str, email: str,
                   department: str | None = None, year: int | None = None) -> None:
    _write(
        "MERGE (s:Student {id: $id}) "
        "SET s.name = $name, s.email = $email, s.department = $department, s.year = $year",
        {"id": student_id, "name": name, "email": email,
         "department": department, "year": year},
    )


def enroll_student(student_id: str, course_code: str, semester: str) -> None:
    _write(
        "MATCH (s:Student {id: $sid}), (c:Course {code: $code}) "
        "MERGE (s)-[:ENROLLED_IN {semester: $sem}]->(c)",
        {"sid": student_id, "code": course_code, "sem": semester},
    )


# === Course / Subject / Concept Operations ==================================

def upsert_course(course_id: str, code: str, name: str,
                  department: str | None = None, semester: str | None = None) -> None:
    _write(
        "MERGE (c:Course {id: $id}) "
        "SET c.code = $code, c.name = $name, c.department = $department, c.semester = $semester",
        {"id": course_id, "code": code, "name": name,
         "department": department, "semester": semester},
    )


def upsert_concept(concept_id: str, name: str, domain: str | None = None,
                   description: str | None = None, difficulty: str | None = None) -> None:
    _write(
        "MERGE (c:Concept {id: $id}) "
        "SET c.name = $name, c.domain = $domain, c.description = $description, c.difficulty = $difficulty",
        {"id": concept_id, "name": name, "domain": domain,
         "description": description, "difficulty": difficulty},
    )


def link_concepts(concept_a_id: str, concept_b_id: str, relationship: str = "RELATED_TO",
                  weight: float = 0.5) -> None:
    _write(
        f"MATCH (a:Concept {{id: $a}}), (b:Concept {{id: $b}}) "
        f"MERGE (a)-[:{relationship} {{weight: $w}}]->(b)",
        {"a": concept_a_id, "b": concept_b_id, "w": weight},
    )


def set_concept_dependency(concept_id: str, depends_on_id: str) -> None:
    link_concepts(concept_id, depends_on_id, "DEPENDS_ON", 1.0)


def course_covers_concept(course_code: str, concept_id: str) -> None:
    _write(
        "MATCH (c:Course {code: $code}), (concept:Concept {id: $cid}) "
        "MERGE (c)-[:COVERS]->(concept)",
        {"code": course_code, "cid": concept_id},
    )


# === Mastery Tracking =======================================================

def update_mastery(student_id: str, concept_id: str, level: int) -> None:
    """Set a student's mastery level (0-100) for a concept."""
    _write(
        "MATCH (s:Student {id: $sid}), (c:Concept {id: $cid}) "
        "MERGE (s)-[m:MASTERED]->(c) "
        "SET m.level = $level, m.last_assessed = datetime()",
        {"sid": student_id, "cid": concept_id, "level": min(100, max(0, level))},
    )


def get_mastery(student_id: str) -> list[dict]:
    """Get all mastered concepts for a student."""
    return _run(
        "MATCH (s:Student {id: $sid})-[m:MASTERED]->(c:Concept) "
        "RETURN c.id AS concept_id, c.name AS concept, c.domain AS domain, "
        "m.level AS level, m.last_assessed AS last_assessed "
        "ORDER BY m.level DESC",
        {"sid": student_id},
    )


def get_weak_concepts(student_id: str, threshold: int = 50) -> list[dict]:
    """Concepts the student has engaged with but hasn't mastered."""
    return _run(
        "MATCH (s:Student {id: $sid})-[m:MASTERED]->(c:Concept) "
        "WHERE m.level < $threshold "
        "RETURN c.id AS concept_id, c.name AS concept, c.domain AS domain, "
        "m.level AS level, c.difficulty AS difficulty "
        "ORDER BY m.level ASC",
        {"sid": student_id, "threshold": threshold},
    )


# === Recommendations ========================================================

def recommend_next_concepts(student_id: str, limit: int = 5) -> list[dict]:
    """Concepts the student should learn next based on course enrollment
    and current mastery gaps."""
    return _run(
        "MATCH (s:Student {id: $sid})-[:ENROLLED_IN]->(course:Course)-[:COVERS]->(subj:Subject) "
        "OPTIONAL MATCH (subj)-[:RELATED_TO]->(related:Concept) "
        "WHERE NOT EXISTS { MATCH (s)-[m:MASTERED]->(related) WHERE m.level >= 70 } "
        "RETURN DISTINCT related.id AS concept_id, related.name AS concept, "
        "related.difficulty AS difficulty, related.domain AS domain "
        "ORDER BY related.difficulty ASC "
        "LIMIT $limit",
        {"sid": student_id, "limit": limit},
    )


def recommend_similar_students_resources(student_id: str, limit: int = 5) -> list[dict]:
    """Documents that peers (same courses) found helpful."""
    return _run(
        "MATCH (s1:Student {id: $sid})-[:ENROLLED_IN]->(c:Course)<-[:ENROLLED_IN]-(s2:Student) "
        "WHERE s1 <> s2 "
        "MATCH (s2)-[v:VIEWED]->(d:Document) "
        "WHERE v.count > 2 AND NOT EXISTS { MATCH (s1)-[:VIEWED]->(d) } "
        "RETURN d.id AS document_id, d.title AS title, COUNT(DISTINCT s2) AS peer_views "
        "ORDER BY peer_views DESC "
        "LIMIT $limit",
        {"sid": student_id, "limit": limit},
    )


def get_concept_prerequisites(concept_id: str) -> list[dict]:
    """Get all prerequisite concepts (transitive DEPENDS_ON chain)."""
    return _run(
        "MATCH (c:Concept {id: $cid})-[:DEPENDS_ON*1..5]->(prereq:Concept) "
        "RETURN prereq.id AS concept_id, prereq.name AS concept, "
        "prereq.difficulty AS difficulty "
        "ORDER BY prereq.difficulty ASC",
        {"cid": concept_id},
    )


# === Document Tracking ======================================================

def record_view(student_id: str, document_id: str) -> None:
    """Record that a student viewed a document (increment counter)."""
    _write(
        "MATCH (s:Student {id: $sid}) "
        "MERGE (d:Document {id: $did}) "
        "MERGE (s)-[v:VIEWED]->(d) "
        "SET v.count = COALESCE(v.count, 0) + 1, v.last_viewed = datetime()",
        {"sid": student_id, "did": document_id},
    )


# === Health ==================================================================

def health() -> dict:
    d = _driver()
    if not d:
        return {"status": "not_configured"}
    try:
        with d.session() as session:
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count "
                "ORDER BY count DESC LIMIT 10"
            )
            nodes = {r["label"]: r["count"] for r in result}
        return {"status": "ok", "node_counts": nodes}
    except Exception as e:
        return {"status": "error", "error": str(e)}
