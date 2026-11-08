.PHONY: setup up down test lint fmt proto

setup:
	@echo "Installing Python service dependencies..."
	for d in services/telephony-gateway services/voice-pipeline services/agent-core; do \
		(cd $$d && pip install -e ".[dev]" --break-system-packages) ; \
	done
	@echo "Installing Node service dependencies..."
	for d in services/orchestration-api services/admin-dashboard; do \
		(cd $$d && npm install) ; \
	done

up:
	docker compose up --build

down:
	docker compose down -v

test:
	for d in services/telephony-gateway services/voice-pipeline services/agent-core; do \
		(cd $$d && python -m pytest) ; \
	done
	(cd services/orchestration-api && npm test)

lint:
	for d in services/telephony-gateway services/voice-pipeline services/agent-core; do \
		(cd $$d && ruff check .) ; \
	done
	(cd services/orchestration-api && npm run lint)

fmt:
	for d in services/telephony-gateway services/voice-pipeline services/agent-core; do \
		(cd $$d && ruff format .) ; \
	done
	(cd services/orchestration-api && npm run fmt)

proto:
	@echo "Regenerating gRPC stubs from shared/proto into each service..."
	./scripts/generate_proto_stubs.sh
