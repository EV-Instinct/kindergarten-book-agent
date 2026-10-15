"""
现代数据可视化图表库 (Modern Analytics Charts) - V3.0 鲜亮版
基于 Plotly 构建，专为教师管理中台定制：
1. 最受欢迎绘本 Top 8 渐变条形图
2. 班级阅读主题偏好环形分布图 (Donut Chart)
"""
import plotly.graph_objects as go
import pandas as pd
from typing import List, Dict, Any

# 鲜亮童趣配色（与 UI 设计系统一致）
C_CORAL = "#FF8A65"
C_CORAL_LINE = "#FF6B6B"
C_PINK = "#F472B6"
C_PINK_LINE = "#DB2777"
C_INK = "#22314A"
C_GRID = "#EDF1F7"
PALETTE_VIVID = ["#FF8A65", "#FFB020", "#2E9AFE", "#22C55E", "#8B5CF6", "#EC4899", "#14B8A6", "#F59E0B"]


def render_popular_books_chart(popular_books: List[Dict[str, Any]]):
    """渲染最受小朋友欢迎的绘本横向堆叠条形图（借阅 + 红心）"""
    if not popular_books:
        return None

    df = pd.DataFrame(popular_books)
    # 按综合热度排序，取 Top 8
    df["total_score"] = df["read_count"] * 2 + df["like_count"] * 3
    df = df.sort_values(by="total_score", ascending=True).tail(8)

    fig = go.Figure()

    # 借阅次数条
    fig.add_trace(go.Bar(
        y=df["title"],
        x=df["read_count"],
        name="翻阅借阅次数",
        orientation="h",
        marker=dict(
            color=C_CORAL,
            line=dict(color=C_CORAL_LINE, width=1.5)
        ),
        hovertemplate="《%{y}》<br>借阅 %{x} 次<extra></extra>"
    ))

    # 红心点赞条
    fig.add_trace(go.Bar(
        y=df["title"],
        x=df["like_count"],
        name="喜爱小红心",
        orientation="h",
        marker=dict(
            color=C_PINK,
            line=dict(color=C_PINK_LINE, width=1.5)
        ),
        hovertemplate="《%{y}》<br>红心 %{x} 颗<extra></extra>"
    ))

    fig.update_layout(
        barmode="stack",
        height=340,
        margin=dict(l=10, r=24, t=36, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=13, color=C_INK),
        xaxis=dict(showgrid=True, gridcolor=C_GRID, zeroline=False, title=""),
        yaxis=dict(showgrid=False, tickfont=dict(size=13, weight=700)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=12, weight=700)),
        bargap=0.42
    )
    return fig


def render_theme_donut_chart(theme_stats: List[Dict[str, Any]]):
    """渲染幼儿阅读主题偏好现代环形图（无借阅数据时回退为藏书结构）"""
    if not theme_stats:
        return None

    df = pd.DataFrame(theme_stats)

    # 全零借阅时回退为按藏书量展示，避免空图表
    if df["total_reads"].fillna(0).sum() <= 0:
        values = df["book_count"]
        center_title = "藏书结构"
    else:
        values = df["total_reads"].fillna(0)
        center_title = "累计借阅"

    fig = go.Figure(data=[go.Pie(
        labels=df["theme"],
        values=values,
        hole=0.62,
        marker=dict(colors=PALETTE_VIVID[:len(df)], line=dict(color="#FFFFFF", width=2.5)),
        textinfo="label+percent",
        textfont=dict(size=12, weight=700, color=C_INK),
        hovertemplate="%{label}<br>%{value}（%{percent}）<extra></extra>",
        sort=False
    )])

    fig.update_layout(
        height=340,
        margin=dict(l=12, r=12, t=16, b=16),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="PingFang SC, Microsoft YaHei, sans-serif", size=12, color=C_INK),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.12, xanchor="center", x=0.5,
                    font=dict(size=12, weight=700)),
        annotations=[dict(text=f"<b>{center_title}</b>", x=0.5, y=0.5, font_size=15,
                          font_color=C_INK, showarrow=False)]
    )
    return fig
