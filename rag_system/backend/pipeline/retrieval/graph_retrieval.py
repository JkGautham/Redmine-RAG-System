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

=== SCHEMA ===
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

Relationship types (ALL directed):
  (Issue)-[:BLOCKS]->(Issue)
  (Issue)-[:BLOCKED_BY]->(Issue)
  (Issue)-[:DUPLICATES]->(Issue)
  (Issue)-[:DUPLICATED_BY]->(Issue)
  (Issue)-[:RELATED_TO]->(Issue)
  (Issue)-[:PRECEDES]->(Issue)
  (Issue)-[:FOLLOWS]->(Issue)
  (Issue)-[:PARENT_OF]->(Issue)
  (Issue)-[:CHILD_OF]->(Issue)
  (Issue)-[:COPIED_TO]->(Issue)
  (Issue)-[:COPIED_FROM]->(Issue)
  (Issue)-[:HAS_JOURNAL]->(JournalEntry)
  (Issue)-[:HAS_ATTACHMENT]->(Attachment)
  (Issue)-[:HAS_STATUS]->(Status)
  (Issue)-[:HAS_TRACKER]->(Tracker)
  (Issue)-[:HAS_PRIORITY]->(Priority)
  (Issue)-[:REPORTED_BY]->(User)
  (Issue)-[:ASSIGNED_TO]->(User)
  (Issue)-[:BELONGS_TO]->(Project)
  (Issue)-[:MENTIONS]->(Entity)

=== STRICT RULES ===
1. Path depths MUST be hardcoded integers: -[:BLOCKS*1..3]->  NOT -[:BLOCKS*1..$depth]->
2. Always include a LIMIT clause (max 50).
3. Return ONLY the Cypher query — no explanation, no markdown fences (```), no comments.
4. Never use PRECEDES|FOLLOWS|PARENT_OF|CHILD_OF|COPIED_TO|COPIED_FROM with undirected (-) patterns;
   always use directed (-> or <-) arrows.

=== BANNED SYNTAX (will cause runtime errors) ===
- `variable := expression`  -- Cypher has no assignment operator. Use aliases: RETURN x AS y
- `CALL { ... }` without `WITH` to pass outer variables in: variables from outside a subquery
  are NOT visible inside unless explicitly imported with WITH.
- `WITH x, y CALL { MATCH ... }` -- you MUST write: `WITH x, y CALL { WITH x, y MATCH ... }`
- Returning a variable defined only inside a CALL{} subquery in the outer RETURN -- subquery
  variables do NOT leak out. Collect them inside the subquery and RETURN them.
- Using $parameters for path depths like *1..$depth.

=== CALL SUBQUERY SCOPING RULES ===
Variables defined outside CALL { } are NOT automatically available inside.
You must import them explicitly:

  -- WRONG:
  MATCH (u:User {name: $name})
  CALL {
    MATCH (u)<-[:REPORTED_BY]-(i:Issue)   -- ERROR: u is not in scope
    RETURN i
  }

  -- CORRECT:
  MATCH (u:User {name: $name})
  CALL {
    WITH u                                -- import u first
    MATCH (u)<-[:REPORTED_BY]-(i:Issue)
    RETURN i
  }
  RETURN i

=== RELATIONSHIP DIRECTION RULES ===
The schema defines (Issue)-[:REPORTED_BY]->(User).
So to find the reporter of an issue:
  MATCH (i:Issue {id: $issueId})-[:REPORTED_BY]->(u:User)

To find all issues reported by a user:
  MATCH (i:Issue)-[:REPORTED_BY]->(u:User {name: $name})

NOT:  MATCH (r:User)<-[:REPORTED_BY]-(j:Issue)  -- this direction is also valid for the
      REPORTED_BY edge above, but be consistent and prefer the outgoing form.

=== GOLDEN EXAMPLES ===

Example 1 — get an issue with its reporter and assignee:
  MATCH (i:Issue {id: $issueId})
  OPTIONAL MATCH (i)-[:REPORTED_BY]->(reporter:User)
  OPTIONAL MATCH (i)-[:ASSIGNED_TO]->(assignee:User)
  RETURN i.id AS id, i.subject AS subject, reporter.name AS reporter, assignee.name AS assignee
  LIMIT 1

Example 2 — latest issue by the same reporter (NO CALL subquery needed):
  MATCH (i:Issue {id: $issueId})-[:REPORTED_BY]->(u:User)
  MATCH (other:Issue)-[:REPORTED_BY]->(u)
  WHERE other.id <> i.id
  RETURN other.id AS otherId, other.subject AS subject, other.created_on AS created_on
  ORDER BY other.created_on DESC
  LIMIT 5

Example 3 — issues related via multi-hop BLOCKS, same reporter:
  MATCH (i:Issue {id: $issueId})-[:REPORTED_BY]->(u:User)
  MATCH (i)-[:BLOCKS*1..3]->(related:Issue)-[:REPORTED_BY]->(u)
  RETURN related.id AS relatedId, related.subject AS subject, related.updated_on AS updated_on
  ORDER BY related.updated_on DESC
  LIMIT 20

Example 4 — CALL subquery correctly importing outer variable:
  MATCH (i:Issue {id: $issueId})-[:REPORTED_BY]->(u:User)
  CALL {
    WITH u
    MATCH (other:Issue)-[:REPORTED_BY]->(u)
    RETURN other ORDER BY other.created_on DESC LIMIT 1
  }
  RETURN i.id AS issueId, other.id AS latestIssueId, other.subject AS latestSubject

Example 5 — blocking chain:
  MATCH path = (blocker:Issue)-[:BLOCKS*1..5]->(i:Issue {id: $issueId})
  RETURN blocker.id AS blockerId, blocker.subject AS subject, blocker.status AS status,
         [n IN nodes(path) | n.id] AS nodePath,
         [r IN relationships(path) | type(r)] AS edgePath
  ORDER BY length(path)
  LIMIT 30

=== TASK ===
{task}
"""


# ── Static anti-pattern rules for local pre-validation ──────────────────────

_BANNED_PATTERNS = [
    # Invalid Cypher assignment operator
    (r":=", "`variable := expr` is not valid Cypher. Use `RETURN expr AS alias` instead."),
    # CALL {} without importing outer variables via WITH inside
    (
        r"CALL\s*\{(?:[^}](?!WITH))*MATCH",
        "CALL { } subquery uses outer variables without importing them. "
        "Add `WITH <var>` as the first line inside CALL { }.",
    ),
    # Parameterised path depth
    (r"\*\d+\.\.\s*\$\w+", "Path depth must be a hardcoded integer, not a parameter (e.g. *1..5 not *1..$n)."),
]


def _validate_cypher(cypher: str) -> list[str]:
    """Return a list of human-readable violation messages, empty if query looks OK."""
    import re
    violations: list[str] = []
    for pattern, message in _BANNED_PATTERNS:
        if re.search(pattern, cypher, re.IGNORECASE | re.DOTALL):
            violations.append(message)
    return violations


def _strip_fences(text: str) -> str:
    for fence in ["```cypher", "```sql", "```", "CYPHER"]:
        text = text.replace(fence, "")
    return text.strip()


def generate_cypher(task: str) -> str:
    """Generate a Neo4j Cypher query from a natural language task description.

    Includes a pre-execution validation pass that feeds specific violation
    messages back to the model for a targeted correction attempt before the
    query ever touches Neo4j.
    """
    from pipeline.llm_manager import chat_with_model
    model = CYPHER_MODEL if CYPHER_MODEL != PRIMARY_MODEL else PRIMARY_MODEL

    response = chat_with_model(
        model=model,
        messages=[{"role": "user", "content": CYPHER_GEN_PROMPT.replace("{task}", task)}],
        options={"temperature": 0.0, "num_predict": 800, "num_ctx": 10240},
    )
    cypher = _strip_fences(response["message"]["content"].strip())

    # Pre-validation: catch common structural errors before hitting Neo4j
    violations = _validate_cypher(cypher)
    if violations:
        violation_list = "\n".join(f"  - {v}" for v in violations)
        correction_prompt = (
            f"The following Cypher query has syntax/structural errors:\n\n"
            f"Query:\n{cypher}\n\n"
            f"Violations found:\n{violation_list}\n\n"
            "Rules to remember:\n"
            "  1. Use `RETURN expr AS alias`, never `variable := expr`.\n"
            "  2. Inside CALL { }, always start with `WITH <outer_var>` for every outer variable you use.\n"
            "  3. Path depths must be literals: *1..5 not *1..$n.\n\n"
            "Return ONLY the corrected Cypher query. No explanation. No markdown fences."
        )
        fixed_resp = chat_with_model(
            model=model,
            messages=[{"role": "user", "content": correction_prompt}],
            options={"temperature": 0.0, "num_predict": 800, "num_ctx": 10240},
        )
        cypher = _strip_fences(fixed_resp["message"]["content"].strip())
        print(
            f"=== [Graph] Cypher pre-validation fixed violations:\n"
            + violation_list
            + f"\nCorrected query:\n{cypher}\n==="
        )

    return cypher


def graph_query_dynamic(task_description: str) -> dict:
    """
    Natural language → Cypher (with pre-validation) → Neo4j.
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
        # Neo4j returned an error — feed it back for a final correction attempt
        correction_prompt = (
            f"The following Cypher query produced a Neo4j error.\n\n"
            f"Query:\n{cypher}\n\n"
            f"Error:\n{str(e)}\n\n"
            "Fix the query and return ONLY the corrected Cypher. No explanation. No markdown fences."
        )
        from pipeline.llm_manager import chat_with_model
        fixed = chat_with_model(
            model=CYPHER_MODEL if CYPHER_MODEL != PRIMARY_MODEL else PRIMARY_MODEL,
            messages=[{"role": "user", "content": correction_prompt}],
            options={"temperature": 0.0, "num_predict": 800},
        )
        fixed_cypher = _strip_fences(fixed["message"]["content"].strip())
        print(f"=== [Graph] Cypher corrected after Neo4j error ===\n{fixed_cypher}\n===")
        try:
            with driver.session() as session:
                result = session.run(fixed_cypher)
                rows = [dict(r) for r in result]
                return {"dynamic_query": rows, "outgoing": [], "incoming": [], "journals": [], "entities": []}
        except Exception as e2:
            return {"dynamic_query": [{"error": str(e2)}], "outgoing": [], "incoming": [], "journals": [], "entities": []}


def graph_get_attachments(issue_id: int) -> list[dict]:
    """
    Query Neo4j for all attachments linked to an issue.
    
    First tries direct HAS_ATTACHMENT relationships.
    If none found, falls back to finding attachments through journal entries
    (which mention file uploads in their changes).
    
    Returns: [{"filename": str, "url": str, "attachment_id": str, "size": str}, ...]
    """
    driver = _get_driver()
    
    def _parse_size(size_str):
        """Parse size like '11.4 KB' to bytes (best effort)."""
        if not size_str:
            return 0
        try:
            # Handle both int and string sizes
            if isinstance(size_str, int):
                return size_str
            size_str = str(size_str).strip()
            if size_str.isdigit():
                return int(size_str)
            # Parse "11.4 KB", "1.5 MB" etc
            parts = size_str.split()
            if len(parts) >= 1:
                val = float(parts[0])
                unit = parts[1].upper() if len(parts) > 1 else "B"
                multipliers = {"B": 1, "KB": 1024, "MB": 1024*1024, "GB": 1024*1024*1024}
                return int(val * multipliers.get(unit, 1))
        except (ValueError, AttributeError):
            pass
        return 0
    
    try:
        with driver.session() as session:
            # Method 1: Direct HAS_ATTACHMENT relationship
            result = session.run("""
                MATCH (i:Issue {id: $id})-[:HAS_ATTACHMENT]->(a:Attachment)
                RETURN
                    a.attachment_id AS attachment_id,
                    a.filename      AS filename,
                    a.url           AS url,
                    a.size          AS size
                ORDER BY a.filename ASC
            """, id=issue_id)
            
            attachments = []
            for record in result:
                att = dict(record)
                if att.get("attachment_id") and att.get("filename") and att.get("url"):
                    attachments.append({
                        "filename":      att["filename"],
                        "url":           att["url"],
                        "attachment_id": str(att["attachment_id"]),
                        "file_size":     _parse_size(att.get("size", 0))
                    })
            
            if attachments:
                return attachments
            
            # Method 2: Fallback - extract from journal entries
            # Journals record file uploads in their changes field (e.g. "File foo.png foo.png added")
            print(f"=== [Graph] No direct HAS_ATTACHMENT edges found, using journal fallback ===")
            result = session.run("""
                MATCH (i:Issue {id: $id})-[:HAS_JOURNAL]->(j:JournalEntry)
                WHERE j.changes IS NOT NULL
                RETURN j.changes as changes
            """, id=issue_id)
            
            # Parse changes to find file mentions
            filenames_mentioned = set()
            for record in result:
                changes = record.get("changes", [])
                if isinstance(changes, list):
                    for change in changes:
                        if isinstance(change, str) and "File" in change and "added" in change:
                            # Parse "File foo.png foo.png added" format
                            parts = change.split()
                            if len(parts) >= 3 and parts[0] == "File":
                                filename = parts[1]
                                filenames_mentioned.add(filename)
            
            # Query for attachments with these filenames
            if filenames_mentioned:
                result = session.run("""
                    MATCH (a:Attachment)
                    WHERE a.filename IN $filenames
                    RETURN
                        a.attachment_id AS attachment_id,
                        a.filename      AS filename,
                        a.url           AS url,
                        a.size          AS size
                    ORDER BY a.filename ASC
                """, filenames=list(filenames_mentioned))
                
                attachments = []
                for record in result:
                    att = dict(record)
                    if att.get("attachment_id") and att.get("filename") and att.get("url"):
                        attachments.append({
                            "filename":      att["filename"],
                            "url":           att["url"],
                            "attachment_id": str(att["attachment_id"]),
                            "file_size":     _parse_size(att.get("size", 0))
                        })
                
                if attachments:
                    print(f"=== [Graph] Found {len(attachments)} attachments via journal fallback ===")
                    return attachments
            
            return []
    except Exception as e:
        print(f"=== [Graph] Failed to retrieve attachments from Neo4j: {e} ===")
        return []


def close():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
