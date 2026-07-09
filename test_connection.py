from common import get_driver

driver = get_driver()
try:
    driver.verify_connectivity()
    with driver.session() as session:
        record = session.run("RETURN 1 AS ok").single()
        print("SUCCESS: connected to Neo4j Aura, test query returned", record["ok"])
except Exception as e:
    print("FAIL:", type(e).__name__, "-- check .env values (not printed here for safety)")
finally:
    driver.close()
