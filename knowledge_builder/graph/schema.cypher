// Neo4j Schema — Constraints and Indexes
// Run this once before the first ingestion.
// Execute via Neo4j Browser or cypher-shell.

// ─────────────────────────────────────────────────────────────
// UNIQUE CONSTRAINTS (also creates index automatically)
// ─────────────────────────────────────────────────────────────

CREATE CONSTRAINT issue_id_unique IF NOT EXISTS
  FOR (n:Issue) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT project_name_unique IF NOT EXISTS
  FOR (n:Project) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT user_name_unique IF NOT EXISTS
  FOR (n:User) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT tracker_name_unique IF NOT EXISTS
  FOR (n:Tracker) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT status_name_unique IF NOT EXISTS
  FOR (n:Status) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT priority_name_unique IF NOT EXISTS
  FOR (n:Priority) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT category_name_unique IF NOT EXISTS
  FOR (n:Category) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT version_name_unique IF NOT EXISTS
  FOR (n:Version) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT entity_canonical_unique IF NOT EXISTS
  FOR (n:Entity) REQUIRE (n.canonical_name, n.entity_type) IS UNIQUE;

CREATE CONSTRAINT attachment_id_unique IF NOT EXISTS
  FOR (n:Attachment) REQUIRE n.attachment_id IS UNIQUE;

CREATE CONSTRAINT journal_id_unique IF NOT EXISTS
  FOR (n:JournalEntry) REQUIRE n.journal_id IS UNIQUE;

// ─────────────────────────────────────────────────────────────
// ADDITIONAL INDEXES (for common query patterns)
// ─────────────────────────────────────────────────────────────

CREATE INDEX issue_status_idx IF NOT EXISTS
  FOR (n:Issue) ON (n.status);

CREATE INDEX issue_priority_idx IF NOT EXISTS
  FOR (n:Issue) ON (n.priority);

CREATE INDEX issue_tracker_idx IF NOT EXISTS
  FOR (n:Issue) ON (n.tracker);

CREATE INDEX issue_created_idx IF NOT EXISTS
  FOR (n:Issue) ON (n.created_on);

CREATE INDEX issue_updated_idx IF NOT EXISTS
  FOR (n:Issue) ON (n.updated_on);

CREATE INDEX entity_type_idx IF NOT EXISTS
  FOR (n:Entity) ON (n.entity_type);
