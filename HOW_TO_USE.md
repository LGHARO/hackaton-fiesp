# Como usar este repositório (HOW_TO_USE)

Guia prático para **rodar os pipelines do zero**: o que instalar, quais dados baixar (e de onde), onde colocar cada arquivo e em que ordem executar. Para entender *o que* cada método faz e *por quê*, veja o [`README.md`](README.md) e os relatórios ([`gate_1/RELATORIO.md`](gate_1/RELATORIO.md), [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md)).

> **Status de verificação deste guia.** Foi escrito a partir da leitura dos scripts. Conferi as URLs públicas nas páginas oficiais, executei os testes unitários do pipeline de ML e testei o trecho de verificação cruzada (§5.6). **Não executei** os pipelines com as bases reais nem os downloads de dentro do ambiente de revisão — se algum comando falhar aí na sua máquina, veja a §8 e avise o time para corrigirmos aqui.

---

## 1. Qual pipeline gera qual entrega

| Base | Pasta / scripts | Entrega | Formato do CNPJ |
|---|---|---|---|
| **Base 1** (57.846 linhas) | `gate_1/scripts/` | `gate_1/palpites_cnpj_top50.csv` | raiz, 8 dígitos (`cnpj_basico`) |
| **Base 2** (23,2 mi, **sem** descrição) | `gate_2/scripts_sem_descricao/` | `gate_2/palpites_base2_top50.csv` | 14 dígitos + `chave_item` |
| **Base 3** (23,2 mi, **com** descrição) | `gate_2/scripts/` | `gate_2/palpites_cnpj_top50_final.csv` | raiz, 8 dígitos (`cnpj_basico`) |
| Abordagem de ML (independente) | `src/`, `main.py` | `outputs/` (não versionado) | 14 dígitos formatados |

Regras do enunciado do Gate 2: até **50 palpites por base**, bases **independentes** (não cruzar uma com a outra no método) e **nenhum CNPJ repetido** entre as Bases 1, 2 e 3 — conferência na §5.6.

---

## 2. Pré-requisitos

- **Python 3.14** (definido em `.python-version` e `pyproject.toml`) e o gerenciador [`uv`](https://docs.astral.sh/uv/).
- **Máquina de referência**: os comentários do `01_cluster_texto.py` registram que a clusterização da Base 3 foi feita com **16 GB de RAM**, por isso roda com `N_WORKERS = 1` (mais workers estouraram a memória).
- **Disco**: os scripts de CNPJ baixam um `.zip` de 2–4 GB por vez e apagam depois de filtrar; some a isso as bases do hackathon e os intermediários em `dados/processado/`.
- **Sempre execute os scripts a partir da raiz do repositório** — todos os caminhos são relativos a ela.

```bash
uv sync                 # instala as dependências do pyproject.toml / uv.lock
```

> O `uv sync` cobre os pipelines de `gate_1/`, `gate_2/` e `shared/`. **Não** cobre o pipeline de ML (`src/`): ele precisa de `pyyaml` e `sentence-transformers`/`torch`, que não estão no `pyproject.toml` (ver §6).

---

## 3. O que vai (e o que não vai) para o GitHub

O `.gitignore` do projeto **exclui**: qualquer pasta `dados/`, todo `*.parquet` (com exceções explícitas para os arquivos de entrega e para as referências pequenas de `data/`), `*.log`, `outputs/*`, `data/raw/IMP_*.csv` e `dados_tabela_exportacoes_importacoes.csv`.

| Item | Vai pro GitHub? | Observação |
|---|---|---|
| Bases do hackathon (`gate_*/dados/raw/…`) | **Não** | Privadas (fornecidas pela organização). Já ignoradas por estarem em `dados/`. |
| Dados públicos baixados (`shared/dados/raw/…`) | **Não** | Reproduzíveis pelos links da §4.2. |
| Intermediários (`*/dados/processado/…`) | **Não** | Grandes e reproduzíveis. |
| Palpites: `gate_1/palpites_cnpj_top50.parquet`, `gate_2/palpites_cnpj_top50.parquet`, `gate_2/palpites_cnpj_top50_final.parquet` | Sim | Exceções explícitas no `.gitignore`. Os `.csv` correspondentes nunca foram ignorados. |
| `gate_2/palpites_base2_top50.csv` e `gate_2/palpites_base2_top50_detalhado.parquet` | Sim | Ambos têm exceção explícita no `.gitignore` (verificado com `git add -n`). **O CSV não está no snapshot atual da branch:** é gerado pelo script 03 da Base 2 e precisa ser commitado depois de rodar. |
| `data/reference/comexstat_2021_ncm_uf.parquet`, `data/processed/cnaes_embeddings.npy` | Sim | Referências do pipeline de ML, com exceção explícita. |
| Logs de execução | **Não** (por padrão) | `*.log` está ignorado. Salve como `.txt` ou adicione `!gate_2/logs/*.log` (ver §7). |
| Referências pequenas (`data/reference/…`, `br_bd_…mercosul.csv`) | Sim | Já versionadas. |

---

## 4. Dados: o que baixar e onde colocar

### 4.1 Bases do hackathon (privadas — vêm da organização)

| Base | Caminho esperado | Colunas usadas pelos scripts |
|---|---|---|
| Base 1 | `gate_1/dados/raw/base_1.parquet` | `numero_de_ordem`, `anomes`, `cod_ncm`, `pais_de_origem`, `descricao_do_produto`, `peso_liquido`, `vmle_dolar` |
| Base 3 (com descrição) | `gate_2/dados/raw/dados_siscori.pq/*.parquet` | `chave_item`, `descricao`, `ncm`, `pais_origem`, `periodo` |
| Base 2 (sem descrição) | `gate_2/dados/raw/dados_siscori_sem_desc.pq/*.parquet` | `chave_item`, `ncm`, `pais_origem`, `periodo`, `vmle_dolar`, `peso_liquido` (lidos como texto; vírgula decimal é tratada) |

> As colunas acima foram deduzidas das consultas dos scripts; confira com o arquivo real caso um script reclame de coluna ausente.

### 4.2 Dados públicos

Os links abaixo foram conferidos nas páginas oficiais em 29/09/2026. Crie as pastas e baixe:

```bash
mkdir -p shared/dados/raw/cnpj

# Comex Stat (MDIC) — importação por município × SH4, ano 2021
curl -L -o shared/dados/raw/IMP_2021_MUN.csv \
  https://balanca.mdic.gov.br/balanca/bd/comexstat-bd/mun/IMP_2021_MUN.csv

# Tabelas auxiliares do Comex Stat (países e municípios)
curl -L -o shared/dados/raw/PAIS.csv    https://balanca.mdic.gov.br/balanca/bd/tabelas/PAIS.csv
curl -L -o shared/dados/raw/UF_MUN.csv  https://balanca.mdic.gov.br/balanca/bd/tabelas/UF_MUN.csv

# Tabela de municípios da Receita (código TOM x IBGE) — vira tom_ibge_municipios.csv
curl -L -o shared/dados/raw/tom_ibge_municipios.csv \
  https://www.gov.br/receitafederal/dados/municipios.csv
```

| Arquivo | Fonte oficial | Usado por |
|---|---|---|
| `IMP_2021_MUN.csv` (`;`, latin-1, layout `CO_ANO;CO_MES;SH4;CO_PAIS;SG_UF_MUN;CO_MUN;KG_LIQUIDO;VL_FOB`) | [Base de dados bruta — MDIC](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta) (seção "Município… Importação") | Gate 1, Base 2, Base 3 |
| `PAIS.csv`, `UF_MUN.csv` | Mesma página, seção "Tabelas de Correlações" | mapeamento de país e município |
| `tom_ibge_municipios.csv` | [Tabela de municípios — Receita Federal](https://www.gov.br/receitafederal/dados/municipios.csv) (5 colunas: TOM, IBGE, nome TOM, nome IBGE, UF) | crosswalk de município; stopwords do score da Base 3 |
| `Estabelecimentos0..9.zip`, `Empresas0..9.zip` | Baixados **automaticamente** pelos scripts de `shared/` | CNPJ candidatos |
| `cnpj/cnaes.csv` | `Cnaes.zip` da mesma pasta dos dados abertos de CNPJ (ver abaixo) | filtro de CNAE não comercial (Base 3) |

**Base de CNPJ (Receita Federal).**
Fonte oficial: [arquivos.receitafederal.gov.br](https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9) (catálogo em [dados.gov.br](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj); layout dos campos em [cnpj-metadados.pdf](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf)).
Os scripts de `shared/scripts/` **não** usam a fonte oficial: baixam de um **espelho de terceiros** (Casa dos Dados), com a data do snapshot fixa na constante `BASE`:

```
https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2026-09-14
```

Consequências: (1) o snapshot é de **14/09/2026**, não de 2021; (2) se o espelho remover essa pasta, os downloads falham com 404 — troque a data em `BASE` nos dois scripts (`baixar_filtrar_estabelecimentos.py` e `baixar_filtrar_empresas.py`) ou baixe os `.zip` na fonte oficial e coloque em `shared/dados/raw/cnpj/`. Registre no relatório qual snapshot foi usado.

**`cnaes.csv`** — o `04_score_final.py` da Base 3 espera um CSV **com cabeçalho** `CO_CNAE,DESCRICAO`, mas o `Cnaes.zip` da Receita vem sem cabeçalho, separado por `;`. Converta:

```python
import pandas as pd
df = pd.read_csv("Cnaes.zip", sep=";", header=None, names=["CO_CNAE", "DESCRICAO"],
                 dtype=str, encoding="latin1")
df.to_csv("shared/dados/raw/cnpj/cnaes.csv", index=False)
```

### 4.3 Lacunas do repositório (leia antes de tentar reproduzir do zero)

Três peças de que os scripts dependem **não estão versionadas**:

1. **`gate_1/dados/processado/df_clusterizado.parquet`** — saída da clusterização de texto do Gate 1, feita num notebook (`nb.ipynb`) que não faz mais parte do repo (o `gate_1/RELATORIO.md` já registra isso). Sem ele, `step3`, `step4`, `step6` e o `mapa_paises.py` (modo `__main__`) não rodam. Peça o arquivo (ou o notebook) a quem fez o Gate 1.
2. **O passo entre `step3` e os downloads de CNPJ.** `step3_filtro_municipios.py` grava `candidatos_municipio_por_grupo.parquet` **sem** a coluna `CO_TOM_STR`, mas `baixar_filtrar_estabelecimentos.py` e `step6_score_final.py` a exigem (a numeração dos scripts pula do 3 para o 4 e do 4 para o 6, o que sugere um passo removido). Contorno provável — *reconstrução minha, não o script original; valide com o autor*:

   ```python
   import pandas as pd
   c  = pd.read_parquet("gate_1/dados/processado/candidatos_municipio_por_grupo.parquet")
   cw = pd.read_parquet("shared/dados/processado/crosswalk_mun_comex_tom.parquet")  # ver §5.1
   c["CO_MUN"], cw["CO_MUN"] = c["CO_MUN"].astype(int), cw["CO_MUN"].astype(int)
   c = c.merge(cw[["CO_MUN", "CO_TOM_STR"]], on="CO_MUN", how="left")
   c.to_parquet("gate_1/dados/processado/candidatos_municipio_por_grupo.parquet", index=False)
   ```
3. **`gate_2/scripts/02_*.py`** — a numeração da Base 3 pula do 01 para o 03. Nada nos scripts seguintes lê uma saída do "02", então provavelmente é só um passo descartado, mas vale confirmar com o autor.

> **Atenção à cobertura da Base 2 e da Base 3.** `estabelecimentos_candidatos.parquet` é filtrado **apenas pelos municípios candidatos do Gate 1** (`alvo_municipios()`). Municípios que aparecem só nas Bases 2 ou 3 ficam fora do universo de CNPJs — nas duas etapas seguintes eles somem silenciosamente nos `join`s. Se a execução final precisar cobrir todos os municípios das Bases 2 e 3, inclua no `alvo_municipios()` também os `co_tom` de `gate_2/dados/processado/linhas_diagnosticas.parquet` (Base 3) e de `gate_2/dados/processado_sem_desc/matches_aduaneiros_exatos.parquet` (Base 2) e refaça os passos de `shared/`.

### 4.4 Estrutura esperada de pastas

```
gate_1/dados/raw/base_1.parquet                       # privada
gate_1/dados/processado/df_clusterizado.parquet       # gerada fora do repo
gate_2/dados/raw/dados_siscori.pq/*.parquet           # Base 3, privada
gate_2/dados/raw/dados_siscori_sem_desc.pq/*.parquet  # Base 2, privada
shared/dados/raw/
├── IMP_2021_MUN.csv
├── PAIS.csv
├── UF_MUN.csv
├── tom_ibge_municipios.csv
└── cnpj/cnaes.csv          # + Estabelecimentos*.zip / Empresas*.zip (temporários)
```

---

## 5. Execução passo a passo

### 5.1 Preparação comum — crosswalk de municípios

Liga o código de município do Comex Stat ao código TOM da Receita (por nome + UF, com fallback fuzzy). Necessário para as Bases 1, 2 e 3.

```bash
mkdir -p shared/dados/processado
uv run python shared/scripts/mapa_municipios.py
# saída: shared/dados/processado/crosswalk_mun_comex_tom.parquet
```

### 5.2 Base 1 (Gate 1)

```bash
uv run python gate_1/scripts/step3_filtro_municipios.py     # municípios candidatos por grupo
# → aplicar aqui o passo que adiciona CO_TOM_STR (ver §4.3, item 2)
uv run python gate_1/scripts/step4_base_unica.py            # opcional: só diagnóstico
# → rodar a §5.3 (CNPJs filtrados) e voltar
uv run python gate_1/scripts/step6_score_final.py           # → gate_1/palpites_cnpj_top50.csv
```

### 5.3 CNPJs candidatos (compartilhado pelas três bases)

Roda **uma vez**. Cada script é retomável (pula as partes já processadas).

```bash
uv run python shared/scripts/baixar_filtrar_estabelecimentos.py   # 10 zips; mantém só ATIVOS nos municípios-alvo
uv run python shared/scripts/baixar_filtrar_empresas.py           # 10 zips; razão social dos CNPJs candidatos
# saídas: shared/dados/processado/estabelecimentos_candidatos.parquet
#         shared/dados/processado/empresas_candidatas.parquet
```

### 5.4 Base 3 (com descrição) — `gate_2/scripts/`

```bash
uv run python gate_2/scripts/01_cluster_texto.py            # HORAS; retomável; grava partes em cluster_parts/
uv run python gate_2/scripts/progresso.py                   # (outro terminal) % e ETA da clusterização
uv run python gate_2/scripts/03_concentracao_municipio.py   # sinal principal: concentração geográfica
uv run python gate_2/scripts/04_score_final.py              # → gate_2/palpites_cnpj_top50.csv (versão preliminar)
uv run python gate_2/scripts/05_cruzamento_sinais.py        # → gate_2/palpites_cnpj_top50_final.csv (entrega)
```

Dependências entre os passos: `03` precisa do crosswalk (§5.1); `04` precisa de `03`, do `shared/` (§5.3), de `tom_ibge_municipios.csv` e de `cnpj/cnaes.csv`; `05` precisa de `01`, `03` e `04`. O `progresso.py` tem `TOTAL_BLOCOS = 5756` fixo — ajuste se a base mudar.

### 5.5 Base 2 (sem descrição) — `gate_2/scripts_sem_descricao/`

```bash
uv run python gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py     # → processado_sem_desc/matches_aduaneiros_exatos.parquet
uv run python gate_2/scripts_sem_descricao/02_monopolio_municipal.py        # → processado_sem_desc/empresas_candidatas_tratadas.parquet
uv run python gate_2/scripts_sem_descricao/03_gerar_top50_base2.py          # → gate_2/palpites_base2_top50.csv (+ _detalhado.parquet)
uv run python gate_2/scripts_sem_descricao/04_validacao_final_independente.py   # auditoria e reescrita do mesmo CSV
```

Pré-requisitos: base 2 no caminho da §4.1, crosswalk (§5.1) e `shared/` processado (§5.3). Metodologia e limitações: [`gate_2/RELATORIO.md`](gate_2/RELATORIO.md) §4 e [`README_BASE2.md`](gate_2/scripts_sem_descricao/README_BASE2.md).

> **O que o `04_validacao_final_independente.py` realmente confere hoje** (leia antes de confiar no "zero colisões"): ele procura `gate_1/palpites_cnpj.csv`, arquivo que **não existe** no repo (o do Gate 1 é `gate_1/palpites_cnpj_top50.csv`, coluna `cnpj_basico`) — nesse caso a checagem do Gate 1 é **pulada sem erro**. Para a Base 3, o arquivo tem `cnpj_basico` (8 dígitos) e não `CNPJ`, então o script só imprime um aviso de raiz repetida e **não remove nem substitui** nada. Use a verificação da §5.6.

### 5.6 Verificação cruzada final (rodar antes de entregar)

Confere: 50 linhas por base, raízes únicas por base, **nenhuma raiz repetida entre Bases 1, 2 e 3** e dígitos verificadores dos CNPJs de 14 dígitos. Compara pela **raiz de 8 dígitos** (critério mais conservador que comparar os 14). Salve como `checar_cruzamento.py` na raiz e rode `uv run python checar_cruzamento.py`. (Testado com os arquivos atuais das Bases 1 e 3 e com uma Base 2 sintética que continha uma colisão e um dígito verificador inválido.)

```python
import pandas as pd

ARQUIVOS = {  # base -> (caminho, coluna do CNPJ)
    "Base 1": ("gate_1/palpites_cnpj_top50.csv", "cnpj_basico"),
    "Base 2": ("gate_2/palpites_base2_top50.csv", "CNPJ"),
    "Base 3": ("gate_2/palpites_cnpj_top50_final.csv", "cnpj_basico"),
}

def digitos(s):
    return s.astype(str).str.replace(r"\D", "", regex=True)

def dv_ok(cnpj14):
    if len(cnpj14) != 14:
        return False
    def dv(base, pesos):
        r = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return 0 if r < 2 else 11 - r
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(cnpj14[:12], p1)
    d2 = dv(cnpj14[:12] + str(d1), [6] + p1)
    return cnpj14[12:] == f"{d1}{d2}"

raizes = {}
for base, (caminho, col) in ARQUIVOS.items():
    try:
        df = pd.read_csv(caminho, dtype=str)
    except FileNotFoundError:
        print(f"[{base}] arquivo não encontrado: {caminho} (pulando)")
        continue
    d = digitos(df[col])
    raiz = d.str[:8] if d.str.len().max() >= 14 else d.str.zfill(8)
    raizes[base] = set(raiz)
    print(f"[{base}] linhas={len(df)} raízes únicas={raiz.nunique()}"
          + ("" if len(df) <= 50 else "  <-- MAIS DE 50 LINHAS"))
    if d.str.len().max() >= 14:
        print(f"[{base}] CNPJs com dígito verificador inválido: {(~d.map(dv_ok)).sum()} de {len(d)}")

bases = list(raizes)
for i in range(len(bases)):
    for j in range(i + 1, len(bases)):
        comuns = raizes[bases[i]] & raizes[bases[j]]
        print(f"{bases[i]} x {bases[j]}: {len(comuns)} raiz(es) em comum", sorted(comuns) if comuns else "")
```

Lembre que "linhas = 50" com "raízes únicas < 50" significa que o mesmo CNPJ foi entregue mais de uma vez dentro da própria base.

---

## 6. Pipeline de ML (opcional, independente)

Descrição completa em [`README_PIPELINE_ML.md`](README_PIPELINE_ML.md). Resumo para rodar:

```bash
# dependências que o pyproject NÃO declara (uso sem alterar o pyproject):
uv run --with pyyaml --with sentence-transformers --with torch python main.py --mode sample
uv run --with pyyaml --with sentence-transformers --with torch python main.py --mode all

# testes unitários (não precisam de torch nem de sentence-transformers):
uv run --with pyyaml python -m unittest tests.test_pipeline -v
```

Para tornar isso permanente: `uv add pyyaml sentence-transformers torch`.

Dados: `data/raw/operacoes_sample.csv` (sintético, versionado), `data/reference/cnae_referencia.csv` (versionado; regenerável com `scripts/fetch_cnae_ibge.py`) e `data/reference/comexstat_2021_ncm_uf.parquet` (versionado; regenerável com `scripts/fetch_comex_stat.py`). A etapa `retrieve` exige ainda `dados_tabela_exportacoes_importacoes.csv` na raiz (não versionado — ver o README do pipeline de ML para o esquema esperado).

---

## 7. Logs para a entrega

O enunciado pede **logs** junto com metodologia e scripts. Hoje:

- **Base 3**: os scripts `01`, `04` e `05` registram cada iteração (bloco de NCM, grupo de score, cruzamento) em SQLite via `joblog.py` → `gate_2/dados/processado/jobs.sqlite` (pasta ignorada pelo git). Exporte um resumo versionável:

  ```bash
  mkdir -p gate_2/logs
  sqlite3 -header -csv gate_2/dados/processado/jobs.sqlite \
    "select job, status, count(*) as n, round(avg(duracao_s),2) as dur_media_s,
            min(started_at) as inicio, max(finished_at) as fim
     from iteracoes group by job, status" > gate_2/logs/base3_resumo_jobs.csv
  ```
  (Sem o CLI `sqlite3`: `pandas.read_sql` sobre `jobs.sqlite` produz a mesma tabela.)
- **Base 2**: os scripts só imprimem no terminal. Capture a saída ao rodar:

  ```bash
  # bash / Git Bash
  uv run python gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py 2>&1 | tee gate_2/logs/base2_01_reconciliacao.txt
  ```
  ```powershell
  # PowerShell
  uv run python gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py 2>&1 | Tee-Object gate_2/logs/base2_01_reconciliacao.txt
  ```
  Repita para `02`, `03` e `04`. Use extensão `.txt` (ou libere `*.log` no `.gitignore`), senão o log não sobe para o GitHub.

---

## 8. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `FileNotFoundError: shared/dados/...` | Script rodado fora da raiz ou dado não baixado | Rode da raiz; confira a §4.4 |
| `KeyError: 'CO_TOM_STR'` em `baixar_filtrar_estabelecimentos.py` / `step6` | Passo ausente entre `step3` e os downloads | §4.3, item 2 |
| Download de CNPJ retorna 404 | Espelho removeu a pasta da data fixa em `BASE` | Trocar `BASE` ou baixar da fonte oficial (§4.2) |
| `ModuleNotFoundError: yaml` / `sentence_transformers` | Dependências do ML fora do `pyproject.toml` | §6 |
| Estouro de memória na clusterização (Base 3) | Blocos grandes de NCM (até ~257 mil descrições únicas) | Manter `N_WORKERS = 1`; fechar outros programas; o script retoma de onde parou |
| Caracteres estranhos (`Ã­`, `Ã¢`) nas mensagens dos scripts da Base 2 | Arquivos salvos com BOM/codificação mista | Só afeta o texto impresso; não altera os resultados |
| `Mês`/`anomes` não casa | O `anomes` da Base 1 usa hífen (`2021-08`) | Já tratado em `step3`; não reformatar a base |
| Planilha corrompida ao abrir `IMP_2021_MUN.csv` | Arquivo grande, separador `;`, latin-1 | Não abrir no Excel; use os scripts |

---

## 9. Fontes citadas

- MDIC — Base de dados bruta do Comex Stat e tabelas auxiliares: <https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta>
- Receita Federal — Dados abertos do CNPJ: <https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9> · catálogo: <https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj> · layout: <https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf>
- Receita Federal — Tabela de municípios (TOM × IBGE): <https://www.gov.br/receitafederal/dados/municipios.csv>
- Espelho usado pelos scripts (terceiros): <https://dados-abertos-rf-cnpj.casadosdados.com.br/>
- IBGE — API de CNAE (usada por `scripts/fetch_cnae_ibge.py`): <https://servicodados.ibge.gov.br/api/v2/cnae/>
