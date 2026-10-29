"""
Análise do Experimento II — escada de oráculos, matriz de confusão e curva
de precisão contra revocação da reconciliação de valor.
"""
import numpy as np
import pandas as pd

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)

res = pd.read_csv("resultado_oraculos.csv")
BANDAS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
mets = ["err_SUM_faturamento", "err_AVG_ticket", "err_MEDIAN_ticket",
        "err_P95_cauda", "err_COUNT_pedidos", "err_SUM_pior_conta"]

print("=" * 110)
print("10. ESCADA DE ORÁCULOS — fração dos casos em que cada oráculo acusa o defeito")
print("    (somente variantes COM defeito, todas as derivas)")
print("=" * 110)
d = res[res["com_defeito"]]
esc = d.groupby("variante", sort=False).agg(
    exececao=("orac_excecao", "mean"),
    igualdade_tabela=("orac_tabela", "mean"),
    igualdade_contagem=("orac_contagem", "mean"),
    erro_SUM_medio=("err_SUM_faturamento", "mean"))
esc.columns = ["(a) excecao", "(b) tabela", "(c) contagem", "erro SUM %"]
print(esc.to_string(float_format=lambda x: f"{x:,.3f}"))
print(f"\n  (a) oráculo de exceção     — usado pelo PrismaDV   : acusa "
      f"{d['orac_excecao'].mean():.1%} dos defeitos")
print(f"  (b) igualdade de tabela    — usada pelo ELT-Bench  : acusa "
      f"{d['orac_tabela'].mean():.1%} dos defeitos, sem dizer o quanto")
print(f"  (c) igualdade de contagem  — controle barato usual : acusa "
      f"{d['orac_contagem'].mean():.1%} dos defeitos")
print(f"  (d) magnitude na métrica   — este trabalho         : "
      f"amplitude de {d['err_SUM_faturamento'].min():+.2f}% a "
      f"{d['err_SUM_faturamento'].max():+.2f}%")

print()
print("=" * 110)
print("11. MATRIZ DE CONFUSÃO POR CAMADA — agora com verdadeiros negativos")
print("    positivo = o controle disparou | condição = a variante tinha defeito")
print("=" * 110)
# C5 dispara se qualquer desvio distribucional exceder a banda, se o teste de
# Kolmogorov-Smirnov rejeitar a 1%, ou se houver incompletude na medida.
BANDA_C5, ALFA_KS = 0.05, 0.01
res["C5_disparo"] = ((res["C5_desvio_max"] > BANDA_C5)
                     | (res["C5_ks_p"] < ALFA_KS)
                     | (res["C5_incompleto"] == True))

linhas = []
for cam, col in [("C1_contagem", "C1_contagem"), ("C2_genericos", "C2_genericos"),
                 ("C3_schema", "C3_schema")]:
    tp = int(((res["com_defeito"]) & (res[col] == True)).sum())
    fn = int(((res["com_defeito"]) & (res[col] == False)).sum())
    fp = int(((~res["com_defeito"]) & (res[col] == True)).sum())
    tn = int(((~res["com_defeito"]) & (res[col] == False)).sum())
    linhas.append(dict(camada=cam, VP=tp, FN=fn, FP=fp, VN=tn,
                       revocacao=tp / (tp + fn) if tp + fn else np.nan,
                       especificidade=tn / (tn + fp) if tn + fp else np.nan,
                       taxa_falso_positivo=fp / (tn + fp) if tn + fp else np.nan))
# C4 avaliada na banda de referência de 5%
col4 = res["C4_desvio_razao"] > 0.05
tp = int(((res["com_defeito"]) & col4).sum()); fn = int(((res["com_defeito"]) & ~col4).sum())
fp = int(((~res["com_defeito"]) & col4).sum()); tn = int(((~res["com_defeito"]) & ~col4).sum())
linhas.append(dict(camada="C4_valor (banda 5%)", VP=tp, FN=fn, FP=fp, VN=tn,
                   revocacao=tp / (tp + fn), especificidade=tn / (tn + fp),
                   taxa_falso_positivo=fp / (tn + fp)))
col5 = res["C5_disparo"]
tp = int(((res["com_defeito"]) & col5).sum()); fn = int(((res["com_defeito"]) & ~col5).sum())
fp = int(((~res["com_defeito"]) & col5).sum()); tn = int(((~res["com_defeito"]) & ~col5).sum())
linhas.append(dict(camada="C5_distribucional (5%)", VP=tp, FN=fn, FP=fp, VN=tn,
                   revocacao=tp / (tp + fn), especificidade=tn / (tn + fp),
                   taxa_falso_positivo=fp / (tn + fp)))
print(pd.DataFrame(linhas).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
print("\n  Observação: a precisão depende da prevalência de defeitos, que aqui é")
print("  artificial (9 variantes defeituosas para 1 limpa). Revocação, especificidade")
print("  e taxa de falso positivo não dependem da prevalência e são as reportadas.")

print()
print("=" * 110)
print("12. FALSO POSITIVO SOB DERIVA LEGÍTIMA — execução limpa (D0), por nível de deriva")
print("    nenhum defeito presente: todo disparo aqui é alarme falso")
print("=" * 110)
limpo = res[~res["com_defeito"]]
tab = limpo.groupby("deriva").agg(
    C1=("C1_contagem", "mean"), C2=("C2_genericos", "mean"),
    C3=("C3_schema", "mean"),
    C4_banda5=("C4_desvio_razao", lambda s: (s > 0.05).mean()),
    C5_banda5=("C5_disparo", "mean"),
    desvio_C4=("C4_desvio_razao", "mean"),
    desvio_C5=("C5_desvio_max", "mean"))
print(tab.to_string(float_format=lambda x: f"{x:,.4f}"))
print("\n  C1, C2 e C3 nunca geram alarme falso, em nenhum nível de deriva.")
print("  C4 reage ao canal de total declarado; C5 reage ao canal de nível de preço.")
print("  Os dois canais são separáveis por construção — ver docstring do gerador.")

print()
print("=" * 110)
print("13. CURVA PRECISÃO × REVOCAÇÃO DA RECONCILIAÇÃO DE VALOR (C4)")
print("    varrida sobre a banda de tolerância, agregando todas as derivas")
print("=" * 110)
rows = []
for b in BANDAS:
    disparo = res["C4_desvio_razao"] > b
    tp = int(((res["com_defeito"]) & disparo).sum())
    fn = int(((res["com_defeito"]) & ~disparo).sum())
    fp = int(((~res["com_defeito"]) & disparo).sum())
    tn = int(((~res["com_defeito"]) & ~disparo).sum())
    rec = tp / (tp + fn) if tp + fn else np.nan
    prec = tp / (tp + fp) if tp + fp else np.nan
    tfp = fp / (tn + fp) if tn + fp else np.nan
    rows.append(dict(banda=f"{b:.1%}", VP=tp, FN=fn, FP=fp, VN=tn,
                     revocacao=rec, taxa_falso_positivo=tfp,
                     precisao_aparente=prec,
                     F1=2 * prec * rec / (prec + rec) if prec and rec else np.nan))
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

print()
print("=" * 110)
print("14. O TRADE-OFF, POR NÍVEL DE DERIVA — revocação e falso positivo lado a lado")
print("=" * 110)
rows = []
for b in BANDAS:
    r = {"banda": f"{b:.1%}"}
    for dv in sorted(res["deriva"].unique()):
        sub = res[res["deriva"] == dv]
        disp = sub["C4_desvio_razao"] > b
        com, sem = sub["com_defeito"], ~sub["com_defeito"]
        rec = (com & disp).sum() / com.sum() if com.sum() else np.nan
        tfp = (sem & disp).sum() / sem.sum() if sem.sum() else np.nan
        r[f"d={dv:.2f} rev"] = rec
        r[f"d={dv:.2f} TFP"] = tfp
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

print()
print("=" * 110)
print("15. DEFEITOS QUE ATRAVESSAM TODAS AS CAMADAS, por nível de deriva (banda 5%)")
print("=" * 110)
res["qualquer"] = (res["C1_contagem"] | res["C2_genericos"] | res["C3_schema"]
                   | (res["C4_desvio_razao"] > 0.05))
sil = res[res["com_defeito"] & ~res["qualquer"]]
if len(sil) == 0:
    print("  nenhum")
else:
    g = sil.groupby(["deriva", "variante"]).agg(
        n=("seed", "count"), erro_SUM=("err_SUM_faturamento", "mean"),
        erro_P95=("err_P95_cauda", "mean"), reais=("abs_SUM", "mean"))
    print(g.to_string(float_format=lambda x: f"{x:,.2f}"))

print()
print("=" * 110)
print("16. A FRONTEIRA DETECÇÃO × ALARME FALSO — ordenada por revocação")
print("    responde à objeção de que só se testaram controles fracos")
print("=" * 110)
fr = []
for nome, col, custo in [
        ("C2 testes genéricos de forma", res["C2_genericos"], "baixo"),
        ("C3 esquema e contrato", res["C3_schema"], "baixo"),
        ("C1 reconciliação de contagem", res["C1_contagem"], "baixo"),
        ("C4 reconciliação de valor", res["C4_desvio_razao"] > 0.05, "alto"),
        ("C5 verificação distribucional", res["C5_disparo"], "médio")]:
    com, sem = res["com_defeito"], ~res["com_defeito"]
    rec = (com & col).sum() / com.sum()
    tfp = (sem & col).sum() / sem.sum()
    fr.append(dict(camada=nome, custo_implantacao=custo,
                   revocacao=rec, taxa_falso_positivo=tfp))
fr = pd.DataFrame(fr).sort_values("revocacao")
print(fr.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
print()
print("  A ordenação por revocação é EXATAMENTE a ordenação por taxa de falso")
print("  positivo. Nenhuma camada domina outra: detecção é comprada com alarme")
print("  falso, de forma monotônica. A exceção é C1, que detecta dois terços dos")
print("  defeitos sem gerar um único alarme falso — e é a de menor custo.")

print()
print("=" * 110)
print("17. O QUE C5 PEGA QUE AS CAMADAS BARATAS NÃO PEGAM")
print("=" * 110)
barato = res["C1_contagem"] | res["C2_genericos"] | res["C3_schema"]
g = res[res["com_defeito"]].groupby("variante", sort=False).apply(
    lambda d: pd.Series({
        "pilha_barata": barato[d.index].mean(),
        "C5": d["C5_disparo"].mean(),
        "erro_SUM_%": d["err_SUM_faturamento"].mean()}), include_groups=False)
g["ganho_C5"] = g["C5"] - g["pilha_barata"]
print(g.sort_values("ganho_C5", ascending=False).to_string(
    float_format=lambda x: f"{x:,.3f}"))
print()
print("  D7 e D8 são o caso decisivo: a pilha barata não os vê (preservam a")
print("  contagem de linhas) e C5 os vê sempre. São também os de maior erro")
print("  monetário. É o argumento mais forte a favor da camada distribucional —")
print("  e a razão pela qual o trabalho NÃO pode afirmar que todo controle falha.")
