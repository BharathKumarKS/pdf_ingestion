
"""Independent read-back after the graph clear — NOT the clear script's own table."""
from neo4j import GraphDatabase
from src.core.config import get_settings
cfg = get_settings()
d = GraphDatabase.driver(f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}", auth=(cfg.memgraph_user, cfg.memgraph_password))
with d.session() as s:
    for q,label in [
        ("MATCH (n:Document) RETURN count(n)","Document"),
        ("MATCH (n:Chunk) RETURN count(n)","Chunk"),
        ("MATCH (n:Page) RETURN count(n)","Page"),
        ("MATCH (n:Concept) RETURN count(n)","Concept"),
        ("MATCH ()-[r:PART_OF]->() RETURN count(r)","PART_OF"),
        ("MATCH ()-[r:ON_PAGE]->() RETURN count(r)","ON_PAGE"),
        ("MATCH ()-[r:MENTIONS]->() RETURN count(r)","MENTIONS"),
        ("MATCH ()-[r:RELATES_TO]->() RETURN count(r)","RELATES_TO"),
        ("MATCH ()-[r:PREREQUISITE_OF]->() RETURN count(r)","PREREQUISITE_OF"),
    ]:
        print(f"  {label:16s} {s.run(q).single()[0]}")
    print("  documents:", s.run("MATCH (d:Document) RETURN d.id AS id").data())
d.close()
