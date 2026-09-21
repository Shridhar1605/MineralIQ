# Spike: R&D sources (1 fetch+parse each)
Result: NOT YET RUN. Success = one HTTP 200 + parsed title/date per source, saved under docs/spikes/samples/ (tests use saved samples, never live sites).
1. CSIR-NML project page 2. CSIR-IMMT publications 3. JNARDDC portal 4. DST/SERB listing 5. OpenAlex API (confirm: does OpenAlex now require API key/mailto? record answer here).
Rate: ≤1 req/s, respect robots.txt. Save raw HTML/JSON + parser note.
Owner: Hrithik. Date: before 2 Oct.
