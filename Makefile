# AImong — question-bank contract verification and backend export.
#
#   make verify     contract + quality audit + exports + tests (no network, no API key)
#   make test       pytest only
#   make export     regenerate backend JSON and seed SQL
#   make contract   re-derive the dataset contract from the canonical data
#   make db-verify  load the seed SQL into a throwaway PostgreSQL and check it

PYTHON ?= python3
PIPELINE := pipeline
export PYTHONPATH := $(CURDIR)/$(PIPELINE)/src

.PHONY: help verify test export contract db-verify install clean

help:
	@sed -n 's/^#   //p' Makefile

install:
	$(PYTHON) -m pip install -r $(PIPELINE)/requirements-dev.txt

contract:
	$(PYTHON) $(PIPELINE)/tools/derive_contract.py

verify:
	@echo "==> contract is current"
	$(PYTHON) $(PIPELINE)/tools/derive_contract.py --check
	@echo
	@echo "==> hard contract + quality audit + export"
	$(PYTHON) -m aimong_qbank.cli verify
	@echo
	@echo "==> tests"
	$(PYTHON) -m pytest $(PIPELINE)

test:
	$(PYTHON) -m pytest $(PIPELINE)

export:
	$(PYTHON) -m aimong_qbank.cli verify

db-verify:
	$(PYTHON) $(PIPELINE)/tools/verify_postgres.py

clean:
	rm -rf $(PIPELINE)/out
	find $(PIPELINE) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
