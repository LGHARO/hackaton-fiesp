# Reidentificação de importadores em bases anonimizadas da Receita Federal

Este repositório reúne **duas abordagens independentes** para o mesmo
problema do hackathon: dada uma base de importações com o importador
anonimizado, gerar candidatos de CNPJ de quem provavelmente fez cada
importação, usando só cruzamento de dados públicos.

## As duas abordagens

- **`gate_1/` + `gate_2/` + `shared/`** — pipeline baseado em clusterização
  de texto (gate_1) e em concentração geográfica pública do comércio
  exterior (gate_2), com CNPJs recuperados via cruzamento com a base
  nacional de CNPJ da Receita Federal. Descrito abaixo.
- **`src/` + `main.py`** — pipeline de machine learning (embeddings
  semânticos, clustering, associação a CNAE oficial e recuperação de CNPJ
  compatível). Descrito em [`README_PIPELINE_ML.md`](README_PIPELINE_ML.md).

Os dois foram desenvolvidos em paralelo por integrantes diferentes da
equipe; os resultados de cada um foram checados entre si (ver seção
"Resultados") pra não entregar CNPJ repetido.

---

## Pipeline gate_1 / gate_2 / shared

```
gate_1/     base menor (57.846 linhas) -- ver gate_1/RELATORIO.md
gate_2/     base maior (23,2 milhões de linhas) -- ver gate_2/RELATORIO.md
shared/     infraestrutura reutilizada pelos dois gates (ver abaixo)
```

Cada `gate_*/` é dividido em:

```
gate_N/
  dados/raw/          entradas brutas especificas desse gate
  dados/processado/   resultados intermediarios (parquet)
  scripts/            pipeline numerado, executar na ordem
  RELATORIO.md         metodologia, achados e limitacoes desse gate
  palpites_cnpj_top50*.csv / .parquet   resultado final (entrega)
```

`shared/` guarda o que **não é específico de nenhum gate** — tabelas de
referência do Brasil (`PAIS.csv`, `UF_MUN.csv`, códigos de município) e a
base nacional de CNPJ da Receita Federal, já filtrada pelos municípios que
os dois gates precisaram consultar. Isso evita baixar/reprocessar a mesma
base de CNPJ (múltiplos GB) duas vezes.

### Como rodar

Pré-requisitos: Python 3.14+, [`uv`](https://docs.astral.sh/uv/) (o projeto
usa `uv run` para gerenciar dependências via `pyproject.toml`/`uv.lock`).
Todo script assume que é executado **a partir da raiz do repositório**, por
exemplo:

```
uv run python gate_1/scripts/step3_filtro_municipios.py
uv run python gate_2/scripts/03_concentracao_municipio.py
```

A ordem de execução de cada gate está documentada na seção "Reprodução" do
`RELATORIO.md` correspondente.

### Dados

`dados/` (em qualquer nível) e a maioria dos `*.parquet` **não vão pro
controle de versão** (ver `.gitignore`) — são grandes (a base de CNPJ
nacional filtrada sozinha passa de 1GB) e inteiramente reprodutíveis a
partir dos scripts. As exceções explícitas são os arquivos de entrega
(`palpites_cnpj_top50*.parquet` de cada gate), que ficam versionados porque
são o resultado final, não dado intermediário.

### Resultados

- `gate_1/palpites_cnpj_top50.csv` (+ `.parquet`)
- `gate_2/palpites_cnpj_top50.csv` e `palpites_cnpj_top50_final.csv` (+
  `.parquet` — o `_final` já incorpora a checagem cruzada com clusterização
  de texto, é a versão recomendada)

Os três conjuntos foram checados entre si e contra `operacoes_reidentificadas.parquet`
(identificado separadamente pela equipe) — **sem nenhum CNPJ repetido** entre
os quatro.

---

## Pipeline de machine learning (`src/`, `main.py`)

Ver [`README_PIPELINE_ML.md`](README_PIPELINE_ML.md) para a documentação
completa: arquitetura em 7 etapas (pré-processamento, baseline TF-IDF,
embeddings semânticos, clustering, associação a CNAE, recuperação de CNPJ e
avaliação), instruções de instalação e execução, e esquema dos arquivos de
saída em `outputs/`.
