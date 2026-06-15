from __future__ import annotations
"""
Stage 2b: Neo4j Graph Retrieval

Graph hops increased to 5 for multi-hop query answering.
All edge types from the knowledge builder are included.
Journals include author + timestamp + content inline.
Dynamic Cypher via CYPHER_MODEL (qwen2.5-coder:7b).
"""

import ollama
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CYPHER_MODEL, PRIMARY_MODEL

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


# ── Hardcoded patterns ────────────────────────────────────────────────────────

def graph_expand(issue_id: int, depth: int = 3) -> dict:
    """
    Multi-hop traversal with 3 hops.
    Returns related issues with full inline journal entries.
    """
    driver = _get_driver()
    with driver.session() as session:

        # 1. Full issue detail
        detail_row = session.run("""
            MATCH (i:Issue {id: $id})
            OPTIONAL MATCH (i)-[:ASSIGNED_TO]->(u:User)
            OPTIONAL MATCH (i)-[:REPORTED_BY]->(r:User)
            OPTIONAL MATCH (i)-[:BELONGS_TO]->(p:Project)
            OPTIONAL MATCH (i)-[:HAS_TRACKER]->(t:Tracker)
            OPTIONAL MATCH (i)-[:HAS_PRIORITY]->(pr:Priority)
            OPTIONAL MATCH (i)-[:HAS_STATUS]->(s:Status)
            RETURN
                i.id          AS id,
                i.subject     AS subject,
                i.status      AS status,
                i.tracker     AS tracker,
                i.priority    AS priority,
                i.created_on  AS created_on,
                i.updated_on  AS updated_on,
                i.summary     AS description,
                u.name        AS assignee,
                r.name        AS reporter,
                p.name        AS project,
                t.name        AS tracker_node,
                pr.name       AS priority_node,
                s.name        AS status_node
        """, id=issue_id)
        detail = {}
        for row in detail_row:
            detail = dict(row)
            # Prefer node-linked values over embedded strings
            detail["status"]   = detail.get("status_node")   or detail.get("status",   "")
            detail["tracker"]  = detail.get("tracker_node")  or detail.get("tracker",  "")
            detail["priority"] = detail.get("priority_node") or detail.get("priority", "")

        # 2. Outgoing edges — 5 hops, all edge types
        query_out = """
            MATCH path = (root:Issue {id: $id})
                         -[:BLOCKS|BLOCKED_BY|DUPLICATES|DUPLICATED_BY|RELATED_TO|
                           PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF|COPIED_TO|COPIED_FROM*1..5]->
                         (related:Issue)
            RETURN
                related.id       AS related_id,
                related.subject  AS subject,
                related.status   AS status,
                related.tracker  AS tracker,
                related.priority AS priority,
                [n IN nodes(path) | n.id] AS node_path,
                [r IN relationships(path) | type(r)] AS edge_path
            ORDER BY length(path) ASC
            LIMIT 50
        """
        print(f"=== [Graph] Static Cypher (Ego Outgoing) ===\n{query_out.strip()}\n")
        out = session.run(query_out, id=issue_id)
        outgoing = [dict(r) for r in out]

        # 3. Incoming edges — what blocks/precedes/is-parent-of THIS (5 hops)
        query_inc = """
            MATCH path = (blocker:Issue)
                  -[:BLOCKS|BLOCKED_BY|DUPLICATES|DUPLICATED_BY|RELATED_TO|
                    PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF|COPIED_TO|COPIED_FROM*1..5]->
                  (root:Issue {id: $id})
            RETURN
                blocker.id       AS related_id,
                blocker.subject  AS subject,
                blocker.status   AS status,
                blocker.tracker  AS tracker,
                blocker.priority AS priority,
                [n IN nodes(path) | n.id] AS node_path,
                [r IN relationships(path) | type(r)] AS edge_path
            ORDER BY length(path) ASC
            LIMIT 30
        """
        print(f"=== [Graph] Static Cypher (Ego Incoming) ===\n{query_inc.strip()}\n")
        inc = session.run(query_inc, id=issue_id)
        incoming = [dict(r) for r in inc]

        # 4. All journal entries with full content
        jnl = session.run("""
            MATCH (i:Issue {id: $id})-[:HAS_JOURNAL]->(j:JournalEntry)
            WHERE j.content IS NOT NULL AND trim(j.content) <> ''
            RETURN
                j.content   AS note,
                j.timestamp AS ts,
                j.author    AS author
            ORDER BY j.timestamp ASC
        """, id=issue_id)
        journals = [
            {"note": r["note"], "created_on": r["ts"], "author": r["author"]}
            for r in jnl
        ]

        # 5. Mentioned entities (commit refs, error codes, usernames)
        ent = session.run("""
            MATCH (i:Issue {id: $id})-[:MENTIONS]->(e:Entity)
            RETURN e.canonical_name AS name, e.entity_type AS type
            LIMIT 20
        """, id=issue_id)
        entities = [dict(r) for r in ent]

    return {
        "issue_id": issue_id,
        "detail":   detail,
        "outgoing": outgoing,
        "incoming": incoming,
        "journals": journals,
        "entities": entities,
    }


def graph_find_duplicate_chain(issue_id: int) -> list[dict]:
    """Trace full duplicate chain — up to 8 hops."""
    driver = _get_driver()
    with driver.session() as session:
        query_dup = """
            MATCH path = (root:Issue {id: $id})
                         -[:DUPLICATES|DUPLICATED_BY*1..8]->(dup:Issue)
            RETURN
                dup.id      AS dup_id,
                dup.subject AS subject,
                dup.status  AS status,
                [n IN nodes(path) | n.id] AS node_path,
                [r IN relationships(path) | type(r)] AS edge_path
            ORDER BY length(path)
        """
        print(f"=== [Graph] Static Cypher (Duplicate Chain) ===\n{query_dup.strip()}\n")
        result = session.run(query_dup, id=issue_id)
        return [dict(r) for r in result]


def graph_blocking_chain(issue_id: int) -> list[dict]:
    """Full upstream blocking chain — what must resolve before this can close. Up to 8 hops."""
    driver = _get_driver()
    with driver.session() as session:
        query_blk = """
            MATCH path = (blocker:Issue)
                         -[:BLOCKS|BLOCKED_BY*1..8]->
                         (root:Issue {id: $id})
            RETURN
                blocker.id      AS blocker_id,
                blocker.subject AS subject,
                blocker.status  AS status,
                [n IN nodes(path) | n.id] AS node_path,
                [r IN relationships(path) | type(r)] AS edge_path
            ORDER BY length(path) DESC
        """
        print(f"=== [Graph] Static Cypher (Blocking Chain) ===\n{query_blk.strip()}\n")
        result = session.run(query_blk, id=issue_id)
        return [dict(r) for r in result]


def graph_shortest_path(start_id: int, end_id: int) -> dict:
    """Find shortest directed path between two issues, up to 10 hops."""
    driver = _get_driver()
    query = """
        MATCH path = shortestPath(
            (a:Issue {id: $start})
            -[:BLOCKS|BLOCKED_BY|RELATED_TO|DUPLICATES|DUPLICATED_BY|
              PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF|COPIED_TO|COPIED_FROM*1..10]->
            (b:Issue {id: $end})
        )
        RETURN
            [n IN nodes(path) | n.id] AS node_path,
            [r IN relationships(path) | type(r)] AS edge_path
    """
    print(f"=== [Graph] Static Cypher (Shortest Path {start_id} -> {end_id}) ===\n{query.strip()}\n")
    with driver.session() as session:
        result = session.run(query, start=start_id, end=end_id)
        rows = [dict(r) for r in result]
        if not rows:
            # Try bidirectional fallback if directed path not found
            return graph_bidirectional_search(start_id, end_id)
        return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}

def graph_bidirectional_search(start_id: int, end_id: int) -> dict:
    """Find shortest undirected path between two issues, up to 8 hops."""
    driver = _get_driver()
    query = """
        MATCH path = shortestPath(
            (a:Issue {id: $start})
            -[:BLOCKS|BLOCKED_BY|RELATED_TO|DUPLICATES|DUPLICATED_BY|
              PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF|COPIED_TO|COPIED_FROM*1..8]-
            (b:Issue {id: $end})
        )
        RETURN
            [n IN nodes(path) | n.id] AS node_path,
            [r IN relationships(path) | type(r)] AS edge_path
    """
    print(f"=== [Graph] Static Cypher (Bidirectional {start_id} <-> {end_id}) ===\n{query.strip()}\n")
    with driver.session() as session:
        result = session.run(query, start=start_id, end=end_id)
        rows = [dict(r) for r in result]
        return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}

def graph_common_ancestors(id1: int, id2: int) -> dict:
    """Find common nodes reachable from both issues."""
    driver = _get_driver()
    query = """
        MATCH 
            path1 = (a:Issue {id: $id1})-[:BLOCKS|BLOCKED_BY|RELATED_TO|DUPLICATES|
                      DUPLICATED_BY|PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF*1..5]->(x:Issue),
            path2 = (b:Issue {id: $id2})-[:BLOCKS|BLOCKED_BY|RELATED_TO|DUPLICATES|
                      DUPLICATED_BY|PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF*1..5]->(x)
        RETURN 
            x.id AS common_node,
            x.subject AS common_subject,
            x.status AS common_status,
            [n IN nodes(path1) | n.id] AS node_path1, [r IN relationships(path1) | type(r)] AS edge_path1,
            [n IN nodes(path2) | n.id] AS node_path2, [r IN relationships(path2) | type(r)] AS edge_path2
        LIMIT 10
    """
    print(f"=== [Graph] Static Cypher (Common Ancestors {id1} & {id2}) ===\n{query.strip()}\n")
    with driver.session() as session:
        result = session.run(query, id1=id1, id2=id2)
        rows = [dict(r) for r in result]
        return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}

# ── Dynamic Cypher generation ────────────────────────────────────────────────

CYPHER_GEN_PROMPT = """You are a Neo4j Cypher expert for a Redmine issue tracker graph.

Node labels and properties:
  Issue        {id: int, subject: str, status: str, tracker: str,
                priority: str, created_on: str, updated_on: str, summary: str}
  JournalEntry {journal_id: str, content: str, timestamp: str, author: str}
  Attachment   {attachment_id: str, filename: str, url: str, size: str}
  Status       {name: str}
  Tracker      {name: str}
  Priority     {name: str}
  User         {name: str}
  Project      {name: str}
  Entity       {canonical_name: str, entity_type: str, display_name: str}

Relationship types:
  (Issue)-[:BLOCKS]->(Issue)
  (Issue)-[:BLOCKED_BY]->(Issue)
  (Issue)-[:DUPLICATES]->(Issue)
  (Issue)-[:DUPLICATED_BY]->(Issue)
  (Issue)-[:RELATED_TO]->(Issue)
  (Issue)-[:HAS_JOURNAL]->(JournalEntry)
  (Issue)-[:HAS_ATTACHMENT]->(Attachment)
  (Issue)-[:HAS_STATUS]->(Status)
  (Issue)-[:HAS_TRACKER]->(Tracker)
  (Issue)-[:HAS_PRIORITY]->(Priority)
  (Issue)-[:REPORTED_BY]->(User)
  (Issue)-[:ASSIGNED_TO]->(User)
  (Issue)-[:BELONGS_TO]->(Project)
  (Issue)-[:MENTIONS]->(Entity)

IMPORTANT RULES:
- Variable-length path depths MUST be hardcoded integers, NOT parameters.
  e.g. -[:BLOCKS*1..3]-> NOT -[:BLOCKS*1..$depth]->
- Always include LIMIT clause (max 50).
- Return ONLY the Cypher query. No explanation. No markdown fences. No comments.

Task: {task}
"""


def generate_cypher(task: str) -> str:
    from pipeline.llm_manager import chat_with_model
    # qwen3:8b handles Cypher well enough; only switch to coder model if configured differently
    model = CYPHER_MODEL if CYPHER_MODEL != PRIMARY_MODEL else PRIMARY_MODEL
    response = chat_with_model(
        model=model,
        messages=[{"role": "user", "content": CYPHER_GEN_PROMPT.replace("{task}", task)}],
        options={"temperature": 0.0, "num_predict": 600, "num_ctx": 4096}
    )
    cypher = response["message"]["content"].strip()
    for fence in ["```cypher", "```sql", "```", "CYPHER"]:
        cypher = cypher.replace(fence, "")
    return cypher.strip()


def graph_query_dynamic(task_description: str) -> dict:
    """
    Natural language → Cypher → Neo4j.
    Returns dict compatible with graph_expand() return format.
    """
    cypher = generate_cypher(task_description)
    print(f"=== [Graph] Dynamic Cypher Generated ===\n{cypher}\n=== [/Graph] ===")
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(cypher)
            rows = [dict(r) for r in result]
            return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}
    except Exception as e:
        correction_prompt = f"""The following Cypher query produced an error.

Query:
{cypher}

Error:
{str(e)}

Fix the query and return ONLY the corrected Cypher. No explanation.
"""
        from pipeline.llm_manager import chat_with_model
        fixed = chat_with_model(
            model=CYPHER_MODEL if CYPHER_MODEL != PRIMARY_MODEL else PRIMARY_MODEL,
            messages=[{"role": "user", "content": correction_prompt}],
            options={"temperature": 0.0, "num_predict": 600}
        )
        fixed_cypher = (fixed["message"]["content"].strip()
                        .replace("```cypher", "").replace("```", "").strip())
        try:
            with driver.session() as session:
                result = session.run(fixed_cypher)
                rows = [dict(r) for r in result]
                return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}
        except Exception as e2:
            return {"dynamic_query": [{"error": str(e2)}], "outgoing": [], "incoming": [], "journals": [], "entities": []}


def close():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
