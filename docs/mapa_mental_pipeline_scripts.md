# Mapa Mental do Pipeline (diretorio scripts)

## 1) Visao Arquitetural (interdependencia entre arquivos)

- [scripts/main.py](scripts/main.py)
  - Ponto de entrada principal do pipeline
  - Orquestra a execucao ponta a ponta
  - Dependencias diretas:
    - [scripts/config.py](scripts/config.py)
    - [scripts/utils.py](scripts/utils.py)
    - [scripts/transformer.py](scripts/transformer.py)
    - [scripts/warehouse.py](scripts/warehouse.py)

- [scripts/processar_trimestres_2025.py](scripts/processar_trimestres_2025.py)
  - Orquestrador alternativo (estado atual espelha a estrutura do main)
  - Reusa as mesmas dependencias do pipeline modular

- [scripts/config.py](scripts/config.py)
  - Define constantes de negocio e de schema
  - Define a classe PipelineConfig (caminhos, fallback de referencias, memoria DuckDB)
  - Alimenta Transformer e Warehouse com regras e paths

- [scripts/transformer.py](scripts/transformer.py)
  - Define a classe CNPJTransformer
  - Executa Bronze -> Silver com Polars
  - Importa regras de [scripts/config.py](scripts/config.py)

- [scripts/warehouse.py](scripts/warehouse.py)
  - Define a classe WarehouseManager
  - Executa Silver -> Gold -> Export
  - Usa DuckDB para joins, deduplicacao e escrita final
  - Consome PipelineConfig de [scripts/config.py](scripts/config.py)

- [scripts/utils.py](scripts/utils.py)
  - setup_logging para padronizar log
  - strip_accents e normalizar_nome para suporte de comparacao geografica

- [scripts/release_processamento.py](scripts/release_processamento.py)
  - Versao monolitica (all-in-one) do mesmo fluxo
  - Contem PipelineConfig, CNPJTransformer e WarehouseManager no mesmo arquivo
  - Serve como referencia historica/operacional quando nao se usa a versao modular

- [scripts/**init**.py](scripts/__init__.py)
  - Marca o diretorio scripts como pacote Python

---

## 2) Mapa Mental do Funcionamento (Markdown)

- Pipeline Receita Federal 2025
  - Entrada e orquestracao
    - [scripts/main.py](scripts/main.py#L59): main
    - [scripts/main.py](scripts/main.py#L31): parse_args (--raw-path, --token)
    - [scripts/main.py](scripts/main.py#L61): setup_logging
    - [scripts/main.py](scripts/main.py#L70): instancia PipelineConfig
    - [scripts/main.py](scripts/main.py#L82): chama CNPJTransformer.processar
    - [scripts/main.py](scripts/main.py#L86): chama WarehouseManager.enriquecer_geografia
    - [scripts/main.py](scripts/main.py#L87): chama WarehouseManager.consolidar_e_deduplicar
    - [scripts/main.py](scripts/main.py#L88): chama WarehouseManager.export_assets

  - Camada Bronze (ingestao de ZIPs)
    - Classe: [scripts/transformer.py](scripts/transformer.py#L29) CNPJTransformer
    - [scripts/transformer.py](scripts/transformer.py#L39): processar
      - Busca .zip em raw_path (rglob)
      - Itera por ZIP e delega para \_processar_zip
    - [scripts/transformer.py](scripts/transformer.py#L61): \_processar_zip
      - Abre ZIP com zipfile
      - Itera entradas internas e chama \_ler_entry
    - [scripts/transformer.py](scripts/transformer.py#L73): \_ler_entry
      - Extrai entrada para CSV temporario
      - Le CSV com fallback de encoding

  - Limpeza de dados (fix das aspas)
    - Objetivo
      - Corrigir campos com aspas e espacos residuais antes dos filtros
      - Evitar falha de comparacao, por exemplo situacao com valor "02" ao inves de 02
    - Implementacao
      - [scripts/transformer.py](scripts/transformer.py#L103):
        - aplica em todas as colunas texto
        - remove aspas: str.replace_all('"', '')
        - remove espacos extras: str.strip_chars()
      - [scripts/transformer.py](scripts/transformer.py#L106):
        - padroniza UF em maiusculo
        - faz zfill no codigo de municipio RFB
    - Efeito pratico
      - situacao_cadastral fica limpa para comparar com 02
      - cnae_principal e cnae_secundario ficam aptos ao regex

  - Camada Silver (filtro de negocio)
    - Criterio 1: Situacao cadastral ativa
      - Regra em [scripts/config.py](scripts/config.py#L38): SITUACAO_ATIVA = 02
      - Aplicacao em [scripts/transformer.py](scripts/transformer.py#L112)
    - Criterio 2: CNAE logistico
      - Lista de CNAEs em [scripts/config.py](scripts/config.py#L24)
      - Regex consolidada em [scripts/config.py](scripts/config.py#L35)
      - Aplicacao em [scripts/transformer.py](scripts/transformer.py#L118)
        - cnae_principal contem regex OU cnae_secundario contem regex
    - Saida Silver
      - Colunas finais em [scripts/config.py](scripts/config.py#L59)
      - Retorno de DataFrame Silver pronto para enriquecimento

  - Camada Gold (DuckDB para enriquecimento geografico)
    - Classe: [scripts/warehouse.py](scripts/warehouse.py#L29) WarehouseManager
    - Conexao e tuning
      - [scripts/warehouse.py](scripts/warehouse.py#L48): \_conectar
        - tenta MotherDuck via token
        - fallback para :memory:
      - [scripts/warehouse.py](scripts/warehouse.py#L76): \_configurar
        - define temp_directory
        - define max_memory
    - Enriquecimento geografico
      - [scripts/warehouse.py](scripts/warehouse.py#L90): enriquecer_geografia
      - Carrega referencias:
        - Municipios RFB (CSV)
        - IBGE (Excel)
      - Registra DataFrames como views Arrow no DuckDB:
        - [scripts/warehouse.py](scripts/warehouse.py#L179)
        - [scripts/warehouse.py](scripts/warehouse.py#L180)
        - [scripts/warehouse.py](scripts/warehouse.py#L181)
      - Executa JOIN SQL:
        - join RFB por cod_mun_rfb
        - join IBGE por nome de municipio normalizado com UPPER(strip_accents(...)) e UF
        - referencia de condicao em [scripts/warehouse.py](scripts/warehouse.py#L202)
      - Materializa tabela gold_2025

  - Consolidacao e exportacao
    - Deduplicacao por CNPJ
      - [scripts/warehouse.py](scripts/warehouse.py#L223): consolidar_e_deduplicar
      - ROW_NUMBER particionado por cnpj_basico
      - Mantem 1 registro final por CNPJ
    - Export final
      - [scripts/warehouse.py](scripts/warehouse.py#L249): export_assets
      - Escreve:
        - base_receita_federal_2025.parquet
        - resumo_por_cidade.parquet
        - amostra_validacao_100linhas.parquet
      - Escrita principal em [scripts/warehouse.py](scripts/warehouse.py#L263)

---

## 3) Dependencias cruzadas (quem depende de quem)

- Fluxo modular principal
  - [scripts/main.py](scripts/main.py) -> [scripts/config.py](scripts/config.py)
  - [scripts/main.py](scripts/main.py) -> [scripts/utils.py](scripts/utils.py)
  - [scripts/main.py](scripts/main.py) -> [scripts/transformer.py](scripts/transformer.py)
  - [scripts/main.py](scripts/main.py) -> [scripts/warehouse.py](scripts/warehouse.py)
  - [scripts/transformer.py](scripts/transformer.py) -> [scripts/config.py](scripts/config.py)
  - [scripts/warehouse.py](scripts/warehouse.py) -> [scripts/config.py](scripts/config.py)

- Fluxo monolitico legado
  - [scripts/release_processamento.py](scripts/release_processamento.py)
    - Nao depende de config/transformer/warehouse externos
    - Embute as classes no proprio arquivo

---

## 4) Resumo executivo para arquitetura

- O pipeline modular atual separa claramente responsabilidades:
  - config centraliza regra e ambiente
  - transformer aplica ingestao e qualidade/filtro
  - warehouse aplica enriquecimento SQL em DuckDB e publica artefatos
  - main orquestra tudo
- O fix das aspas e uma etapa critica de qualidade de dados antes da regra de negocio.
- O DuckDB funciona como engine analitica da camada Gold: integra dados tabulares, executa JOIN geografico robusto e escreve resultados em Parquet com eficiencia.
