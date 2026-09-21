"""Graph builder (Stage 3). Pure stdlib; emits node/edge lists that load
unchanged into Neo4j (descoping ladder: or stay as PG tables + NetworkX).

Node ids: 'rec:{key}', 'org:{canonical}', 'min:{ID}', 'stg:{ID}', 'fam:{ID}'.
Edges: record -applicant_of-> org, record -classified_as-> taxonomy node,
org -cofiled_with-> org (one undirected pair per shared record).

reconcile() checks internal consistency AND, when expected_counts (e.g. PG
row counts) are supplied, cross-store agreement — the Stage-3 gate's
'graph counts reconcile with PostgreSQL' requirement. No live DB exists yet,
so tests reconcile against pipeline output; Week 2 plugs in real row counts.
"""
from itertools import combinations


def _rec_key(r):
    return r.get("fixture_id") or r.get("appl_no") or r.get("source_url")


def build_graph(records, resolver):
    nodes, edges = {}, []
    for r in records:
        rk = f"rec:{_rec_key(r)}"
        nodes[rk] = {"type": "record", "kind": r.get("kind"),
                     "title": r.get("title", "")}
        orgs = sorted({resolver.resolve(a) for a in r.get("applicants", []) if a})
        for o in orgs:
            nodes.setdefault(f"org:{o}", {"type": "org", "name": o})
            edges.append((rk, f"org:{o}", "applicant_of"))
        for mid in r.get("mineral_ids", []) or []:
            nodes.setdefault(f"min:{mid}", {"type": "mineral", "id": mid})
            edges.append((rk, f"min:{mid}", "classified_as"))
        for sid in r.get("stage_ids", []) or []:
            nodes.setdefault(f"stg:{sid}", {"type": "stage", "id": sid})
            edges.append((rk, f"stg:{sid}", "classified_as"))
        for fid in r.get("process_family_ids", []) or []:
            nodes.setdefault(f"fam:{fid}", {"type": "family", "id": fid})
            edges.append((rk, f"fam:{fid}", "classified_as"))
        for a, b in combinations([f"org:{o}" for o in orgs], 2):
            edges.append((a, b, "cofiled_with"))
    return {"nodes": nodes, "edges": edges}


def reconcile(graph, n_records, expected_counts=None):
    nodes, edges = graph["nodes"], graph["edges"]
    rec_nodes = sum(1 for v in nodes.values() if v["type"] == "record")
    dangling = [(a, b) for a, b, _ in edges if a not in nodes or b not in nodes]
    ok = rec_nodes == n_records and not dangling
    report = {"record_nodes": rec_nodes, "expected_records": n_records,
              "node_count": len(nodes), "edge_count": len(edges),
              "dangling_edges": len(dangling), "consistent": ok}
    if expected_counts:
        for k, v in expected_counts.items():
            report[f"pg_{k}"] = v
        ok = ok and expected_counts.get("records") == rec_nodes
        report["consistent"] = ok
    return ok, report
