# Ptrade Order Tool

Ptrade Order Tool 是一个用于维护 PTrade 日常交易计划的桌面工具。它导入 PTrade 盘后持仓 JSON，编辑开仓、止盈、止损等条件单，校验确认后导出给 PTrade 策略脚本读取的订单 JSON。

项目包含两部分：

- 桌面工具：维护股票基础数据、交易日历、交易日草稿、条件单确认和订单导出。
- 运行脚本：[src/ptrade_order_tool/runtime/in-app.py](src/ptrade_order_tool/runtime/in-app.py)，在 PTrade 量化环境中读取订单 JSON 并执行自动监控。

目标是把每日手工改 JSON 的流程整理成可搜索、可校验、可确认、可回看、可重复导出的稳定工作流。

## 核心能力

- 自动或手动导入 `ptrade_data/YYYYMMDD.json`；没有盘后 JSON 时可创建空白交易日。
- 解析 `Fund`、`Hold`，展示账户总额、持仓市值、可用余额、开仓金额。
- 标准券等非股票资产不进入股票列表；其市值用于校准可用余额。
- 按 `全部 / 开仓 / 持仓` 查看股票单元，支持历史日期只读回看。
- 支持代码、名称、拼音、拼音首字母搜索股票，候选可键盘或鼠标选择。
- 支持突破买、回调买、止盈、止损多条条件单添加、确认、删除和一次撤销。
- 价格和股数使用位数输入控件，支持键盘输入、千分位显示、增加/删除最高位，并防止滚轮误改。
- 订单修改后自动回到未确认状态；存在未确认订单或阻断项时禁止导出。
- “更多”菜单支持将当前管理日期的盘后 JSON 和导出 JSON 同步到当前界面。
- 持仓止盈/止损合计、开仓卖单合计和止盈/止损价格关系会在股票卡片内即时提示。
- 上一交易日订单 JSON 中的止盈/止损单可按原价格和股数继承到当前持仓，并设为未确认。
- 股票基础数据、交易日历、日线行情可通过 Tushare Pro 维护；网络异常不会阻断编辑和导出。
- 后台 worker 处理 Tushare 请求，避免阻塞 UI，并管理快速切换日期时的 worker 生命周期。

## 项目结构

```text
PtradeTool/
  src/ptrade_order_tool/          桌面工具源码
  src/ptrade_order_tool/data/     SQLite、PTrade JSON、Tushare、导出模块
  src/ptrade_order_tool/ui/       PySide6 界面和交互控件
  src/ptrade_order_tool/runtime/  PTrade 环境运行脚本
  tests/                          自动化测试
  tests/fixtures/                 测试样例
  scripts/build_macos.sh          macOS 打包脚本
  scripts/build_windows.ps1       Windows 打包脚本
  ptrade-order-tool.spec          PyInstaller 打包配置
  pyproject.toml                  Python 项目配置
```

`.venv/`、`build/`、`dist/`、根目录 `data/`、缓存目录、临时目录和日志文件不进入 git。

## 日常使用

1. 打开桌面工具。
2. 在“设置目录及Token”中配置：
   - PTrade 盘后目录：存放 `ptrade_data/YYYYMMDD.json`。
   - 订单导出目录：生成 `order_data/YYYYMMDD.json`。
   - Tushare Token：维护股票基础数据、交易日历和可选日线行情。
3. 软件优先打开最新盘后 JSON；找不到时打开最近交易日的空白交易单。
4. 检查账户信息，维护开仓、止盈、止损订单。
5. 每条订单确认后执行导出。
6. 如当前管理日期的盘后 JSON 或导出 JSON 与界面不一致，可在“更多”中执行“同步JSON到界面”；盘后 JSON 同步 `Fund/Hold`，导出 JSON 同步订单计划并设为已确认。
7. 将导出的 `order_data/YYYYMMDD.json` 放到 PTrade 研究环境对应目录。
8. 在 PTrade 中运行 [in-app.py](src/ptrade_order_tool/runtime/in-app.py) 进行次日自动监控。

## Tushare Token

Token 读取优先级：

1. 系统环境变量 `TUSHARE_TOKEN`
2. 可执行文件同目录 `.env`
3. 应用数据目录 `.env`

推荐在设置窗口输入 Token。留空表示不修改已有 Token。

使用的 Tushare 接口：

- `stock_basic`：股票代码、名称和拼音搜索基础数据。
- `trade_cal`：交易日历。
- `daily`：日线价格、涨跌幅、成交额和迷你 K 线。

日线行情是可选增强链路。Token 无效、网络异常或接口暂不可用时，界面静默隐藏行情，不影响订单编辑和导出。

## 本地数据

桌面工具使用 SQLite 保存状态：

- `sessions`：交易日草稿、源 JSON 路径、导出路径和导出状态。
- `fund_snapshots`：账户资金快照。
- `holdings`：导入的持仓数据。
- `draft_stocks`：手动添加的开仓股票。
- `orders`：条件单草稿。
- `stock_basic`：股票基础数据缓存。
- `trade_calendar`：交易日历缓存。
- `daily_quotes`：日线行情缓存。

缓存表使用主键 upsert。行情按日期做 in-flight 去重；旧日期请求返回后只写缓存，不刷新当前 UI。

## 输入 JSON

盘后输入 JSON 以 PTrade 导出格式为准，测试样例见 [tests/fixtures/ptrade_20260225.json](tests/fixtures/ptrade_20260225.json)。

导入链路使用：

- `Fund.cash`
- `Fund.positions_value`
- `Fund.portfolio_value`
- `Hold` 中的证券代码、证券名称、持仓数量、可用数量、最新价、成本价、市值、盈亏等字段

标准券规则：

- 不作为股票出现在编辑界面。
- 市值不计入持仓市值。
- 市值加入校准后的可用余额。

## 导出 JSON

导出路径：

```text
order_data/YYYYMMDD.json
```

导出结构：

```json
{
  "002153.SZ": {
    "stock_name": "石基信息",
    "buy_limit": [
      {"price": 11.4, "shares": 1400}
    ],
    "sell_profit": [
      {"price": 12.65, "shares": 2800}
    ],
    "sell_loss": [
      {"price": 10.99, "shares": 2800}
    ]
  }
}
```

导出规则：

- 只导出已确认订单。
- 价格必须大于 0，最多两位小数。
- 股数必须大于 0，且为 100 股整数倍。
- 未确认订单、无效价格或无效股数会阻断导出。
- 持仓止盈/止损合计不等于持仓数量时在股票卡片内提示，不阻断导出。
- 开仓卖单不强制阻断，可用于次日继承。
- 已存在导出文件时会提示是否覆盖。

导出 JSON 只包含 `stock_name` 和订单 `price/shares`，供 PTrade 运行脚本消费。

## 开发运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m ptrade_order_tool.main
```

也可以使用入口命令：

```bash
ptrade-order-tool
```

## 测试与验证

全量测试：

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

空白检查：

```bash
git diff --check
```

测试覆盖导入、账户校准、草稿存储、历史删除、股票搜索、交易日历、Tushare 客户端、行情缓存、订单继承、导出校验、数字输入控件、设置窗口、启动流程、主要 UI 操作、后台 worker 生命周期和打包脚本。

## 打包

macOS：

```bash
bash scripts/build_macos.sh
```

Windows PowerShell：

```powershell
scripts/build_windows.ps1
```

两个脚本共用 [ptrade-order-tool.spec](ptrade-order-tool.spec)。macOS 下生成 `.app`，Windows 下生成 onedir 产物。输出目录为 `dist/`。

## 稳定性边界

- 桌面工具使用 Python + PySide6；本地状态使用 SQLite，配置使用 JSON，Token 使用 `.env`。
- UI 渲染不依赖盘后 JSON 或日线行情，主流程不会被可选数据阻断。
- Tushare 请求放在后台 worker 中；SQLite 读写集中在主线程。
- 后台 worker 由窗口统一持有和收尾，避免 QThread 运行中被销毁。
- 快速切换日期时，旧日期 worker 返回的数据只写缓存，不刷新当前 UI。
- 历史日期不可直接编辑，避免误改旧交易日计划。
- 订单必须逐条确认，导出前以确认状态作为明确边界。
- 桌面工具只生成订单 JSON，不直接下单。
- PTrade 运行脚本盘前读取不到新的订单 JSON 时，会保留上一轮有效监控计划；买单依赖 `buy_date` 跳过非买入日，止盈/止损继续作为持仓风险控制承接。
