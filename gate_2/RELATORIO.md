# Gate 2 — reidentificação em escala (23,2 milhões de linhas)

## 1. O problema, de novo, mas maior

Essa segunda base tem 23,2 milhões de registros de importação (jul-dez de
2021), cada um com o importador escondido. O objetivo é o mesmo do primeiro
gate: dar 50 palpites de CNPJ de quem provavelmente fez essas importações.
Mas essa base tem uma diferença que obrigou a repensar o método do zero, não
só "rodar a mesma coisa em mais dados".

## 2. Por que o método antigo não dava pra só escalar

No primeiro gate, cada linha da base tinha um número de declaração
escondido, mas repetido — se duas linhas tinham o mesmo número, elas
vinham do mesmo despacho de importação, quase certamente da mesma empresa.
Isso funcionava como uma "costura" entre linhas: agrupávamos primeiro pelo
texto da descrição do produto (empresas repetem o jeito de escrever) e
depois confirmávamos esses grupos batendo o número de declaração
compartilhado. Duas pistas concordando.

Nessa segunda base, esse número de declaração não existe mais — cada linha é
praticamente única, sem nenhuma pista de que duas linhas vieram do mesmo
despacho. Isso quer dizer que, se a gente clusterizasse só pelo texto (como
antes), perderíamos a segunda pista de confirmação. E pra descrições de
produtos genéricos — "parafuso M6 aço inox", por exemplo — duas empresas
completamente diferentes escrevem quase a mesma frase. Sem a segunda pista,
o risco de juntar empresas diferentes num grupo só ficou grande demais pra
confiar só nisso.

Precisávamos de uma fonte de evidência que não dependesse de comparar
linhas entre si.

## 3. A ideia central: o Brasil já revela isso sozinho

O governo publica, mês a mês, quanto cada município brasileiro importou de
cada tipo de produto, de cada país de origem — sem dizer qual empresa fez
a importação (isso é sigiloso), só o total por cidade. Essa estatística por
si só é inofensiva: saber que "São Paulo importou US$ X de tecido chinês em
julho" não identifica ninguém, porque São Paulo tem milhares de empresas.

Só que, pra muitos produtos, a realidade da economia brasileira é bem menos
distribuída do que isso. Importação é concentrada em portos e polos
industriais especializados: quase todo vidro automotivo da Alemanha entra
por um punhado de cidades; quase toda importação de um instrumento musical
raro de um país específico passa por uma única cidade que tem um
distribuidor especializado naquilo. Quando checamos isso diretamente nos
dados públicos, o padrão foi muito mais forte do que esperávamos: **de
quase 211 mil combinações de (mês, tipo de produto, país de origem), 41%
têm 99% ou mais do total nacional concentrado numa única cidade.**

Isso significa que, pra uma fatia enorme das combinações, **a própria
estatística pública já entrega o município** — sem precisar adivinhar nada
a partir do texto da nossa base. Se uma linha da nossa base bate com uma
dessas combinações "de cidade única", já sabemos com bastante confiança de
onde ela veio, mesmo sem comparar essa linha com nenhuma outra.

Quando aplicamos isso na base de 23,2 milhões de linhas, **1,64 milhão delas
(7,1% do total) caíram em combinações desse tipo**, cobrindo 605 municípios
diferentes. Esse virou o sinal principal do gate 2 — não o texto.

## 4. Do município pro CNPJ: a descrição como desempate

Saber a cidade ainda deixa muitos CNPJs possíveis (uma cidade grande tem
milhares de empresas cadastradas). É aqui que a descrição do produto volta a
importar, mas com um papel diferente do gate 1: em vez de ser a base pra
formar grupos, ela serve só pra **desempatar entre os candidatos que já
moram naquela cidade**.

A lógica: dentro de cada cidade, olhamos as descrições das importações que
caíram ali e procuramos palavras que sejam raras em geral (não são jargão
comum de declaração aduaneira, tipo "produto", "marca", "fiscal") mas se
repetem várias vezes ali — essas palavras tendem a ser o nome de uma marca,
de um produto de nicho, ou de um termo técnico do ramo daquela empresa.
Depois comparamos essas palavras com a razão social e o nome fantasia de
cada empresa cadastrada naquela cidade, e escolhemos a que bate melhor.

Um cuidado que só percebemos ao ver os primeiros resultados: uma palavra
pode ser rara *na descrição de um produto* mas comum *em nome de empresa* —
"MINISTÉRIO", por exemplo, quase nunca aparece descrevendo uma fralda, mas é
comum em nome de instituição religiosa. Isso gerava pareamentos sem
sentido (uma igreja "importando" fraldas só porque a palavra bateu por
acaso). A correção foi checar a raridade da palavra dos dois lados —
também no universo de nomes de empresa, não só no de descrições de
produto — e descartar as que são comuns demais em qualquer um dos dois.

## 5. Uma segunda fonte de confirmação: o texto, de novo, mas como bônus

Mesmo sem poder confiar só nele, o texto ainda tem valor como **checagem
independente**. Fizemos, em paralelo, a mesma clusterização de texto do
gate 1 (agrupar descrições parecidas) nas 23,2 milhões de linhas inteiras,
sem depender da concentração geográfica.

A ideia do cruzamento final: para cada palpite de empresa que a concentração
geográfica gerou, olhamos se as linhas que apontaram pra aquele
palpite também formam, entre si, um cluster de texto coerente (ou seja, se
elas realmente parecem ter sido escritas pela mesma "mão"). Quando as duas
fontes de evidência — uma geográfica, outra textual, calculadas de formas
completamente diferentes — apontam pro mesmo lugar, a confiança sobe bastante.
Quando as linhas do mesmo palpite estão espalhadas em vários clusters de
texto diferentes, é um sinal de alerta de que talvez estejamos somando mais
de uma empresa sob o mesmo palpite.

Importante: essa concordância confirma que as linhas são **consistentes
entre si**, não que o CNPJ escolhido está **certo** — uma empresa errada,
mas cujas linhas realmente vieram de uma fonte única e consistente, também
mostraria concordância alta. É um reforço de confiança, não uma prova.

## 6. O que isso deu

O resultado final está em `gate_2/palpites_cnpj_top50_final.csv`: 50
candidatos, ranqueados por um score que combina os três ingredientes
(concentração geográfica, força do casamento de texto, e concordância entre
os dois sinais). Alguns achados se destacam por baterem com marcas ou
empresas reais e bem específicas — não são só palpites estatísticos vagos:

- **Magnesita Refratários S.A.**, batendo com importação de óxido de
  magnésio (matéria-prima do setor de refratários da empresa) — 96% de
  concordância entre os dois sinais.
- **Stemac S.A. Grupos Geradores**, batendo com peças do setor de geradores
  — fabricante real e conhecido do ramo.
- **TE Connectivity Brasil**, batendo com componentes eletromecânicos — uma
  multinacional real do setor de conectores eletrônicos.
- **ASR Cerâmica** e **Nansen Instrumentos de Precisão**, com praticamente
  100% de concordância entre os sinais.

## 7. Limitações (vale saber antes de usar os 50 palpites)

- **É uma heurística de investigação, não uma prova.** Ela reduz um
  universo de milhares de empresas possíveis pra uma lista curta e
  plausível — não é uma confirmação legal ou definitiva de quem importou o
  quê.
- **Falsos positivos por coincidência de palavra ainda acontecem.** A
  correção da seção 4 resolveu os casos mais óbvios, mas não é perfeita —
  algumas palavras (como "importadora" no nome da própria empresa) ainda
  passam pelo filtro sem serem realmente distintivas.
- **A concentração geográfica cobre uma fatia da base, não tudo.** Ela deu
  sinal forte pra 7,1% das linhas. O resto da base (a maioria) não tem essa
  pista geográfica tão clara, e depende mais do sinal de texto, que é mais
  fraco nessa base (ver seção 2).
- **Nota técnica, pra quem for reproduzir**: o processamento foi feito numa
  máquina com pouca memória disponível pra esse volume de dados, o que
  obrigou a rodar alguns passos mais devagar (um de cada vez, em vez de em
  paralelo) só por limitação de hardware — isso afetou o tempo de execução,
  não a qualidade do resultado.
