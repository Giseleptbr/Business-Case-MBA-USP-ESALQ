"""
Teste de viabilidade — "Onde posicionar a validação quando a transformação é escrita por IA:
custo do erro silencioso em pipeline analítico."

Business Case MBA USP/ESALQ em Engenharia de Software — Gisele Fonseca de Aguiar Silva
Executado em 27/10/2026.

PERGUNTA DE VIABILIDADE
  Quando um modelo de transformação com defeito semântico (do tipo que a literatura de
  text-to-SQL documenta) roda em pipeline analítico, (a) ele executa sem exceção?
  (b) o dano às métricas de negócio tem dispersão mensurável? (c) os controles usuais
  de qualidade de dados o detectam?

CRITÉRIO DE APROVAÇÃO
  O tema avança se existir ao menos um subconjunto de defeitos que executa em silêncio,
  produz erro material, E passa por todas as camadas de controle testadas.
  Se todos os controles pegarem tudo, a pergunta de gestão esvazia e o tema morre.

GERAÇÃO DE DADOS (procedimentos declarados, conforme exigido pelo manual do curso)
  Ver docstring de `gerar_cenario`.
"""

import numpy as np
import pandas as pd
import duckdb

# ----------------------------------------------------------------------------------
# PARÂMETROS DO CENÁRIO
# ----------------------------------------------------------------------------------
N_CONTAS = 100
N_PEDIDOS = 30_000
JANELA_DIAS = 90
DATA_INICIO = pd.Timestamp("2026-01-01")

# status de origem
P_CANCELADO = 0.08
P_PENDENTE = 0.07
# status ausente (lacuna de ingestão) — probabilidade CRESCENTE com o valor do pedido,
# reproduzindo o mecanismo de falha correlacionada já validado em 21/10/2026
P_STATUS_NULO_BASE = 0.030
K_CORRELACAO = 0.90

# dupla carga de itens (defeito real da origem, exige dedup a jusante)
P_ITEM_DUPLICADO = 0.02

# pedidos válidos sem nenhum item (receita legitimamente zero)
P_PEDIDO_SEM_ITEM = 0.03


def gerar_cenario(seed):
    """
    Gera um cenário sintético de pedidos e itens com verdade conhecida por construção.

    Procedimentos estatísticos:
      - porte da conta: lognormal(mu=0, sigma=0.8), normalizado pela média
      - alocação de pedidos às contas: multinomial com probabilidade proporcional ao porte
      - carimbo de tempo do pedido: uniforme discreto sobre os 90 dias da janela
      - itens por pedido: 1 + Poisson(lambda=2)
      - quantidade por item: 1 + Poisson(lambda=1)
      - preço unitário: lognormal(mu=3.2, sigma=0.7) escalado pelo porte da conta
      - desconto: uniforme discreto sobre {0, 0.05, 0.10, 0.15}
      - status: multinomial(cancelado=0.08, pendente=0.07, concluído=0.85)
      - status ausente: Bernoulli com p = 0.030 * (1 + 0.90 * z), z = valor padronizado
        do pedido truncado em [-1, 3]  → falha CORRELACIONADA ao valor
      - duplicação de item: Bernoulli(p=0.02), linha replicada com o MESMO item_id
      - pedido sem item: Bernoulli(p=0.03)

    Retorna (raw_orders, raw_items, verdade) onde `verdade` é calculada a partir do
    processo gerador, sem passar por SQL.
    """
    rng = np.random.default_rng(seed)

    # --- contas ---------------------------------------------------------------
    porte = rng.lognormal(0.0, 0.8, N_CONTAS)
    porte = porte / porte.mean()
    contas = pd.DataFrame({"account_id": np.arange(1, N_CONTAS + 1), "porte": porte})

    # --- pedidos --------------------------------------------------------------
    conta_do_pedido = rng.choice(N_CONTAS, size=N_PEDIDOS, p=porte / porte.sum()) + 1
    dia = rng.integers(0, JANELA_DIAS, size=N_PEDIDOS)
    hora = rng.integers(0, 24, size=N_PEDIDOS)
    order_ts = DATA_INICIO + pd.to_timedelta(dia, unit="D") + pd.to_timedelta(hora, unit="h")

    u = rng.random(N_PEDIDOS)
    status = np.where(u < P_CANCELADO, "cancelled",
             np.where(u < P_CANCELADO + P_PENDENTE, "pending", "completed"))

    sem_item = rng.random(N_PEDIDOS) < P_PEDIDO_SEM_ITEM
    n_itens = 1 + rng.poisson(2.0, size=N_PEDIDOS)
    n_itens[sem_item] = 0

    orders = pd.DataFrame({
        "order_id": np.arange(1, N_PEDIDOS + 1),
        "account_id": conta_do_pedido,
        "order_ts": order_ts,
        "status": status,
        "n_itens": n_itens,
    })

    # --- itens ----------------------------------------------------------------
    order_id_rep = np.repeat(orders["order_id"].values, n_itens)
    porte_rep = contas.set_index("account_id").loc[
        np.repeat(orders["account_id"].values, n_itens), "porte"
    ].values
    m = len(order_id_rep)

    qty = 1 + rng.poisson(1.0, size=m)
    unit_price = rng.lognormal(3.2, 0.7, size=m) * porte_rep
    discount = rng.choice([0.0, 0.05, 0.10, 0.15], size=m)

    items = pd.DataFrame({
        "item_id": np.arange(1, m + 1),
        "order_id": order_id_rep,
        "sku": rng.integers(1000, 9999, size=m),
        "qty": qty,
        "unit_price": np.round(unit_price, 2),
        "discount_pct": discount,
    })
    items["linha_liquida"] = items["qty"] * items["unit_price"] * (1 - items["discount_pct"])

    # valor verdadeiro do pedido (antes de qualquer duplicação)
    valor_pedido = items.groupby("order_id")["linha_liquida"].sum()
    orders["valor_verdadeiro"] = orders["order_id"].map(valor_pedido).fillna(0.0)

    # Total declarado pelo sistema de origem (cabeçalho denormalizado).
    # NÃO é oráculo: inclui imposto e frete, que o modelo analítico exclui de propósito.
    #   - alíquota por conta: uniforme em [0,07 ; 0,15]  (proxy de variação estadual)
    #   - frete por pedido:   lognormal(mu=2,3; sigma=0,6), zero em pedido sem item
    # Consequência: a reconciliação de valor contra a origem só opera com banda de
    # tolerância larga, e defeitos menores que a banda passam por ela.
    aliq_conta = dict(zip(contas["account_id"], rng.uniform(0.07, 0.15, N_CONTAS)))
    aliquota = orders["account_id"].map(aliq_conta).values
    frete = rng.lognormal(2.3, 0.6, N_PEDIDOS)
    frete[n_itens == 0] = 0.0
    orders["declared_total"] = np.round(
        orders["valor_verdadeiro"].values * (1 + aliquota) + frete, 2)

    # --- status ausente, CORRELACIONADO ao valor -------------------------------
    v = orders["valor_verdadeiro"].values
    z = np.clip((v - v.mean()) / (v.std() + 1e-9), -1.0, 3.0)
    p_nulo = np.clip(P_STATUS_NULO_BASE * (1.0 + K_CORRELACAO * z), 0.0, 0.95)
    # só pedidos NÃO cancelados perdem o status (o cancelamento vem de outro sistema)
    elegivel = orders["status"].values != "cancelled"
    virou_nulo = (rng.random(N_PEDIDOS) < p_nulo) & elegivel
    orders["status_origem"] = orders["status"]
    orders.loc[virou_nulo, "status"] = None

    # --- dupla carga de itens --------------------------------------------------
    dup = items[rng.random(len(items)) < P_ITEM_DUPLICADO].copy()
    items_raw = pd.concat([items, dup], ignore_index=True)

    # --- ship_ts: posterior ao pedido ------------------------------------------
    atraso = rng.integers(1, 8, size=N_PEDIDOS)
    orders["ship_ts"] = orders["order_ts"] + pd.to_timedelta(atraso, unit="D")

    raw_orders = orders[["order_id", "account_id", "order_ts", "ship_ts",
                         "status", "declared_total"]].copy()
    raw_items = items_raw[["item_id", "order_id", "sku", "qty",
                           "unit_price", "discount_pct"]].copy()

    # --- VERDADE, por construção ------------------------------------------------
    # Pedido conta como receita se NÃO foi cancelado na origem. Status ausente é
    # lacuna de ingestão, não cancelamento: o pedido é válido.
    valido = orders["status_origem"].values != "cancelled"
    verdade_pedidos = orders.loc[valido, ["order_id", "account_id", "valor_verdadeiro"]].copy()
    verdade_pedidos = verdade_pedidos.rename(columns={"valor_verdadeiro": "revenue"})

    return raw_orders, raw_items, verdade_pedidos, contas


# ----------------------------------------------------------------------------------
# CATÁLOGO DE DEFEITOS
# Cada variante é SQL executável. A âncora indica o tipo de erro na taxonomia publicada.
# ----------------------------------------------------------------------------------
JAN_INI = "'2026-01-01'"
JAN_FIM = "'2026-03-31'"   # 90 dias a partir de 01/01/2026 → último dia é 31/03

ITENS_DEDUP = """
    SELECT DISTINCT item_id, order_id, qty, unit_price, discount_pct FROM raw_items
"""

REFERENCIA = f"""
WITH itens AS ({ITENS_DEDUP}),
linhas AS (
    SELECT order_id, SUM(qty * unit_price * (1 - discount_pct)) AS valor
    FROM itens GROUP BY order_id
)
SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
       COALESCE(l.valor, 0) AS revenue
FROM raw_orders o
LEFT JOIN linhas l ON l.order_id = o.order_id
WHERE (o.status IS NULL OR o.status <> 'cancelled')
  AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
"""

DEFEITOS = {
    "D1_fanout_join": dict(
        ancora="erro de grão / fan-out — 'joining orders to order_items, then summing orders.total'",
        sql=f"""
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               SUM(o.declared_total) AS revenue
        FROM raw_orders o
        JOIN raw_items i ON i.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        GROUP BY 1,2,3
        """),

    "D2_inner_join": dict(
        ancora="erro de sintese — INNER em lugar de LEFT descarta pedidos sem item",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               l.valor AS revenue
        FROM raw_orders o
        JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D3_null_logica_tres_valores": dict(
        ancora="ma interpretacao do banco — logica de tres valores: status <> 'cancelled' descarta NULL",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE o.status <> 'cancelled'
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D4_valor_de_filtro_fabricado": dict(
        ancora="fabricated filter value — literal em caixa alta nunca casa; filtro vira no-op",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'CANCELLED')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D5_coluna_de_data_errada": dict(
        ancora="ma interpretacao do schema — filtra por ship_ts em lugar de order_ts",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.ship_ts >= {JAN_INI} AND o.ship_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D6_sem_dedup": dict(
        ancora="omissao de deduplicacao — dupla carga da origem contada duas vezes",
        sql=f"""
        WITH linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                        FROM raw_items GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D7_desconto_ignorado": dict(
        ancora="semantica de coluna errada — ignora discount_pct",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price) AS valor FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D8_preco_de_grao_errado": dict(
        ancora="erro de grao aritmetico — MAX(preco) * SUM(qtd) em pedido multi-item",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id,
                          MAX(unit_price) * SUM(qty) * (1 - MAX(discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts >= {JAN_INI} AND o.order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
        """),

    "D9_fronteira_de_janela": dict(
        ancora="fronteira de intervalo — BETWEEN sobre timestamp exclui o ultimo dia",
        sql=f"""
        WITH itens AS ({ITENS_DEDUP}),
        linhas AS (SELECT order_id, SUM(qty*unit_price*(1-discount_pct)) AS valor
                   FROM itens GROUP BY order_id)
        SELECT o.order_id, o.account_id, CAST(o.order_ts AS DATE) AS order_date,
               COALESCE(l.valor, 0) AS revenue
        FROM raw_orders o
        LEFT JOIN linhas l ON l.order_id = o.order_id
        WHERE (o.status IS NULL OR o.status <> 'cancelled')
          AND o.order_ts BETWEEN {JAN_INI} AND {JAN_FIM}
        """),
}


# ----------------------------------------------------------------------------------
# MÉTRICAS DE NEGÓCIO
# ----------------------------------------------------------------------------------
def metricas(gold):
    r = gold["revenue"].astype(float)
    por_conta = gold.groupby("account_id")["revenue"].sum()
    return {
        "SUM_faturamento": r.sum(),
        "AVG_ticket": r.mean() if len(r) else np.nan,
        "MEDIAN_ticket": r.median() if len(r) else np.nan,
        "P95_cauda": r.quantile(0.95) if len(r) else np.nan,
        "COUNT_pedidos": float(len(r)),
        "MAX_pedido": r.max() if len(r) else np.nan,
        "SUM_pior_conta": por_conta.max() if len(por_conta) else np.nan,
    }


# ----------------------------------------------------------------------------------
# CAMADAS DE CONTROLE
# C1  reconciliação de contagem de linhas (controle barato e mais comum)
# C2  testes genéricos estilo dbt: unique / not_null / relationships / accepted_values
# C3  teste de schema (colunas e tipos esperados)
# C4  reconciliação de valor contra total declarado pela origem (controle caro)
# ----------------------------------------------------------------------------------
TOL_C1 = 0.001   # 0,1% — reconciliação de contagem é exata, tolerância estreita
TOL_C4 = 0.05    # 5%  — reconciliação de valor contra origem imperfeita; a banda tem
                 #       de acomodar a deriva do mix de imposto e frete. 5% é generoso
                 #       para o padrão de mercado e ainda assim deixa defeitos passarem.


def controles(gold, raw_orders, contas, con, razao_calibrada):
    res = {}

    # --- C1: contagem de pedidos no gold vs contagem independente na origem -------
    esperado = con.execute(f"""
        SELECT COUNT(DISTINCT order_id) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0]
    obtido = gold["order_id"].nunique()
    desvio = abs(obtido - esperado) / max(esperado, 1)
    res["C1_reconciliacao_contagem"] = bool(desvio > TOL_C1)

    # --- C2: testes genéricos estilo dbt no grão do modelo -----------------------
    t_unique = gold["order_id"].duplicated().any()
    t_notnull_pk = gold["order_id"].isna().any()
    t_notnull_rev = gold["revenue"].isna().any()
    t_rel = (~gold["account_id"].isin(contas["account_id"])).any()
    t_nonneg = (gold["revenue"].astype(float) < 0).any()
    res["C2_dbt_generico"] = bool(t_unique or t_notnull_pk or t_notnull_rev or t_rel or t_nonneg)
    res["_C2_detalhe"] = dict(unique=bool(t_unique), not_null_pk=bool(t_notnull_pk),
                              not_null_revenue=bool(t_notnull_rev),
                              relationships=bool(t_rel), nao_negativo=bool(t_nonneg))

    # --- C3: schema ---------------------------------------------------------------
    esperadas = {"order_id", "account_id", "order_date", "revenue"}
    ok_cols = esperadas.issubset(set(gold.columns))
    ok_tipo = pd.api.types.is_numeric_dtype(gold["revenue"]) if "revenue" in gold else False
    res["C3_schema"] = bool(not (ok_cols and ok_tipo))

    # --- C4: reconciliação de valor contra o total declarado na origem ------------
    # A origem declara valor COM imposto e frete; o modelo analítico exclui ambos.
    # O controle real é uma razão calibrada: durante um período saudável a equipe
    # observou gold/origem ≈ razao_calibrada, e alerta quando a razão corrente
    # desvia mais que TOL_C4 dela.
    total_origem = con.execute(f"""
        SELECT SUM(declared_total) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0] or 0.0
    total_gold = float(gold["revenue"].sum())
    razao = total_gold / total_origem if total_origem else np.nan
    desvio_v = abs(razao - razao_calibrada) / razao_calibrada if razao_calibrada else np.nan
    res["C4_reconciliacao_valor"] = bool(desvio_v > TOL_C4)
    res["_C4_desvio_razao_%"] = float(desvio_v * 100) if np.isfinite(desvio_v) else np.nan

    return res


# ----------------------------------------------------------------------------------
# EXECUÇÃO
# ----------------------------------------------------------------------------------
def rodar(seed, verificar_harness=False):
    raw_orders, raw_items, verdade, contas = gerar_cenario(seed)
    con = duckdb.connect()
    con.register("raw_orders", raw_orders)
    con.register("raw_items", raw_items)

    m_verdade = metricas(verdade)

    # validação do harness: SQL de referência deve reproduzir a verdade construída
    gold_ref = con.execute(REFERENCIA).df()
    m_ref = metricas(gold_ref)

    # calibração do controle C4 com o pipeline saudável (razão gold/origem de referência)
    total_origem_ref = con.execute(f"""
        SELECT SUM(declared_total) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0] or 0.0
    razao_calibrada = float(gold_ref["revenue"].sum()) / total_origem_ref if total_origem_ref else np.nan
    if verificar_harness:
        print("--- verificacao do harness (referencia SQL vs verdade construida) ---")
        for k in m_verdade:
            d = (m_ref[k] - m_verdade[k]) / m_verdade[k] * 100 if m_verdade[k] else 0.0
            print(f"  {k:20s} verdade={m_verdade[k]:>18,.2f}  sql_ref={m_ref[k]:>18,.2f}  dif={d:+.6f}%")
        print()

    linhas = []
    for nome, d in DEFEITOS.items():
        try:
            gold = con.execute(d["sql"]).df()
            excecao = None
        except Exception as e:
            gold, excecao = None, f"{type(e).__name__}: {e}"

        reg = {"seed": seed, "defeito": nome, "ancora": d["ancora"],
               "excecao": excecao}

        if gold is None:
            linhas.append(reg)
            continue

        m = metricas(gold)
        for k in m_verdade:
            base = m_verdade[k]
            reg[f"err_{k}"] = (m[k] - base) / base * 100 if base else np.nan
        reg["abs_SUM"] = m["SUM_faturamento"] - m_verdade["SUM_faturamento"]
        reg.update(controles(gold, raw_orders, contas, con, razao_calibrada))
        linhas.append(reg)

    con.close()
    return pd.DataFrame(linhas), m_verdade


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 50)

    # 1) verificar harness com uma semente
    _, mv = rodar(42, verificar_harness=True)
    print(f"Faturamento verdadeiro (semente 42): R$ {mv['SUM_faturamento']:,.2f}  "
          f"em {int(mv['COUNT_pedidos']):,} pedidos\n")

    # 2) 30 sementes
    todas = []
    for s in range(1, 31):
        df, _ = rodar(s)
        todas.append(df)
    res = pd.concat(todas, ignore_index=True)
    res.to_csv("resultado_viab_llm.csv", index=False)
    print(f"Rodadas: {len(res)} ({res['seed'].nunique()} sementes x {res['defeito'].nunique()} defeitos)")
    print("Salvo em resultado_viab_llm.csv")
