# Reidentificação de importadores em base anonimizada da Receita Federal

## 1. Objetivo

A base `dados/raw/base_1.parquet` traz 57.846 registros de importação (ano de 2021)
com o importador anonimizado (`numero_de_ordem` é um hash). O objetivo era estimar
**50 CNPJs candidatos** a serem os importadores por trás dessa base, documentar o
método e apontar como a Receita/MDIC podem evitar que esse tipo de reidentificação
seja feito por terceiros.

**Resultado**: `palpites_cnpj_top50.csv` (50 linhas: grupo interno, CNPJ raiz de 8
dígitos, razão social e um nível de confiança `alta`/`media`/`baixa`).

## 2. A base é de uma empresa só ou de várias?

Tratamos a base inteira como um "grupo" único e comparamos o perfil agregado
(mês x SH4 x país) contra as estatísticas de importação por município do Comex
Stat (`scripts/step4_base_unica.py`). Nenhum município cobriu mais que **41%**
das combinações declaradas — ou seja, **não existe um único município (logo,
não existe uma única empresa) que explique a base inteira**. A base reúne
declarações de importação de **milhares de empresas diferentes**, a maioria
aparecendo só uma ou poucas vezes (mediana de 1 transação por grupo depois da
clusterização).

## 3. Metodologia

### 3.1 Clusterizar registros do mesmo provável importador (`nb.ipynb`)

Empresas e despachantes aduaneiros reaproveitam o mesmo estilo de texto nas
declarações. Agrupamos por similaridade textual:

1. TF-IDF de caracteres (`analyzer="char_wb"`, n-gramas 3-5) sobre as descrições
   únicas em minúsculo.
2. `TruncatedSVD(100)` + normalização L2 (aproxima cosseno por distância
   euclidiana).
3. `HDBSCAN(min_cluster_size=5, min_samples=3)` -> `cluster_txt`.
4. União dos clusters de texto que compartilham `numero_de_ordem` via
   `scipy.sparse.csgraph.connected_components` (ruído vira nó próprio) -> `grupo`.

Resultado: **28.265 grupos** (prováveis importadores/despachantes distintos).

### 3.2 Achar municípios candidatos por grupo (`scripts/step3_filtro_municipios.py`)

Para cada grupo, agregamos (mês, SH4, país) -> soma de valor FOB e peso líquido,
e cruzamos com `IMP_2021_MUN.csv` (Comex Stat, importação por município). Um
município "bate" com o grupo se cobre pelo menos 90% das combinações do grupo
dentro de 2% de tolerância em valor e peso.

Duas armadilhas resolvidas nesse passo:
- **`anomes` tem hífen** (`"2021-08"`, não `"202108"` como a doc original
  dizia) — quebrava a extração do mês.
- **O código de município do Comex Stat nem sempre é o código IBGE real**: a
  própria tabela oficial do governo (`UF_MUN.csv`) lista São Paulo como
  `3450308`, quando o código IBGE de fato é `3550308`. Cruzar municípios só por
  código teria descartado silenciosamente ~17 mil registros (a maior cidade do
  país). Corrigido casando por **nome + UF normalizados**
  (`scripts/mapa_municipios.py`), com fallback fuzzy (rapidfuzz) para variações
  de grafia.

Sem o país como filtro, quase todo grupo grande já colapsa para 1-4 municípios
candidatos com 100% de cobertura. Com o país (`scripts/mapa_paises.py`, que
casa os 129 nomes de país da base contra a tabela oficial `PAIS.csv` do Comex
Stat, com fallback fuzzy) o filtro fica ainda mais discriminativo.

### 3.3 CNPJs candidatos por município (`scripts/baixar_filtrar_estabelecimentos.py`, `baixar_filtrar_empresas.py`)

O MDIC costumava publicar uma lista de empresas exportadoras/importadoras
(CNPJ + razão social + município), mas **descontinuou essa publicação em 2023**
depois de reconhecer, em nota oficial, que cruzá-la com as estatísticas por
município permite reidentificar CNPJ, país e produto de uma empresa — **o
mesmo ataque que este projeto reproduz** (ver seção 5). Sem esse atalho, os
candidatos vêm direto da base pública de CNPJ da Receita Federal
(`dados.gov.br`, ~5GB comprimidos entre `Estabelecimentos` e `Empresas`),
filtrada para manter só estabelecimentos **ativos** nos municípios candidatos
do passo 3.4 (crosswalk código de município Comex -> código TOM usado pela
Receita, via tabela oficial `municipios.csv` da Receita +
`tom_ibge_municipios.csv`).

### 3.4 Score e ranking (`scripts/step6_score_final.py`)

Para cada grupo com pelo menos 3 transações e no máximo 5 municípios
candidatos (~1.223 grupos; grupos menores não têm perfil confiável o
bastante e foram descartados do ranking):

1. Extraímos palavras-chave da descrição do produto do grupo, ponderadas por
   **raridade no resto da base** (`local_count / global_document_frequency`,
   um TF-IDF simplificado) — isso evita que jargão genérico de declaração
   aduaneira ("nome comercial", "marca", "lote", "forma", "matéria-prima")
   vire "palavra-chave", já que aparece em quase toda descrição e não
   discrimina nada.
2. Pré-filtramos os candidatos daquele(s) município(s) por substring
   (`str.contains` vetorizado) contendo alguma palavra-chave — necessário
   porque São Paulo sozinho tem 2,7 milhões de estabelecimentos ativos, e
   rodar fuzzy match completo pra cada grupo contra todos eles é inviável
   (bilhões de comparações).
3. Só então rodamos `rapidfuzz.fuzz.token_set_ratio` entre razão
   social+nome fantasia e as palavras-chave, nos poucos candidatos que
   sobraram do filtro.
4. Score final = `0.5 * cobertura_município + 0.4 * fuzzy_score + 0.1 * min(n_transações/500, 1)`.

O nível de confiança (`alta`/`media`/`baixa`) reflete quantas palavras-chave
específicas bateram e quantos candidatos concorrentes existiam no
pré-filtro — **não é uma garantia**, é só uma indicação de o quanto o sinal
textual foi específico vs. genérico.

## 4. Limitações (leia antes de usar os 50 CNPJs)

- **Heurística, não prova.** Um match fuzzy alto entre a descrição do produto
  e a razão social é evidência circunstancial, não confirmação.
  "SCP CREDITO LINHA VERDE" bater com a palavra "VERDE" é um exemplo de falso
  positivo provável — "verde" é comum demais mesmo depois da ponderação por
  raridade.
- **Cobertura de método, não de universo**: só rodamos o score nos ~1.223
  grupos com poucas transações candidatas e poucos municípios candidatos
  (o subconjunto onde a heurística é tratável computacionalmente). A base
  tem 28 mil grupos; a maioria (mediana 1 transação) não tem perfil
  suficiente para gerar um palpite confiável.
- **Ano único (2021)**: a base só cobre 2021, então o cruzamento com Comex
  Stat também usou só `IMP_2021_MUN.csv`.
- **~10% dos grupos** não bateram com nenhum município no filtro do passo 3
  (perfil não compatível com as estatísticas públicas, ex. combinações
  raras de mês/SH4/país).

## 5. Como evitar que outros façam a mesma coisa

Isto não é hipotético: o **próprio MDIC já documentou esse vetor de ataque**
em nota oficial de março de 2023 (`Nota-sobre-lista-de-exportadores-e-importadores.pdf`,
balanca.economia.gov.br) e agiu sobre ele — descontinuou a publicação da lista
de empresas exportadoras/importadoras exatamente porque cruzá-la com as
estatísticas por município permitia revelar valor, país parceiro e produto
ao nível de CNPJ, violando o sigilo fiscal do Art. 2º da Portaria RFB
nº 2.344/2011.

Recomendações concretas pra quem publica microdados de comércio exterior
(ou qualquer base "anonimizada" cruzável com dados públicos granulares):

1. **Nunca publicar duas granularidades complementares ao mesmo tempo.**
   Se existe uma estatística pública por município (ou qualquer corte fino
   o bastante pra ser quase único), uma lista de "quem está em cada
   município" não pode ser pública também — a interseção das duas
   reidentifica. Foi exatamente a decisão que o MDIC tomou.
2. **Não deixar a descrição do produto livre.** A maior fonte de vazamento
   nesta base não foi o cruzamento de município — foi a **descrição do
   produto conter o nome da marca/empresa** ("PERFUME PARIS", "EDITORA FTD",
   "FREIOS UNIAO"). Um campo de texto livre além do código NCM estruturado
   reintroduz o identificador que a anonimização tentou remover. Usar um
   dicionário controlado de descrições por NCM, ou truncar/generalizar o
   texto livre, elimina essa classe inteira de vazamento.
3. **k-anonimato explícito no nível de publicação**: antes de publicar um
   agregado (por município, por cluster de texto, etc.), checar se pelo
   menos *k* empresas distintas contribuem para aquela célula — células com
   1-2 contribuintes deveriam ser suprimidas ou agregadas com uma vizinha.
4. **Ruído/arredondamento em campos numéricos de alta cardinalidade**
   (peso líquido e valor FOB com muitas casas decimais, como visto na base,
   são quase um identificador por si só quando cruzados com outra fonte que
   tenha o mesmo valor exato).
5. **Não reciclar hashes estáveis** (`numero_de_ordem`) sem rotacioná-los
   por publicação/período — um hash estável permite ligar registros da
   mesma empresa ao longo do tempo, que é exatamente o que possibilitou a
   clusterização neste projeto.

## 6. Reprodução

O repositório é dividido em `gate_1/` (este gate), `gate_2/` (a base de 23,2M
linhas) e `shared/` (infraestrutura reutilizada pelos dois: tabelas de
referência do Brasil e a base nacional de CNPJ da Receita). Todos os scripts
assumem que são executados a partir da raiz do repositório.

```
shared/
  dados/raw/            PAIS.csv, UF_MUN.csv, tom_ibge_municipios.csv, IMP_2021_MUN.csv, cnpj/
  dados/processado/     crosswalks de pais/municipio + candidatos de CNPJ (Estabelecimentos/Empresas)
  scripts/
    mapa_paises.py                       pais_de_origem -> CO_PAIS (Comex Stat)
    mapa_municipios.py                   CO_MUN (Comex) -> CO_MUNICIPIO (TOM/Receita)
    baixar_filtrar_estabelecimentos.py   baixa+filtra Estabelecimentos da Receita
    baixar_filtrar_empresas.py           baixa+filtra Empresas da Receita

gate_1/
  dados/raw/            base_1.parquet
  dados/processado/     df_clusterizado.parquet, candidatos_municipio_por_grupo.parquet, palpites_cnpj.parquet
  scripts/
    step3_filtro_municipios.py           municipios candidatos por grupo
    step4_base_unica.py                  testa a hipotese de empresa unica
    step6_score_final.py                 score final e top 50 -> gate_1/palpites_cnpj_top50.csv
  palpites_cnpj_top50.csv                resultado final
```

Ordem de execução: a clusterização de texto original (passo 3.1, que gera
`gate_1/dados/processado/df_clusterizado.parquet`) foi feita num notebook que
não faz mais parte do repositório -- o parquet gerado por ela é o
pré-requisito de tudo abaixo. A partir dele: `step3_filtro_municipios.py` ->
`step4_base_unica.py` (opcional, só diagnóstico) ->
`shared/scripts/baixar_filtrar_estabelecimentos.py` ->
`shared/scripts/baixar_filtrar_empresas.py` -> `step6_score_final.py`.
