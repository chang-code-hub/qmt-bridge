# QMT Bridge Server API — Prompt Reference

> 本文档供外部项目（如策略系统、量化平台、AI Agent）作为 API 调用提示词使用。
> 完整交互式文档（Swagger JSON）：http://localhost:8080/openapi.json

---

## 概述

QMT Bridge 将 miniQMT（xtquant）的行情与交易能力通过 HTTP / WebSocket 暴露给局域网设备。

- **Base URL**: `http://<host>:8080`
- **响应格式**: JSON，`{"code": 0, "message": "ok", "data": ...}`
- **认证**: 数据接口默认无需认证；交易接口需要 `X-API-Key` 请求头
- **代码格式**: 统一使用 `code.exchange`（如 `000001.SZ`）

---

## 一、行情数据 `/api/market/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/market/full_tick` | GET | `stocks`（逗号分隔，如 `000001.SZ,600000.SH`） | 实时全推行情快照 |
| `/api/market/indices` | GET | — | 主要指数实时行情 |
| `/api/market/market_data_ex` | GET | `stocks`, `period="1d"`, `start_time`, `end_time`, `count=-1`, `dividend_type="none"`, `fill_data=True` | 扩展 K 线历史行情（含复权） |
| `/api/market/local_data` | GET | 同上 | 本地缓存行情（不触发网络请求） |
| `/api/market/divid_factors` | GET | `stock`, `start_time`, `end_time` | 除权因子数据 |
| `/api/market/market_data` | GET | `stocks`, `fields="open,high,low,close,volume"`, `period`, `start_time`, `end_time`, `count`, `dividend_type`, `fill_data` | 原始 K 线行情 |
| `/api/market/market_data3` | GET | 同上（fields 可为空） | 返回 DataFrame 字典格式 |
| `/api/market/full_kline` | GET | `stock`, `period`, `start_time`, `end_time` | 完整 K 线 |
| `/api/market/fullspeed_orderbook` | GET | `stock`, `start_time`, `end_time` | 极速委托簿 |
| `/api/market/transactioncount` | GET | `stock`, `start_time`, `end_time` | 逐笔成交计数 |

---

## 二、L2 / Tick 数据 `/api/tick/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/tick/l2_quote` | GET | `stock`, `start_time`, `end_time`, `count=-1` | L2 逐笔报价 |
| `/api/tick/l2_order` | GET | 同上 | L2 逐笔委托 |
| `/api/tick/l2_transaction` | GET | 同上 | L2 逐笔成交 |
| `/api/tick/l2_thousand_quote` | GET | 同上 | L2 千档行情报价 |
| `/api/tick/l2_thousand_orderbook` | GET | 同上 | L2 千档委托簿 |
| `/api/tick/l2_thousand_trade` | GET | 同上 | L2 千档成交数据 |
| `/api/tick/l2_thousand_queue` | GET | `stock` | L2 千档队列 |
| `/api/tick/broker_queue` | GET | `stock` | 经纪商队列 |
| `/api/tick/order_rank` | GET | `stock` | 委托排名 |

---

## 三、板块管理 `/api/sector/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/sector/list` | GET | — | 所有板块列表 |
| `/api/sector/stocks` | GET | `sector`, `real_timetag=-1` | 板块成分股 |
| `/api/sector/info` | GET | `sector=""` | 板块详细信息 |
| `/api/sector/create_folder` | POST | `{folder_name}` | 创建板块文件夹 |
| `/api/sector/create` | POST | `{sector_name, parent_node=""}` | 创建板块 |
| `/api/sector/add_stocks` | POST | `{sector_name, stock_list}` | 向板块添加股票 |
| `/api/sector/remove_stocks` | POST | `{sector_name, stock_list}` | 从板块移除股票 |
| `/api/sector/remove` | DELETE | `sector_name` | 删除板块 |
| `/api/sector/reset` | POST | `{sector_name, stock_list}` | 重置板块成分股 |

---

## 四、交易日历 `/api/calendar/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/calendar/trading_dates` | GET | `market`, `start_time`, `end_time`, `count=-1` | 交易日列表 |
| `/api/calendar/holidays` | GET | — | 节假日列表 |
| `/api/calendar/trading_calendar` | GET | `market`, `start_time`, `end_time` | 交易日历 |
| `/api/calendar/trading_period` | GET | `stock` | 合约交易时段 |
| `/api/calendar/is_trading_date` | GET | `market`, `date` | 判断是否为交易日 |
| `/api/calendar/prev_trading_date` | GET | `market`, `date=""` | 前一交易日 |
| `/api/calendar/next_trading_date` | GET | `market`, `date=""` | 下一交易日 |
| `/api/calendar/trading_dates_count` | GET | `market`, `start_time`, `end_time` | 交易日数量统计 |

---

## 五、财务数据 `/api/financial/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/financial/data` | GET | `stocks`, `tables=""`, `start_time`, `end_time`, `report_type="report_time"` | 财务报表数据 |
| `/api/financial/data_ori` | GET | 同上 | 原始格式财务数据 |

---

## 六、合约信息 `/api/instrument/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/instrument/detail_list` | GET | `stocks`, `iscomplete=False` | 批量合约详情 |
| `/api/instrument/type` | GET | `stock` | 合约类型 |
| `/api/instrument/ipo_info` | GET | `start_time`, `end_time` | 新股 IPO 信息 |
| `/api/instrument/index_weight` | GET | `index_code` | 指数成分股权重 |
| `/api/instrument/his_st_data` | GET | `stock` | 历史 ST 状态数据 |

---

## 七、期权数据 `/api/option/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/option/detail` | GET | `option_code` | 期权合约详情 |
| `/api/option/chain` | GET | `undl_code` | 期权链（标的对应全部期权） |
| `/api/option/list` | GET | `undl_code`, `dedate`, `opttype=""`, `isavailable=False` | 期权合约列表 |
| `/api/option/his_option_list` | GET | `undl_code`, `dedate` | 历史期权合约列表 |

---

## 八、ETF `/api/etf/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/etf/list` | GET | — | 沪深 ETF 列表 |
| `/api/etf/info` | GET | `stock` | ETF 申赎信息及成分股 |

---

## 九、可转债 `/api/cb/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/cb/list` | GET | — | 沪深可转债列表 |
| `/api/cb/info` | GET | `stock` | 可转债基本信息 |

---

## 十、期货 `/api/futures/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/futures/main_contract` | GET | `code_market`, `start_time`, `end_time` | 主力合约 |
| `/api/futures/sec_main_contract` | GET | 同上 | 次主力合约 |

---

## 十一、系统元数据 `/api/meta/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/meta/markets` | GET | — | 所有市场列表 |
| `/api/meta/period_list` | GET | — | K 线周期列表 |
| `/api/meta/stock_list` | GET | `category` | 按类别获取证券列表 |
| `/api/meta/last_trade_date` | GET | `market` | 最近交易日 |
| `/api/meta/version` | GET | — | QMT Bridge 版本 |
| `/api/meta/xtdata_version` | GET | — | xtquant 库版本 |
| `/api/meta/connection_status` | GET | — | xtdata 连接状态 |
| `/api/meta/health` | GET | — | 健康检查 |
| `/api/meta/quote_server_status` | GET | — | 行情服务器详细状态 |

---

## 十二、数据下载 `/api/download/*`

| Endpoint | Method | 请求体 | 说明 |
|----------|--------|--------|------|
| `/api/download/history_data2` | POST | `{stock_list, period, start_time, end_time}` | 批量下载历史行情 |
| `/api/download/financial_data` | POST | `{stock_list, table_list, start_time, end_time}` | 下载财务数据 |
| `/api/download/sector_data` | POST | — | 下载板块成分数据（自动预下载） |
| `/api/download/index_weight` | POST | — | 下载指数权重（自动预下载） |
| `/api/download/etf_info` | POST | — | 下载 ETF 信息（自动预下载） |
| `/api/download/cb_data` | POST | — | 下载可转债数据（自动预下载） |
| `/api/download/history_contracts` | POST | — | 下载历史合约（自动预下载） |
| `/api/download/financial_data2` | POST | `{stock_list, table_list}` | 同步下载财务数据 v2 |
| `/api/download/metatable_data` | POST | — | 下载合约元数据表 |
| `/api/download/holiday_data` | POST | — | 下载节假日日历（自动预下载） |
| `/api/download/his_st_data` | POST | `{stock_list, period, start_time, end_time}` | 下载历史 ST 数据 |
| `/api/download/tabular_data` | POST | `{table_list}` | 下载表格数据 |

---

## 十三、公式计算 `/api/formula/*`

| Endpoint | Method | 请求体/参数 | 说明 |
|----------|--------|-------------|------|
| `/api/formula/call` | POST | `{formula_name, stock_code, period="1d", start_time, end_time, count=-1, dividend_type="none", params={}}` | 单只股票公式计算 |
| `/api/formula/call_batch` | POST | 同上 + `stock_codes: list[str]` | 批量公式计算 |
| `/api/formula/generate_index_data` | POST | `{index_code, stock_list, weights, period, start_time, end_time}` | 自定义指数生成 |
| `/api/formula/create` | POST | `{formula_name, formula_file, formula_type=""}` | 创建公式 |
| `/api/formula/import` | POST | `{formula_file}` | 导入公式 |
| `/api/formula/delete` | DELETE | `formula_name`（Query） | 删除公式 |
| `/api/formula/list` | GET | — | 获取公式列表 |

---

## 十四、港股通 `/api/hk/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/hk/stock_list` | GET | — | 全部港股通标的（沪港通+深港通） |
| `/api/hk/connect_stocks` | GET | `connect_type="north"`（north/south） | 按通道方向获取互联互通标的 |
| `/api/hk/broker_dict` | GET | — | 港股经纪商字典 |

---

## 十五、表格数据 `/api/tabular/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/tabular/data` | GET | `table_name`, `stocks=""`, `start_time`, `end_time` | 按表名查询表格数据 |
| `/api/tabular/tables` | GET | — | 列出所有可用数据表 |
| `/api/tabular/formula` | GET | `table_name`, `stocks=""`, `start_time`, `end_time` | 查询公式表格数据 |

---

## 十六、工具 `/api/utility/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/utility/stock_name` | GET | `stock` | 获取股票中文名称 |
| `/api/utility/batch_stock_name` | GET | `stocks` | 批量获取股票名称 |
| `/api/utility/code_to_market` | GET | `stock` | 判断代码归属市场 |
| `/api/utility/search` | GET | `keyword`, `category="沪深A股"`, `limit=20` | 按关键字搜索股票 |

---

## 十七、因子 `/api/factors/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/factors/list` | GET | — | 列出所有已注册因子 |
| `/api/factors/{factor_name}` | GET | `stocks`, `start_date`, `end_date`, `dividend_type="none"` | 查询因子历史数据（支持复权） |
| `/api/factors/compute` | POST | `{factor_name, stock_codes, start_time, end_time, years=0}` | 手动触发因子计算 |

---

## 十八、交易接口（需 `X-API-Key` 认证）

### 18.1 普通交易 `/api/trading/*`

| Endpoint | Method | 请求体/参数 | 说明 |
|----------|--------|-------------|------|
| `/api/trading/order` | POST | `{account_id, stock_code, order_type, order_volume, price_type=5, price=0.0, strategy_name, order_remark}` | 同步下单 |
| `/api/trading/cancel` | POST | `{account_id, order_id}` | 同步撤单 |
| `/api/trading/cancel_by_sysid` | POST | `{account_id, market, sysid}` | 按系统编号撤单 |
| `/api/trading/cancel_by_sysid_async` | POST | 同上 | 按系统编号异步撤单 |
| `/api/trading/orders` | GET | `account_id`, `cancelable_only=False` | 查询当日委托 |
| `/api/trading/positions` | GET | `account_id` | 查询持仓 |
| `/api/trading/asset` | GET | `account_id` | 查询资产 |
| `/api/trading/trades` | GET | `account_id` | 查询当日成交 |
| `/api/trading/order_detail` | GET | `order_id`, `account_id` | 查询单笔委托详情 |
| `/api/trading/batch_order` | POST | `list[OrderRequest]` | 批量下单 |
| `/api/trading/batch_cancel` | POST | `list[CancelRequest]` | 批量撤单 |
| `/api/trading/account_status` | GET | `account_id` | 账户连接状态 |
| `/api/trading/account_status_detail` | GET | — | 账户状态详情 |
| `/api/trading/secu_account` | GET | `account_id` | 证券子账户 |
| `/api/trading/order_async` | POST | 同 `OrderRequest` | 异步下单 |
| `/api/trading/cancel_async` | POST | `{account_id, order_id}` | 异步撤单 |
| `/api/trading/order/{order_id}` | GET | `order_id`, `account_id` | 查询单笔委托 |
| `/api/trading/trade/{trade_id}` | GET | `trade_id`, `account_id` | 查询单笔成交 |
| `/api/trading/position/{stock_code}` | GET | `stock_code`, `account_id` | 查询单只股票持仓 |
| `/api/trading/new_purchase_limit` | GET | `account_id` | 新股申购额度 |
| `/api/trading/ipo_data` | GET | — | IPO 日历 |
| `/api/trading/account_infos` | GET | — | 所有已注册账户信息 |
| `/api/trading/com_fund` | GET | `account_id` | 期权/期货账户资金 |
| `/api/trading/com_position` | GET | `account_id` | 期权/期货账户持仓 |
| `/api/trading/export_data` | POST | `{account_id, result_path, data_type, start_time, end_time, user_param}` | 导出交易数据 |
| `/api/trading/query_data` | POST | 同上 | 查询已导出数据 |
| `/api/trading/sync_transaction` | POST | `{account_id, operation, data_type, deal_list=[]}` | 同步外部成交记录 |

### 18.2 两融交易 `/api/credit/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/credit/order` | POST | 同 `OrderRequest` | 信用交易下单 |
| `/api/credit/positions` | GET | `account_id` | 两融持仓 |
| `/api/credit/asset` | GET | `account_id` | 信用账户资产 |
| `/api/credit/debt` | GET | `account_id` | 信用负债合约 |
| `/api/credit/slo_stocks` | GET | `account_id` | 融券标的列表 |
| `/api/credit/subjects` | GET | `account_id` | 标的证券列表 |
| `/api/credit/assure` | GET | `account_id` | 担保品信息 |

### 18.3 资金划转 `/api/fund/*`

| Endpoint | Method | 请求体 | 说明 |
|----------|--------|--------|------|
| `/api/fund/transfer` | POST | `{account_id, transfer_direction, amount}` | 账户间资金划转 |
| `/api/fund/ctp_option_to_future` | POST | `{opt_account_id, ft_account_id, balance}` | 期权→期货跨市场划转 |
| `/api/fund/ctp_future_to_option` | POST | 同上 | 期货→期权跨市场划转 |
| `/api/fund/secu_transfer` | POST | `{account_id, transfer_direction, stock_code, volume, transfer_type}` | 证券划转 |

### 18.4 转融通 `/api/smt/*`

| Endpoint | Method | 请求体/参数 | 说明 |
|----------|--------|-------------|------|
| `/api/smt/quoter` | GET | `account_id` | 查询报价方 |
| `/api/smt/compact` | GET | `account_id` | 查询约定合约 |
| `/api/smt/orders` | GET | `account_id` | 查询 SMT 委托 |
| `/api/smt/negotiate_order_async` | POST | `{account_id, src_group_id, order_code, date, amount, apply_rate, dict_param={}}` | 异步协商下单 |
| `/api/smt/appointment_order_async` | POST | `{account_id, order_code, date, amount, apply_rate}` | 异步预约委托 |
| `/api/smt/appointment_cancel_async` | POST | `{account_id, apply_id}` | 异步取消预约 |
| `/api/smt/compact_renewal_async` | POST | `{account_id, cash_compact_id, order_code, defer_days, defer_num, apply_rate}` | 异步合约展期 |
| `/api/smt/compact_return_async` | POST | `{account_id, src_group_id, cash_compact_id, order_code, occur_amount}` | 异步合约归还 |

### 18.5 银证转账 `/api/bank/*`

| Endpoint | Method | 请求体/参数 | 说明 |
|----------|--------|-------------|------|
| `/api/bank/transfer_in` | POST | `{account_id, bank_no, bank_account, balance, bank_pwd="", fund_pwd=""}` | 银行转证券 |
| `/api/bank/transfer_out` | POST | 同上 | 证券转银行 |
| `/api/bank/transfer_in_async` | POST | 同上 | 异步银行转证券 |
| `/api/bank/transfer_out_async` | POST | 同上 | 异步证券转银行 |
| `/api/bank/info` | GET | `account_id` | 查询绑定银行 |
| `/api/bank/amount` | POST | `{account_id, bank_no, bank_account, bank_pwd}` | 查询银行余额 |
| `/api/bank/transfer_stream` | GET | `account_id`, `start_date`, `end_date`, `bank_no=""`, `bank_account=""` | 查询转账流水 |

---

## 十九、WebSocket 实时推送

### 19.1 `/ws/realtime` — 实时行情订阅
- **协议**: 客户端发送 `{"stocks": ["000001.SZ"], "period": "tick"}`（支持 tick/1m/5m/1d 等）
- **功能**: 逐只股票订阅实时行情，先 REST 拉取历史数据，再通过 WS 推送增量

### 19.2 `/ws/whole_quote` — 全市场行情订阅
- **协议**: 客户端发送 `{"codes": ["SH", "SZ"]}`
- **功能**: 全市场行情批量订阅

### 19.3 `/ws/download_progress` — 下载进度推送
- **协议**: 客户端发送 `{"stocks": [...], "period": "1d", "start_time": "...", "end_time": "..."}`
- **推送**: `{"finished": N, "total": M, "stock": "...", "status": "ok"}`，完成后返回 `{"status": "done", "results": {...}}`

### 19.4 `/ws/formula` — 公式实时计算
- **订阅**: `{"action": "subscribe", "formula_name": "MA", "stock_code": "000001.SZ", "period": "1d", "count": -1, "dividend_type": "none", "params": {}}`
- **确认**: `{"action": "subscribed", "seq_id": 123}`
- **推送**: `{"type": "formula_update", "formula_name": "MA", "stock_code": "...", "data": {...}}`
- **取消**: `{"action": "unsubscribe", "seq_id": 123}`

### 19.5 `/ws/trade` — 交易事件推送（需 `?api_key=xxx`）
- **事件类型**: `order`, `trade`, `order_error`, `cancel_error`, `connected`, `disconnected`, `asset`, `position`, `account_status`

### 19.6 `/ws/l2_thousand` — L2 千档行情
- **协议**: 客户端发送 `{"stocks": ["000001.SZ"]}`
- **功能**: L2 千档行情实时推送（需要 Level-2 权限）

---

## 二十、旧版兼容接口 `/api/*`

| Endpoint | Method | 参数 | 说明 |
|----------|--------|------|------|
| `/api/history` | GET | `stock`, `period="1d"`, `count=100`, `fields` | 单只股票历史 K 线 |
| `/api/batch_history` | GET | `stocks`, `period`, `count`, `fields` | 批量历史 K 线 |
| `/api/full_tick` | GET | `stocks` | 全推行情 |
| `/api/sector_stocks` | GET | `sector` | 板块成分股 |
| `/api/instrument_detail` | GET | `stock` | 合约详情 |
| `/api/download` | POST | `{stock, period="1d", start, end}` | 单只股票下载 |

---

## 常用参数说明

| 参数 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `stock` / `stock_code` | string | `000001.SZ` | 单只股票代码 |
| `stocks` / `stock_list` | string | `000001.SZ,600000.SH` | 多只股票（逗号分隔） |
| `period` | string | `1d` / `1m` / `5m` / `tick` / `l2thousand` | K 线周期 |
| `start_time` / `end_time` | string | `20240101` / `2024-01-01` | 时间范围 |
| `count` | int | `-1` / `100` | 返回条数，`-1` 表示全部 |
| `dividend_type` | string | `none` / `front` / `back` | 复权方式：不复权/前复权/后复权 |
| `fields` | string | `open,high,low,close,volume` | 返回字段（逗号分隔） |
| `account_id` | string | — | 资金账号 |
| `order_type` | int | — | 委托类型（详见 xtquant 文档） |
| `price_type` | int | `5` | 报价类型，`5` 为市价 |

---

## 注意事项

1. **并发安全**: 所有 xtdata 调用已通过 `asyncio.Lock` 串行化，HTTP 端点无需额外处理并发。
2. **BSON 断言崩溃**: 若调用 `get_local_data` / `get_market_data_ex` 时进程崩溃（`Assertion failed: u < 1000000`），**重启 QMT 客户端软件**即可恢复。
3. **交易接口**: 需要在服务端启用交易模块并配置 `X-API-Key`。
4. **Level-2 数据**: L2 相关接口需要 QMT 客户端具备 Level-2 行情权限。
