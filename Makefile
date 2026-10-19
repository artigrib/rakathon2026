# One core, one case per process (env CASE, see cases/README.md). Default case: screening.
#   make data CASE=seniors          build the case's data file
#   make run CASE=seniors PORT=8001 uvicorn with that case (http://localhost:PORT/app/)
#   make test CASE=seniors          core + contract of every case + cases/seniors/tests
#   make test-all                   make test for every cases/*/case.json
#   make up | make up-all           docker compose: screening only | screening + seniors + collections
#   make stop-cases                 stop seniors + collections containers (screening keeps running)
#   make agent CASE=seniors         create the case's ElevenLabs agent (AGENT_ID=… updates it, ARGS=--print dry run)
CASE ?= screening
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
CASES := $(sort $(patsubst cases/%/case.json,%,$(wildcard cases/*/case.json)))
PORT_screening := 8000
PORT_seniors := 8001
PORT_collections := 8002
PORT ?= $(or $(PORT_$(CASE)),8000)
COMPOSE := docker compose -f deploy/docker-compose.yml

.PHONY: help cases data run test test-all up up-all stop-cases agent

help:
	@sed -n '2,8p' Makefile | sed 's/^# //'
	@echo "cases: $(CASES)"

cases:
	@echo $(CASES)

data:
	CASE=$(CASE) $(PY) -m cases.$(CASE).build

run:
	CASE=$(CASE) $(PY) -m uvicorn backend.app:app --host 127.0.0.1 --port $(PORT)

test:
	CASE=$(CASE) $(PY) -m pytest -q

test-all:
	@fail=; for c in $(CASES); do echo "== CASE=$$c"; CASE=$$c $(PY) -m pytest -q || fail="$$fail $$c"; done; \
	if [ -n "$$fail" ]; then echo "FAILED:$$fail"; exit 1; else echo "all cases passed: $(CASES)"; fi

up:
	$(COMPOSE) up -d --build

up-all:
	$(COMPOSE) --profile cases up -d --build

stop-cases:   # stops only seniors + collections, never the production app
	$(COMPOSE) --profile cases stop app-seniors app-collections

agent:
	CASE=$(CASE) $(PY) scripts/elevenlabs_agent.py --case $(CASE) $(ARGS) $(AGENT_ID)
