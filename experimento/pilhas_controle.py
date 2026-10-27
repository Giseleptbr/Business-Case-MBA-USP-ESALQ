"""
Risco residual por pilha de controles realista.
As pilhas refletem o que organizacoes efetivamente rodam, em ordem crescente de custo.
"""
import pandas as pd
import numpy as np

pd.set_option("display.width", 250)
res = pd.read_csv("resultado_viab_llm.csv")
mets = ["err_SUM_faturamento", "err_AVG_ticket", "err_MEDIAN_ticket",
        "err_P95_cauda", "err_COUNT_pedidos", "err_SUM_pior_conta"]

PILHAS = {
    "A_so_schema":            ["C3_schema"],
    "B_padrao_dbt":           ["C2_dbt_generico", "C3_schema"],
    "C_dbt_mais_contagem":    ["C1_reconciliacao_contagem", "C2_dbt_generico", "C3_schema"],
    "D_completa_com_valor":   ["C1_reconciliacao_contagem", "C2_dbt_generico",
                               "C3_schema", "C4_reconciliacao_valor"],
}

med = res.groupby("defeito", sort=False)[mets + ["abs_SUM"]].mean()

print("=" * 140)
print("7. RISCO RESIDUAL POR PILHA DE CONTROLES")
print("   'passa' = defeito que nenhum controle da pilha detectou em NENHUMA das 30 sementes")
print("=" * 140)
linhas = []
for nome, cs in PILHAS.items():
    detectado = res.assign(d=res[cs].any(axis=1)).groupby("defeito", sort=False)["d"].mean()
    passam = detectado[detectado == 0].index.tolist()
    pior_sum = med.loc[passam, "err_SUM_faturamento"].abs().max() if passam else 0.0
    pior_qq = med.loc[passam, mets].abs().max().max() if passam else 0.0
    exposicao = med.loc[passam, "abs_SUM"].abs().sum() if passam else 0.0
    linhas.append({
        "pilha": nome,
        "controles": len(cs),
        "defeitos_que_passam": len(passam),
        "pior_erro_SUM_%": round(pior_sum, 2),
        "pior_erro_qualquer_metrica_%": round(pior_qq, 2),
        "exposicao_somada_R$": round(exposicao, 2),
        "quais": ", ".join(p.split("_", 1)[0] for p in passam) or "-",
    })
print(pd.DataFrame(linhas).to_string(index=False))

print()
print("=" * 140)
print("8. O SALTO DECISIVO: o que a reconciliacao de VALOR acrescenta sobre a pilha C")
print("=" * 140)
detC = res.assign(d=res[PILHAS["C_dbt_mais_contagem"]].any(axis=1)).groupby("defeito", sort=False)["d"].mean()
detD = res.assign(d=res[PILHAS["D_completa_com_valor"]].any(axis=1)).groupby("defeito", sort=False)["d"].mean()
ganho = [d for d in detC.index if detC[d] == 0 and detD[d] > 0]
print(f"Defeitos que SO a reconciliacao de valor pega: {ganho}")
for d in ganho:
    print(f"   {d:30s} erro SUM {med.loc[d,'err_SUM_faturamento']:+8.2f}%   "
          f"R$ {med.loc[d,'abs_SUM']:>14,.2f}")
resid = [d for d in detD.index if detD[d] == 0]
print(f"\nRisco residual mesmo com a pilha completa: {resid}")
for d in resid:
    print(f"   {d:30s} erro SUM {med.loc[d,'err_SUM_faturamento']:+8.2f}%   "
          f"P95 {med.loc[d,'err_P95_cauda']:+6.2f}%   R$ {med.loc[d,'abs_SUM']:>12,.2f}")

print()
print("=" * 140)
print("9. DEFEITOS INVISIVEIS NA METRICA PRINCIPAL mas materiais em outra")
print("=" * 140)
for d in med.index:
    s = abs(med.loc[d, "err_SUM_faturamento"])
    outras = med.loc[d, [m for m in mets if m != "err_SUM_faturamento"]].abs().max()
    if s < 1.0 and outras > 1.0:
        pior = med.loc[d, [m for m in mets if m != "err_SUM_faturamento"]].abs().idxmax()
        print(f"   {d:30s} SUM {med.loc[d,'err_SUM_faturamento']:+.3f}%  mas  "
              f"{pior.replace('err_','')} {med.loc[d,pior]:+.2f}%")
