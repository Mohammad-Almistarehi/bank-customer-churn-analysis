"""
Bank Customer Churn Analysis
----------------------------
Cleans the raw customer file, adds analysis groups, calculates the churn KPIs
and saves summary tables and charts.

Run from the project root:
    python src/churn_analysis.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "bank_churn_customers.csv"
CLEAN = ROOT / "data" / "bank_churn_clean.csv"
OUT = ROOT / "outputs"
IMG = ROOT / "images"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
df = pd.read_csv(RAW, parse_dates=["JoinDate", "ChurnDate"])
log = [("Raw file", len(df))]

# ---------------------------------------------------------------------------
# 2. Data quality checks
# ---------------------------------------------------------------------------
dup_mask = df.duplicated(keep="first")
print(f"Exact duplicate copies: {dup_mask.sum()}")
df = df[~dup_mask]
log.append(("Less: duplicate copies removed", int(dup_mask.sum())))

invalid_age = (df["Age"] < 18) | (df["Age"] > 100)
missing_score = df["CreditScore"].isna() | (df["CreditScore"] == 0)
bad_dates = (df["Churned"] == 1) & (df["ChurnDate"] < df["JoinDate"])

log.append(("Less: invalid age (<18 or >100)", int(invalid_age.sum())))
log.append(("Less: missing credit score", int(missing_score.sum())))
log.append(("Less: churn date before join date", int(bad_dates.sum())))

df = df[~(invalid_age | missing_score | bad_dates)].copy()
log.append(("Clean records", len(df)))

recon = pd.DataFrame(log, columns=["Step", "Records"])
recon.to_csv(OUT / "record_reconciliation.csv", index=False)
print(recon.to_string(index=False))

# ---------------------------------------------------------------------------
# 3. Calculated fields (same groups as in the ACL computed fields)
# ---------------------------------------------------------------------------
df["AgeGroup"] = pd.cut(df["Age"], [17, 30, 40, 50, 60, 70, 200],
                        labels=["18-30", "31-40", "41-50", "51-60", "61-70", "71+"])
df["CreditScoreGroup"] = pd.cut(df["CreditScore"], [0, 499, 599, 699, 799, 850],
                                labels=["300-499", "500-599", "600-699", "700-799", "800-850"])
df["BalanceGroup"] = pd.cut(df["Balance_JOD"], [-1, 0, 5000, 20000, 50000, float("inf")],
                            labels=["1. Zero", "2. Up to 5K", "3. 5K-20K", "4. 20K-50K", "5. 50K+"])
df.to_csv(CLEAN, index=False)

# ---------------------------------------------------------------------------
# 4. KPIs
# ---------------------------------------------------------------------------
churned = df[df["Churned"] == 1]
kpis = {
    "Customers": len(df),
    "Churned customers": len(churned),
    "Retained customers": int((df["Churned"] == 0).sum()),
    "Churn rate": round(df["Churned"].mean(), 4),
    "Total balance (JOD)": round(df["Balance_JOD"].sum(), 3),
    "Balance lost to churn (JOD)": round(churned["Balance_JOD"].sum(), 3),
    "Share of balance lost": round(churned["Balance_JOD"].sum() / df["Balance_JOD"].sum(), 4),
    "Customers with complaints": int((df["Complaints_12M"] > 0).sum()),
    "Avg satisfaction - churned": round(churned["SatisfactionScore"].mean(), 2),
    "Avg satisfaction - retained": round(df.loc[df["Churned"] == 0, "SatisfactionScore"].mean(), 2),
}
pd.Series(kpis, name="Value").to_csv(OUT / "kpis.csv", header=True)
print("\nKPIs")
for k, v in kpis.items():
    print(f"  {k}: {v}")


def churn_by(col):
    t = (df.groupby(col, observed=True)
           .agg(Customers=("CustomerID", "count"), Churned=("Churned", "sum")))
    t["ChurnRate"] = (t["Churned"] / t["Customers"]).round(4)
    return t


groups = {
    "AgeGroup": "Age group", "NumProducts": "Number of products", "Complaints_12M": "Complaints (12 months)",
    "CreditScoreGroup": "Credit score group", "BalanceGroup": "Balance group", "Region": "Region",
    "IsActiveMember": "Active member", "Gender": "Gender", "PreferredChannel": "Preferred channel",
}
for col in groups:
    churn_by(col).to_csv(OUT / f"churn_by_{col}.csv")

reasons = churned["ChurnReason"].value_counts().rename_axis("Reason").to_frame("Churned")
reasons["Share"] = (reasons["Churned"] / reasons["Churned"].sum()).round(4)
reasons.to_csv(OUT / "churn_reasons.csv")

monthly = churned.groupby(churned["ChurnDate"].dt.to_period("M")).size().rename("Churned")
monthly.to_csv(OUT / "churn_by_month.csv")

# ---------------------------------------------------------------------------
# 5. Charts
# ---------------------------------------------------------------------------
BLUE, ORANGE = "#2E86DE", "#F39C12"


def bar_with_rate(col, title, fname):
    t = churn_by(col)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(t.index.astype(str), t["Customers"], color=BLUE, label="Customers")
    ax.set_ylabel("Customers")
    ax2 = ax.twinx()
    ax2.plot(t.index.astype(str), t["ChurnRate"] * 100, color=ORANGE, marker="o", label="Churn rate")
    ax2.set_ylabel("Churn rate (%)")
    ax2.set_ylim(0, max(t["ChurnRate"] * 100) * 1.25)
    ax.set_title(title)
    fig.legend(loc="upper right", bbox_to_anchor=(0.88, 0.88))
    fig.tight_layout()
    fig.savefig(IMG / fname, dpi=120)
    plt.close(fig)


bar_with_rate("AgeGroup", "Churn by age group", "churn_by_age.png")
bar_with_rate("NumProducts", "Churn by number of products", "churn_by_products.png")
bar_with_rate("Complaints_12M", "Churn by complaints (last 12 months)", "churn_by_complaints.png")

fig, ax = plt.subplots(figsize=(7, 4))
r = reasons.sort_values("Churned")
ax.barh(r.index, r["Churned"], color=ORANGE)
for i, v in enumerate(r["Churned"]):
    ax.text(v + 5, i, str(v), va="center")
ax.set_title("Why customers left")
fig.tight_layout()
fig.savefig(IMG / "churn_reasons.png", dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(monthly.index.strftime("%b"), monthly.values, color=BLUE, marker="o")
for x, y in zip(monthly.index.strftime("%b"), monthly.values):
    ax.annotate(str(y), (x, y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
ax.set_title("Churned customers by month (2025)")
ax.set_ylim(0, monthly.max() * 1.2)
fig.tight_layout()
fig.savefig(IMG / "churn_by_month.png", dpi=120)
plt.close(fig)

print("\nDone. Clean data, tables and charts were saved.")
