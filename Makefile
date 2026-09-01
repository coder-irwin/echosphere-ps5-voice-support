.PHONY: install test run docker-build docker-run demo-reset

install:
	pip install -r requirements.txt

test:
	pytest -q

run:
	uvicorn app.main:app --reload --port 8080

docker-build:
	docker build -t shopwave-ps5 .

docker-run:
	docker run --rm -p 8080:8080 --env-file .env shopwave-ps5

# Restores demo data and drops all live sessions. Point BASE_URL at the deployed service
# when resetting on demo day; defaults to local.
demo-reset:
	curl -s -X POST "$${BASE_URL:-http://127.0.0.1:8080}/admin/reset"
