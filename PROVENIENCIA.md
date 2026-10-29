# Proveniência dos dados — de onde vem cada número do Business Case

**Business Case MBA USP/Esalq em Engenharia de Software · Gisele Fonseca de Aguiar Silva**
Pasta montada em 27 out. 2026. Todas as saídas desta pasta foram geradas pelos
scripts aqui presentes, nesta mesma data, e não foram editadas à mão.

Este documento existe para responder, com rastro verificável, à pergunta
"de onde você tirou os dados das tabelas?". Para cada tabela e afirmação
numérica do documento, indica o arquivo, a linha e o comando que a produziu.

---

## 1. Como reproduzir tudo do zero

```bash
pip install pandas numpy duckdb pyyaml

cd experimento
python3 viab_llm_silencioso.py      # gera resultado_viab_llm.csv (270 execuções)
python3 analise_viab_llm.py         # matriz defeito x controle
python3 pilhas_controle.py          # risco residual por pilha

cd ../mineracao
python3 minerar_cobertura_dbt.py --autoteste    # afere o parser, não precisa de token
```

O experimento inteiro roda em cerca de 20 segundos. As sementes são fixas
(1 a 30), então os números saem idênticos a cada execução, em qualquer máquina.
As versões exatas de Python e bibliotecas usadas estão em `ambiente.txt`, e
`checksums.txt` traz o SHA-256 de cada script e do CSV.

---

## 2. Mapa tabela → origem

### Tabela 1 — Procedimentos estatísticos de geração do cenário simulado

| | |
|---|---|
| **Origem** | `experimento/viab_llm_silencioso.py`, função `gerar_cenario()`, linha 50 |
| **Parâmetros** | constantes nas linhas 30 a 47 do mesmo arquivo |
| **Saída que comprova** | `experimento/saida_1_experimento.txt` |

Cada linha da tabela corresponde a uma chamada de geração aleatória no código.
A docstring da função repete a lista completa dos procedimentos, de modo que o
texto do Business Case e o código não possam divergir sem que se perceba.

A falha correlacionada ao valor está na linha 40 (`P_STATUS_NULO_BASE = 0.030`)
combinada com `K_CORRELACAO = 0.90`: a probabilidade de status ausente é
`0,030 × (1 + 0,90z)`, com `z` padronizado e truncado em `[-1; 3]`.

### Tabela 2 — Mecanismos de defeito semântico injetados

| | |
|---|---|
| **Origem** | `experimento/viab_llm_silencioso.py`, dicionário `DEFEITOS`, linha 196 |
| **Saída que comprova** | `experimento/saida_2_analise.txt`, seção 1 |

Cada entrada do dicionário traz o SQL executável do defeito e, no campo
`ancora`, a classe correspondente na taxonomia publicada. Os nove defeitos são
consultas reais sobre as mesmas tabelas de origem, não descrições.

A afirmação de que **nenhum dos nove levanta exceção** é verificável na coluna
`excecao` do CSV: todas as 270 linhas estão vazias nessa coluna.

### Tabela 3 — Camadas de controle e critérios de disparo

| | |
|---|---|
| **Origem** | `experimento/viab_llm_silencioso.py`, função `controles()`, linha 352 |
| **Tolerâncias** | `TOL_C1 = 0.001` (linha 346) e `TOL_C4 = 0.05` (linha 347) |
| **Saída que comprova** | `experimento/saida_2_analise.txt`, seção 2 |

A reconciliação de valor (C4) opera por razão calibrada, não por igualdade,
porque o total declarado na origem inclui imposto e frete que o modelo analítico
exclui de propósito. A calibração está em `rodar()`, linha 404.

### Tabela 4 — Correspondência entre camada de controle e teste observável

| | |
|---|---|
| **Origem** | `mineracao/minerar_cobertura_dbt.py`, linhas 87 a 115 |
| **Conjuntos** | `C1_CONTAGEM` (89), `C2_GENERICOS` (87), `C3_SCHEMA_TESTES` (98), `C4_VALOR` (107) |
| **Classificação** | função `classificar()`, linha 336 |
| **Saída que comprova** | `mineracao/saida_autoteste_parser.txt` |

Este é o mapeamento que torna as duas frentes comparáveis: liga cada camada do
experimento ao teste que um projeto real declara.

---

## 3. Afirmações do texto e onde se comprovam

### "As duas apurações coincidiram nas sete métricas, com diferença relativa nula até a sexta casa decimal"

`experimento/saida_1_experimento.txt`, bloco `verificacao do harness`. A verdade
do cenário é calculada a partir do processo gerador, sem passar por SQL
(linhas finais de `gerar_cenario()`), e comparada ao SQL de referência
(constante `REFERENCIA`). Todas as sete métricas saem com `dif=+0.000000%`.

Esta é a conferência de validade interna: sem ela, erro atribuído a um defeito
injetado poderia ser erro do próprio aparato de medição.

### "Os testes genéricos e o teste de schema não detectaram nenhum dos nove defeitos"

`experimento/saida_2_analise.txt`, seção 2: as colunas `C2_dbt_generico` e
`C3_schema` valem 0,000 nas nove linhas. Seção 4 do mesmo arquivo lista,
camada por camada, o que cada uma detecta e a que é cega.

### "Um defeito produziu erro superior a sessenta por cento no faturamento apurado"

`experimento/saida_2_analise.txt`, seção 1, linha `D8_preco_de_grao_errado`:
+62,153% com desvio-padrão de 0,400 entre as 30 sementes. A linha
correspondente da seção 2 mostra que `C1_reconciliacao_contagem` vale 0,000
para esse defeito, isto é, a reconciliação de contagem é cega a ele.

### "Risco residual por pilha de controles"

`experimento/saida_3_pilhas.txt`, seção 7. As pilhas A a D e a exposição somada
de cada uma. A seção 8 isola o que só a reconciliação de valor detecta.

### "Defeito invisível na métrica principal e material em outra"

`experimento/saida_3_pilhas.txt`, seção 9: `D2_inner_join` erra −0,000% na soma
do faturamento e +4,45% na mediana do ticket.

### "Sensibilidade à banda de tolerância"

Esta varredura foi executada em sessão interativa e **ainda não está em script
desta pasta**. Para que entre no Business Case, precisa ser reimplementada como
script reproduzível. Ver pendências, item 2.

### Aferição do instrumento de mineração

`mineracao/saida_autoteste_parser.txt`: dez de dez, com quatro casos de YAML de
gabarito conhecido e seis de classificação de pilha. Os casos estão na constante
`FIXTURES`, linha 568.

`mineracao/saida_afericao_yaml_real.txt`: conferência contra arquivo real de
`dbt-labs/jaffle_shop`, com o resultado batendo com a leitura manual do arquivo.
Os arquivos reais coletados estão em `mineracao/yaml_reais/`.

---

## 3-bis. Experimento II — escada de oráculos, verdadeiros negativos e falso positivo

Acrescentado em 29 out. 2026, após a revisão sistemática da literatura. O Experimento I
permanece intacto: este NÃO o substitui, acrescenta o que a RSL mostrou que o campo exige.

**Scripts:** `experimento/experimento_oraculos.py` e `experimento/analise_oraculos.py`
**Dados:** `experimento/resultado_oraculos.csv` — 1.500 execuções
(30 sementes x 5 níveis de deriva x 10 variantes, sendo uma delas sem defeito)
**Saídas:** `saida_4_oraculos.txt` e `saida_5_analise_oraculos.txt`

### Por que existe

A RSL mostrou que a literatura comparável (Redyuk et al., EDBT 2021; Tu et al., KDD '23)
reporta **matriz de confusão e precisão/revocação por tipo de defeito**. O Experimento I
só submetia aos controles as variantes defeituosas, de modo que havia apenas verdadeiro
positivo e falso negativo — era possível calcular revocação, e mais nada.

Acrescentar uma execução limpa não bastaria: sobre um cenário idêntico ao de calibração
nenhum controle dispara, e a taxa de falso positivo sairia zero por construção. Por isso
foi introduzida **deriva legítima de negócio** entre o período de calibração e o período
medido — deslocamento do mix de alíquota e elevação do frete, nenhum dos quais é defeito
e nenhum dos quais altera a verdade da métrica.

### Resultado 1 — escada de oráculos (seção 10 da saída)

| Oráculo | Quem o usa | Acusa |
|---|---|---|
| exceção de execução | PrismaDV | **0,0%** dos defeitos |
| igualdade exata de tabela | ELT-Bench | **100,0%**, sem informar a magnitude |
| igualdade de contagem de linhas | prática corrente | **66,7%** |
| magnitude do erro na métrica | este trabalho | amplitude de **−6,33% a +409,54%** |

Os dois oráculos da literatura são os extremos inúteis: um não vê nada, o outro vê tudo
sem distinguir erro de 0,0% de erro de 409%. O caso D2 é o exemplo limpo: a igualdade de
tabela o acusa, e o erro no faturamento é exatamente 0,000%.

### Resultado 2 — matriz de confusão (seção 11)

| Camada | VP | FN | FP | VN | Revocação | Especificidade | Taxa de falso positivo |
|---|---|---|---|---|---|---|---|
| C1 contagem | 900 | 450 | 0 | 150 | 0,667 | 1,000 | **0,000** |
| C2 genéricos | 0 | 1350 | 0 | 150 | **0,000** | 1,000 | 0,000 |
| C3 schema | 0 | 1350 | 0 | 150 | **0,000** | 1,000 | 0,000 |
| C4 valor (banda 5%) | 959 | 391 | 60 | 90 | 0,710 | 0,600 | **0,400** |

**O achado econômico central do Business Case está nesta tabela.** A única camada que
detecta mais que a reconciliação de contagem é também a única que gera alarme falso. O
ganho marginal de C1 para C4 é de **4,3 pontos percentuais de revocação**, comprados com
**40% de taxa de falso positivo**.

A precisão não é reportada como resultado porque depende da prevalência de defeitos, que
aqui é artificial (nove variantes defeituosas para uma limpa). Revocação, especificidade
e taxa de falso positivo não dependem da prevalência.

### Resultado 3 — falso positivo sob deriva (seção 12)

C1, C2 e C3 nunca disparam falsamente, em nenhum nível de deriva. C4 com banda de 5%
tem taxa de falso positivo de 0% até deriva de 0,05 e de **100% a partir de deriva de
0,10**. O limiar é abrupto.

### Resultado 4 — a curva de trade-off (seções 13 e 14)

Apertar a banda de 5% para 0,5% eleva a revocação de 0,710 para 0,938 e a taxa de falso
positivo de 0,400 para 0,800. A tabela 14 cruza banda e deriva e é a tabela de decisão:
**a banda ótima depende do nível de deriva, que não é conhecido de antemão.**

> ⚠️ **Advertência metodológica que precisa constar do texto.** Em deriva de 0,20 com
> banda de 5%, a revocação de C4 é 1,00 — e a taxa de falso positivo também é 1,00. O
> controle dispara sempre. Revocação alta sem especificidade não é detecção, é alarme
> permanente, e os defeitos "detectados" nessa faixa foram detectados pelo motivo errado.
> Nenhum número de revocação deste experimento deve ser lido sem a especificidade ao lado.

### Resultado 5 — o que ainda atravessa tudo (seção 15)

Com banda de 5%, D6 (omissão de deduplicação) atravessa todas as camadas até deriva de
0,05, e D7 (desconto ignorado, R$ 682.912 de erro) atravessa a partir de deriva de 0,05.
Quais defeitos sobrevivem **muda conforme a deriva**, o que é mais um argumento de que a
configuração de controles não pode ser fixada sem conhecer o regime de variação do negócio.

### Resultado 6 — a camada distribucional C5, e a fronteira detecção × alarme falso

Acrescentada em 29 out. 2026, em resposta à objeção mais provável de um parecerista:
que o trabalho teria testado apenas controles fracos. C5 reproduz a família de
verificações que a literatura comparável avalia (Deequ, TensorFlow Data Validation,
Auto-Validate): tamanho, completude, média, desvio-padrão, mediana e máximo contra
valores calibrados em período saudável, mais teste de Kolmogorov-Smirnov de duas
amostras. Para que C5 também pudesse gerar alarme falso, acrescentou-se um segundo
canal de deriva legítima — inflação de preço —, separável do canal que atinge C4.

| Camada | Custo | Revocação | Taxa de falso positivo |
|---|---|---|---|
| C2 testes genéricos de forma | baixo | **0,000** | 0,000 |
| C3 esquema e contrato | baixo | **0,000** | 0,000 |
| C1 reconciliação de contagem | baixo | 0,667 | **0,000** |
| C4 reconciliação de valor | alto | 0,710 | 0,400 |
| C5 verificação distribucional | médio | **0,812** | **0,600** |

**A ordenação por revocação é exatamente a ordenação por taxa de falso positivo.**
Nenhuma camada domina outra: detecção é comprada com alarme falso, de forma
monotônica. A exceção é C1, que detecta dois terços dos defeitos sem gerar um único
alarme falso, e é a de menor custo de implantação.

O ganho específico de C5 está nos dois defeitos que a pilha barata não enxerga porque
preservam a contagem de linhas: **D7 (desconto ignorado, +8,1%) e D8 (erro de grão,
+62,2%), ambos detectados por C5 em 100% das execuções**. São também os de maior erro
monetário.

> Consequência para a tese, e é uma correção importante: **o trabalho não pode afirmar
> que todo controle falha.** Existe uma camada que detecta os defeitos de maior impacto.
> A afirmação defensável é mais precisa: as camadas que as equipes efetivamente declaram
> — completude, unicidade, validade e integridade referencial, conforme Ustunboyacioglu
> et al. (EASE 2024) — detectam zero de nove, enquanto a camada que os detectaria custa
> 60% de taxa de falso positivo e não é a que se encontra declarada na prática.

---

## 4. O que NÃO está medido — declarar como limitação

Esta seção é tão importante quanto as anteriores. Nenhum número abaixo existe,
e nenhum deles deve aparecer no Business Case como se existisse.

1. **A mineração de projetos públicos não foi executada.** O instrumento está
   pronto e aferido, mas a coleta exige token próprio do GitHub. Nenhum número
   sobre cobertura de testes em projetos reais pode ser afirmado ainda. O
   protocolo está em `mineracao/PROTOCOLO_MINERACAO.md`.

2. **A curva de falso positivo da banda de tolerância não foi medida.** Mediu-se
   apenas a revocação de C4, não a precisão. Como o gerador não tem deriva
   legítima do mix de imposto e frete, não há como estimar alarme falso. É o
   núcleo econômico do Business Case e está em aberto.

3. **Os nove defeitos foram escritos pela pesquisadora** a partir da taxonomia
   publicada, e não colhidos de saída real de modelo de linguagem. O experimento
   demonstra que defeitos dessas classes atravessam os controles; não demonstra
   com que frequência modelos os produzem.

4. **Engine única.** Os nove defeitos rodaram apenas em DuckDB 2.0.0. D3 depende
   de lógica de três valores e D9 de semântica de intervalo fechado, ambas
   padrão da linguagem, mas não reverificadas em outro motor nesta rodada.

5. **Dados sintéticos.** Nenhum dado de organização foi utilizado, por decisão e
   por exigência de confidencialidade. A validade externa é limitada e deve ser
   declarada.

6. **Duas heurísticas do instrumento de mineração erram por construção**: a que
   identifica material didático por nome e descrição, e a que identifica
   reconciliação em teste singular por padrão textual, que superestima a camada
   C4. Ambas exigem conferência manual por amostra.

---

## 5. Conteúdo da pasta

```
business-case-dados/
├── PROVENIENCIA.md                      este arquivo
├── ambiente.txt                         versões de Python e bibliotecas
├── checksums.txt                        SHA-256 dos scripts e do CSV
├── experimento/
│   ├── viab_llm_silencioso.py           gera o cenário, injeta os defeitos, aplica os controles
│   ├── analise_viab_llm.py              matriz defeito x controle, cegueira por camada
│   ├── pilhas_controle.py               risco residual por pilha de controles
│   ├── resultado_viab_llm.csv           as 270 execuções, uma por linha
│   ├── saida_1_experimento.txt          verificação do harness e confirmação das 270 execuções
│   ├── saida_2_analise.txt              seções 1 a 6 da análise
│   └── saida_3_pilhas.txt               seções 7 a 9 da análise
├── mineracao/
│   ├── minerar_cobertura_dbt.py         instrumento de mineração, quatro fases
│   ├── PROTOCOLO_MINERACAO.md           desenho amostral e critérios de exclusão
│   ├── saida_autoteste_parser.txt       dez de dez no gabarito conhecido
│   ├── saida_afericao_yaml_real.txt     conferência contra arquivo real
│   └── yaml_reais/                      arquivos de projetos reais usados na aferição
└── documento/
    ├── main.tex                         Business Case, arquivo único, compila sozinho
    ├── main.pdf                         resultado da compilação
    └── mbauspesalq_alternativa.sty      versão em dois arquivos, caso prefira separar
```

---

## 6. Observação sobre o CSV

`resultado_viab_llm.csv` tem 270 linhas de dados, uma por combinação de defeito e
semente. Colunas relevantes para conferência:

- `seed`, `defeito`, `ancora` — identificação da execução
- `excecao` — vazia em todas as linhas, o que comprova o silêncio
- `err_*` — erro relativo percentual em cada uma das sete métricas
- `abs_SUM` — erro absoluto em unidades monetárias no faturamento
- `C1_reconciliacao_contagem`, `C2_dbt_generico`, `C3_schema`, `C4_reconciliacao_valor`
  — se cada controle disparou naquela execução
- `_C4_desvio_razao_%` — o desvio observado na razão de reconciliação, que
  permite recalcular a detecção de C4 sob outras bandas de tolerância sem
  reexecutar o experimento
