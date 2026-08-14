"""短板库跨场聚合分析（纯标准库，离线可跑）。

把多场面试沉淀到本地 SQLite 的 weaknesses 表，按租户 / 场景聚合：
- 分类分布：哪个维度的短板出现最频繁
- 严重度分布：low / medium / high / critical 的占比
- 跨场趋势：同一分类在面试时间轴上的严重度走向（improving / worsening / stable）
- 反复短板：出现 ≥2 次的分类（重点攻克对象）

与隐私铁律一致：数据只来自本地 Store，不出域、无遥测。
"""
from __future__ import annotations

from collections import Counter, defaultdict

# 严重度 → 数值（用于趋势比较，数值越低越好）
SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def aggregate_weaknesses(store, tenant_id: str, scenario: str | None = None, since: str | None = None) -> dict:
    """聚合某 tenant 的短板库。

    Args:
        store:       本地 Store 实例
        tenant_id:   租户标识（作用域隔离）
        scenario:   可选，仅分析该场景（如 '保研'）；None 表示全部
        since:      可选，ISO 时间下界过滤（created_at >= since）
    Returns:
        结构化聚合字典，供 render_aggregate_report 渲染或上层消费。
    """
    weak = store.get_weaknesses()  # 全部：session_id, category, detail, severity, created_at
    sessions = store.list_sessions()  # 含 finished_at；id->meta
    s_meta = {s["id"]: s for s in sessions}

    keep = {sid for sid, s in s_meta.items() if (scenario is None or s["scenario"] == scenario)}
    items = [w for w in weak if w["session_id"] in keep]
    if since:
        items = [w for w in items if (w.get("created_at") or "") >= since]

    # 分类计数
    cat_counter = Counter(w["category"] for w in items)
    # 严重度计数
    sev_counter = Counter(w["severity"] for w in items)

    # 跨场趋势：按面试结束时间排序后，看每个分类的严重度序列走向
    ordered = [s for s in sessions if s["id"] in keep]
    ordered.sort(key=lambda s: s.get("finished_at") or s.get("created_at") or "")
    seq_index = {s["id"]: i for i, s in enumerate(ordered)}

    per_cat = defaultdict(list)
    for w in items:
        per_cat[w["category"]].append(
            (seq_index.get(w["session_id"], 0), SEV_RANK.get(w["severity"], 2), w["detail"])
        )

    trends = {}
    for cat, entries in per_cat.items():
        entries.sort()
        seq = [e[1] for e in entries]
        first, last = entries[0][1], entries[-1][1]
        if len(entries) >= 2:
            if last < first:
                direction = "improving"
            elif last > first:
                direction = "worsening"
            else:
                direction = "stable"
        else:
            direction = "insufficient"
        trends[cat] = {
            "count": len(entries),
            "avg_severity": round(sum(seq) / len(seq), 2),
            "direction": direction,
            "first_severity": first,
            "latest_severity": last,
        }

    top_recurring = [
        {"category": c, "count": n} for c, n in cat_counter.most_common() if n >= 2
    ]

    return {
        "tenant_id": tenant_id,
        "scenario_filter": scenario,
        "session_count": len(keep),
        "weakness_count": len(items),
        "category_counts": dict(cat_counter),
        "severity_counts": dict(sev_counter),
        "category_trends": trends,
        "top_recurring": top_recurring,
    }


def render_aggregate_report(agg: dict) -> str:
    """把聚合结果渲染为可读的 Markdown 报告。"""
    lines = []
    lines.append(f"# 短板库聚合分析报告（tenant={agg['tenant_id']}）\n")
    lines.append(f"- 分析范围：{agg['scenario_filter'] or '全部场景'}")
    lines.append(f"- 覆盖面试场次：{agg['session_count']}")
    lines.append(f"- 短板记录总数：{agg['weakness_count']}\n")

    if agg["weakness_count"] == 0:
        lines.append("（暂无短板数据，先完成几场面试再来分析。）")
        return "\n".join(lines)

    lines.append("## 一、分类分布（哪个维度最薄弱）")
    for c, n in sorted(agg["category_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"- {c}：{n} 次")
    total = agg["weakness_count"]
    lines.append(f"（合计 {total} 条）\n")

    lines.append("## 二、严重度分布")
    for s, n in sorted(agg["severity_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"- {s}：{n} 次")
    lines.append("")

    lines.append("## 三、跨场趋势（按面试时间顺序，严重度数值越低越好）")
    for c, t in sorted(agg["category_trends"].items(), key=lambda x: -x[1]["count"]):
        arrow = {
            "improving": "↓ 改善中",
            "worsening": "↑ 恶化中",
            "stable": "→ 持平",
            "insufficient": "· 样本不足",
        }.get(t["direction"], t["direction"])
        lines.append(
            f"- {c}：出现 {t['count']} 次，平均严重度 {t['avg_severity']}，"
            f"趋势 **{arrow}**（首次 {t['first_severity']} → 最近 {t['latest_severity']}）"
        )
    lines.append("")

    lines.append("## 四、反复出现的短板（≥2 次，优先攻克）")
    if agg["top_recurring"]:
        for r in agg["top_recurring"]:
            lines.append(f"- {r['category']}（{r['count']} 次）")
    else:
        lines.append("- 暂无反复出现的短板，保持得不错。")
    lines.append("")

    lines.append("## 五、行动建议")
    if agg["top_recurring"]:
        for r in agg["top_recurring"]:
            lines.append(
                f"- 针对「{r['category']}」：准备结构化素材——亲手实现的部分 + 踩过的坑 + "
                f"量化结果（指标提升%、论文贡献度），用三段式讲清楚。"
            )
    else:
        lines.append("- 维持当前复盘节奏，持续积累更多场次以获得更稳定的趋势信号。")

    return "\n".join(lines)


if __name__ == "__main__":
    print("analytics 模块自检：聚合与渲染函数已就绪（需配合 Store 使用）。")
