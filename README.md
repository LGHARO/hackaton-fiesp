# Reidentificação de importadores em bases anonimizadas da Receita Federal

Este repositório reúne as soluções da equipe para o hackathon FIESP: dada uma base de importações com o importador anonimizado, **gerar palpites de CNPJ** de quem provavelmente fez cada importação, usando apenas cruzamento com dados públicos. Além dos palpites, o trabalho documenta **como** a reidentificação foi possível e propõe um plano de mitigação das vulnerabilidades encontradas.

> **Como rodar do zero** (dados a baixar, fontes, ordem de execução, o que não vai para o GitHub): [`HOW_TO_USE.md`](HOW_TO_USE.md).

---

## Status das entregas

| Etapa | Base | Conteúdo | Documentação |
|---|---|---|---|
| **Gate 1** | Base 1 — 57.846 linhas | até 50 palpites | [`gate_1/RELATORIO.md`](gate_1/RELATORIO.md) |
| **Gate 2** | Base 2 — 23,2 mi de linhas, **sem** descrição do produto | até 50 palpites | [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §4 e [`README_BASE2.md`](gate_2/scripts_sem_descricao/README_BASE2.md) |
| **Gate 2** | Base 3 — 23,2 mi de linhas, **com** descrição do produto | até 50 palpites | [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §3 |
| Gate 3 | — | a definir | — |

O Gate 2 exige, além dos 100 palpites (50 por base): relatório com metodologia, fontes, logs e scripts, e um **plano de mitigação das vulnerabilidades** (está em [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §7).

**Regras do enunciado:** as bases do Gate 2 são exercícios **independentes** (não podem ser cruzadas entre si no método) e **nenhum CNPJ pode se repetir** entre os palpites das Bases 1, 2 e 3.

> **Nomenclatura.** Seguimos a adotada pela equipe: a base **com** descrição é a **Base 3**; a base **sem** descrição (campo textual suprimido) é a **Base 2**.

---

## Abordagens

O repositório contém **duas abordagens independentes** para o mesmo problema. Foram desenvolvidas em paralelo por integrantes diferentes da equipe.

### 1. Cruzamento com estatísticas públicas — `gate_1/`, `gate_2/`, `shared/`

É a abordagem que gera as entregas oficiais. Cada base explora um sinal diferente:

| | Base 1 (Gate 1) | Base 3 (Gate 2, com descrição) | Base 2 (Gate 2, sem descrição) |
|---|---|---|---|
| **Sinal principal** | Clusterização de texto (HDBSCAN) unida por `numero_de_ordem` compartilhado; município por cobertura ≥ 90% das combinações (mês, SH4, país) com tolerância de 2% em valor e peso | Concentração geográfica pública (Comex Stat): combinações (mês, SH4, país) concentradas em 1 município | **Reconciliação exata de FOB e peso líquido** com o Comex Stat municipal |
| **Do município ao CNPJ** | Pontuação de razão social/nome fantasia × palavras da descrição | Palavras raras da descrição × razão social/nome fantasia (`rapidfuzz`) | Apenas densidade de empresas no município (`score = 1/N`) |
| **Confirmação** | União de grupos por declaração compartilhada | Concordância com a clusterização de texto | — |
| **Scripts** | `gate_1/scripts/` | `gate_2/scripts/` | `gate_2/scripts_sem_descricao/` |
| **Formato do CNPJ** | raiz de 8 dígitos (`cnpj_basico`) | raiz de 8 dígitos (`cnpj_basico`) | 14 dígitos + `chave_item` |

Em uma frase por base:

- **Base 1:** o texto da descrição forma grupos; o número de declaração repetido une clusters da mesma empresa; o perfil agregado de cada grupo é comparado ao Comex Stat municipal para achar os municípios candidatos, e razão social/nome fantasia × palavras da descrição escolhem o CNPJ.
- **Base 3:** sem número de declaração, o texto perde força; o sinal principal passa a ser o município revelado pela própria estatística pública (41% das ~211 mil combinações mês × SH4 × país têm ≥ 99% do valor nacional em uma única cidade), e o texto serve de desempate e de checagem.
- **Base 2:** sem texto nenhum, o ataque usa o "duplo balanço": operações que são as únicas de sua combinação (mês, SH4, país) têm FOB e peso idênticos ao total público de *um* município — o que revela onde a importação ocorreu. Esse é o **ponto fraco mais explícito** encontrado: o município é identificado com boa confiança; a empresa dentro dele, não (ver limitações em [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §4.3).

### 2. Pipeline de machine learning — `src/`, `main.py`

Embeddings semânticos, clustering, associação a CNAE oficial e recuperação de CNPJ compatível, com desempate por UF via Comex Stat e dashboard HTML. **Não é usado para gerar os palpites do Gate 2** — é uma abordagem independente, documentada em [`README_PIPELINE_ML.md`](README_PIPELINE_ML.md).

---

## Estrutura do repositório

```
.
├── HOW_TO_USE.md                 # guia de execução: dados, fontes, ordem dos scripts
├── README.md                     # este arquivo
├── README_PIPELINE_ML.md         # documentação do pipeline de ML (src/, main.py)
├── pyproject.toml / uv.lock      # dependências (gerenciadas com uv)
│
├── gate_1/                       # Base 1
│   ├── scripts/                  # step3, step4, step6
│   ├── palpites_cnpj_top50.csv   # entrega (+ .parquet)
│   └── RELATORIO.md
│
├── gate_2/                       # Bases 2 e 3
│   ├── scripts/                  # Base 3 (com descrição): 01, 03, 04, 05 + joblog/progresso
│   ├── scripts_sem_descricao/    # Base 2 (sem descrição): 01 a 04 + README_BASE2.md
│   ├── palpites_cnpj_top50_final.csv   # entrega da Base 3 (versão recomendada, + .parquet)
│   ├── palpites_cnpj_top50.csv         # Base 3, versão preliminar (sem o cruzamento com o texto)
│   ├── palpites_base2_top50.csv        # entrega da Base 2 (gerada pelo script 03; ver nota abaixo)
│   └── RELATORIO.md
│
├── shared/scripts/               # infraestrutura comum aos gates
│   ├── mapa_municipios.py        # crosswalk município Comex Stat -> código TOM da Receita
│   ├── mapa_paises.py            # país da base -> código de país do Comex Stat
│   ├── baixar_filtrar_estabelecimentos.py   # CNPJ ativos nos municípios-alvo
│   └── baixar_filtrar_empresas.py           # razão social dos candidatos
│
├── src/, main.py, config/        # pipeline de ML (ver README_PIPELINE_ML.md)
├── scripts/                      # coleta de referências do pipeline de ML (CNAE/IBGE, Comex Stat)
├── data/reference/               # referências pequenas versionadas (CNAE, Comex Stat NCM×UF)
├── tests/                        # testes unitários do pipeline de ML
└── visualizar_resultados.py      # dashboard/exportação do pipeline de ML
```

Dentro de `gate_*/` e `shared/`, os dados brutos e intermediários ficam em `dados/` (**não versionados**): `dados/raw/` (entradas), `dados/processado/` (intermediários).

> **Nota sobre `palpites_base2_top50.csv`:** o arquivo é gerado por `gate_2/scripts_sem_descricao/03_gerar_top50_base2.py` (e reescrito pelo `04_...`). Ele **não estava presente** no snapshot desta branch; depois de rodar os passos da Base 2, versione-o (o `.gitignore` já o libera).

---

## Como rodar (resumo)

Pré-requisitos: Python 3.14 e [`uv`](https://docs.astral.sh/uv/). **Todo script é executado a partir da raiz do repositório.**

```bash
uv sync                                                   # instala as dependências

# comum às três bases
uv run python shared/scripts/mapa_municipios.py
uv run python shared/scripts/baixar_filtrar_estabelecimentos.py
uv run python shared/scripts/baixar_filtrar_empresas.py

# Base 3 (com descrição)
uv run python gate_2/scripts/01_cluster_texto.py          # demora horas; retomável
uv run python gate_2/scripts/03_concentracao_municipio.py
uv run python gate_2/scripts/04_score_final.py
uv run python gate_2/scripts/05_cruzamento_sinais.py      # -> palpites_cnpj_top50_final.csv

# Base 2 (sem descrição)
uv run python gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py
uv run python gate_2/scripts_sem_descricao/02_monopolio_municipal.py
uv run python gate_2/scripts_sem_descricao/03_gerar_top50_base2.py
uv run python gate_2/scripts_sem_descricao/04_validacao_final_independente.py
```

Isso pressupõe as bases do hackathon (privadas) e os dados públicos já baixados nos caminhos esperados. **A lista completa de arquivos, os links de download e as lacunas conhecidas estão em [`HOW_TO_USE.md`](HOW_TO_USE.md).** A ordem de execução da Base 1 e a verificação cruzada final também.

---

## Dados: o que vai e o que não vai para o GitHub

O `.gitignore` **exclui**: qualquer pasta `dados/`, todo `*.parquet` (exceto os de entrega abaixo), `*.log`, `outputs/*`, `data/raw/IMP_*.csv` e `dados_tabela_exportacoes_importacoes.csv`.

| Item | Versionado? |
|---|---|
| Bases do hackathon (privadas) e dados públicos baixados | **Não** — ficam em `dados/`; ver `HOW_TO_USE.md` para obter |
| Intermediários (`*/dados/processado/`) | **Não** — grandes e reproduzíveis pelos scripts |
| Palpites finais (`.csv` e `.parquet` de `gate_1/` e `gate_2/`, incl. `palpites_base2_top50_detalhado.parquet`) | **Sim** — exceções explícitas no `.gitignore` |
| Referências pequenas (`data/reference/`, `br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv`, embeddings de CNAE) | **Sim** |
| Logs `.log` | **Não** — salvar como `.txt` (ver `HOW_TO_USE.md` §7) |

---

## Resultados e conformidade

- **Base 1:** `gate_1/palpites_cnpj_top50.csv` — 50 linhas, 46 raízes distintas.
- **Base 3:** `gate_2/palpites_cnpj_top50_final.csv` — 50 linhas, 48 raízes distintas; confiança 3 alta, 41 média, 6 baixa. O ranking ordena primeiro por confiança e depois por score.
- **Base 2:** `gate_2/palpites_base2_top50.csv` — 50 pares (`chave_item`, `CNPJ` de 14 dígitos), gerado pelo script 03.

**Conferência de "nenhum CNPJ repetido entre as bases"** (feita pela **raiz de 8 dígitos**, critério mais conservador que os 14 dígitos): Base 1 × Base 3 = **0 raízes em comum**. A Base 2 só pode ser conferida depois de gerada; o script de verificação está em [`HOW_TO_USE.md`](HOW_TO_USE.md) §5.6. O `04_validacao_final_independente.py` tem alcance limitado (ver [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §5), então **não** deve ser a única checagem antes de entregar.

---

## Limitações (leia antes de usar os palpites)

- **São heurísticas de investigação, não provas.** Reduzem milhares de empresas possíveis a uma lista curta; nenhum score é probabilidade calibrada.
- **Universo de candidatos:** o cadastro de CNPJ é de 2026 (snapshot de 14/09/2026, de um espelho de terceiros), enquanto as operações são de 2021 — empresas que fecharam nesse intervalo não aparecem; empresas abertas depois aparecem.
- **Cobertura geográfica:** o filtro de CNPJs candidatos usa os municípios candidatos do Gate 1; municípios que só aparecem nas Bases 2 e 3 podem ficar sem candidatos (detalhes e correção em `HOW_TO_USE.md` §4.3).
- **Base 2:** o CNPJ de 14 dígitos é montado como raiz + `0001` + `00`; os dígitos verificadores reais podem diferir, e o desempate entre empresas do mesmo município é arbitrário. A expectativa de acertos é baixa (≈ 1/N por palpite, N entre 536 e 5.476 empresas por município).
- **Reprodutibilidade:** o `df_clusterizado.parquet` do Gate 1 veio de um notebook que não está no repositório, e há passos numerados ausentes (`gate_1` step 5, `gate_2/scripts` 02). Ver `HOW_TO_USE.md` §4.3.

---

## Plano de mitigação (resumo)

A reidentificação foi possível **compondo dados públicos individualmente inofensivos**. As mitigações propostas, em ordem de prioridade (detalhes, evidências e custos em [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §7):

1. **P1 — atacam os sinais principais das Bases 2 e 3:** arredondar/agrupar FOB e peso em faixas (V2); *k*-anonimato sobre (mês, SH4, país) nos microdados (V3); supressão de células do Comex Stat municipal com poucos contribuintes (V1).
2. **P2 — vazamento textual:** dicionário controlado de descrições por NCM ou redação automática de nomes próprios (V4).
3. **P3 — governança:** rotação de hashes de identificadores (V5) e avaliação de risco por composição antes de cada publicação (V6).

Nenhuma mitigação foi implementada ou medida; os próprios scripts servem como teste de regressão (ver §7.2 do relatório).

---

## Mapa da documentação

| Documento | Para quê |
|---|---|
| [`HOW_TO_USE.md`](HOW_TO_USE.md) | Rodar o projeto: dados, fontes, ordem, verificação, logs, problemas comuns |
| [`gate_1/RELATORIO.md`](gate_1/RELATORIO.md) | Metodologia e limitações da Base 1 |
| [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) | Metodologia, fontes, conformidade, logs e plano de mitigação das Bases 2 e 3 |
| [`gate_2/scripts_sem_descricao/README_BASE2.md`](gate_2/scripts_sem_descricao/README_BASE2.md) | Nota metodológica da Base 2 (execução registrada pela equipe) |
| [`README_PIPELINE_ML.md`](README_PIPELINE_ML.md) | Pipeline de machine learning (`src/`, `main.py`) |
