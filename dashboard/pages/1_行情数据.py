"""行情数据 — K 线图、实时快照、大盘指数。"""

import sys
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd

# 将 dashboard/ 加入 sys.path 以便 import _sidebar
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _sidebar import require_client

st.set_page_config(page_title="行情数据 - QMT Bridge", layout="wide")
st.title("行情数据")

client = require_client()

# ── K 线图 ────────────────────────────────────────────────────────

st.header("K 线图")

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    stock_code = st.text_input("股票代码", value="000001.SZ", key="kline_stock")
with col2:
    period = st.selectbox("周期", ["1d", "1w", "1m", "5m", "15m", "30m", "60m"], key="kline_period")
with col3:
    count = st.number_input("条数", value=120, min_value=10, max_value=1000, step=10, key="kline_count")
with col4:
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
        key="kline_dividend",
    )

if st.button("查询 K 线", key="btn_kline"):
    try:
        with st.spinner("查询中..."):
            data = client.get_history_ex(
                [stock_code],
                period=period,
                count=count,
                dividend_type=dividend_type,
            )
        df = data.get(stock_code)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            st.info("未获取到数据。")
        else:
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)

            x_axis = df["time"] if "time" in df.columns else df.index
            current_price = float(df["close"].iloc[-1]) if "close" in df.columns else None

            # ── 构建复合图表: K线 + 成交量 + 筹码分布 ──────────────────
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "xy"}, {"type": "xy"}],
                       [{"type": "xy"}, None]],
                column_widths=[0.75, 0.25],
                row_heights=[0.7, 0.3],
                shared_xaxes="columns",
                vertical_spacing=0.05,
                horizontal_spacing=0.05,
            )

            # K线
            fig.add_trace(go.Candlestick(
                x=x_axis,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="K线",
                increasing_line_color="#e74c3c",
                decreasing_line_color="#3498db",
            ), row=1, col=1)

            # 成交量
            if "volume" in df.columns:
                vol_colors = [
                    "#e74c3c" if df["close"].iloc[i] >= df["open"].iloc[i] else "#3498db"
                    for i in range(len(df))
                ]
                fig.add_trace(go.Bar(
                    x=x_axis,
                    y=df["volume"],
                    marker_color=vol_colors,
                    name="成交量",
                    showlegend=False,
                ), row=2, col=1)

            # 统一 K 线与筹码分布的 Y 轴范围，使价格对齐
            price_min = float(df["low"].min()) * 0.998 if "low" in df.columns else None
            price_max = float(df["high"].max()) * 1.002 if "high" in df.columns else None

            # 筹码分布（右侧，与 K 线等高）— 仅日线模式显示
            if period == "1d" and "index" in df.columns:
                time_values = df["index"]
                start_date = str(int(time_values.iloc[0]))
                end_date = str(int(time_values.iloc[-1]))
                chip = client.get_chip_distribution(
                    stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    dividend_type=dividend_type,
                )
                if chip and chip.get("price_levels") and chip.get("volumes"):
                    price_levels = chip.get("price_levels", [])
                    volumes = chip.get("volumes", [])
                    avg_cost = chip.get("avg_cost", 0.0)
                    max_volume_price = chip.get("max_volume_price", 0.0)
                    concentration = chip.get("concentration", 0.0)
                    total_volume = chip.get("total_volume", 0.0)

                    bin_width = price_levels[1] - price_levels[0] if len(price_levels) > 1 else 1.0
                    y_centers = [p + bin_width / 2 for p in price_levels]

                    # 按获利/套牢分色
                    chip_colors = [
                        "#e74c3c" if (current_price is not None and y >= current_price) else "#3498db"
                        for y in y_centers
                    ]

                    fig.add_trace(go.Bar(
                        x=volumes,
                        y=y_centers,
                        orientation="h",
                        marker_color=chip_colors,
                        marker_line_color="white",
                        marker_line_width=0.3,
                        opacity=0.85,
                        name="筹码量",
                        showlegend=False,
                    ), row=1, col=2)

                    # 当前价横线
                    if current_price is not None:
                        fig.add_hline(
                            y=current_price,
                            line_dash="dash",
                            line_color="#f39c12",
                            line_width=1.5,
                            annotation_text=f"当前价 {current_price:.2f}",
                            annotation_position="right",
                            row=1, col=2,
                        )
                    # 平均成本线
                    if avg_cost > 0:
                        fig.add_hline(
                            y=avg_cost,
                            line_dash="dashdot",
                            line_color="#9b59b6",
                            line_width=1.5,
                            annotation_text=f"平均成本 {avg_cost:.2f}",
                            annotation_position="right",
                            row=1, col=2,
                        )
                    # 最大筹码线
                    if max_volume_price > 0:
                        fig.add_hline(
                            y=max_volume_price,
                            line_dash="dot",
                            line_color="#1abc9c",
                            line_width=1.5,
                            annotation_text=f"最大筹码 {max_volume_price:.2f}",
                            annotation_position="right",
                            row=1, col=2,
                        )

                    # 获利比例文字
                    if current_price is not None and total_volume > 0:
                        profit_volume = sum(v for y, v in zip(y_centers, volumes) if y >= current_price)
                        profit_ratio = profit_volume / total_volume * 100
                        info_text = f"获利比例: {profit_ratio:.1f}%<br>集中度: {concentration:.2%}<br>总筹码: {total_volume / 1e4:.0f}万"
                        fig.add_annotation(
                            x=0.98, y=0.95,
                            xref="paper", yref="paper",
                            text=info_text,
                            showarrow=False,
                            font=dict(size=11),
                            bgcolor="rgba(245, 222, 179, 0.7)",
                            bordercolor="gray",
                            borderwidth=1,
                            align="left",
                        )

            fig.update_layout(
                title=f"{stock_code} — {period} K 线",
                xaxis_rangeslider_visible=False,
                height=650,
                hovermode="x unified",
            )
            # 筹码分布 Y 轴始终跟随 K 线主图
            fig.update_yaxes(matches='y', row=1, col=2)
            fig.update_xaxes(showticklabels=False, row=1, col=2)
            fig.update_xaxes(title_text="日期", row=2, col=1)
            fig.update_yaxes(title_text="价格", row=1, col=1)
            fig.update_yaxes(title_text="成交量", row=2, col=1)

            st.plotly_chart(fig, use_container_width=True)

            with st.expander("查看原始数据"):
                st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"查询失败: {e}")

st.markdown("---")

# ── 实时快照 ──────────────────────────────────────────────────────

st.header("实时快照")

snapshot_codes = st.text_input(
    "输入股票代码（逗号分隔）",
    value="000001.SZ, 600519.SH, 000858.SZ",
    key="snapshot_codes",
)

if st.button("获取快照", key="btn_snapshot"):
    try:
        codes = [c.strip() for c in snapshot_codes.split(",") if c.strip()]
        with st.spinner("查询中..."):
            data = client.get_market_snapshot(codes)
        if not data:
            st.info("未获取到数据。")
        else:
            rows = []
            for code, info in data.items():
                if isinstance(info, dict):
                    rows.append({**info, "代码": code})
            if rows:
                df = pd.DataFrame(rows)
                if "代码" in df.columns:
                    cols = ["代码"] + [c for c in df.columns if c != "代码"]
                    df = df[cols]
                st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"查询失败: {e}")

st.markdown("---")

# ── 大盘指数 ──────────────────────────────────────────────────────

st.header("大盘指数")

if st.button("刷新指数", key="btn_indices"):
    try:
        with st.spinner("查询中..."):
            data = client.get_major_indices()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not data:
            st.info("未获取到指数数据。")
        else:
            if isinstance(data, dict):
                rows = []
                for code, info in data.items():
                    if isinstance(info, dict):
                        rows.append({**info, "代码": code})
                if rows:
                    df = pd.DataFrame(rows)
                    if "代码" in df.columns:
                        cols = ["代码"] + [c for c in df.columns if c != "代码"]
                        df = df[cols]
                    st.dataframe(df, use_container_width=True)
                else:
                    st.json(data)
            elif isinstance(data, list):
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                st.json(data)
    except Exception as e:
        st.error(f"查询失败: {e}")
