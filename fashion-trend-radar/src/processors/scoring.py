def compute_keyword_score(df):
    if df.empty or "value" not in df.columns:
        return 0

    values = df["value"].dropna().tolist()
    if len(values) < 4:
        return 0

    latest = values[-1]
    avg_all = sum(values) / len(values)
    recent_avg = sum(values[-4:]) / min(4, len(values))
    peak = max(values) if values else 0

    growth_score = max(0, latest - avg_all)
    momentum_score = max(0, recent_avg - avg_all)
    consistency_score = avg_all / peak * 100 if peak else 0

    return round((growth_score * 0.45) + (momentum_score * 0.35) + (consistency_score * 0.20), 2)
