# Gate 2 — reidentificação em escala (Bases 2 e 3, 23,2 milhões de linhas cada)

## 1. Escopo e resumo

O Gate 2 trabalha com **duas bases independentes de 23,2 milhões de registros de importação**, com o importador anonimizado. O objetivo continua sendo reidentificar importadores pelo CNPJ. A entrega é: até 50 palpites para a Base 2 + até 50 para a Base 3, este relatório (metodologia, fontes, logs e scripts) e um plano de mitigação das vulnerabilidades encontradas. As duas bases não são cruzadas entre si no método, e nenhum CNPJ pode se repetir entre os palpites das Bases 1, 2 e 3.

**Nomenclatura.** Seguimos a adotada pela equipe: a base **com** descrição do produto é a **Base 3**; a base **sem** descrição (campo textual suprimido) é a **Base 2**.

| | Base 3 (com descrição) | Base 2 (sem descrição) |
|---|---|---|
| Pasta dos scripts | `gate_2/scripts/` | `gate_2/scripts_sem_descricao/` |
| Sinal principal | Concentração geográfica pública (Comex Stat) | Reconciliação exata de valor FOB e peso líquido com o Comex Stat |
| Sinal para escolher o CNPJ | Palavras raras da descrição × razão social / nome fantasia | Apenas densidade de empresas no município (não há texto) |
| Sinal de confirmação | Concordância com a clusterização de texto | — |
| Entrega | `gate_2/palpites_cnpj_top50_final.csv` | `gate_2/palpites_base2_top50.csv` |
| Formato do CNPJ | raiz de 8 dígitos (`cnpj_basico`) | 14 dígitos + `chave_item` |

Este pipeline não usa o pipeline de ML de `src/` (ver `README_PIPELINE_ML.md`): ele é uma abordagem independente.

**Como reproduzir:** [`HOW_TO_USE.md`](../HOW_TO_USE.md). **Vulnerabilidades e mitigação:** seção 7.

---

## 2. Fontes de dados

| Fonte | O que fornece | Base(s) | Acesso |
|---|---|---|---|
| Bases do hackathon (`dados_siscori.pq`, `dados_siscori_sem_desc.pq`) | Operações de importação anonimizadas | 3 e 2 | Privado (organização) |
| Comex Stat / MDIC — `IMP_2021_MUN.csv` | Importação 2021 por município do importador × SH4 × país × mês (valor FOB e peso líquido) | 2 e 3 | Público — [base de dados bruta](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta) |
| Comex Stat / MDIC — `PAIS.csv`, `UF_MUN.csv` | Tabelas de correlação de país e município | 2 e 3 | Público (mesma página) |
| Receita Federal — dados abertos do CNPJ (Estabelecimentos, Empresas, Cnaes) | Estabelecimentos ativos, razão social, nome fantasia, CNAE, município (código TOM) | 2 e 3 | Público — [fonte oficial](https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9); os scripts baixam de um espelho de terceiros, **snapshot de 14/09/2026** |
| Receita Federal — tabela de municípios (TOM × IBGE) | Crosswalk de código de município | 2 e 3 | Público — [municipios.csv](https://www.gov.br/receitafederal/dados/municipios.csv) |

Duas ressalvas sobre as fontes: (i) o cadastro de CNPJ é de 2026, enquanto as operações são de 2021 — empresas que existiam em 2021 e fecharam **não estão** no universo de candidatos (só estabelecimentos ativos), e empresas abertas depois **estão**; (ii) o universo de estabelecimentos foi filtrado pelos municípios candidatos do Gate 1 (ver seção 8).

---

## 3. Base 3 (com descrição)

### 3.1 O problema, de novo, mas maior

A base tem 23,2 milhões de registros de importação (jul–dez de 2021), cada um com o importador escondido. O objetivo é o mesmo do primeiro gate: dar 50 palpites de CNPJ de quem provavelmente fez essas importações. Mas ela tem uma diferença que obrigou a repensar o método do zero, não só "rodar a mesma coisa em mais dados".

### 3.2 Por que o método antigo não dava para só escalar

No primeiro gate, cada linha tinha um número de declaração escondido, mas repetido — duas linhas com o mesmo número vinham do mesmo despacho, quase certamente da mesma empresa. Isso funcionava como uma "costura": agrupávamos pelo texto da descrição (empresas repetem o jeito de escrever) e confirmávamos os grupos pelo número de declaração compartilhado. Duas pistas concordando.

Nesta base o número de declaração não existe mais — cada linha é praticamente única. Se clusterizássemos só pelo texto, perderíamos a segunda pista. E, para descrições genéricas ("parafuso M6 aço inox"), empresas diferentes escrevem quase a mesma frase; o risco de juntar empresas distintas num grupo ficou grande demais. Precisávamos de uma fonte de evidência que não dependesse de comparar linhas entre si.

### 3.3 A ideia central: o Brasil já revela isso sozinho

O governo publica, mês a mês, quanto cada município importou de cada tipo de produto, de cada país de origem — sem dizer qual empresa. Isso parece inofensivo, mas, para muitos produtos, a importação é concentrada em portos e polos especializados. Checando diretamente nos dados públicos: **de quase 211 mil combinações de (mês, tipo de produto, país de origem), 41% têm 99% ou mais do total nacional concentrado numa única cidade.**

Para essa fatia, a própria estatística pública já entrega o município. Aplicando na base de 23,2 milhões de linhas, **1,64 milhão delas (7,1%) caíram em combinações desse tipo**, cobrindo 605 municípios diferentes. Esse é o sinal principal da Base 3 (`03_concentracao_municipio.py`; aceita combinações com concentração ≥ 99% e até 3 municípios candidatos).

### 3.4 Do município ao CNPJ: a descrição como desempate

Saber a cidade ainda deixa muitos CNPJs possíveis. Aqui a descrição volta, com papel diferente do Gate 1: em vez de formar grupos, ela **desempata entre os candidatos que já moram naquela cidade** (`04_score_final.py`).

- A unidade de análise é (município, SH4): o município vem do passo anterior e o SH4 evita misturar produtos de empresas diferentes que caem na mesma cidade.
- Dentro de cada grupo com ao menos 3 linhas, procuramos palavras raras em geral (não são jargão aduaneiro), que se repetem ao menos 2 vezes ali — tendem a ser marca, produto de nicho ou termo técnico do ramo da empresa.
- Comparamos essas palavras com razão social e nome fantasia dos estabelecimentos ativos do município (pré-filtro por substring + `rapidfuzz.token_set_ratio`) e escolhemos o melhor casamento.
- **Correção de falsos positivos.** Uma palavra pode ser rara na descrição de produto e comum em nome de empresa ("MINISTÉRIO" quase nunca descreve uma fralda, mas é comum em nome de instituição religiosa). Passamos a checar a raridade dos dois lados e a descartar palavras comuns em qualquer um. Também excluímos, **antes** do casamento, estabelecimentos cujo CNAE é estruturalmente não comercial (condomínio, clube, igreja, escritório de contabilidade, escola, clínica etc.) e nomes de municípios como palavra-chave (indicam origem, não marca).

**Score do grupo:** `0,35 × concentração + 0,45 × fuzzy + 0,20 × min(linhas/100, 1)`. **Confiança:** *alta* se fuzzy ≥ 0,85 e ≥ 3 palavras-chave; *média* se fuzzy ≥ 0,75 e ≥ 2; *baixa* nos demais. A confiança mede a **especificidade do casamento de texto**, não a probabilidade de o CNPJ estar certo.

### 3.5 Uma segunda fonte de confirmação: o texto, como bônus

Mesmo sem poder confiar só nele, o texto vale como checagem independente. Fizemos, em paralelo, a clusterização de texto do Gate 1 nas 23,2 milhões de linhas (`01_cluster_texto.py`): bloqueio por NCM de 8 dígitos (5.756 blocos); TF-IDF de caracteres (3–5) + SVD de 80 componentes; HDBSCAN nos blocos com até 20 mil descrições únicas e MiniBatchKMeans nos maiores (90 blocos concentram mais da metade das linhas).

No cruzamento (`05_cruzamento_sinais.py`), para cada palpite verificamos se as linhas que apontaram para ele também formam, entre si, um cluster de texto coerente (**concordância** = fração das linhas no maior cluster). Se sim, a confiança sobe; se estão espalhadas em vários clusters, é sinal de alerta de que somamos mais de uma empresa sob o mesmo palpite. Isso confirma que as linhas são **consistentes entre si**, não que o CNPJ está **certo**.

### 3.6 Resultado

`gate_2/palpites_cnpj_top50_final.csv` — 50 linhas, com `score_final = score + 0,1 × concordância`. **O ranking ordena primeiro por confiança e só depois por score**: existem apenas 55 grupos de confiança alta/média contra 4.203 de baixa, e sem essa regra os de baixa, inflados pela concordância, expulsavam 48 dos 55 do top 50.

- Distribuição: **3 alta, 41 média, 6 baixa**; concordância média 0,52 (mediana 0,48); os 50 grupos somam 14.093 linhas da base, em 24 municípios (16 deles em `co_tom` 7107 e 9 em `6001`).
- **Stemac S.A. Grupos Geradores** (alta): descrição com "STEMAC" e "GRUPOS GERADORES", fabricante real do ramo; 14 linhas, concordância 57%.
- **Intimissimi Ltda.** (média): a própria marca aparece na descrição.
- **Magnesita Refratários S.A.** (baixa): óxido de magnésio/refratários, matéria-prima do setor da empresa; fuzzy baixo (0,61), mas concordância de 96% em 203 linhas.
- **ASR Cerâmica Ltda.** (baixa): argila caulinítica; 9.532 linhas com concordância ~100%. Com tantas linhas num mesmo (município, SH4), é provável que haja **mais de um importador** por trás — a concordância mostra homogeneidade de produto, não empresa única.
- A versão preliminar (`palpites_cnpj_top50.csv`, sem o cruzamento) traz outros casos, como a **TE Connectivity Brasil**, que não aparece no top 50 final.

### 3.7 Limitações da Base 3

- **Heurística de investigação, não prova.** Reduz milhares de empresas possíveis a uma lista curta e plausível; não é confirmação de quem importou o quê.
- **Falsos positivos por coincidência de palavra ainda acontecem** ("importadora" no nome da própria empresa, por exemplo, passa pelo filtro sem ser distintiva). Vários palpites de confiança média têm razão social genérica.
- **A concentração geográfica cobre uma fatia da base**: sinal forte para 7,1% das linhas. O resto depende mais do texto, que é o sinal mais fraco nesta base.
- **CNPJs repetidos dentro da própria entrega.** Como a unidade é (município, SH4), a mesma empresa pode ganhar mais de um grupo: na versão atual, o top 50 tem **48 raízes distintas** (Talento S/A e MC Revestimentos aparecem duas vezes, em SH4 diferentes). Na prática são 48 palpites independentes.
- **Universo de candidatos** com as ressalvas da seção 2 (cadastro de 2026 × operações de 2021; filtro por municípios do Gate 1).
- **Nota técnica de reprodução:** o processamento foi feito numa máquina de 16 GB, o que obrigou a rodar a clusterização com 1 worker — afetou o tempo, não a qualidade.

---

## 4. Base 2 (sem descrição)

### 4.1 O ataque de balanço aduaneiro (duplo balanço exato)

Sem o campo `descricao`, a clusterização de texto não existe. Mas a base preserva variáveis numéricas contínuas de alta precisão (valor FOB e peso líquido) junto de identificadores categóricos granulares (mês, NCM, país). O Comex Stat publica os totais de FOB e peso por **município do importador × SH4 × país × mês**. A ideia: se uma operação da base é **a única** naquela combinação (mês, SH4, país), o total público do município que a realizou é exatamente o valor dela — e os valores batem.

**Passo 1 — `01_reconciliacao_fob_peso.py`:**
1. Agrega o Comex Stat por (mês, SH4, país, município), somando FOB e peso.
2. Na Base 2, agrupa por (mês, SH4, país) e mantém só as combinações com **exatamente 1 linha** (operações "atômicas").
3. Cruza com o Comex Stat exigindo `|FOB_base − FOB_pub| ≤ 1,0` **e** `|peso_base − peso_pub| ≤ 1,0`.
4. Mantém só os casos em que o cruzamento aponta **um único município** e o crosswalk para o código TOM existe.

Segundo a execução registrada pela equipe (`README_BASE2.md`), isso recuperou **5.516 operações** de forma unívoca, sem nenhum dado textual — cerca de 0,02% das 23,2 milhões de linhas.

### 4.2 Do município ao CNPJ

**Passo 2 — `02_monopolio_municipal.py`:** junta estabelecimentos ativos e razão social (base pública da Receita), padroniza o código TOM em 4 dígitos, monta o CNPJ completo e conta quantas **raízes de CNPJ distintas** há em cada município (`qtd_raizes_no_mun`).

**Passo 3 — `03_gerar_top50_base2.py`:**
1. Restringe-se aos **150 municípios de menor `qtd_raizes_no_mun`** presentes nos matches (evita o produto cartesiano contra todos os estabelecimentos do país).
2. **Score de monopólio relativo:** `score = 1 / qtd_raizes_no_mun`.
3. Desempate por valor FOB da operação, decrescente.
4. Deduplica: no máximo um palpite por raiz de CNPJ e um por `chave_item`.
5. Entrega os 50 primeiros: `gate_2/palpites_base2_top50.csv` (`chave_item`, `CNPJ`) e `palpites_base2_top50_detalhado.parquet`.

**Passo 4 — `04_validacao_final_independente.py`:** padroniza colunas e formato, tenta cruzar contra o Gate 1 e a Base 3, deduplica e reaplica o corte de 50. Ver a seção 5 sobre o alcance real dessa checagem.

O CNPJ completo é montado como **raiz (8 dígitos) + ordem `0001` + dígito verificador `00`** — ou seja, assume que o estabelecimento é a matriz e usa um valor fixo para os dois últimos dígitos.

### 4.3 Limitações da Base 2

- **O município é identificado com boa confiança; a empresa, não.** Nada nos dados distingue as empresas de um mesmo município: o "score de monopólio" é a **densidade** de empresas (1/N), não a probabilidade de acerto. Se o importador for uma das N raízes do município e nenhuma se destacar, cada palpite acerta com chance ≈ 1/N; com N entre 536 e 5.476 (faixa registrada no `README_BASE2.md`), a soma de 1/N nos 50 palpites é **no máximo ≈ 0,09 acerto esperado** sob essa hipótese. Um sinal a mais (por exemplo, compatibilidade entre o CNAE do estabelecimento e o SH4 da operação) é o caminho natural para melhorar isso.
- **Empates resolvidos de forma arbitrária.** Todas as empresas de um mesmo município têm o mesmo score e a mesma operação como candidata; a escolha entre elas depende da ordem interna do banco (o script desliga `preserve_insertion_order`). Duas execuções podem gerar CNPJs diferentes.
- **CNPJ de 14 dígitos com sufixo fixo.** O sufixo `000100` assume matriz e dígitos verificadores `00`; os verificadores reais dependem dos 12 primeiros dígitos. Além disso, o estabelecimento no município pode ser uma filial, e a matriz da mesma raiz pode estar em outra cidade.
- **Cobertura mínima:** só operações em combinação atômica (≈ 0,02% da base) e só nos municípios presentes no universo de CNPJs (seção 2).
- **Universo de candidatos:** cadastro de 2026 (apenas ativos) para operações de 2021.
- **Tolerância de 1,0** em USD e kg: a exigência de município único reduz o risco de falso casamento, mas não o elimina.
- Os números de 5.516 operações e da faixa de 536 a 5.476 empresas por município vêm da execução da equipe; o log correspondente deve acompanhar a entrega (seção 6).

---

## 5. Conformidade entre bases (CNPJs não repetidos)

**Regra:** nenhum CNPJ pode se repetir entre os palpites das Bases 1, 2 e 3, e as bases não são cruzadas no método. Como as Bases 1 e 3 entregam a raiz (8 dígitos) e a Base 2 entrega 14 dígitos, a conferência é feita pela **raiz** — critério mais conservador que comparar os 14 dígitos.

- **Como verificar:** script da seção 5.6 do [`HOW_TO_USE.md`](../HOW_TO_USE.md) — confere 50 linhas por base, raízes únicas, interseções entre as três bases e dígitos verificadores.
- **Alcance real do `04_validacao_final_independente.py`:** procura `gate_1/palpites_cnpj.csv` (o arquivo do Gate 1 é `gate_1/palpites_cnpj_top50.csv`, com `cnpj_basico`), e, se não o encontra, **pula a checagem do Gate 1 sem erro**. Para a Base 3, o arquivo traz `cnpj_basico` e não `CNPJ`, então o script só emite aviso de raiz repetida, sem remover ou substituir nada. Além disso, a comparação com o Gate 1 seria feita sobre 14 dígitos (com zeros à esquerda), o que não detectaria colisão de raiz caso o arquivo traga só 8 dígitos. O "banco de reservas" (`_detalhado.parquet`) contém apenas os mesmos 50 candidatos, então não há de onde repor. A conferência independente da seção 5.6 substitui essa garantia.
- **Estado da verificação (revisão de 29/09/2026):** Base 1 × Base 3 — **0 raízes em comum** (também 0 entre a Base 1 e a versão preliminar da Base 3). Dentro de cada base há raízes repetidas: 46 únicas em 50 linhas na Base 1 e 48 em 50 na Base 3. A Base 2 não pôde ser conferida: `gate_2/palpites_base2_top50.csv` não estava no repositório analisado.

---

## 6. Logs e rastreabilidade

- **Base 3:** `01_cluster_texto.py`, `04_score_final.py` e `05_cruzamento_sinais.py` registram cada iteração (job, item, status, início, fim, duração, nº de linhas, detalhe) em SQLite, via `joblog.py`, em `gate_2/dados/processado/jobs.sqlite`. O `progresso.py` calcula % concluído e ETA da clusterização a partir dele.
- **Base 2:** os scripts só imprimem no terminal; a saída deve ser capturada ao executar (`tee`/`Tee-Object`, ver `HOW_TO_USE.md` §7).
- Os logs da execução final devem ser anexados em `gate_2/logs/` (resumo do SQLite em CSV e as saídas de terminal da Base 2 em `.txt`, pois `*.log` está no `.gitignore`).
- Semente e determinismo: a clusterização usa `random_state=0`; a seleção da Base 2 não é determinística (ver seção 4.3).

---

## 7. Plano de mitigação das vulnerabilidades

Todas as vulnerabilidades abaixo foram **exploradas por este trabalho** usando apenas dados públicos. Cada uma vem com a evidência, a mitigação proposta e o custo. Os valores de parâmetros (como *k*) são pontos de partida, a calibrar com a organização. Nenhuma mitigação foi implementada ou medida; a seção 7.2 descreve como medir.

### 7.1 Vulnerabilidades e mitigações

**V1 — Estatística municipal publicada com granularidade demais (Bases 2 e 3).**
*Evidência:* 41% das ~211 mil combinações (mês, SH4, país) têm ≥ 99% do valor nacional concentrado em 1 município; 1,64 milhão de linhas da Base 3 (7,1%) foram atribuídas a município só com isso.
*Mitigação:* **supressão de células** do Comex Stat municipal com menos de *k* empresas contribuintes (proposta inicial: *k* = 5) e regra de dominância (suprimir quando um contribuinte responde por parcela muito alta do valor), com **supressão complementar** para evitar recuperação por diferença; onde a célula não atingir o critério, **generalizar** (município → UF ou região, SH4 → SH2, mês → trimestre); publicar com defasagem.
*Custo:* perda de detalhe regional para pesquisa.

**V2 — Valores FOB e peso líquido com precisão exata nos dois lados (Base 2).**
*Evidência:* a reconciliação com tolerância de 1,0 USD/kg, em combinações atômicas, recuperou 5.516 operações de forma unívoca.
*Mitigação:* **arredondar ou agrupar em faixas logarítmicas** FOB e peso, tanto nas estatísticas públicas quanto nos microdados anonimizados (a quebra de um dos lados já inviabiliza a igualdade); alternativamente, **ruído calibrado** (privacidade diferencial) nos agregados; não publicar valor e peso exatos simultaneamente.
*Custo:* perda de precisão em análises de preço unitário.

**V3 — Combinações raras de quase-identificadores nos microdados (Base 2).**
*Evidência:* o ataque só funciona em combinações (mês, SH4, país) com **uma única linha**.
*Mitigação:* **k-anonimato sobre (mês, SH4, país)** nos microdados: suprimir ou generalizar registros em combinações com menos de *k* linhas (SH4 → SH2, país → bloco, mês → trimestre).
*Custo:* menor resolução para produtos e origens de nicho.

**V4 — Descrição livre do produto vaza marca e razão social (Base 3; Base 1).**
*Evidência:* palpites de alta confiança vêm de palavras como "STEMAC" e "GRUPOS GERADORES"; no Gate 1, "PERFUME PARIS", "EDITORA FTD", "FREIOS UNIAO".
*Mitigação:* **dicionário controlado de descrições por NCM** em vez de texto livre; ou **redação automática de nomes próprios** (reconhecimento de entidades e lista de razões sociais do CNPJ como bloqueio) e supressão de termos que aparecem em menos de *k* operações.
*Custo:* perde-se informação técnica de especificação.

**V5 — Identificadores estáveis permitem ligar registros (Base 1).**
*Evidência:* no Gate 1, o `numero_de_ordem` estável sustentou a clusterização. Nas Bases 2 e 3 o identificador é único por linha e a clusterização de texto perdeu força — a remoção funcionou como mitigação.
*Mitigação:* manter identificadores únicos por linha e **rotacionar hashes** por publicação/período.
*Custo:* baixo.

**V6 — Composição de fontes públicas (todas as bases).**
*Evidência:* o ataque usa só dados públicos e legítimos isoladamente (Comex Stat por município + cadastro de CNPJ). O próprio MDIC já descontinuou a lista pública de empresas importadoras/exportadoras por esse motivo (ver `gate_1/RELATORIO.md` §3.3 e §5).
*Mitigação:* **avaliação de risco por composição antes de cada publicação** (teste do "intruso motivado" com dados públicos, como este trabalho); não publicar duas granularidades complementares ao mesmo tempo; oferecer microdados detalhados apenas em ambiente controlado com acordo de uso.
*Custo:* processo e prazo de publicação maiores.

| Prioridade | Ações | Motivo |
|---|---|---|
| **P1** | V2 (arredondar FOB/peso), V3 (k-anonimato nos microdados) e V1 (supressão de células) | Atacam diretamente os sinais principais das Bases 2 e 3, com custo relativamente baixo |
| **P2** | V4 (controlar/redigir a descrição) | Elimina a classe de vazamento textual da Base 3 |
| **P3** | V5 (rotação de hashes) e V6 (processo de avaliação por composição) | Governança contínua |

### 7.2 Como validar a mitigação

Os próprios scripts servem como **teste de regressão** do risco: aplicar a mitigação às estatísticas e aos microdados e reexecutar os passos de ataque. Indicadores, com o valor atual como linha de base:

| Indicador | Linha de base | Script |
|---|---|---|
| Linhas da Base 3 atribuídas a município por concentração ≥ 99% | 1,64 milhão (7,1%) | `gate_2/scripts/03_concentracao_municipio.py` |
| Operações da Base 2 reconciliadas de forma unívoca | 5.516 | `gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py` |
| Palpites de confiança alta/média na Base 3 | 55 grupos | `gate_2/scripts/04_score_final.py` |

A meta de redução deve ser definida com a organização; o resultado esperado é que cada indicador caia para perto de zero.

---

## 8. Reprodução

Guia completo, com dados a baixar, fontes e ordem de execução: [`HOW_TO_USE.md`](../HOW_TO_USE.md). Resumo da ordem:

```
shared/scripts/mapa_municipios.py                      # crosswalk município Comex -> TOM
shared/scripts/baixar_filtrar_estabelecimentos.py      # CNPJ ativos nos municípios-alvo
shared/scripts/baixar_filtrar_empresas.py              # razão social dos candidatos

# Base 3
gate_2/scripts/01_cluster_texto.py -> 03_concentracao_municipio.py -> 04_score_final.py -> 05_cruzamento_sinais.py

# Base 2
gate_2/scripts_sem_descricao/01_reconciliacao_fob_peso.py -> 02_monopolio_municipal.py -> 03_gerar_top50_base2.py -> 04_validacao_final_independente.py
```

Ressalvas de reprodutibilidade:

- O filtro de municípios dos CNPJs candidatos usa **apenas** os municípios candidatos do Gate 1 (`gate_1/dados/processado/candidatos_municipio_por_grupo.parquet`); municípios que só aparecem nas Bases 2 ou 3 ficam sem candidatos.
- O `df_clusterizado.parquet` do Gate 1 vem de um notebook que não está no repositório, e o passo que adiciona `CO_TOM_STR` a `candidatos_municipio_por_grupo.parquet` também não está versionado (ver `HOW_TO_USE.md` §4.3). A numeração da Base 3 pula do script 01 para o 03.
- A base de CNPJ é um snapshot de 14/09/2026 de um espelho de terceiros.
