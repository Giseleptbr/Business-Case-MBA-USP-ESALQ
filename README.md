# Custo do erro silencioso em pipelines analíticos

**Onde posicionar a validação de dados, e quanto de risco sobra em cada configuração.**

Business Case do MBA USP/Esalq em Engenharia de Software · Gisele Fonseca de Aguiar Silva
Entrega: dezembro de 2027 · Última atualização desta pasta: 29 out. 2026

---

## 1. O problema

Um pipeline analítico pode terminar com status de sucesso, respeitar o esquema
declarado, preservar a contagem de linhas, não emitir nenhum nulo inesperado — e ainda
assim publicar um número errado.

Isso acontece quando o código de transformação contém um **defeito semântico**: lógica
que executa sem erro mas não corresponde à intenção de negócio. Uma junção no grão
errado, um filtro que nunca casa, uma coluna de data trocada. O pipeline fica verde, a
tabela é materializada, e a métrica entregue ao negócio está incorreta.

O problema importa porque **os controles de qualidade de uso corrente verificam a forma
da tabela, não o significado do número** — chave única, ausência de nulos, integridade
referencial, conformidade de tipos. Defeito semântico, por definição, preserva a forma.

## 2. A pergunta

> Quais mecanismos de defeito semântico escapam a cada camada de controle de qualidade,
> qual o viés induzido por tipo de métrica de negócio, e qual o risco residual de cada
> configuração de controles?

A decisão de gestão na ponta é uma **matriz de alocação**: qual verificação posicionar em
qual camada, dado o mecanismo de defeito e as métricas que o negócio consome.

---

## 3. O que foi construído

| # | Instrumento | Estado |
|---|---|---|
| I | **Experimento de injeção de defeitos** — 9 mecanismos × 4 camadas × 7 métricas × 30 sementes = **270 execuções** | executado |
| II | **Escada de oráculos e fronteira de detecção** — acrescenta execução limpa, deriva legítima e 5ª camada = **1.500 execuções** | executado |
| III | **Instrumento de mineração** — mede quais camadas de controle projetos dbt públicos declaram | construído, não executado |
| IV | **Revisão sistemática da literatura** — seis frentes, formato de artigo | executada |

Todos os dados são **simulados a partir de procedimentos estatísticos declarados**, o que
o manual do curso admite para Engenharia de Software. Nenhum dado de organização foi
utilizado.

---

## 4. Descobertas

### 4.1 O silêncio é total

**Nenhuma das execuções levantou exceção.** Os nove defeitos executam e materializam
tabela. Antes de qualquer injeção, verificou-se que o instrumento media o que se propunha
a medir: a verdade calculada a partir do processo gerador coincidiu com a implementação
de referência em SQL nas sete métricas, com **diferença nula até a sexta casa decimal**.

### 4.2 A escada de oráculos

Cada oráculo vê uma coisa diferente, e os dois usados pela literatura são os extremos
inúteis.

| Oráculo | Quem o usa | Acusa |
|---|---|---|
| exceção de execução | PrismaDV | **0,0%** dos defeitos |
| igualdade exata de tabela | ELT-Bench | **100%**, sem informar a magnitude |
| igualdade de contagem de linhas | prática corrente | **66,7%** |
| magnitude do erro na métrica | este trabalho | **−6,3% a +409,5%** |

O caso limpo é o defeito D2: a igualdade de tabela o acusa, e o erro no faturamento é
exatamente **0,000%**.

### 4.3 A fronteira detecção × alarme falso

Com execução limpa e deriva legítima de negócio, é possível calcular a matriz de confusão
completa — não apenas revocação.

| Camada | Custo | Revocação | Taxa de falso positivo |
|---|---|---|---|
| C2 testes genéricos de forma | baixo | **0,000** | 0,000 |
| C3 esquema e contrato | baixo | **0,000** | 0,000 |
| C1 reconciliação de contagem | baixo | 0,667 | **0,000** |
| C4 reconciliação de valor | alto | 0,710 | 0,400 |
| C5 verificação distribucional | médio | **0,812** | **0,600** |

**A ordenação por revocação é exatamente a ordenação por taxa de falso positivo.**
Detecção é comprada com alarme falso, de forma monotônica. A única exceção é C1, que
detecta dois terços dos defeitos sem gerar um único alarme falso, e é a mais barata.

### 4.4 A camada que funciona não é a que está implantada

C5 detecta em 100% das execuções os dois defeitos que a pilha barata não enxerga, porque
preservam a contagem de linhas — e que são os de maior erro monetário:

- **D7**, desconto ignorado: +8,1% de erro, R$ 682.912
- **D8**, erro de grão aritmético: +62,2% de erro, R$ 5.234.168

Isso obriga a uma formulação mais precisa, e mais forte, do que "todo controle falha":

> As camadas que as equipes **efetivamente declaram** — completude, unicidade, validade e
> integridade referencial — detectam **zero de nove**. A camada que as detectaria custa
> **60% de taxa de falso positivo** e não é a que se encontra declarada na prática.

É esta formulação que torna a mineração (instrumento III) peça central do argumento, e
não evidência auxiliar: é ela que estabelece o que está de fato implantado.

### 4.5 Vulnerabilidade dependente da métrica

Um defeito pode ser invisível na métrica principal e material em outra. O D2 erra
**0,000% no faturamento e +4,45% na mediana do ticket**. E o pior caso não é o
faturamento: o D8 erra **+72,0% no percentil 95** contra +62,2% na soma. Métricas de
cauda — exposição, limite de crédito, maior sinistro — são as mais vulneráveis e as menos
monitoradas.

### 4.6 O axioma da detecção tardia não se sustenta

A crença de que "validar cedo é mais barato" é tratada como axioma pela indústria. A
revisão da literatura encontrou que o maior teste publicado, com **171 projetos, 47.376
registros de defeito e 268.726 registros de tempo, não encontrou evidência consistente do
efeito**. Os próprios proponentes da curva registraram que o fator de escalada para
sistemas pequenos e não críticos é "mais como 5:1 do que 100:1", e os gradientes
efetivamente medidos ficam entre 2 e 8 vezes, não 100.

Consequência para este trabalho: **o argumento não é que detectar tarde custa caro. É que
a detecção não acontece.** Não há gradiente de custo a discutir quando o defeito nunca é
detectado.

### 4.7 A lacuna de pesquisa, em sua forma estreita

A revisão sistemática mostrou que as formulações amplas **não sobrevivem**: três trabalhos
já medem detecção por tipo de defeito, e um já avalia modelos dbt escritos por agentes
contra tabelas materializadas. O que sobrevive é uma **conjunção de quatro condições**,
nenhuma atendida simultaneamente por qualquer trabalho localizado:

1. o defeito é **mutação semântica do código de transformação**, não corrupção injetada
   nos dados de entrada;
2. o oráculo **não é a falha de execução**;
3. **camadas heterogêneas** de controle são comparadas entre si;
4. a variável dependente é um **indicador de negócio**.

Dois autores da área declaram a lacuna por conta própria, o que vale mais que
reivindicá-la: um grupo propôs em 2022 um estudo de impacto que nunca foi publicado, e um
levantamento de 2026 afirma que mapear tipos de erro para técnicas de detecção permanece
um desafio em aberto.

---

## 5. O que ainda NÃO se sabe

Esta seção tem o mesmo peso da anterior. Nenhum número abaixo existe.

| Item | Situação |
|---|---|
| **Ineditismo** | Não verificado. As buscas em bases indexadas dependem de acesso institucional e estão em stand by por decisão. |
| **Mineração de projetos reais** | Instrumento pronto e aferido (10/10 em gabarito conhecido), **coleta não executada** — exige token próprio do GitHub. |
| **Origem dos defeitos** | Os nove foram escritos a partir da taxonomia publicada, **não colhidos de saída real de modelo de linguagem**. |
| **Engines** | Os defeitos rodaram apenas em DuckDB. Reverificação multi-engine pendente. |
| **Validade externa** | Dados sintéticos, por decisão e por confidencialidade. |
| **Heurísticas da mineração** | Duas erram por construção e exigem conferência manual por amostra. |
| **Deriva legítima** | Modelada por dois canais (mix de alíquota/frete e nível de preço). Sazonalidade, entrada de cliente grande e mudança de mix de produto **não** foram modeladas. |

> ⚠️ **Advertência de leitura.** Em deriva alta, a revocação de C4 e C5 chega a 1,00 — e a
> taxa de falso positivo também. O controle dispara sempre. Isso não é detecção, é alarme
> permanente. **Nenhum número de revocação deste experimento deve ser lido sem a
> especificidade ao lado.**

---

## 6. Como reproduzir

```bash
pip install pandas numpy duckdb scipy pyyaml

cd experimento
python3 viab_llm_silencioso.py      # Experimento I  — 270 execuções, ~20 s
python3 analise_viab_llm.py         # matriz defeito × controle
python3 pilhas_controle.py          # risco residual por pilha
python3 experimento_oraculos.py     # Experimento II — 1.500 execuções, ~75 s
python3 analise_oraculos.py         # escada de oráculos e fronteira

cd ../mineracao
python3 minerar_cobertura_dbt.py --autoteste   # afere o parser, dispensa token
```

As sementes são fixas, de 1 a 30, de modo que os números saem idênticos a cada execução,
em qualquer máquina. A reprodutibilidade foi conferida em diretório limpo: a saída
regerada é idêntica à registrada. Versões em `ambiente.txt`, hashes em `checksums.txt`.

---

## 7. Estrutura

```
.
├── README.md                  este arquivo
├── PROVENIENCIA.md            mapa tabela → script → linha → saída
├── ambiente.txt               versões de Python e bibliotecas
├── checksums.txt              SHA-256 dos scripts e dos dados
├── experimento/
│   ├── viab_llm_silencioso.py      Experimento I: gerador, defeitos, controles
│   ├── analise_viab_llm.py         matriz defeito × controle
│   ├── pilhas_controle.py          risco residual por pilha
│   ├── experimento_oraculos.py     Experimento II: oráculos, deriva, C5
│   ├── analise_oraculos.py         confusão, fronteira, curva de tolerância
│   ├── resultado_viab_llm.csv      270 execuções
│   ├── resultado_oraculos.csv      1.500 execuções
│   └── saida_*.txt                 saídas registradas de cada script
├── mineracao/
│   ├── minerar_cobertura_dbt.py    instrumento de levantamento, quatro fases
│   ├── PROTOCOLO_MINERACAO.md      desenho amostral e critérios de exclusão
│   ├── yaml_reais/                 arquivos reais usados na aferição
│   └── saida_*.txt                 autoteste e aferição
└── documento/
    ├── main.tex                    Business Case em LaTeX, arquivo único
    └── main.pdf                    resultado da compilação
```

> **Nota sobre o formato de entrega.** O Business Case deve ser depositado em Word
> (`.doc`/`.docx`) e PDF, redigido sobre o template institucional. O LaTeX desta pasta
> serve ao **artigo**, não ao Business Case; o texto transfere, a diagramação não.

---

## 8. Onde a proveniência de cada número está

`PROVENIENCIA.md` mapeia, para cada tabela do Business Case, o arquivo, a linha e a saída
que a produziu — e lista em seção própria o que **não** está medido. É o documento a
abrir quando a pergunta for "de onde vem este número".
