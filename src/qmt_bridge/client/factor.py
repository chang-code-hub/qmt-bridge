"""FactorMixin — 因子数据客户端方法。

封装了与因子计算和查询相关的客户端接口，包括：
- 列出所有已注册因子
- 查询指定因子的历史数据（支持复权调整）
- 手动触发因子计算
- 筹码分布可视化（同花顺风格）

底层对应 /api/factors/* 端点。
"""

from typing import Optional


class FactorMixin:
    """因子数据客户端方法集合。"""

    def list_factors(self) -> list[dict]:
        """列出所有已注册的因子及其描述信息。

        Returns:
            因子元信息列表，每项包含 ``name`` 和 ``description``
        """
        resp = self._get("/api/factors/list")
        return resp.get("data", [])

    def get_factor_history(
        self,
        factor_name: str,
        stocks: list[str],
        start_date: str = "",
        end_date: str = "",
        dividend_type: str = "none",
    ) -> list[dict]:
        """查询指定股票、指定因子的历史数据。

        支持前复权/后复权调整（仅当因子声明了 price_fields 时生效）。

        Args:
            factor_name: 因子名称，如 ``"chip"``（筹码分布）
            stocks: 股票代码列表，如 ``["000001.SZ", "600519.SH"]``
            start_date: 开始日期，格式 ``"20230101"``
            end_date: 结束日期，格式 ``"20230101"``
            dividend_type: 除权类型:
                - ``"none"``: 不复权
                - ``"front"``: 前复权
                - ``"back"``: 后复权
                - ``"front_ratio"``: 等比前复权
                - ``"back_ratio"``: 等比后复权

        Returns:
            因子记录列表，每条记录包含 ``stock_code``、``trade_date``、
            ``factor_data``（因子计算结果字典）等字段
        """
        resp = self._get(f"/api/factors/{factor_name}", {
            "stocks": ",".join(stocks),
            "start_date": start_date,
            "end_date": end_date,
            "dividend_type": dividend_type,
        })
        return resp.get("data", [])

    def compute_factor(
        self,
        factor_name: str,
        stocks: list[str],
        start_time: str = "",
        end_time: str = "",
        years: int = 0,
    ) -> dict:
        """手动触发指定因子对指定股票的计算。

        计算结果会写入服务端数据库，之后可通过 ``get_factor_history()`` 查询。

        Args:
            factor_name: 因子名称
            stocks: 股票代码列表
            start_time: 开始时间，格式 ``"20230101"``
            end_time: 结束时间
            years: 若指定则按最近 N 年计算（优先级高于 start_time）

        Returns:
            计算结果摘要
        """
        return self._post("/api/factors/compute", {
            "factor_name": factor_name,
            "stock_codes": stocks,
            "start_time": start_time,
            "end_time": end_time,
            "years": years,
        })

    def get_chip_distribution(
        self,
        stock: str,
        date: str = "",
        dividend_type: str = "none",
    ) -> dict:
        """获取单只股票的最新筹码分布数据。

        若未指定 date，返回该股票最新日期的筹码分布。

        Args:
            stock: 股票代码，如 ``"000001.SZ"``
            date: 指定日期 ``"20230101"``，为空则取最新
            dividend_type: 除权类型

        Returns:
            筹码分布数据字典，包含 ``price_levels``（价格档位）、
            ``volumes``（各档位筹码量）、``avg_cost``（平均成本）、
            ``max_volume_price``（最大筹码价格）、``concentration``（集中度）等
        """
        records = self.get_factor_history(
            "chip",
            [stock],
            start_date=date,
            end_date=date,
            dividend_type=dividend_type,
        )
        if not records:
            return {}
        # 取最新一条
        latest = max(records, key=lambda r: r.get("trade_date", ""))
        return latest.get("factor_data", {})

    def plot_chip_distribution(
        self,
        stock: str,
        date: str = "",
        dividend_type: str = "none",
        current_price: Optional[float] = None,
        figsize: tuple = (10, 6),
    ):
        """绘制同花顺风格的筹码分布图。

        横向柱状图展示各价格区间的持仓量分布，并标注当前价、平均成本、
        最大筹码价格等关键价位。

        Args:
            stock: 股票代码
            date: 指定日期，为空则取最新
            dividend_type: 除权类型
            current_price: 当前价格（用于标注获利/套牢盘分界线，
                不传入时尝试从行情接口获取）
            figsize: 图表尺寸

        Returns:
            matplotlib Axes 对象（方便后续调整）

        Raises:
            ImportError: 未安装 matplotlib
            ValueError: 未找到筹码分布数据
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError("绘制筹码分布图需要安装 matplotlib: pip install matplotlib") from exc

        chip = self.get_chip_distribution(stock, date, dividend_type)
        if not chip:
            raise ValueError(f"未找到 {stock} 的筹码分布数据，请先调用 compute_factor('chip', ['{stock}']) 计算")

        price_levels = chip.get("price_levels", [])
        volumes = chip.get("volumes", [])
        avg_cost = chip.get("avg_cost", 0.0)
        max_volume_price = chip.get("max_volume_price", 0.0)
        concentration = chip.get("concentration", 0.0)
        total_volume = chip.get("total_volume", 0.0)

        if not price_levels or not volumes:
            raise ValueError("筹码分布数据格式异常，缺少 price_levels 或 volumes")

        # 获取当前价格（用于区分获利/套牢盘）
        if current_price is None:
            try:
                tick = self.get_full_tick([stock])
                current_price = tick.get(stock, {}).get("lastPrice") or tick.get(stock, {}).get("close")
            except Exception:
                current_price = None

        # 构建每个 bar 的上下边界（edges）
        import numpy as np
        # price_levels 是 hist 的左边界，需要补一个右边界
        bin_width = price_levels[1] - price_levels[0] if len(price_levels) > 1 else 1.0
        edges = list(price_levels) + [price_levels[-1] + bin_width]

        # 计算各 bar 的中心和高度
        y_centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(volumes))]
        bar_height = bin_width * 0.9

        # 按是否高于当前价分色
        if current_price is not None:
            colors = [
                "#e74c3c" if y >= current_price else "#3498db"
                for y in y_centers
            ]
        else:
            colors = ["#2ecc71"] * len(volumes)

        fig, ax = plt.subplots(figsize=figsize)

        # 绘制横向柱状图
        ax.barh(
            y_centers,
            volumes,
            height=bar_height,
            color=colors,
            edgecolor="white",
            linewidth=0.3,
            alpha=0.85,
        )

        # 标注线
        if current_price is not None:
            ax.axhline(y=current_price, color="#f39c12", linestyle="--", linewidth=1.5, label=f"当前价 {current_price:.2f}")
        if avg_cost > 0:
            ax.axhline(y=avg_cost, color="#9b59b6", linestyle="-.", linewidth=1.5, label=f"平均成本 {avg_cost:.2f}")
        if max_volume_price > 0:
            ax.axhline(y=max_volume_price, color="#1abc9c", linestyle=":", linewidth=1.5, label=f"最大筹码 {max_volume_price:.2f}")

        # 计算获利比例
        if current_price is not None and total_volume > 0:
            profit_volume = sum(v for y, v in zip(y_centers, volumes) if y >= current_price)
            profit_ratio = profit_volume / total_volume * 100
            ax.text(
                0.98, 0.95,
                f"获利比例: {profit_ratio:.1f}%\n集中度: {concentration:.2%}\n总筹码: {total_volume/1e4:.0f}万",
                transform=ax.transAxes,
                fontsize=10,
                verticalalignment="top",
                horizontalalignment="right",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )

        ax.set_xlabel("筹码量")
        ax.set_ylabel("价格")
        date_str = date or "最新"
        ax.set_title(f"{stock} 筹码分布 ({date_str})")
        ax.legend(loc="lower right")
        ax.grid(axis="x", alpha=0.3)

        plt.tight_layout()
        return ax
