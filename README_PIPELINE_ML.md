# Pipeline Local de Machine Learning: Importações -> CNAE -> CNPJs Candidatos

Este repositório contém uma solução modular, reprodutível e totalmente local em Python para relacionar operações de importação aduaneiras anonimizadas a atividades econômicas oficiais do **CNAE (Classificação Nacional de Atividades Econômicas - IBGE)** e, subsequentemente, recuperar **CNPJs compatíveis** em bases públicas de empresas (ex.: exportadoras/importadoras e dados da Receita Federal).

---

## 1. Arquitetura da Solução

O pipeline é estritamente separado em **7 etapas modulares**, garantindo isolamento conceitual entre agrupamento não supervisionado, recuperação semântica e busca cadastral:

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
│ Base Pública de Empresas      │────▶┌──────────────────────┐
│ - 1.2M+ CNPJs                 │     │ 6. Recuperação CNPJs │
│ - CNAE Primário / Secundário  │     │    - Índice Invertido│
│ - Prioridade 'Ativa'          │     │    - Ponderação tipo │
└───────────────────────────────┘     │    - Ranking final   │
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
```

---

## 2. Restrições Conceituais e Limitações Estatísticas

> [!IMPORTANT]
> **Clustering NÃO atribui rótulos**: Algoritmos de clustering (K-Means, HDBSCAN, Ward) são estritamente **não supervisionados**. Eles particionam o espaço vetorial com base em densidade ou distância geométrica entre termos de produtos, mas **não sabem o que é um CNAE**. Por isso, a associação semântica dos clusters e operações aos CNAEs oficiais é feita em etapa posterior por projeção vetorial no catálogo do IBGE.

### Limitações Estatísticas e Metodológicas:

1. **Score NÃO é Probabilidade**:
   - Os scores retornados (`score_total`, `score_cnae_combinado`) são combinações lineares ponderadas de similaridades de cosseno e regras setoriais.
   - **Não** são probabilidades calibradas $P(\text{CNAE} \mid \text{Operação})$ nem $P(\text{CNPJ} \mid \text{Operação})$. Apresentá-los como probabilidade seria estatisticamente incorreto.
2. **Multiplicidade de CNAEs e Holdings**:
   - Empresas reais operam com um CNAE primário e até 99 CNAEs secundários. Empresas de comércio exterior (ex.: *Trading Companies*, operadores logísticos) importam produtos com dezenas de NCMs que não coincidem com o seu CNAE principal.
3. **Lacuna Semântica e NCM vs Descrição**:
   - A descrição do NCM é genérica e fiscal (ex.: *"Outras obras de plástico"*), enquanto a `descricao_do_produto` traz termos técnicos, especificações e modelos de engenharia. A representação canônica combina ambos para mitigar ruídos.
4. **Isenção de Autoria**:
   - A presença de um CNPJ no ranking final indica **apenas compatibilidade cadastral de atividade econômica com o tipo de mercadoria**. Não constitui prova ou afirmação de que a empresa realizou a importação.

---

## 3. Estrutura do Projeto

```
hackaton/
├── config/
│   └── config.yaml            # Hiperparâmetros de pré-processamento, modelos, clustering e pesos
├── data/
│   ├── raw/                   # Arquivos originais (operações, empresas, NCM)
│   ├── processed/             # Parquet processado e cache de embeddings (.npy)
│   └── reference/             # Catálogo oficial CNAE do IBGE (com notas explicativas e atividades)
├── src/
│   ├── __init__.py
│   ├── config.py              # Parser e validação de configurações
│   ├── schemas.py             # Schemas tipados de dados e saída
│   ├── preprocessing.py       # Limpeza técnica, padronização NCM/CNAE, união e Parquet
│   ├── baseline.py            # Baseline interpretável TF-IDF (palavras + char-wb) + Cosseno
│   ├── embeddings.py          # Embeddings semânticos locais com SentenceTransformers e cache
│   ├── clustering.py          # MiniBatchKMeans, HDBSCAN, Hierárquico e métricas intrínsecas
│   ├── association.py         # Associação de centróides e operações a CNAEs com decomposição de score
│   ├── retrieval.py           # Índice invertido de empresas e geração do ranking de CNPJs
│   ├── evaluation.py          # Métricas (Silhouette, Davies-Bouldin, estabilidade, Recall@K, MRR)
│   └── pipeline.py            # Orquestrador unificado de ponta a ponta
├── scripts/
│   └── fetch_cnae_ibge.py     # Script para coletar a estrutura canônica CNAE do IBGE
├── tests/
│   └── test_pipeline.py       # Testes unitários do pipeline
├── main.py                    # Interface de Linha de Comando (CLI)
└── README.md                  # Documentação completa
```

---

## 4. Instruções de Instalação e Execução Local

### Pré-requisitos
- Python 3.10+ (testado em Python 3.11 e 3.13)
- Ambiente virtual configurado

```bash
# 1. Ativar o ambiente virtual
source .venv/bin/activate

# 2. Instalar dependências (caso configure em novo ambiente)
pip install numpy pandas polars pyarrow scikit-learn sentence-transformers torch pyyaml pydantic tqdm
```

### Como Rodar com a sua Própria Base Local

Para executar o pipeline com a sua base de dados aduaneira local, você tem duas opções simples:

#### Opção 1: Via Linha de Comando (Recomendada)
Passe o caminho direto para o seu arquivo local (`.parquet` ou `.csv`) através do argumento `--input`:
```bash
python main.py --input /caminho/para/seu_arquivo_de_operacoes.parquet --mode all
```

#### Opção 2: Editando o arquivo `config/config.yaml`
Abra `config/config.yaml` e aponte para o seu arquivo local:
```yaml
data:
  operations_file: "caminho/para/seu_arquivo.parquet"
```
Em seguida, execute:
```bash
python main.py --mode all
```

### Dados Públicos Complementares
1. **Cadastro de Empresas Exportadoras/Importadoras (`dados_tabela_exportacoes_importacoes.csv`)**:
   Obtido nos dados abertos do MDIC / Receita Federal. Coloque o arquivo na raiz do projeto (ele está no `.gitignore` para não ultrapassar limites de tamanho).
2. **Dados Oficiais de Comércio Exterior do Comex Stat**:
   Para baixar e indexar os fluxos oficiais de importação (usados no desempate geográfico por UF):
   ```bash
   python scripts/fetch_comex_stat.py
   ```

### Visualização e Exportação de Palpites

Após a execução do pipeline, utilize o visualizador para inspecionar e exportar os palpites reidentificados:
```bash
# Exibir no terminal o Top 50 de empresas únicas reidentificadas com desempate do Comex Stat:
python visualizar_resultados.py --top-especificos 50

# Gerar e abrir o Dashboard HTML interativo no navegador:
python visualizar_resultados.py --open
```

### Execução de Etapas Isoladas
```bash
python main.py --mode baseline    # Baseline interpretável TF-IDF
python main.py --mode preprocess  # Pré-processamento e validação
python main.py --mode embeddings  # Geração de embeddings densos
python main.py --mode cluster     # Clustering K-Means e métricas
python main.py --mode associate   # Associação semântica com CNAEs
python main.py --mode retrieve    # Recuperação de CNPJs compatíveis
python main.py --mode evaluate    # Geração de relatórios de avaliação
```
Executa automaticamente:
1. Pré-processamento e serialização em Parquet.
2. Predições do baseline interpretável.
3. Inferência de embeddings neurais densos locais com cache em disco.
4. Exploração de $K$ ideal e clustering no espaço original vs PCA.
5. Associação desagregada Operação/Cluster -> CNAE oficial.
6. Recuperação de CNPJs na base pública via índice invertido.
7. Relatório de avaliação intrínseca e amostra de auditoria manual.

#### C. Executar Etapas Isoladas:
```bash
python main.py --mode preprocess    # Pré-processamento e validação
python main.py --mode embeddings    # Geração de embeddings densos
python main.py --mode cluster       # Clustering e métricas de agrupamento
python main.py --mode associate     # Associação semântica com CNAEs
python main.py --mode retrieve      # Recuperação de CNPJs compatíveis
python main.py --mode evaluate      # Geração de relatórios de avaliação
```

---

## 5. Esquema dos Arquivos de Saída

### Arquivo Principal: `outputs/candidatos_cnpjs_finais.csv` (e `.parquet`)
Contém as colunas exatas especificadas:
- `numero_de_ordem`: identificador anonimizado da operação;
- `cluster_id`: identificador do grupo formado pelo clustering;
- `cnae_candidato`: código oficial da classe CNAE mais próxima (ex.: `21.21-1`);
- `descricao_cnae`: descrição oficial do IBGE;
- `ranking_cnae`: posição do CNAE para a operação (1 a $K$);
- `similaridade_operacao_cnae`: similaridade de cosseno direta entre a operação e o CNAE;
- `similaridade_cluster_cnae`: similaridade de cosseno entre o centróide do cluster e o CNAE;
- `compatibilidade_ncm_cnae`: indicador estrutural (via correlação NCM/ISIC);
- `cnpj_candidato`: CNPJ de empresa com atividade econômica correspondente;
- `tipo_cnae_empresa`: `PRIMARIA` ou `SECUNDARIA`;
- `ranking_cnpj`: ordem do CNPJ entre as empresas compatíveis com o CNAE;
- `score_total`: score composto heurístico e desagregado;
- `limitacoes`: advertência metodológica explícita.

### Arquivo de Auditoria Manual: `outputs/amostra_inspecao_manual.csv`
Subconjunto formatado para revisão humana, contendo a descrição completa do produto, descrição oficial do NCM, cluster atribuído e empresas sugeridas.
