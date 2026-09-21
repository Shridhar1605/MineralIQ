.PHONY: regress test s1 s2 s3 s4 s5 s6 up down validate fixtures harvest evaluate drift rebaseline
regress:
	python3 -m pytest -m "s1 or s2 or s3 or s4 or s5 or s6" -q
	python3 scripts/check_drift.py
s1:
	python3 -m pytest -m s1 -q
s2:
	python3 -m pytest -m s2 -q
s3:
	python3 -m pytest -m s3 -q
s4:
	python3 -m pytest -m s4 -q
s5:
	python3 -m pytest -m s5 -q
s6:
	python3 -m pytest -m s6 -q
harvest:
	python3 scripts/harvest.py --check
evaluate:
	python3 scripts/evaluate.py
validate:
	python3 scripts/validate_taxonomy.py
fixtures:
	python3 scripts/load_fixtures.py --check
up:
	docker compose up --build
down:
	docker compose down
drift:
	python3 scripts/check_drift.py
rebaseline:
	python3 scripts/check_drift.py --record
