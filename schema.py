from common import get_driver

CONSTRAINTS = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.paperId IS UNIQUE",
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.authorId IS UNIQUE",
    "CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
]

driver = get_driver()
try:
    with driver.session() as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)
            print("OK:", stmt)
finally:
    driver.close()
