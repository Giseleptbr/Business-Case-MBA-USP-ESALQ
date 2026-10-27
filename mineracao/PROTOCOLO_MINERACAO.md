# Protocolo de mineração — cobertura de testes em projetos dbt públicos

**Business Case MBA USP/ESALQ em Engenharia de Software · Gisele Fonseca de Aguiar Silva**
Instrumento construído e aferido em 27/10/2026. Execução da coleta pendente.

---

## 1. Por que este estudo existe

O experimento de injeção de defeitos (27/10/2026) mostrou que a pilha de controles
composta por teste de schema mais testes genéricos detecta **zero de nove** defeitos
semânticos. Esse é um resultado de laboratório. Ele só vira afirmação sobre a prática
se for possível dizer **qual fração dos projetos reais roda exatamente essa pilha**.

Essa é a função desta mineração, e é o componente que mais aumenta a chance de
publicação em JSS / IST / EMSE, porque transforma um experimento sintético em estudo
de duas partes — experimento controlado mais evidência de campo. É também o método que
o próprio grupo de Foidl e coautores usou para entrar no JSS, na mesma linha de pesquisa.

---

## 2. Por que você precisa rodar, e não eu

A sessão em que o instrumento foi construído tem acesso ao GitHub restrito a
repositórios previamente configurados. Foram testadas e bloqueadas:

| Rota | Resultado |
|---|---|
| `/search/code` (busca de código) | HTTP 403 — endpoint não disponível na sessão |
| `/repos/{owner}/{repo}` (API por repositório) | HTTP 403 — acesso não habilitado |
| `codeload.github.com` (tarball) | HTTP 403 |
| BigQuery `github_repos` | sem credenciais GCP |
| `raw.githubusercontent.com` | ✅ funciona, mas **não enumera árvore de arquivos** |

A última linha é a que importa. Sem enumerar a árvore, só dá para buscar arquivos por
caminho adivinhado — e eu testei: **6 de 18 caminhos convencionais retornaram 200**, o
resto deu 404 por branch e layout diferentes. Medir cobertura assim subestimaria o número
de testes de forma sistemática, e subestimar cobertura é exatamente a direção que
favorece a minha hipótese. **Por isso não produzi número algum por essa via.**

Com um token seu de escopo `public_repo`, nada disso se aplica: a busca de código libera,
a API por repositório libera, e a amostragem passa a ser aleatória sobre frame definido,
que é o que o artigo exige.

---

## 3. Execução

```bash
pip install pyyaml
export GITHUB_TOKEN=ghp_...        # token clássico, escopo public_repo

python3 minerar_cobertura_dbt.py --autoteste            # confere o parser (sem token)
python3 minerar_cobertura_dbt.py --fase frame           # ~15 min, monta o frame
python3 minerar_cobertura_dbt.py --fase amostra --n 200 --seed 42
python3 minerar_cobertura_dbt.py --fase coletar         # baixa e parseia
python3 minerar_cobertura_dbt.py --fase relatorio
```

Tudo fica em `mineracao_dbt/`: `frame.jsonl`, `amostra.json`, `resultado.jsonl` e cache
dos tarballs. O cache permite reexecutar o parser sem rebaixar nada — útil quando você
ajustar o vocabulário de testes.

---

## 4. Desenho amostral, redigível direto na seção de métodos

**Frame.** Repositórios públicos contendo arquivo `dbt_project.yml`, localizados pela
busca de código do GitHub. Como a busca devolve no máximo 1.000 resultados por consulta,
o frame é montado por **estratificação em nove faixas de tamanho de repositório**
(parâmetro `size:`), o que ultrapassa esse teto sem recorrer a amostragem por
conveniência. O frame é gravado com carimbo de data e reutilizado, de modo que o sorteio
seja reproduzível.

**Exclusões**, aplicadas nesta ordem e **contabilizadas por critério** no relatório:

| Código | Critério | Justificativa |
|---|---|---|
| E1 | fork | não representa decisão própria de teste |
| E2 | arquivado | não reflete prática corrente |
| E3 | sem diretório de modelos | não é projeto dbt utilizável |
| E4 | menos de 5 modelos | projeto de brinquedo |
| E5 | heurística de material didático no nome ou descrição | tutorial, curso, demo, sandbox |

E5 é heurística por expressão regular e **precisa de conferência manual por amostra** —
declare isso como ameaça de validade. Sugiro revisar manualmente 30 exclusões por E5 e
reportar a taxa de erro.

**Amostragem.** Aleatória simples sem reposição sobre o frame elegível, semente fixa.
n = 200 é suficiente para estimar uma proporção com margem aproximada de ±7 pontos a 95%.
Se quiser ±5, use n = 384.

---

## 5. O mapeamento que liga a mineração ao experimento

É aqui que o estudo fecha, e é a parte que vale defender com cuidado na banca e no artigo.
Cada camada do experimento tem correspondente observável em projeto dbt real:

| Camada | O que é no experimento | Como se observa em projeto real |
|---|---|---|
| **C1** reconciliação de contagem | compara contagem do gold com a origem | `dbt_utils.equal_rowcount`, `fewer_rows_than`, `cardinality_equality`, `elementary.volume_anomalies`, `dbt_expectations.expect_table_row_count_to_equal_other_table` |
| **C2** testes genéricos | `unique`, `not_null`, `relationships`, não-negatividade | os quatro testes nativos do dbt |
| **C3** schema | colunas e tipos esperados | `config.contract.enforced`, `constraints`, testes de tipo do `dbt_expectations` |
| **C4** reconciliação de valor | compara total do gold com total de controle da origem | pacote `audit_helper` (`compare_relations`, `compare_queries`), `dbt_utils.expression_is_true`, `equality`, agregados do `dbt_expectations` (`expect_column_sum_to_be_between`, `_mean_`, `_median_`, `_quantile_`), testes singulares com heurística de reconciliação |

O projeto é classificado na pilha mais alta que possui. A heurística dos testes
singulares (regex por `compare_relations`, `except`, `minus`, `reconcil`, `sum(`)
**é a parte mais frágil do instrumento** — ela superestima C4, porque um `sum()` em teste
singular nem sempre é reconciliação. Trate como limite superior de C4 e confira
manualmente uma amostra.

---

## 6. Aferição já feita

**Autoteste com gabarito conhecido: 10 de 10.** Quatro fixtures de YAML cobrindo
`tests:` clássico, `data_tests:` do dbt 1.8+, contratos e `constraints`, modelo sem teste,
e `sources` com `freshness`; mais seis casos de classificação de pilha.

```
OK  fixture 1..4          OK  classificacao 1..6          AUTOTESTE PASSOU
```

**Aferição contra YAML real.** `dbt-labs/jaffle_shop/models/schema.yml`, lido do
repositório: 2 modelos, 2 com teste, `{unique: 2, not_null: 8, relationships: 1,
accepted_values: 1}` → classificado como `B_padrao_dbt`. Confere com a leitura manual
do arquivo.

Leitura de `packages.yml` aferida em dois projetos de produção:
`cal-itp/data-infra` → `dbt-labs/dbt_utils` + `metaplane/dbt_expectations`;
`bgarcevic/danish-democracy-data` → `dbt-labs/dbt_utils`.

O parser lida com os formatos que de fato aparecem, incluindo a renomeação `tests:` →
`data_tests:` introduzida no dbt 1.8, que um parser ingênuo perderia inteira.

---

## 7. O que o relatório vai produzir

- distribuição dos projetos pelas cinco pilhas (`Z` sem controle até `D` completa)
- presença de cada camada isoladamente, não exclusiva
- cobertura de modelos por teste: mediana, p25, p75; e fração de projetos com zero testes
- ranking dos testes mais declarados
- pacotes de teste em uso e sua penetração
- a linha que fecha o argumento: **quantos projetos declaram apenas controles que o
  experimento mostrou detectarem zero de nove defeitos semânticos**

---

## 8. Ameaças de validade a declarar

1. **Projetos públicos não representam projetos corporativos.** Pipeline de banco não vai
   para o GitHub. A direção do viés é discutível e precisa ser argumentada, não assumida:
   projetos públicos podem ser mais bem testados (vitrine) ou menos (lado de hobby).
   Declare como limitação aberta, sem escolher a direção sem evidência.
2. **A heurística E5 de material didático erra.** Confira 30 exclusões manualmente.
3. **A heurística de reconciliação em teste singular superestima C4.** Limite superior.
4. **Teste declarado não é teste executado.** O instrumento lê declaração, não execução
   em CI. Um projeto pode declarar testes e nunca rodar `dbt build`. Medir execução exigiria
   ler configuração de CI — extensão possível, e provavelmente valiosa.
5. **O frame depende da busca de código do GitHub**, que não documenta completude nem
   critério de indexação.

---

## 9. Próximos passos depois da coleta

1. Rodar as quatro fases e conferir o relatório
2. Conferência manual das duas heurísticas (itens 2 e 3 acima)
3. Com o número em mãos, reescrever o achado central do artigo na forma
   "X% dos projetos dbt públicos declaram apenas controles que não detectam nenhum dos
   nove mecanismos de defeito testados"
4. Busca sistemática (pendência 3 do documento do tema) para confirmar que esta mineração
   específica não foi feita antes — **sem isso não se afirma ineditismo**

---

*Instrumento: `minerar_cobertura_dbt.py`. Aferido em 27/10/2026 com autoteste de gabarito
conhecido (10/10) e contra YAML real de `dbt-labs/jaffle_shop`, `cal-itp/data-infra` e
`bgarcevic/danish-democracy-data`. Frame candidato inicial obtido de
`InfuseAI/awesome-public-dbt-projects` (21 repositórios) — usado apenas para aferir o
parser, jamais como amostra, por ser lista curada e portanto enviesada.*
