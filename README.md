# Ptrade Order Tool

Ptrade Order Tool 是一个轻量桌面工具，用于把 PTrade 盘后导出的持仓 JSON 转换成次日自动监控交易所需的订单 JSON。项目包含两部分：

- 桌面工具：导入盘后数据、编辑并确认买单/止盈单/止损单、导出订单 JSON。
- PTrade 策略脚本：[src/ptrade_order_tool/runtime/in-app.py](/Users/mark/SelfFiles/PtradeTool/src/ptrade_order_tool/runtime/in-app.py)：在 PTrade 量化环境中读取订单 JSON 并执行自动监控。

软件目标是把每日下单计划从手工改 JSON，改成可检查、可提醒、可重复导出的桌面工作流。

## 当前能力

- 自动或手动导入 `ptrade_data/YYYYMMDD.json`。
- 识别 PTrade 盘后 JSON 的 `Fund` 和 `Hold` 结构。
- 标准券等非股票资产不进入持仓股票列表；其市值计入可用余额校准，股票市值只统计真实持仓股票。
- 顶部展示账户总额、股票市值、可用余额。
- 按 `全部 / 开仓 / 持仓` 查看股票单元。
- 每个股票单元展示股票代码、股票名和持仓信息。
- 支持按股票代码、股票名、拼音、首字母搜索股票。
- 股票基础数据通过 Tushare Pro `stock_basic` 缓存到本地，交易日历通过 `trade_cal` 缓存到本地。
- 打开软件时会异步尝试生成或更新股票基础数据，不阻塞窗口。
- 支持买单、止盈单、止损单多条添加和删除。
- 每条订单必须点击确认后才允许导出。
- 删除订单支持临时撤销。
- 价格和股数使用位数输入控件，支持键盘输入和点击位数选择数字。
- 持仓股的 `sell_profit` 合计和 `sell_loss` 合计分别校验是否等于 `enable_amount`。
- 历史日期只读，但可以重新导出订单 JSON。
- 持仓导入时，如果上一交易日订单 JSON 存在对应止盈/止损单，会自动继承并调整为当前 `enable_amount`，状态为未确认。
- 导出的订单 JSON 只保留 `stock_name` 和各订单的 `price/shares`。

## 项目结构

```text
PtradeTool/
  src/ptrade_order_tool/       桌面工具源码
  tests/                       自动化测试
  tests/fixtures/              盘后 JSON 和订单 JSON 测试样例
  src/ptrade_order_tool/runtime/in-app.py
                                PTrade 量化环境自动监控脚本
  scripts/build_macos.sh       macOS 打包脚本
  scripts/build_windows.ps1    Windows 打包脚本
  ptrade-order-tool.spec       PyInstaller 打包配置
  pyproject.toml               Python 项目配置
```

运行产物不会进入 git：`.venv/`、`build/`、`dist/`、缓存目录、临时目录都已在 `.gitignore` 中排除。

## 日常使用流程

1. 打开桌面工具。
2. 在 `设置目录` 中配置：
   - PTrade 盘后目录：存放 `ptrade_data/YYYYMMDD.json`。
   - 订单导出目录：导出给 `in-app.py` 读取的 `order_data/YYYYMMDD.json`。
   - Tushare Token：可直接输入，软件会保存到应用数据目录的 `.env`。
3. 软件自动打开最新的盘后 JSON。
4. 检查顶部账户总额、股票市值、可用余额是否符合预期。
5. 对每个股票添加或修改订单。
6. 每条订单确认后再导出。
7. 将导出的 `order_data/YYYYMMDD.json` 放到 PTrade 研究环境对应目录。
8. PTrade 中运行 [src/ptrade_order_tool/runtime/in-app.py](/Users/mark/SelfFiles/PtradeTool/src/ptrade_order_tool/runtime/in-app.py) 进行次日自动监控。

## Tushare Token

Token 可以通过三种方式配置，读取优先级如下：

1. 系统环境变量 `TUSHARE_TOKEN`
2. 可执行文件同目录 `.env`
3. 应用数据目录 `.env`

推荐直接在软件的 `设置目录` 窗口输入 Token。留空表示不修改已有 Token。

## 输入 JSON

盘后输入 JSON 以 PTrade 导出格式为准，本项目使用真实样例锁定结构：

- [tests/fixtures/ptrade_20260225.json](/Users/mark/SelfFiles/PtradeTool/tests/fixtures/ptrade_20260225.json)

当前导入链路使用：

- `Fund.cash`
- `Fund.positions_value`
- `Fund.portfolio_value`
- `Hold` 中的证券代码、证券名称、持仓数量、可用数量、最新价、成本价、市值、盈亏等字段

标准券处理规则：

- 标准券不作为股票出现在编辑界面。
- 标准券市值不计入股票市值。
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
- 持仓股止盈合计和止损合计不等于 `enable_amount` 时提示，但不强制阻断。
- 开仓股存在卖单不阻断，因为可用于次日继承。
- 已存在导出文件时会提示是否覆盖。

## 运行开发版

```bash
python3 -m pip install -e ".[dev]"
.venv/bin/python -m ptrade_order_tool.main
```

也可以使用入口命令：

```bash
ptrade-order-tool
```

## 测试

```bash
.venv/bin/python -m pytest -v
```

当前测试覆盖导入、账户校准、股票基础数据、交易日历、草稿继承、导出校验、数字输入控件、设置窗口、启动流程和主要 UI 操作。

## 打包

macOS：

```bash
bash scripts/build_macos.sh
```

Windows PowerShell：

```powershell
scripts/build_windows.ps1
```

打包产物输出到 `dist/`。当前 macOS `.app` 约 103M，主要体积来自 Python 运行时和 PySide6/Qt。

## 设计边界

- 桌面应用使用 Python + PySide6，不使用 Web 界面。
- 本地数据使用 SQLite，配置使用 JSON，Token 使用 `.env`。
- 历史日期不可修改，避免误改旧交易日计划。
- 订单必须逐条确认，导出前以确认状态作为明确边界。
- PTrade 策略脚本和桌面工具分离：桌面工具只生成订单 JSON，不直接下单。
