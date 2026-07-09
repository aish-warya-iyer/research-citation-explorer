"""Example graph traversal queries for the citation/co-authorship graph.

Run directly for a demo against the currently loaded "graph neural networks" data:
    python3 queries.py
"""
from common import get_driver

CITATION_PATH_QUERY = """
MATCH (a:Paper {paperId: $paper_id_1}), (b:Paper {paperId: $paper_id_2})
MATCH path = shortestPath((a)-[:CITES*..6]-(b))
RETURN [n IN nodes(path) | n.title] AS titles, length(path) AS hops
"""

MOST_CITED_IN_TOPIC_QUERY = """
MATCH (p:Paper)-[:IN_TOPIC]->(:Topic {name: $topic})
RETURN p.paperId AS paperId, p.title AS title, p.citationCount AS citationCount
ORDER BY p.citationCount DESC
LIMIT $limit
"""

# Co-authorship degree centrality, computed with plain Cypher (no GDS plugin
# needed -- AuraDB Free doesn't include Graph Data Science). "Degree" here is
# the number of distinct collaborators a researcher has among the loaded papers.
COAUTHOR_CENTRALITY_QUERY = """
MATCH (a:Author)-[:AUTHORED]->(:Paper)<-[:AUTHORED]-(b:Author)
WHERE a <> b
WITH a, count(DISTINCT b) AS coauthor_count
RETURN a.authorId AS authorId, a.name AS name, coauthor_count
ORDER BY coauthor_count DESC
LIMIT $limit
"""

# Search box query: keyword match against title/topic, falling back to the
# topic's most-cited papers when the query is blank or matches the seeded
# topic name -- this graph only has "graph neural networks" loaded.
SEARCH_QUERY = """
MATCH (p:Paper)
OPTIONAL MATCH (p)-[:IN_TOPIC]->(t:Topic)
WITH p, t
WHERE $q = '' OR toLower(p.title) CONTAINS toLower($q) OR toLower(t.name) CONTAINS toLower($q)
RETURN p.paperId AS paperId, p.title AS title, p.year AS year, p.citationCount AS citationCount, p.summary AS summary
ORDER BY p.citationCount DESC
LIMIT $limit
"""


def search_papers(session, q, limit=20):
    return list(session.run(SEARCH_QUERY, q=q or "", limit=limit))


def most_cited_papers(session, topic, limit=5):
    return list(session.run(MOST_CITED_IN_TOPIC_QUERY, topic=topic, limit=limit))


def citation_path(session, paper_id_1, paper_id_2):
    result = session.run(CITATION_PATH_QUERY, paper_id_1=paper_id_1, paper_id_2=paper_id_2)
    return result.single()


def coauthor_centrality(session, limit=10):
    return list(session.run(COAUTHOR_CENTRALITY_QUERY, limit=limit))


if __name__ == "__main__":
    driver = get_driver()
    topic = "graph neural networks"
    try:
        with driver.session() as session:
            print(f"--- Top 5 most-cited papers in '{topic}' ---")
            for row in most_cited_papers(session, topic):
                print(f"  [{row['citationCount']:>6}] {row['title']}")

            print("\n--- Top 10 authors by co-authorship degree centrality ---")
            for row in coauthor_centrality(session):
                print(f"  {row['coauthor_count']:>3} collaborators -- {row['name']}")

            print("\n--- Citation path between the two most-cited papers ---")
            top2 = most_cited_papers(session, topic, limit=2)
            if len(top2) == 2:
                record = citation_path(session, top2[0]["paperId"], top2[1]["paperId"])
                if record:
                    print(f"  {record['hops']} hop(s): " + " -> ".join(record["titles"]))
                else:
                    print("  No path found within 6 hops between these two papers.")
    finally:
        driver.close()
