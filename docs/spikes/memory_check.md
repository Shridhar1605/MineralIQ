# Spike: memory check (8 GB machine)
Result: NOT YET RUN (Docker not installed on this Mac — install + run `docker compose up` on staging VM).
Procedure: start db (+ api) with sample data, record `docker stats` RSS. Then try +neo4j, +opensearch one at a time. If total >6 GB → apply descoping ladder steps 1–2 IMMEDIATELY (drop Neo4j → PG tables + NetworkX; replace search engine → PG full-text). The compose file already has neo4j/opensearch commented out for this reason.
Owner: Hrithik/Shidhar. Date: before 2 Oct.
