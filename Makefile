# PeopleLens AI, NOVAORA
# Alvos das fases F1 a F4. Nenhum alvo escreve no repositorio remoto.

PY ?= python3
SEED ?= 42
PROFILE ?= dev
export PYTHONPATH := src

.PHONY: help install data data-full data-smoke raw pipeline model queues contracts trust all validate test samples clean-data clean-processed

help:
	@echo "install     instala as dependencias"
	@echo "data        gera o ground truth no perfil dev (10%)"
	@echo "raw         gera a verdade e projeta nos sistemas-fonte da onda 1 (F2)"
	@echo "pipeline    roda a F3 sobre o RAW: ingestao, profiling, padronizacao, DE/PARA, qualidade"
	@echo "queues      mostra o estado das filas de governanca, sem decidir nada"
	@echo "model       constroi a camada analitica L3 (dimensoes e fatos) a partir do conformado"
	@echo "contracts   verifica a coerencia entre catalogo de checks e contratos de KPI"
	@echo "trust       mostra a distribuicao de trust score da ultima execucao"
	@echo "all         raw + pipeline, ponta a ponta"
	@echo "data-full   gera o ground truth no volume completo (F8)"
	@echo "data-smoke  gera o ground truth minimo, usado pelos testes"
	@echo "validate    gera e roda so as validacoes de coerencia, sem escrever"
	@echo "test        roda a suite de testes"
	@echo "clean-data  remove os dados gerados (regeneraveis pelo seed)"

install:
	pip install -r requirements.txt

data:
	$(PY) -m generator.run --profile $(PROFILE) --seed $(SEED)

raw:
	$(PY) -m generator.run --profile $(PROFILE) --seed $(SEED) --stage all

pipeline:
	$(PY) -m pipeline

model:
	$(PY) -m analytics.model.build

all: raw pipeline model

# Leitura das filas. Nao aprova, nao rejeita e nao promove nada: a aprovacao
# passa por chamada explicita de Governance.approve, com valor, responsavel e
# justificativa (ADR-0009, principio 5).
contracts:
	@$(PY) -c "from generator import config; from analytics import contracts; \
	p = contracts.verify(config.load()); print('\n'.join(p) if p else 'catalogo e contratos coerentes')"

trust:
	@$(PY) -c "import json, polars as pl; from analytics import trust; \
	print(json.dumps(trust.summary(pl.read_parquet('data/processed/metadata/kpi_trust_score.parquet')), indent=2, ensure_ascii=False))"

queues:
	@$(PY) -c "from generator import config; from mapping.resolution import Governance; \
	import json; g = Governance(config.load()); print(json.dumps(g.summary(), indent=2, ensure_ascii=False))"

data-full:
	$(PY) -m generator.run --profile full --seed $(SEED)

data-smoke:
	$(PY) -m generator.run --profile smoke --seed $(SEED)

validate:
	$(PY) -m generator.run --profile $(PROFILE) --seed $(SEED) --no-write

test:
	$(PY) -m pytest tests -q

clean-data:
	rm -rf data/synthetic/truth data/raw data/processed/* data/governance/*.db docs/f1_metrics.* docs/f2_projection.md docs/f3_pipeline.* docs/f4_mapping_proposal.md docs/f6_model.json

clean-processed:
	rm -rf data/processed/* data/governance/*.db
