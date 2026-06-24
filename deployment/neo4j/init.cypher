-- Neo4j Knowledge Graph — Initial Constraints and Indexes
-- Run after Neo4j starts: cat init.cypher | cypher-shell -u neo4j -p <password>

-- Uniqueness constraints (also create indexes automatically)
CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:Student) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT faculty_id IF NOT EXISTS FOR (f:Faculty) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT department_id IF NOT EXISTS FOR (d:Department) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT course_id IF NOT EXISTS FOR (c:Course) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT course_code IF NOT EXISTS FOR (c:Course) REQUIRE c.code IS UNIQUE;
CREATE CONSTRAINT subject_id IF NOT EXISTS FOR (s:Subject) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT assignment_id IF NOT EXISTS FOR (a:Assignment) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;

-- Lookup indexes for common traversals
CREATE INDEX student_email IF NOT EXISTS FOR (s:Student) ON (s.email);
CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name);
CREATE INDEX concept_domain IF NOT EXISTS FOR (c:Concept) ON (c.domain);
CREATE INDEX subject_name IF NOT EXISTS FOR (s:Subject) ON (s.name);
CREATE INDEX course_semester IF NOT EXISTS FOR (c:Course) ON (c.semester);

-- Full-text search indexes
CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
  FOR (c:Concept) ON EACH [c.name, c.description];
CREATE FULLTEXT INDEX course_search IF NOT EXISTS
  FOR (c:Course) ON EACH [c.name, c.code];
