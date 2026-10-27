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
