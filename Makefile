.PHONY: up
up:
	docker-compose up --build --remove-orphans -d
	@$(DONE)

.PHONY: down
down:
	docker-compose down --remove-orphans
	@$(DONE)

.PHONY: docker-shell
docker-shell:
	docker-compose run --rm throat /bin/bash
	@$(DONE)
