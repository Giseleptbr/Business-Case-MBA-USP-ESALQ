"""
Experimento II — escada de oráculos, verdadeiros negativos e curva de falso positivo.

Business Case MBA USP/ESALQ em Engenharia de Software — Gisele Fonseca de Aguiar Silva
Executado em 29/10/2026. Sucede `viab_llm_silencioso.py`, que permanece intacto como
proveniência das Tabelas 1 a 4. Este script NÃO o substitui: acrescenta três medições
que a revisão sistemática da literatura mostrou serem exigidas pelo campo.

O QUE ESTE SCRIPT ACRESCENTA

  1. EXECUÇÃO LIMPA (variante D0). O experimento anterior só submetia aos controles as
     variantes defeituosas, de modo que havia apenas verdadeiros positivos e falsos
     negativos. Sem verdadeiro negativo não há precisão, não há especificidade e não há
     matriz de confusão — e a literatura comparável (Redyuk et al., EDBT 2021; Tu et al.,
     KDD '23) reporta matriz de confusão e precisão/revocação por tipo de defeito.

  2. DERIVA LEGÍTIMA. Uma execução limpa sobre um cenário idêntico ao de calibração
     jamais dispara qualquer controle, e a taxa de falso positivo sairia zero por
     construção, o que não é resultado, é artefato. Introduz-se portanto variação de
     negócio legítima entre o período de calibração e o período medido: deslocamento do
     mix de alíquota e elevação do frete. Nenhuma delas é defeito. É essa variação que
     cria a possibilidade real de alarme falso e permite levantar a curva de
     precisão contra revocação.

  3. ESCADA DE ORÁCULOS. Cada variante é avaliada sob quatro oráculos de severidade
     crescente, o que quantifica o que cada um deixa passar:
       (a) exceção de execução        — o oráculo do PrismaDV
       (b) igualdade exata de tabela  — o oráculo do ELT-Bench
       (c) igualdade de contagem      — o controle barato usual
       (d) magnitude do erro na métrica de negócio — o oráculo deste trabalho

GERAÇÃO DOS DADOS: ver docstring de `gerar_cenario`. Procedimentos estatísticos
declarados, conforme exigência do manual para dado simulado.
"""

import numpy as np
import pandas as pd
import duckdb

# O catálogo de defeitos, o SQL de referência e os parâmetros do cenário vêm do
# Experimento I, de modo que exista UMA única definição de cada um. O gerador é
# redefinido aqui porque precisa do parâmetro de deriva.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import viab_llm_silencioso as exp1

N_CONTAS = exp1.N_CONTAS
N_PEDIDOS = exp1.N_PEDIDOS
JANELA_DIAS = exp1.JANELA_DIAS
DATA_INICIO = exp1.DATA_INICIO
P_CANCELADO = exp1.P_CANCELADO
P_PENDENTE = exp1.P_PENDENTE
P_STATUS_NULO_BASE = exp1.P_STATUS_NULO_BASE
K_CORRELACAO = exp1.K_CORRELACAO
P_ITEM_DUPLICADO = exp1.P_ITEM_DUPLICADO
P_PEDIDO_SEM_ITEM = exp1.P_PEDIDO_SEM_ITEM
DEFEITOS = exp1.DEFEITOS
REFERENCIA = exp1.REFERENCIA
JAN_INI, JAN_FIM = exp1.JAN_INI, exp1.JAN_FIM
metricas = exp1.metricas
TOL_C1 = exp1.TOL_C1

# Níveis de deriva legítima avaliados. 0,00 reproduz o cenário de calibração.
DERIVAS = [0.00, 0.02, 0.05, 0.10, 0.20]

# Bandas de tolerância varridas para a reconciliação de valor (C4).
BANDAS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]

SEMENTES = range(1, 31)


def gerar_cenario(seed, deriva=0.0):
    """
    Gera pedidos e itens com verdade conhecida por construção.

    Procedimentos estatísticos (idênticos aos do Experimento I):
      - porte da conta: lognormal(mu=0, sigma=0,8), normalizado pela média
      - alocação de pedidos: multinomial com probabilidade proporcional ao porte
      - carimbo de tempo: uniforme discreta sobre os 90 dias da janela
      - itens por pedido: 1 + Poisson(lambda=2); quantidade: 1 + Poisson(lambda=1)
      - preço unitário: lognormal(mu=3,2; sigma=0,7) escalado pelo porte
      - desconto: uniforme discreta sobre {0; 0,05; 0,10; 0,15}
      - status: multinomial(cancelado 0,08; pendente 0,07; concluído 0,85)
      - status ausente: Bernoulli com p = 0,030·(1 + 0,90z), z truncado em [-1; 3]
      - duplicação de item: Bernoulli(0,02); pedido sem item: Bernoulli(0,03)

    DERIVA LEGÍTIMA (parâmetro `deriva`, acréscimo deste experimento). Representa
    variação de negócio entre o período de calibração dos controles e o período
    medido. NÃO é defeito. Atua por dois canais distintos, de propósito:

      CANAL 1 — total declarado pela origem (atinge C4, a reconciliação de valor)
        - alíquota por conta: uniforme em [0,07 + d ; 0,15 + d]
        - frete por pedido: lognormal(mu=2,3 + d; sigma=0,6)
        Elevam o total declarado sem alterar o valor líquido, de modo que a razão
        de reconciliação se afasta da razão calibrada sem que exista erro.

      CANAL 2 — nível de preço (atinge C5, a verificação distribucional)
        - preço unitário multiplicado por (1 + d), representando inflação de preço
        Desloca a distribuição do faturamento por pedido sem que exista erro: a
        verdade é recalculada sobre o mesmo deslocamento, de modo que o erro
        relativo de uma execução limpa continua sendo zero.

    Os dois canais são separáveis por construção, porque C4 observa apenas a razão
    entre o total apurado e o total declarado, e C5 observa apenas a distribuição
    do faturamento apurado. Há um acoplamento residual: ao elevar o valor líquido,
    o canal 2 reduz o peso relativo do frete e eleva levemente a razão de C4. O
    efeito é de segunda ordem e está declarado como limitação.
    """
    rng = np.random.default_rng(seed)

    porte = rng.lognormal(0.0, 0.8, N_CONTAS)
    porte = porte / porte.mean()
    contas = pd.DataFrame({"account_id": np.arange(1, N_CONTAS + 1), "porte": porte})

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

    order_id_rep = np.repeat(orders["order_id"].values, n_itens)
    porte_rep = contas.set_index("account_id").loc[
        np.repeat(orders["account_id"].values, n_itens), "porte"].values
    m = len(order_id_rep)

    qty = 1 + rng.poisson(1.0, size=m)
    # canal 2 da deriva: inflação legítima de preço
    unit_price = rng.lognormal(3.2, 0.7, size=m) * porte_rep * (1.0 + deriva)
    discount = rng.choice([0.0, 0.05, 0.10, 0.15], size=m)

    items = pd.DataFrame({
        "item_id": np.arange(1, m + 1), "order_id": order_id_rep,
        "sku": rng.integers(1000, 9999, size=m), "qty": qty,
        "unit_price": np.round(unit_price, 2), "discount_pct": discount,
    })
    items["linha_liquida"] = items["qty"] * items["unit_price"] * (1 - items["discount_pct"])

    valor_pedido = items.groupby("order_id")["linha_liquida"].sum()
    orders["valor_verdadeiro"] = orders["order_id"].map(valor_pedido).fillna(0.0)

    # --- total declarado pela origem, COM deriva legítima ----------------------
    aliq_conta = dict(zip(contas["account_id"],
                          rng.uniform(0.07 + deriva, 0.15 + deriva, N_CONTAS)))
    aliquota = orders["account_id"].map(aliq_conta).values
    frete = rng.lognormal(2.3 + deriva, 0.6, N_PEDIDOS)
    frete[n_itens == 0] = 0.0
    orders["declared_total"] = np.round(
        orders["valor_verdadeiro"].values * (1 + aliquota) + frete, 2)

    # --- status ausente, correlacionado ao valor -------------------------------
    v = orders["valor_verdadeiro"].values
    z = np.clip((v - v.mean()) / (v.std() + 1e-9), -1.0, 3.0)
    p_nulo = np.clip(P_STATUS_NULO_BASE * (1.0 + K_CORRELACAO * z), 0.0, 0.95)
    elegivel = orders["status"].values != "cancelled"
    virou_nulo = (rng.random(N_PEDIDOS) < p_nulo) & elegivel
    orders["status_origem"] = orders["status"]
    orders.loc[virou_nulo, "status"] = None

    dup = items[rng.random(len(items)) < P_ITEM_DUPLICADO].copy()
    items_raw = pd.concat([items, dup], ignore_index=True)

    atraso = rng.integers(1, 8, size=N_PEDIDOS)
    orders["ship_ts"] = orders["order_ts"] + pd.to_timedelta(atraso, unit="D")

    raw_orders = orders[["order_id", "account_id", "order_ts", "ship_ts",
                         "status", "declared_total"]].copy()
    raw_items = items_raw[["item_id", "order_id", "sku", "qty",
                           "unit_price", "discount_pct"]].copy()

    valido = orders["status_origem"].values != "cancelled"
    verdade = orders.loc[valido, ["order_id", "account_id", "valor_verdadeiro"]].copy()
    verdade = verdade.rename(columns={"valor_verdadeiro": "revenue"})
    return raw_orders, raw_items, verdade, contas


# ----------------------------------------------------------------------------------
# ESCADA DE ORÁCULOS
# ----------------------------------------------------------------------------------
def oraculos(gold, gold_ref, excecao):
    """Avalia a saída sob quatro oráculos de severidade crescente."""
    if gold is None:
        return dict(orac_excecao=True, orac_tabela=True,
                    orac_contagem=True, _n=0)

    # (a) exceção de execução — oráculo do PrismaDV
    o_exc = excecao is not None

    # (b) igualdade exata de tabela — oráculo do ELT-Bench
    a = gold[["order_id", "revenue"]].sort_values("order_id").reset_index(drop=True)
    b = gold_ref[["order_id", "revenue"]].sort_values("order_id").reset_index(drop=True)
    if len(a) != len(b) or not a["order_id"].equals(b["order_id"]):
        o_tab = True
    else:
        o_tab = not np.allclose(a["revenue"].astype(float),
                                b["revenue"].astype(float), rtol=1e-9, atol=1e-6)

    # (c) igualdade de contagem de linhas
    o_cnt = len(gold) != len(gold_ref)

    return dict(orac_excecao=o_exc, orac_tabela=o_tab,
                orac_contagem=o_cnt, _n=len(gold))


# ----------------------------------------------------------------------------------
# CONTROLES — idênticos ao Experimento I, com C4 devolvendo o desvio bruto para que
# a banda de tolerância possa ser varrida a posteriori, sem reexecutar nada.
# ----------------------------------------------------------------------------------
def perfil_distribucional(gold):
    """Analisadores no estilo Deequ/TFDV sobre a coluna de medida."""
    r = gold["revenue"].astype(float)
    return dict(n=len(r), completude=float(r.notna().mean()),
                media=float(r.mean()), desvio=float(r.std()),
                mediana=float(r.median()), maximo=float(r.max()),
                amostra=r.sample(min(len(r), 5000), random_state=0).to_numpy())


def controle_distribucional(gold, perfil_cal):
    """
    C5 — verificação distribucional por coluna, calibrada em período saudável.

    Reproduz a família de verificações que a literatura comparável avalia
    (Deequ, TensorFlow Data Validation, Auto-Validate): tamanho, completude,
    média, desvio-padrão, mediana e máximo contra os valores calibrados, mais
    um teste de duas amostras de Kolmogorov-Smirnov contra a amostra calibrada.

    Devolve os desvios BRUTOS, para que a banda de tolerância possa ser varrida
    a posteriori sem reexecutar o experimento, tal como se faz para C4.
    """
    from scipy import stats as _st
    p = perfil_distribucional(gold)

    def rel(a, b):
        return abs(a - b) / abs(b) if b else (0.0 if a == b else np.inf)

    desvios = {
        "C5_dev_tamanho": rel(p["n"], perfil_cal["n"]),
        "C5_dev_media": rel(p["media"], perfil_cal["media"]),
        "C5_dev_desvio": rel(p["desvio"], perfil_cal["desvio"]),
        "C5_dev_mediana": rel(p["mediana"], perfil_cal["mediana"]),
        "C5_dev_maximo": rel(p["maximo"], perfil_cal["maximo"]),
    }
    desvios["C5_incompleto"] = bool(p["completude"] < 1.0)
    ks = _st.ks_2samp(p["amostra"], perfil_cal["amostra"])
    desvios["C5_ks_stat"] = float(ks.statistic)
    desvios["C5_ks_p"] = float(ks.pvalue)
    desvios["C5_desvio_max"] = float(max(v for k, v in desvios.items()
                                         if k.startswith("C5_dev_")))
    return desvios


def controles(gold, contas, con, razao_calibrada):
    res = {}
    esperado = con.execute(f"""
        SELECT COUNT(DISTINCT order_id) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0]
    obtido = gold["order_id"].nunique()
    res["C1_contagem"] = bool(abs(obtido - esperado) / max(esperado, 1) > TOL_C1)

    res["C2_genericos"] = bool(
        gold["order_id"].duplicated().any() or gold["order_id"].isna().any()
        or gold["revenue"].isna().any()
        or (~gold["account_id"].isin(contas["account_id"])).any()
        or (gold["revenue"].astype(float) < 0).any())

    esperadas = {"order_id", "account_id", "order_date", "revenue"}
    res["C3_schema"] = bool(not (esperadas.issubset(set(gold.columns))
                                 and pd.api.types.is_numeric_dtype(gold["revenue"])))

    total_origem = con.execute(f"""
        SELECT SUM(declared_total) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0] or 0.0
    razao = float(gold["revenue"].sum()) / total_origem if total_origem else np.nan
    desvio = abs(razao - razao_calibrada) / razao_calibrada if razao_calibrada else np.nan
    res["C4_desvio_razao"] = float(desvio) if np.isfinite(desvio) else np.nan
    return res


# ----------------------------------------------------------------------------------
def calibrar(seed):
    """
    Calibra os controles em período saudável (sem deriva, sem defeito).
    Devolve a razão gold/origem usada por C4 e o perfil distribucional usado por C5.
    """
    raw_orders, raw_items, _, _ = gerar_cenario(seed, deriva=0.0)
    con = duckdb.connect()
    con.register("raw_orders", raw_orders); con.register("raw_items", raw_items)
    gold_ref = con.execute(REFERENCIA).df()
    tot = con.execute(f"""
        SELECT SUM(declared_total) FROM raw_orders
        WHERE (status IS NULL OR status <> 'cancelled')
          AND order_ts >= {JAN_INI} AND order_ts < DATE {JAN_FIM} + INTERVAL 1 DAY
    """).fetchone()[0] or 0.0
    con.close()
    razao = float(gold_ref["revenue"].sum()) / tot if tot else np.nan
    return razao, perfil_distribucional(gold_ref)


def rodar(seed, deriva, razao_calibrada, perfil_cal):
    raw_orders, raw_items, verdade, contas = gerar_cenario(seed, deriva)
    con = duckdb.connect()
    con.register("raw_orders", raw_orders); con.register("raw_items", raw_items)

    m_verdade = metricas(verdade)
    gold_ref = con.execute(REFERENCIA).df()

    variantes = {"D0_sem_defeito": REFERENCIA}
    variantes.update({k: v["sql"] for k, v in DEFEITOS.items()})

    linhas = []
    for nome, sql in variantes.items():
        try:
            gold, exc = con.execute(sql).df(), None
        except Exception as e:
            gold, exc = None, f"{type(e).__name__}: {e}"

        reg = {"seed": seed, "deriva": deriva, "variante": nome,
               "com_defeito": nome != "D0_sem_defeito", "excecao": exc}
        reg.update(oraculos(gold, gold_ref, exc))

        if gold is not None:
            m = metricas(gold)
            for k in m_verdade:
                base = m_verdade[k]
                reg[f"err_{k}"] = (m[k] - base) / base * 100 if base else np.nan
            reg["abs_SUM"] = m["SUM_faturamento"] - m_verdade["SUM_faturamento"]
            reg.update(controles(gold, contas, con, razao_calibrada))
            reg.update(controle_distribucional(gold, perfil_cal))
        linhas.append(reg)

    con.close()
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    print("Calibrando os controles em período saudável (deriva = 0)...")
    cal = {s: calibrar(s) for s in SEMENTES}
    print(f"  razão média gold/origem (C4): "
          f"{np.mean([c[0] for c in cal.values()]):.6f}")
    print(f"  média calibrada do faturamento por pedido (C5): "
          f"{np.mean([c[1]['media'] for c in cal.values()]):,.2f}")

    todas = []
    for d in DERIVAS:
        for s in SEMENTES:
            todas.append(rodar(s, d, cal[s][0], cal[s][1]))
        print(f"  deriva {d:.2f} concluída")
    res = pd.concat(todas, ignore_index=True)
    res.to_csv("resultado_oraculos.csv", index=False)
    print(f"\nExecuções: {len(res)} "
          f"({res['seed'].nunique()} sementes x {len(DERIVAS)} derivas "
          f"x {res['variante'].nunique()} variantes)")
    print("Salvo em resultado_oraculos.csv")
