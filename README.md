# Reidentificação de importadores em bases anonimizadas da Receita Federal

Duas rodadas (gates) do mesmo problema: a Receita Federal publica bases de
importação com o importador anonimizado. O objetivo, em cada gate, é gerar
50 palpites de CNPJ de quem provavelmente fez cada importação, usando só
cruzamento de dados públicos — sem nenhum vazamento direto de identidade na
base.

## Estrutura do repositório

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

## Como rodar

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

## Dados

`dados/` (em qualquer nível) e a maioria dos `*.parquet` **não vão pro
controle de versão** (ver `.gitignore`) — são grandes (a base de CNPJ
nacional filtrada sozinha passa de 1GB) e inteiramente reprodutíveis a
partir dos scripts. As exceções explícitas são os arquivos de entrega
(`palpites_cnpj_top50*.parquet` de cada gate), que ficam versionados porque
são o resultado final, não dado intermediário.

## Resultados

- `gate_1/palpites_cnpj_top50.csv` (+ `.parquet`)
- `gate_2/palpites_cnpj_top50.csv` e `palpites_cnpj_top50_final.csv` (+
  `.parquet` — o `_final` já incorpora a checagem cruzada com clusterização
  de texto, é a versão recomendada)

Os três conjuntos foram checados entre si e contra `operacoes_reidentificadas.parquet`
(identificado separadamente pela equipe) — **sem nenhum CNPJ repetido** entre
os quatro.

## Nota para quem for sincronizar com um repositório remoto existente

Este histórico local começou do zero durante uma reorganização grande: os
arquivos do gate_1 (que originalmente estavam soltos na raiz do repo, num
layout `scripts/`+`dados/` só) foram movidos para a estrutura
`gate_1/` / `shared/` acima, e os caminhos de arquivo dentro de cada script
foram atualizados junto. Se o remoto compartilhado ainda tiver o layout
antigo (ou alguém tiver trabalhado em cima dele em paralelo), espere:

- **Conflitos de "modificado aqui, deletado lá"** nos scripts que existiam
  no layout antigo (`scripts/mapa_paises.py`, `scripts/step3_filtro_municipios.py`
  etc.) — o git pode não detectar automaticamente que o arquivo só mudou de
  pasta, principalmente porque o conteúdo também mudou (os caminhos internos
  foram reescritos).
- **Arquivos de dados brutos/processados não vão conflitar de verdade** —
  a maioria está fora do controle de versão dos dois lados, então o pior
  caso é só precisar rodar os scripts de novo pra regerar o que faltar.
- **Antes de fazer push ou merge**: rode `git fetch` e dê uma olhada em
  `git log --oneline --all` e `git diff` contra o remoto **antes** de
  resolver qualquer conflito às pressas — a reorganização é grande o
  suficiente pra valer a pena revisar arquivo por arquivo, não só aceitar
  "ours"/"theirs" no automático.
