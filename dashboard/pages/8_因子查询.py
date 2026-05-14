"""因子查询 — 因子列表、历史数据查询、筹码分布可视化。"""

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _sidebar import require_client

st.set_page_config(page_title="因子查询 - QMT Bridge", layout="wide")
st.title("因子查询")

client = require_client()

# ── 因子列表 ──────────────────────────────────────────────────────

st.header("可用因子")

try:
    factors = client.list_factors()
    if factors:
        df_factors = pd.DataFrame(factors)
        st.dataframe(df_factors, use_container_width=True)
    else:
        st.info("未获取到因子列表。")
except Exception as e:
    st.error(f"获取因子列表失败: {e}")

st.markdown("---")

# ── 因子历史数据查询 ──────────────────────────────────────────────

st.header("因子历史数据查询")

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    factor_name = st.selectbox("选择因子", ["chip"], key="factor_name")
with col2:
    stock_input = st.text_input("股票代码", value="000001.SZ", key="factor_stock")
with col3:
    start_date = st.text_input("开始日期", value="", placeholder="YYYYMMDD", key="factor_start")
with col4:
    end_date = st.text_input("结束日期", value="", placeholder="YYYYMMDD", key="factor_end")

col5, col6 = st.columns([1, 3])
with col5:
    dividend_type = st.selectbox(
        "除权类型",
        ["none", "front", "back", "front_ratio", "back_ratio"],
        format_func=lambda x: {
            "none": "不复权",
            "front": "前复权",
            "back": "后复权",
            "front_ratio": "等比前复权",
            "back_ratio": "等比后复权",
        }.get(x, x),
        key="factor_dividend",
    )

if st.button("查询因子数据", key="btn_factor_query"):
    try:
        stocks = [s.strip() for s in stock_input.split(",") if s.strip()]
        with st.spinner("查询中..."):
            data = client.get_factor_history(
                factor_name,
                stocks,
                start_date=start_date,
                end_date=end_date,
                dividend_type=dividend_type,
            )
        if not data:
            st.info("未获取到数据。")
        else:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)

            # 如果是筹码分布因子，提供可视化
            if factor_name == "chip":
                st.markdown("---")
                st.subheader("筹码分布可视化")

                for record in data:
                    stock_code = record.get("stock_code", "")
                    trade_date = record.get("trade_date", "")
                    chip = record.get("factor_data", {})

                    if not chip:
                        continue

                    price_levels = chip.get("price_levels", [])
                    volumes = chip.get("volumes", [])
                    avg_cost = chip.get("avg_cost", 0.0)
                    max_volume_price = chip.get("max_volume_price", 0.0)
                    concentration = chip.get("concentration", 0.0)
                    total_volume = chip.get("total_volume", 0.0)

                    if not price_levels or not volumes:
                        continue

                    # 计算 bar 中心和高度
                    bin_width = price_levels[1] - price_levels[0] if len(price_levels) > 1 else 1.0
                    y_centers = [p + bin_width / 2 for p in price_levels]

                    # 获取当前价格（用于区分获利/套牢盘）
                    current_price = None
                    try:
                        tick = client.get_full_tick([stock_code])
                        tick_data = tick.get(stock_code, {})
                        current_price = tick_data.get("lastPrice") or tick_data.get("close")
                    except Exception:
                        current_price = None

                    # 分色
                    colors = []
                    for y in y_centers:
                        if current_price is not None:
                            colors.append("#e74c3c" if y >= current_price else "#3498db")
                        else:
                            colors.append("#2ecc71")

                    fig = go.Figure()

                    fig.add_trace(go.Bar(
                        x=volumes,
                        y=y_centers,
                        orientation="h",
                        marker_color=colors,
                        marker_line_color="white",
                        marker_line_width=0.3,
                        opacity=0.85,
                        name="筹码量",
                    ))

                    # 标注线
                    if current_price is not None:
                        fig.add_hline(
                            y=current_price,
                            line_dash="dash",
                            line_color="#f39c12",
                            line_width=2,
                            annotation_text=f"当前价 {current_price:.2f}",
                            annotation_position="right",
                        )
                    if avg_cost > 0:
                        fig.add_hline(
                            y=avg_cost,
                            line_dash="dashdot",
                            line_color="#9b59b6",
                            line_width=2,
                            annotation_text=f"平均成本 {avg_cost:.2f}",
                            annotation_position="right",
                        )
                    if max_volume_price > 0:
                        fig.add_hline(
                            y=max_volume_price,
                            line_dash="dot",
                            line_color="#1abc9c",
                            line_width=2,
                            annotation_text=f"最大筹码 {max_volume_price:.2f}",
                            annotation_position="right",
                        )

                    # 获利比例信息
                    annotations = []
                    if current_price is not None and total_volume > 0:
                        profit_volume = sum(v for y, v in zip(y_centers, volumes) if y >= current_price)
                        profit_ratio = profit_volume / total_volume * 100
                        info_text = f"获利比例: {profit_ratio:.1f}%<br>集中度: {concentration:.2%}<br>总筹码: {total_volume / 1e4:.0f}万"
                        annotations.append(dict(
                            x=0.98, y=0.95,
                            xref="paper", yref="paper",
                            text=info_text,
                            showarrow=False,
                            font=dict(size=12),
                            bgcolor="rgba(245, 222, 179, 0.7)",
                            bordercolor="gray",
                            borderwidth=1,
                            align="left",
                        ))

                    fig.update_layout(
                        title=f"{stock_code} 筹码分布 ({trade_date})",
                        xaxis_title="筹码量",
                        yaxis_title="价格",
                        annotations=annotations,
                        height=500,
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"查询失败: {e}")

st.markdown("---")

# ── 手动触发因子计算 ──────────────────────────────────────────────

st.header("手动触发因子计算")

with st.expander("触发计算（数据缺失时使用）"):
    col_c1, col_c2 = st.columns([2, 1])
    with col_c1:
        compute_stock = st.text_input("股票代码", value="000001.SZ", key="compute_stock")
    with col_c2:
        compute_years = st.number_input("计算年数", value=1, min_value=0, max_value=10, step=1, key="compute_years")

    compute_start = st.text_input("开始日期（覆盖年数）", value="", placeholder="YYYYMMDD", key="compute_start")
    compute_end = st.text_input("结束日期", value="", placeholder="YYYYMMDD", key="compute_end")

    if st.button("触发 chip 因子计算", key="btn_compute"):
        try:
            stocks = [s.strip() for s in compute_stock.split(",") if s.strip()]
            with st.spinner("计算中..."):
                result = client.compute_factor(
                    "chip",
                    stocks,
                    start_time=compute_start,
                    end_time=compute_end,
                    years=compute_years,
                )
            st.success("计算完成")
            st.json(result)
        except Exception as e:
            st.error(f"计算失败: {e}")
