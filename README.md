# Ptrade Order Tool

Ptrade Order Tool 是一个面向 PTrade 日常交易计划维护的桌面工具。它可以导入 PTrade 盘后持仓 JSON，也可以在没有盘后 JSON 的情况下直接创建空白交易日，编辑开仓、止盈、止损等条件单，并导出给 PTrade 策略脚本读取的订单 JSON。

项目包含两部分：

- 桌面工具：维护股票基础数据、交易日历、交易日草稿、条件单确认和订单 JSON 导出。
- PTrade 运行脚本：[src/ptrade_order_tool/runtime/in-app.py](src/ptrade_order_tool/runtime/in-app.py)：在 PTrade 量化环境中读取订单 JSON 并执行自动监控。

核心目标是把每日交易计划从手工改 JSON，整理成可搜索、可校验、可确认、可回看、可重复导出的稳定桌面工作流。

## 当前能力

- 自动或手动导入 `ptrade_data/YYYYMMDD.json`。
- 没有盘后 JSON 时也可以打开空白交易日并编辑开仓交易单。
- 解析 PTrade 盘后 JSON 的 `Fund` 和 `Hold` 数据。
- 标准券等非股票资产不进入股票列表；其市值不计入持仓市值，但参与可用余额校准。
- 顶部展示账户总额、持仓市值、可用余额、开仓金额。
- 按 `全部 / 开仓 / 持仓` 查看股票单元，进入日期时默认显示持仓页。
- 支持按股票代码、股票名称、拼音、拼音首字母搜索股票。
- 股票搜索候选支持键盘上下选择、回车确认、鼠标悬停高亮和点击确认。
- 股票基础数据通过 Tushare Pro `stock_basic` 缓存到本地 SQLite。
- 交易日历通过 Tushare Pro `trade_cal` 自动维护，用于日期列表、历史回看和下一交易日推断。
- 日线行情通过 Tushare Pro `daily` 可选拉取；拿到数据时展示价格、涨跌幅、成交额和迷你 K 线，拿不到时静默隐藏。
- 行情和基础数据拉取使用后台 worker，不阻塞 UI；worker 有 in-flight 去重和生命周期管理，避免快速切换日期时重复拉取或闪退。
- 支持突破买、回调买、止盈、止损多条条件单添加、确认和删除。
- 每条订单修改后会回到未确认状态；存在未确认或阻断项时禁止导出。
- 股票单元和单条订单均支持删除，删除后支持一次撤销。
- 历史日期只读；可通过“删除历史数据”专门清理某日数据，删除后该日会以空日期补回，`全部` 为 0。
- 价格和股数使用位数输入控件，支持键盘输入、光标位重置、禁止滚轮误改数值。
- 持仓股的止盈合计和止损合计会校验是否等于可卖数量。
- 持仓导入时，如果上一交易日订单 JSON 存在对应止盈/止损单，会自动继承并按当前可卖数量调整，状态为未确认。
- 导出的订单 JSON 只保留 `stock_name` 和各订单的 `price/shares`。

## 项目结构

```text
PtradeTool/
  src/ptrade_order_tool/          桌面工具源码
  src/ptrade_order_tool/data/     SQLite、PTrade JSON、Tushare、导出相关数据模块
  src/ptrade_order_tool/ui/       PySide6 界面和交互控件
  src/ptrade_order_tool/runtime/  PTrade 环境运行脚本
  tests/                          自动化测试
  tests/fixtures/                 盘后 JSON 和订单 JSON 测试样例
  scripts/build_macos.sh          macOS 打包脚本
  scripts/build_windows.ps1       Windows 打包脚本
  ptrade-order-tool.spec          PyInstaller 跨平台打包配置
  pyproject.toml                  Python 项目配置
```

运行产物不会进入 git：`.venv/`、`build/`、`dist/`、根目录 `data/`、缓存目录和临时目录都应由 `.gitignore` 排除。

## 日常使用流程

1. 打开桌面工具。
2. 在“设置目录及Token”中配置：
   - PTrade 盘后目录：存放 `ptrade_data/YYYYMMDD.json`。
   - 订单导出目录：导出给 `in-app.py` 读取的 `order_data/YYYYMMDD.json`。
   - Tushare Token：用于维护股票基础数据、交易日历和可选日线行情。
3. 软件会优先打开最新盘后 JSON；如果没有盘后 JSON，则打开最近交易日的空白交易单。
4. 检查顶部账户总额、持仓市值、可用余额和开仓金额。
5. 使用股票搜索框添加开仓股票，或在持仓股票中维护止盈/止损。
6. 每条订单确认后再导出。
7. 将导出的 `order_data/YYYYMMDD.json` 放到 PTrade 研究环境对应目录。
8. PTrade 中运行 [src/ptrade_order_tool/runtime/in-app.py](src/ptrade_order_tool/runtime/in-app.py) 进行次日自动监控。

## Tushare Token

Token 可以通过三种方式配置，读取优先级如下：

1. 系统环境变量 `TUSHARE_TOKEN`
2. 可执行文件同目录 `.env`
3. 应用数据目录 `.env`

推荐直接在软件的设置窗口输入 Token。留空表示不修改已有 Token。

当前使用的 Tushare 接口：

- `stock_basic`：股票代码、名称、拼音搜索基础数据。
- `trade_cal`：交易日历维护。
- `daily`：交易日价格、涨跌幅、成交额和迷你 K 线展示。

日线行情是可选增强链路：Token 无效、网络异常、接口暂不可用或盘后数据未返回时，界面不会报错，也不会阻断订单编辑和导出。

## 本地数据

桌面工具使用 SQLite 保存本地状态，主要数据包括：

- `sessions`：交易日草稿、源 JSON 路径、导出路径和导出状态。
- `fund_snapshots`：账户资金快照。
- `holdings`：导入的持仓数据。
- `draft_stocks`：手动添加的开仓股票。
- `orders`：条件单草稿。
- `stock_basic`：Tushare 股票基础数据缓存。
- `trade_calendar`：交易日历缓存。
- `daily_quotes`：日线行情缓存。

缓存表使用主键 upsert，不会因重复拉取产生重复记录。行情拉取按日期做 in-flight 去重；旧日期请求返回后会写入缓存，但不会刷新当前日期 UI。

## 输入 JSON

盘后输入 JSON 以 PTrade 导出格式为准，本项目使用真实样例锁定结构：

- [tests/fixtures/ptrade_20260225.json](tests/fixtures/ptrade_20260225.json)

当前导入链路使用：

- `Fund.cash`
- `Fund.positions_value`
- `Fund.portfolio_value`
- `Hold` 中的证券代码、证券名称、持仓数量、可用数量、最新价、成本价、市值、盈亏等字段

标准券处理规则：

- 标准券不作为股票出现在编辑界面。
- 标准券市值不计入持仓市值。
- 标准券市值加入校准后的可用余额。

## 导出 JSON

导出文件路径为：

```text
order_data/YYYYMMDD.json
```

导出结构示例：

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

- 未确认订单会阻断导出。
- 价格必须大于 0，最多两位小数。
- 股数必须大于 0，且为 100 股整数倍。
- 持仓股止盈合计和止损合计不等于可卖数量时提示，但不强制阻断。
- 开仓股存在卖单不阻断，因为可用于次日继承。
- 已存在导出文件时会提示是否覆盖。

## 开发运行

建议使用虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
```

运行桌面工具：

```bash
.venv/bin/python -m ptrade_order_tool.main
```

也可以使用入口命令：

```bash
ptrade-order-tool
```

## 测试与验证

运行全量测试：

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

当前测试覆盖导入、账户校准、草稿存储、历史删除、股票搜索、交易日历、Tushare 客户端、日线行情缓存、订单继承、导出校验、数字输入控件、设置窗口、启动流程、主要 UI 操作、后台 worker 生命周期和打包脚本。

检查代码空白：

```bash
git diff --check
```

## 打包

macOS：

```bash
bash scripts/build_macos.sh
```

Windows PowerShell：

```powershell
scripts/build_windows.ps1
```

两个脚本共用 [ptrade-order-tool.spec](ptrade-order-tool.spec)。spec 会在 macOS 下额外生成 `.app`，Windows 下生成 onedir 产物，避免 macOS `BUNDLE` 配置影响 Windows 打包。

打包产物输出到 `dist/`。当前 macOS `.app` 约 103M，主要体积来自 Python 运行时和 PySide6/Qt。

## 稳定性设计

- UI 渲染不依赖盘后 JSON 或日线行情，主流程不会被可选数据阻断。
- Tushare 网络请求放在后台 worker 中执行，SQLite 读写集中在主线程。
- 后台 worker 由窗口统一持有和收尾，避免 QThread 运行中被销毁。
- 日线行情按日期做 in-flight 去重，重复切换日期不会重复启动同日拉取。
- 旧日期 worker 返回的数据只写缓存，不刷新当前 UI，避免状态错位。
- 删除历史日期会清理草稿、持仓、订单和手动股票；日期列表会从交易日历补回空日期。
- 打包配置不引入额外重型依赖，尽量控制产物体积。

## 设计边界

- 桌面应用使用 Python + PySide6，不使用 Web 界面。
- 本地数据使用 SQLite，配置使用 JSON，Token 使用 `.env`。
- 历史日期不可直接编辑，避免误改旧交易日计划。
- 订单必须逐条确认，导出前以确认状态作为明确边界。
- PTrade 运行脚本和桌面工具分离：桌面工具只生成订单 JSON，不直接下单。
