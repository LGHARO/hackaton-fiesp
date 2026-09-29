# Pipeline de Machine Learning: Importações → CNAE → CNPJs Candidatos

Solução modular, reprodutível e totalmente local em Python que relaciona operações de importação anonimizadas a atividades econômicas oficiais do **CNAE (IBGE/CONCLA)** e, a partir delas, recupera **CNPJs compatíveis** em uma base pública de empresas, com desempate geográfico por UF usando dados oficiais do **Comex Stat (MDIC)**.

> **Este pipeline é independente** das abordagens de `gate_1/`, `gate_2/` e `shared/` (que geram as entregas oficiais das Bases 1, 2 e 3 — ver [`README.md`](README.md)). Ele **não** é usado para gerar os palpites do Gate 2. Para instruções de execução de todo o repositório e lista de dados a baixar, veja [`HOW_TO_USE.md`](HOW_TO_USE.md).
>
> **Schema de entrada:** o pipeline foi construído para o layout da Base 1 (`numero_de_ordem`, `anomes`, `cod_ncm`, `pais_de_origem`, `descricao_do_produto`, `peso_liquido`, `vmle_dolar`). As Bases 2 e 3 do Gate 2 têm colunas diferentes (`chave_item`, `ncm`, `periodo`, …) e exigiriam adaptação antes de passar por aqui.

---

## 1. Arquitetura da solução

O pipeline é separado em **7 etapas modulares**, isolando agrupamento não supervisionado, recuperação semântica e busca cadastral:

```
[Base de Operações] + [Tabela Oficial NCM]
               │
               ▼
┌──────────────────────────────────────────────┐
│ 1. Pré-processamento & Validação de Schemas  │
│    - Normalização técnica de descrições      │
│    - Padronização NCM (8 dígitos)            │
│    - Montagem do texto canônico de entrada   │
└──────────────────────┬───────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
┌─────────────────────────┐   ┌──────────────────────────────┐
│ 2. Baseline Interpretável│   │ 3. Embeddings Semânticos     │
│    - TF-IDF Palavras    │   │    - SentenceTransformers    │
│    - TF-IDF Caracteres  │   │      Multilíngue (PT)        │
│    - Similaridade Cosseno│   │    - Normalização L2         │
└─────────────────────────┘   │    - Cache em disco (.npy)   │
                              └──────────────┬───────────────┘
                                             │
                                             ▼
                              ┌──────────────────────────────┐
                              │ 4. Clustering Não Supervisionado
                              │    - MiniBatchKMeans / HDBSCAN
                              │    - Busca de K (Silhouette, DB)
                              │    - Espaço Original vs PCA/UMAP
                              └──────────────┬───────────────┘
                                             │
                                             ▼
┌───────────────────────────────┐     ┌──────────────────────┐
│ Base Oficial CNAE (IBGE CONCLA)│────▶│ 5. Associação CNAE   │
│ - Descrição, divisão, notas   │     │    - Centróide vs CNAE│
└───────────────────────────────┘     │    - Operação vs CNAE │
                                      │    - NCM-ISIC Crosswalk
                                      │    - Scores Separados │
                                      └──────────────┬───────┘
                                                     │
┌───────────────────────────────┐                    ▼
│ Base Pública de Empresas      │────▶┌──────────────────────┐   ┌────────────────────────┐
│ - CNPJ, razão social, UF      │     │ 6. Recuperação CNPJs │◀──│ Comex Stat (MDIC) 2021 │
│ - CNAE primário               │     │    - Índice Invertido│   │ NCM × mês × UF         │
└───────────────────────────────┘     │    - Desempate por UF│   │ (desempate geográfico) │
                                      │    - Ranking final   │   └────────────────────────┘
                                      └──────────────┬───────┘
                                                     │
                                                     ▼
                                      ┌──────────────────────┐
                                      │ 7. Avaliação & Auditoria
                                      │    - Métricas intrínsecas
                                      │    - Coerência setorial
                                      │    - Amostra auditável
                                      │    - Recall@K / MRR (se
                                      │      houver ground truth)
                                      └──────────────────────┘
                                                     │
                                                     ▼
                                      ┌──────────────────────┐
                                      │ visualizar_resultados.py
                                      │  - Score de especificidade
                                      │  - Top 50 empresas únicas
                                      │  - Dashboard HTML
                                      └──────────────────────┘
```

### Desempate geográfico com o Comex Stat (etapa 6)

Para cada empresa candidata de um CNAE, a UF do cadastro é confrontada com as UFs que efetivamente registraram importação daquele NCM em 2021 (tabela de referência `data/reference/comexstat_2021_ncm_uf.parquet`). O resultado vira o campo `status_comex_uf` e um fator multiplicativo sobre o score:

| `status_comex_uf` | Significado | Fator no score | Prioridade na ordenação |
|---|---|---|---|
| `VALIDADO_MES` | a UF da empresa importou esse NCM no mês da operação | × 1,30 | 1 |
| `VALIDADO_ANO` | a UF importou esse NCM em algum mês de 2021 | × 1,10 | 2 |
| `SEM_REGISTRO` | sem UF na empresa ou NCM ausente na referência (neutro) | × 1,00 | 3 |
| `INCOMPATIVEL_UF` | o NCM nunca foi importado para essa UF em 2021 | × 0,20 | 4 |

As empresas são ordenadas primeiro pela prioridade (quem tem importação confirmada na UF vem antes) e depois pelo score. Os fatores são heurísticos, definidos no código de `src/retrieval.py` (e replicados em `visualizar_resultados.py`); não vêm de calibração estatística.

### Score de especificidade (`visualizar_resultados.py`)

Para priorizar candidatos em nichos pequenos, o visualizador calcula:

```
score_especificidade = score_comex_total × log10(100000 / (empresas_no_cnae + 1))
```

onde `empresas_no_cnae` é a contagem de empresas com aquele CNAE primário na base de empresas. Um score alto num CNAE com poucas empresas vale mais do que o mesmo score num CNAE com milhares. Também é um heurístico, não uma probabilidade.

---

## 2. Restrições conceituais e limitações estatísticas

> [!IMPORTANT]
> **Clustering NÃO atribui rótulos.** K-Means, HDBSCAN e Ward são não supervisionados: particionam o espaço vetorial por densidade ou distância, mas **não sabem o que é um CNAE**. A associação de clusters e operações a CNAEs é feita numa etapa posterior, por projeção vetorial no catálogo do IBGE.

1. **Score não é probabilidade.** `score_total`, `score_cnae_combinado` e `score_especificidade` são combinações lineares ponderadas de similaridades de cosseno, regras setoriais e fatores do Comex Stat. **Não** são probabilidades calibradas P(CNAE | operação) nem P(CNPJ | operação).
2. **Multiplicidade de CNAEs e holdings.** Empresas reais têm um CNAE primário e até 99 secundários; trading companies e operadores logísticos importam NCMs que nada têm a ver com o CNAE principal. **Na implementação atual, apenas o CNAE primário é indexado** (`tipo_cnae_empresa` é sempre `PRIMARIA`); o parâmetro `secondary_cnae_score` existe na configuração, mas não é usado.
3. **Lacuna semântica NCM × descrição.** A descrição oficial do NCM é genérica e fiscal (ex.: "Outras obras de plástico"), enquanto `descricao_do_produto` traz termos técnicos e modelos. O texto canônico combina os dois para mitigar ruído.
4. **O desempate por UF é fraco.** Muitas UFs importam o mesmo NCM no mesmo mês; o critério elimina candidatos claramente incompatíveis, mas não identifica a empresa. O Comex Stat usado aqui é agregado por UF — ao contrário das abordagens de `gate_2/`, que usam a granularidade municipal.
5. **Isenção de autoria.** Um CNPJ no ranking indica **apenas compatibilidade cadastral de atividade econômica com o tipo de mercadoria**. Não é prova nem afirmação de que a empresa realizou a importação.
6. **Base de empresas sem data de referência garantida.** A qualidade do resultado depende do arquivo `dados_tabela_exportacoes_importacoes.csv` (ver §4); confira a data do cadastro antes de comparar com operações de 2021.

---

## 3. Estrutura do projeto

```
.
├── config/
│   └── config.yaml             # Hiperparâmetros: pré-processamento, modelos, clustering e pesos
├── data/
│   ├── raw/                    # Operações de entrada (operacoes_sample.csv sintético é versionado)
│   ├── processed/              # Parquet processado e cache de embeddings (.npy) — em geral não versionado
│   └── reference/              # Catálogo CNAE (IBGE) e Comex Stat NCM×UF — versionados
├── src/
│   ├── config.py               # Parser e validação de configurações
│   ├── schemas.py              # Schemas tipados de dados e saída
│   ├── preprocessing.py        # Limpeza técnica, padronização NCM/CNAE, união e Parquet
│   ├── baseline.py             # Baseline TF-IDF (palavras + char-wb) + cosseno
│   ├── embeddings.py           # Embeddings locais com SentenceTransformers e cache
│   ├── clustering.py           # MiniBatchKMeans, HDBSCAN, hierárquico e métricas
│   ├── association.py          # Associação centróide/operação → CNAE, com score decomposto
│   ├── retrieval.py            # Índice invertido de empresas, desempate Comex Stat, ranking de CNPJs
│   ├── evaluation.py           # Silhouette, Davies-Bouldin, estabilidade, Recall@K, MRR
│   ├── sample_data.py          # Gerador de operações sintéticas
│   └── pipeline.py             # Orquestrador de ponta a ponta
├── scripts/
│   ├── fetch_cnae_ibge.py      # Coleta a estrutura canônica do CNAE na API do IBGE
│   └── fetch_comex_stat.py     # Baixa o Comex Stat 2021 e gera a referência NCM × mês × UF
├── tests/
│   └── test_pipeline.py        # Testes unitários
├── main.py                     # CLI
├── visualizar_resultados.py    # Inspeção no terminal, Top 50 e dashboard HTML
└── br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv   # Tabela NCM (Base dos Dados), com id_isic_classe
```

---

## 4. Dados necessários

| Arquivo | Necessário para | Versionado? | Origem |
|---|---|---|---|
| `data/raw/operacoes_sample.csv` | demonstração (`--mode sample`) | Sim (sintético) | gerado por `python main.py --mode sample` |
| Sua base de operações (`.parquet`/`.csv`) | execução real | **Não** (privada) | fornecida pela organização do hackathon |
| `br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv` | descrição oficial do NCM e crosswalk NCM→ISIC | Sim | Base dos Dados (diretório "Nomenclatura Comum do Mercosul") |
| `data/reference/cnae_referencia.csv` | associação a CNAE | Sim | regenerável com `scripts/fetch_cnae_ibge.py` (API pública do IBGE) |
| `data/reference/comexstat_2021_ncm_uf.parquet` | desempate por UF | Sim | regenerável com `scripts/fetch_comex_stat.py` (MDIC) |
| `dados_tabela_exportacoes_importacoes.csv` (raiz) | etapa `retrieve` (recuperação de CNPJs) | **Não** (`.gitignore`) | ver abaixo |

**Cadastro de empresas (`dados_tabela_exportacoes_importacoes.csv`).** A etapa `retrieve` lê este arquivo, que precisa ter as colunas `cnpj`, `razao_social`, `cnae_2_primaria`, `sigla_uf` e `id_municipio_nome`. É a estrutura da tabela de empresas exportadoras/importadoras derivada dos dados abertos do MDIC/Receita Federal; **o MDIC descontinuou a publicação da lista original em 2023** (ver `gate_1/RELATORIO.md`), então esse arquivo deve ser obtido com a equipe. Ele não pode ir para o GitHub (tamanho). Sem ele, as etapas 1–5 rodam normalmente; só a `retrieve` falha.

---

## 5. Instalação e execução

### Pré-requisitos

- Python 3.14 (definido em `.python-version`/`pyproject.toml`) e [`uv`](https://docs.astral.sh/uv/). Os módulos de `src/` em si não usam recursos exclusivos do 3.14, mas o ambiente do projeto é o do `pyproject.toml`.
- O `uv sync` instala as dependências dos pipelines de `gate_*` e **não** as deste pipeline. O pipeline de ML também precisa de `pyyaml` e `sentence-transformers` (que traz `torch`), e a etapa `retrieve` grava Parquet (`pyarrow`, já presente).

```bash
# uso pontual, sem alterar o pyproject:
uv run --with pyyaml --with sentence-transformers --with torch python main.py --mode sample

# ou tornar permanente:
uv add pyyaml sentence-transformers torch
```

Sem `uv`, num ambiente virtual comum:

```bash
pip install numpy pandas pyarrow scikit-learn sentence-transformers torch pyyaml
```

> Na primeira execução com embeddings, o modelo `paraphrase-multilingual-MiniLM-L12-v2` é baixado do Hugging Face (é necessário acesso à internet nesse momento; depois fica em cache local).

### Testar rapidamente com dados sintéticos

```bash
python main.py --mode sample --sample-size 500     # gera data/raw/operacoes_sample.csv
python main.py --mode all                          # roda as 7 etapas sobre a amostra
```

A etapa 6 (recuperação de CNPJs) precisa do cadastro de empresas da §4. Sem ele, use `--mode` por etapa até `associate`.

### Rodar com a sua base

**Opção 1 — linha de comando (recomendada):**

```bash
python main.py --input /caminho/para/operacoes.parquet --mode all
```

**Opção 2 — `config/config.yaml`:**

```yaml
data:
  operations_file: "caminho/para/seu_arquivo.parquet"
```

```bash
python main.py --mode all
```

### Etapas isoladas

```bash
python main.py --mode preprocess    # 1. Pré-processamento e validação
python main.py --mode baseline      # 2. Baseline TF-IDF
python main.py --mode embeddings    # 3. Embeddings densos (cache em disco; --force-recompute ignora o cache)
python main.py --mode cluster       # 4. Clustering e métricas
python main.py --mode associate     # 5. Associação semântica com CNAEs
python main.py --mode retrieve      # 6. Recuperação de CNPJs (exige o cadastro de empresas)
python main.py --mode evaluate      # 7. Avaliação e amostra de auditoria
```

Cada etapa executa as anteriores automaticamente se ainda não estiverem em memória (o estado não persiste entre invocações separadas da CLI, exceto o cache de embeddings e os arquivos em `outputs/`).

Cobertura do `--mode all`: (1) pré-processamento e Parquet; (2) predições do baseline; (3) embeddings com cache; (4) busca de *K* e clustering, comparando espaço original × PCA; (5) associação operação/cluster → CNAE; (6) recuperação de CNPJs com desempate Comex Stat; (7) avaliação intrínseca e amostra para auditoria manual.

### Atualizar as referências (opcional)

```bash
python scripts/fetch_cnae_ibge.py     # refaz data/reference/cnae_referencia.csv a partir da API do IBGE
python scripts/fetch_comex_stat.py    # baixa data/raw/IMP_2021.csv (grande) e refaz o parquet NCM × mês × UF
```

> O `fetch_comex_stat.py` filtra os NCMs presentes em `data/processed/operacoes_processadas.parquet` (gerado na etapa 1). Se esse arquivo não existir, ele mantém **todos** os NCMs. **Atenção:** o script desativa a verificação de certificado SSL no download (`CERT_NONE`) — se possível, baixe `IMP_2021.csv` manualmente de <https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta> para `data/raw/`, e o script o reutiliza.

### Visualização e exportação dos palpites

Depois da etapa 6:

```bash
python visualizar_resultados.py --top-especificos 50    # Top 50 empresas únicas (terminal)
python visualizar_resultados.py --open                  # gera e abre o dashboard HTML
python visualizar_resultados.py --op OP-1000001         # inspeciona uma operação
python visualizar_resultados.py --cluster 17            # candidatos de um cluster
python visualizar_resultados.py --top 10                # 10 operações com maior score médio
python visualizar_resultados.py --no-html               # só terminal
python visualizar_resultados.py --file outputs/candidatos_cnpjs_finais.csv   # arquivo alternativo
```

### Testes

```bash
uv run --with pyyaml python -m unittest tests.test_pipeline -v
```

Os testes cobrem limpeza/formatação, baseline, clustering e associação, e **não** precisam de `torch` nem de `sentence-transformers`.

---

## 6. Esquema dos arquivos de saída (`outputs/`, não versionado)

### `candidatos_cnpjs_finais.csv` / `.parquet` — arquivo principal

| Coluna | Descrição |
|---|---|
| `numero_de_ordem` | identificador anonimizado da operação |
| `cluster_id` | grupo formado pelo clustering |
| `cnae_candidato` | classe CNAE mais próxima (ex.: `21.21-1`) |
| `descricao_cnae` | descrição oficial do IBGE |
| `ranking_cnae` | posição do CNAE para a operação (1 a *K*) |
| `similaridade_operacao_cnae` | cosseno direto entre a operação e o CNAE |
| `similaridade_cluster_cnae` | cosseno entre o centróide do cluster e o CNAE |
| `compatibilidade_ncm_cnae` | indicador estrutural (via correlação NCM/ISIC) |
| `cnpj_candidato` | CNPJ de 14 dígitos com atividade correspondente (`NENHUM_CNPJ_LOCALIZADO` se o CNAE não tem empresas na base) |
| `tipo_cnae_empresa` | `PRIMARIA` (única valor gerado hoje) ou `NENHUMA` |
| `sigla_uf` | UF da empresa candidata |
| `status_comex_uf` | `VALIDADO_MES`, `VALIDADO_ANO`, `SEM_REGISTRO` ou `INCOMPATIVEL_UF` (ver §1) |
| `ranking_cnpj` | ordem do CNPJ entre as empresas compatíveis com o CNAE |
| `score_total` | score composto heurístico (inclui o fator Comex Stat) |
| `limitacoes` | advertência metodológica explícita |

### Outros arquivos

| Arquivo | Etapa | Conteúdo |
|---|---|---|
| `baseline_cnae_predictions.csv` | 2 | predições top-*k* do baseline TF-IDF |
| `k_search_clustering_metrics.csv` | 4 | métricas por valor de *K* testado |
| `associacoes_operacoes_cnae.csv` | 5 | associação operação/cluster → CNAE, sem CNPJ |
| `relatorio_avaliacao_intrinseca.json` | 7 | métricas de clustering e coerência setorial |
| `amostra_inspecao_manual.csv` | 7 | 20 operações com descrição completa, NCM, cluster e empresas sugeridas, para revisão humana |
| `top50_empresas_candidatas_hackaton.csv` / `.parquet` | visualizador | Top 50 **CNPJs distintos** por score de especificidade, com `status_comex_uf` |
| `visualizacao_interativa.html` | visualizador | dashboard autossuficiente (amostra de até 2.500 linhas + Top 50) |

---

## 7. Limitações de implementação conhecidas

- **Desempenho da indexação.** `build_index` percorre o cadastro com `iterrows` e guarda tudo em memória; adequado para cadastros de centenas de milhares de linhas, mas lento/pesado para o CNPJ nacional completo.
- **Apenas CNAE primário** é indexado (ver §2, item 2), e a coluna `situacao_cadastral` é fixada como `ATIVA` — o arquivo de empresas não é filtrado por situação.
- **Comex Stat por UF**, não por município: o desempate elimina UFs incompatíveis, mas não separa empresas da mesma UF.
- **Estado não persistido entre execuções.** Cada chamada da CLI reexecuta as etapas anteriores necessárias (com cache apenas para embeddings).
- **Qualidade da avaliação.** As métricas são intrínsecas (coerência dos clusters e dos CNAEs); Recall@K e MRR só existem se houver *ground truth*, que o repositório não traz.
