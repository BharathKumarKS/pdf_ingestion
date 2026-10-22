
from neo4j import GraphDatabase
d=GraphDatabase.driver("bolt://localhost:7687",auth=("memgraph","synapse"))
q_edge = """
MATCH (a:Concept)-[r:RELATES_TO]-(b:Concept)
RETURN a.name AS a, b.name AS b, r.weight AS w
ORDER BY r.weight DESC
"""
q_cooc = """
MATCH (a:Concept {name:$a}), (b:Concept {name:$b})
MATCH (c:Chunk)-[:MENTIONS]->(a)
MATCH (c)-[:MENTIONS]->(b)
RETURN count(DISTINCT c) AS cooc
"""
with d.session() as s:
    rows = s.run(q_edge).data()
    print("total edges:", len(rows))
    # sample: highest weights, a few weight-2, a few weight-1
    seen=set(); sample=[]
    for r in rows[:6]: sample.append(r)
    for r in rows:
        if r["w"]==2 and len([x for x in sample if x["w"]==2])<4: sample.append(r)
    for r in rows:
        if r["w"]==1 and len([x for x in sample if x["w"]==1])<4: sample.append(r)
    ok=0; bad=0
    for r in sample:
        cooc = s.run(q_cooc, a=r["a"], b=r["b"]).single()["cooc"]
        match = "MATCH" if cooc == r["w"] else "MISMATCH"
        if cooc == r["w"]: ok+=1
        else: bad+=1
        print(f"  w={r['w']:3d}  chunks_mentioning_both={cooc:3d}  {match}   {r['a'][:28]!r} / {r['b'][:28]!r}")
    print(f"sampled {len(sample)}: {ok} match, {bad} mismatch")
d.close()
