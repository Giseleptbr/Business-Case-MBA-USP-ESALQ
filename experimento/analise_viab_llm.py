import pandas as pd
import numpy as np

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)

res = pd.read_csv("resultado_viab_llm.csv")
ctrl = ["C1_reconciliacao_contagem", "C2_dbt_generico", "C3_schema", "C4_reconciliacao_valor"]
mets = ["err_SUM_faturamento", "err_AVG_ticket", "err_MEDIAN_ticket",
        "err_P95_cauda", "err_COUNT_pedidos", "err_SUM_pior_conta"]

print("=" * 150)
print("1. EXECUCAO E DANO — media de 30 sementes, desvio-padrao entre parenteses")
print("=" * 150)
rows = []
for d, g in res.groupby("defeito", sort=False):
    r = {"defeito": d,
         "excecao": "SIM" if g["excecao"].notna().any() else "nao"}
    for m in mets:
        r[m.replace("err_", "")] = f"{g[m].mean():+8.3f} ({g[m].std():.3f})"
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 150)
print("2. MATRIZ DEFEITO x CONTROLE — fracao das 30 sementes em que o controle disparou")
print("=" * 150)
mat = res.groupby("defeito", sort=False)[ctrl].mean()
mat["ALGUM_controle"] = res.groupby("defeito", sort=False)[ctrl].any(axis=1).groupby(res["defeito"]).mean() \
    if False else res.assign(algum=res[ctrl].any(axis=1)).groupby("defeito", sort=False)["algum"].mean()
mat["erro_SUM_medio_%"] = res.groupby("defeito", sort=False)["err_SUM_faturamento"].mean()
mat["erro_abs_SUM_R$"] = res.groupby("defeito", sort=False)["abs_SUM"].mean()
print(mat.to_string(float_format=lambda x: f"{x:,.3f}"))

print()
print("=" * 150)
print("3. DEFEITOS QUE PASSAM TOTALMENTE SILENCIOSOS (nenhuma excecao, nenhum controle)")
print("=" * 150)
res["algum_controle"] = res[ctrl].any(axis=1)
sil = res[(res["excecao"].isna()) & (~res["algum_controle"])]
if len(sil) == 0:
    print(">>> NENHUM. Todos os defeitos foram detectados por alguma camada. TEMA REPROVADO.")
else:
    g = sil.groupby("defeito", sort=False).agg(
        sementes_silenciosas=("seed", "nunique"),
        erro_SUM=("err_SUM_faturamento", "mean"),
        erro_AVG=("err_AVG_ticket", "mean"),
        erro_P95=("err_P95_cauda", "mean"),
        erro_COUNT=("err_COUNT_pedidos", "mean"),
        erro_pior_conta=("err_SUM_pior_conta", "mean"),
        reais=("abs_SUM", "mean"))
    print(g.to_string(float_format=lambda x: f"{x:,.3f}"))

print()
print("=" * 150)
print("4. CEGUEIRA POR CAMADA — materialidade por METRICA: defeito e material se")
print("   QUALQUER metrica de negocio erra mais de 1% em media")
print("=" * 150)
med = res.groupby("defeito", sort=False)[mets].mean()
materiais = med.index[(med.abs() > 1.0).any(axis=1)].tolist()
print(f"Defeitos materiais ({len(materiais)} de {res['defeito'].nunique()}): {materiais}\n")
mat_def = res[res["defeito"].isin(materiais)]
for c in ctrl + ["algum_controle"]:
    pega = sorted(mat_def[mat_def[c].astype(bool)]["defeito"].unique())
    passa = sorted(set(materiais) - set(pega))
    print(f"{c}")
    print(f"   detecta : {pega if pega else '(nenhum)'}")
    print(f"   e cego a: {passa if passa else '(nenhum)'}\n")

print()
print("=" * 150)
print("5. DISPERSAO DO DANO — ha variancia para explicar?")
print("=" * 150)
d = res.groupby("defeito", sort=False)["err_SUM_faturamento"].agg(["mean", "std", "min", "max"])
print(d.to_string(float_format=lambda x: f"{x:+,.3f}"))
print(f"\nAmplitude do erro em SUM entre defeitos: "
      f"{res['err_SUM_faturamento'].min():+.2f}% a {res['err_SUM_faturamento'].max():+.2f}%")
print(f"Defeitos com viés NEGATIVO (subestima): "
      f"{sorted(d[d['mean'] < -0.5].index.tolist())}")
print(f"Defeitos com viés POSITIVO (superestima): "
      f"{sorted(d[d['mean'] > 0.5].index.tolist())}")

print()
print("=" * 150)
print("6. METRICA MAIS VULNERAVEL por defeito silencioso")
print("=" * 150)
if len(sil):
    for dft, g in sil.groupby("defeito", sort=False):
        piores = {m.replace("err_", ""): g[m].mean() for m in mets}
        top = sorted(piores.items(), key=lambda kv: -abs(kv[1]))[:3]
        print(f"  {dft:30s} " + "  |  ".join(f"{k} {v:+.2f}%" for k, v in top))
