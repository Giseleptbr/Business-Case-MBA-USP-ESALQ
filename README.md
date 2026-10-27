# Business Case — dados, scripts e evidências

**MBA USP/Esalq em Engenharia de Software · Gisele Fonseca de Aguiar Silva**
Tema: custo do erro silencioso em pipelines analíticos e onde posicionar a
validação de dados. Pasta montada em 27 out. 2026.

Esta pasta reúne tudo o que produziu os números do Business Case: os scripts,
os dados gerados, as saídas registradas e o documento em LaTeX. Nada aqui foi
editado à mão — todas as saídas vieram dos scripts desta mesma pasta.

---

## Por onde começar

| Se você quer… | Leia |
|---|---|
| saber de onde vem cada tabela do Business Case | `PROVENIENCIA.md` |
| saber o que o estudo **não** mediu | `PROVENIENCIA.md`, seção 4 |
| reproduzir os números | `PROVENIENCIA.md`, seção 1 |
| entender o desenho amostral da mineração | `mineracao/PROTOCOLO_MINERACAO.md` |
| ler o Business Case | `documento/main.pdf` |
| editar o Business Case | `documento/main.tex` (arquivo único, compila sozinho) |

---

## O que foi feito, em um parágrafo

Construiu-se um experimento de injeção de defeitos sobre um pipeline analítico
com verdade conhecida por construção. Nove mecanismos de defeito semântico,
cada um ancorado em classe documentada na literatura, foram confrontados com
quatro camadas de controle de qualidade de dados, medindo-se o erro induzido em
sete métricas de negócio ao longo de 30 repetições — 270 execuções no total.
Antes de qualquer injeção, verificou-se que o instrumento media o que se
propunha a medir: a verdade calculada a partir do processo gerador coincidiu com
a implementação de referência em SQL nas sete métricas, com diferença nula até a
sexta casa decimal. Em paralelo, construiu-se e aferiu-se um instrumento para
levantar, em projetos públicos de transformação de dados, quais camadas de
controle as equipes efetivamente declaram; esse levantamento ainda não foi
executado.

## O que se encontrou

Nenhuma das 270 execuções levantou exceção: os nove defeitos executam e
materializam tabela. Os testes genéricos de forma e o teste de esquema — a
camada de validação de maior penetração na prática — não detectaram nenhum dos
nove, por verificarem a forma da tabela, que todo defeito semântico preserva. A
reconciliação de contagem de linhas detectou seis dos nove e permaneceu cega aos
três que preservam a contagem, um dos quais produziu erro de 62% no faturamento
apurado. O detalhe por defeito, por camada e por métrica está nas saídas
registradas em `experimento/`.

## O que ainda não se sabe

A mineração de projetos públicos não foi executada, então nenhum número sobre a
prática real pode ser afirmado. A curva de falso positivo da banda de tolerância
não foi medida: avaliou-se apenas a revocação da reconciliação de valor, não a
precisão. Os nove defeitos foram escritos a partir da taxonomia publicada, e não
colhidos de saída real de modelo de linguagem. A lista completa das limitações,
com o que cada uma impede de afirmar, está na seção 4 do `PROVENIENCIA.md`.

---

## Estrutura

```
.
├── README.md                  este arquivo
├── PROVENIENCIA.md            mapa tabela -> script -> linha -> saída
├── ambiente.txt               versões de Python e bibliotecas
├── checksums.txt              SHA-256 dos scripts e do CSV
├── experimento/               o experimento de injeção de defeitos
├── mineracao/                 o instrumento de levantamento e seu protocolo
└── documento/                 o Business Case em LaTeX
```

## Requisitos

```bash
pip install pandas numpy duckdb pyyaml
```

As sementes são fixas (1 a 30), de modo que os números saem idênticos a cada
execução, em qualquer máquina. Reprodutibilidade conferida em diretório limpo:
a saída regerada é byte a byte igual à registrada.
