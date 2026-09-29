# Metodologia de Reidentificação — Base 2 (Sem Descrição)

## 1. Princípio do Ataque de Balanço Aduaneiro (Duplo Balanço Exato)
A anonimização pela simples supressão do campo textual (`descricao`) mostra-se ineficaz quando preservadas variáveis numéricas contínuas de alta precisão aliadas a identificadores categóricos granulares.

O Comex Stat disponibiliza dados públicos agregados mensais em nível municipal (`IMP_2021_MUN.csv`), contendo os totais de `VL_FOB` (valor em dólares) e `KG_LIQUIDO` (peso líquido em quilogramas) indexados pelo sistema harmonizado `SH4` (primeiros 4 dígitos da NCM), código de país de origem e mês.

O script `01_reconciliacao_fob_peso.py` implementa a reconciliação reversa via DuckDB:
1. Isola registros da Base 2 onde a combinação `(mes, sh4, co_pais)` é atômica (`count(*) = 1`).
2. Cruza esses registros com o agregado municipal público aplicando tolerância decimal estrita:
   $$\Vert{}FOB_{\text{base2}} - FOB_{\text{pub}}\Vert{} \le 1.0 \quad \land \quad \Vert{}Peso_{\text{base2}} - Peso_{\text{pub}}\Vert{} \le 1.0$$
3. Filtra apenas os casos onde a correspondência retornou um município unívoco (`n_mun_distintos = 1`), convertendo o identificador do município para o padrão cadastral TOM de 4 dígitos (`co_tom`). Esse processo recuperou determinística e univocamente 5.516 operações sem qualquer necessidade de dados textuais.

## 2. Seleção por Concentração Territorial e Volume Financeiro
Após desvendar a localização física exata da importação, o script `02_monopolio_municipal.py` e o otimizador `03_gerar_top50_base2.py` mapeiam as empresas candidatas na base aberta da Receita Federal:
1. **Poda e Resolução de Escopo:** Em vez de gerar o produto cartesiano contra os mais de 24 milhões de estabelecimentos do país, o pipeline isola os municípios com menor densidade de empresas ativas presentes nas operações reconciliadas (concentração variando entre 536 e 5.476 empresas, mitigando a dispersão caótica das capitais).
2. **Função de Confiança (Score de Monopólio Relativo):**
   $$\text{Score} = \frac{1}{\text{qtd\_raizes\_no\_mun}}$$
3. **Desempate por Volume Financeiro (FOB):** Dentro dos municípios de maior concentração territorial, as operações são priorizadas pelo montante financeiro negociado (`fob_base2` decrescente), visto que transações de alto valor apresentam menor probabilidade de ruído ou fracionamento contábil.
4. **Deduplicação Estrita:** Aplica-se partição analítica (`ROW_NUMBER() OVER`) para garantir no máximo uma atribuição por CNPJ raiz e uma por `chave_item`.

## 3. Auditoria, Desduplicação Global e Validação de Compliance
O script `04_validacao_final_independente.py` atua como barreira de compliance antes da submissão:
- **Formatação Estrita:** Padroniza as colunas exclusivas `chave_item` e `CNPJ` (com preenchimento de zeros à esquerda para garantir rigorosamente 14 dígitos).
- **Prevenção de Colisões Cross-Gate:** Cruza a lista de palpites contra os CNPJs já selecionados no **Gate 1** (`gate_1/palpites_cnpj.csv`) e as raízes da **Base 3** (`gate_2/palpites_cnpj_top50_final.csv`), garantindo zero colisão direta de palpites e maximizando a cobertura de acertos da equipe.
- **Auto-reparo com Banco de Reservas:** Caso ocorresse colisão, os candidatos excedentes seriam substituídos automaticamente a partir do arquivo detalhado de contingência (`palpites_base2_top50_detalhado.parquet`).

## 4. Plano de Mitigação de Vulnerabilidades
Para mitigar a vulnerabilidade estrutural de reidentificação por balanço numérico em bases públicas aduaneiras desidentificadas:
- **Aplicação de $k$-Anonimato Geográfico:** Ocultar ou suprimir do Comex Stat municipal células agregadas compostas por menos de $k = 5$ importadores ou transações independentes em determinado município/período.
- **Perturbação Numérica e Microagregação:** Inserir ruído estocástico controlado (privacidade diferencial) ou agrupar os valores contínuos de FOB e Peso Líquido em intervalos/faixas logarítmicas de magnitude, quebrando a viabilidade da correspondência unívoca por igualdade decimal exata.