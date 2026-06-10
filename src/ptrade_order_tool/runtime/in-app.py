"""
PTrade量化环境的策略代码
功能：对接本地管理的下单数据，实现自动下单
流程：每个交易日更新下单数据的json文件到量化环境
"""


import json
import pathlib
from copy import deepcopy
from datetime import datetime


# ---------- 参数区 ----------
# 买单委托未成撤单时间（s）
CANCEL_SECONDS_FOR_BUY = 180

# 卖单委托未成撤单时间（s）
CANCEL_SECONDS_FOR_SELL = 18

# 文件夹路径
ORDER_DIR = "order_data/" # 斜杠不要少，因为禁用了os模块
OUTPUT_DIR = "ptrade_data/"

# 账号（用于核查有效性）
ACCOUNT = "8884032925"
# ----------------------------


def read_json(json_path):
    """读取json文件内容，返回字典形式"""
    return json.loads(pathlib.Path(json_path).read_text(encoding="utf-8"))


def update_json(json_path, data_dict, indent=2):
    """保存json文件"""
    pathlib.Path(json_path).write_text(json.dumps(data_dict, ensure_ascii=False, indent=indent), encoding="utf-8")


def ts_code_trans(ts_code):
    """转换股票代码到量化环境符合的格式"""
    return ts_code.replace(".SH", ".SS") # 上证股票改成量化环境对应的后缀


def stock_code_trans(stock_code):
    """"转换股票代码到tushare符合的格式"""
    if '.' not in stock_code:
        if stock_code.startswith('00') or stock_code.startswith('30'): # 深市
            stock_code = stock_code + ".SZ"
        elif stock_code.startswith('60') or stock_code.startswith('68'): # 沪市
            stock_code = stock_code + ".SH"
    return stock_code.replace(".SS", ".SH").replace(".XSHG", ".SH").replace(".XSHE", ".SZ")


def get_quote_level_price(snapshot, group_name, level=5):
    """从盘口队列中读取指定档位价格，缺失时返回None"""
    quote_group = snapshot.get(group_name) or {}
    level_data = quote_group.get(level)
    if not level_data:
        return None
    return level_data[0]


def date_str_to_weekday(date_str):
    """日期字符串转为星期"""
    # 将 YYYYMMDD 字符串解析成 datetime 对象
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    
    # 获取对应的周几，中文格式
    weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return weekday_cn[date_obj.weekday()]  # weekday()：0表示周一，6表示周日
        

def initialize(context):
    """初始化，该函数只会在交易启动的时候运行一次"""
    # 参数传递
    g.cancel_seconds_for_buy = CANCEL_SECONDS_FOR_BUY
    g.cancel_seconds_for_sell = CANCEL_SECONDS_FOR_SELL
    g.order_dir = ORDER_DIR
    g.output_dir = OUTPUT_DIR
    g.account = ACCOUNT
    
    # 研究界面根目录路径
    g.notebook_path = get_research_path()

    # 在研究界面创建输出目录
    create_dir(g.output_dir)
    
    # 信息字典
    g.order_result = {} # 存在监控数据
    g.entrust_record = {} # 当前交易日委托记录 {"buy"/"sell_profit"/"sell_loss": {order_id: 委托信息, ...}}
    
    # 标记order数据是否有效
    g.order_data_ready = False
    
    # 启用监控
    run_interval(
        context,
        tick_logic, # 自定义的策略函数
        seconds=3 # 每3s触发（量化环境目前最小即为3s） 
    ) # 默认使用券商配置时间范围进行处理
 

def before_trading_start(context, data):
    """交易日盘前处理，拿到对应的监控数据，该函数在开启交易时立即执行，从隔日开始每天9:10分(默认)执行"""
    # 当前日期
    g.current_date = datetime.now().strftime('%Y%m%d')
    
    # 检查账号有效期
    next_trading_date = get_trading_day_by_date(g.current_date, day=1)
    flag = permission_test(account=g.account, end_date=next_trading_date)
    if not flag:
        log.warning(f"！！！提示：账号将于下一个交易日 {next_trading_date} {date_str_to_weekday(next_trading_date)} 失效（授权不通过）")
        
    # 委托记录重置
    g.entrust_record.clear()
    
    # 读取order数据
    order_date = get_trading_day_by_date(g.current_date, day=-1) # 当前日期前一个交易日
    order_json_path = g.notebook_path + g.order_dir + f"{order_date}.json"
    try:
        order_result = read_json(order_json_path)
    except Exception as e:
        log.warning(f"读取order数据错误: {str(e)}")
        order_result = None
    
    # 数据有效时更新系列参数（order_result, buy_date）
    if order_result:
        # 拿到对应数据
        g.order_result.clear()
        for ts_code, info_dict in order_result.items():
            stock_code = ts_code_trans(ts_code) # 代码转换处理
            g.order_result[stock_code] = info_dict
        
        # 标记数据有效
        g.order_data_ready = True
        
    # 打印信息
    if g.order_data_ready:
        log.info("----- trading start -------")
        log.info(f"管理日期: {order_date} {date_str_to_weekday(order_date)}")
        log.info(f"当前日期: {g.current_date} {date_str_to_weekday(g.current_date)}")
        
        # 买单交易日期
        g.buy_date = get_trading_day_by_date(order_date, day=1)
        log.info(f"买单日期: {g.buy_date} {date_str_to_weekday(g.buy_date)}")
        
        log.info("监控股票:")
        for index, (ts_code, info_dict) in enumerate(g.order_result.items(), start=1):
            log.info(f"{index}. {ts_code} {info_dict}")
    else:
        log.info("没有获取到有效监控数据")
      
    log.info("盘前处理完毕")
    

def tick_logic(context):
    """每tick处理逻辑"""
    # 检查数据有效性
    if not g.order_data_ready:
        return    
    
    # 当前单位时间的开始时间，datetime.datetime对象(北京时间)
    now = context.blotter.current_dt
    
    # 先处理委托（撤单等）
    manage_entrust(context)
    
    # 逐票监控
    for stock_code, info_dict in g.order_result.items():
        # 股票名
        stock_name = info_dict["stock_name"]
        
        # 行情快照
        snapshot = get_snapshot(stock_code).get(stock_code)
        if not snapshot:
            log.warning(f"行情快照获取失败: {stock_code} {stock_name}")
            continue
        
        # 最新成交价
        current_price = snapshot["last_px"]
        # 最新高价
        current_high_price = snapshot["high_px"]
        # 最新低价
        current_low_price = snapshot["low_px"]

        # -------- 买入逻辑 --------
        # 买单日期才有效
        if g.current_date == g.buy_date:
            for buy_stop_order in info_dict.get("buy_stop", []): # 遍历买单 buy_stop
                # 此买单已匹配
                if buy_stop_order.get("order_done"):
                    continue
                   
                # 触发价
                buy_stop_trigger_price = buy_stop_order["price"]
                if current_price >= buy_stop_trigger_price: # 价格触发，>=
                    # 触发即标记买单已匹配
                    buy_stop_order["order_done"] = True

                    # 股数
                    buy_shares = buy_stop_order["shares"] 
                    
                    # 获取保护限价
                    buy_limit_price = get_quote_level_price(snapshot, "offer_grp", level=5) # 保护限价设置为卖5价
                    if not buy_limit_price:
                        buy_stop_order["order_status"] = "no_limit_price"
                        log.warning(f"stop买单保护限价获取失败: {stock_code} {stock_name}")
                        continue

                    # 核验账户资金
                    current_cash = context.portfolio.cash # 当前可用资金(不包含冻结资金)
                    cash_at_least = buy_shares * current_price # 至少资金
                    if current_cash < cash_at_least: # 资金不足，错过此买单
                        buy_stop_order["order_status"] = "insufficient_cash"
                        log.warning(f"资金不足错过stop买单: {stock_code} {stock_name}，当前可用资金 {current_cash:,.2f} < {cash_at_least:,.2f} 元")
                        continue

                    # 查看最新高价是否大于等于预设最大止盈位置，成立则忽略此买单（通常是高开情形）
                    sell_profit_orders = info_dict.get("sell_profit", [])
                    if sell_profit_orders: # 有止盈单才检查
                        sell_profit_trigger_price_max = max(sell_profit_order["price"] for sell_profit_order in sell_profit_orders) # 预设最大止盈位置
                        if current_high_price >= sell_profit_trigger_price_max:
                            buy_stop_order["order_status"] = "over_profit_price"
                            log.warning(f"高价超过预设止盈位置，忽略stop买单: {stock_code} {stock_name}，高价: {current_high_price}，预设止盈价: {sell_profit_trigger_price_max}")
                            continue

                    # 下单
                    order_id = order_market(stock_code, amount=buy_shares, market_type=4, limit_price=buy_limit_price) # 正数表示买入，负数表示卖出

                    # 下单成功
                    if order_id is not None:
                        # 记录委托
                        g.entrust_record.setdefault("buy", {})
                        g.entrust_record["buy"][order_id] = {
                            "stock_code": stock_code,
                            "stock_name": stock_name,
                            "current_price": current_price,
                            "entrust_shares": buy_shares,
                            "entrust_time": context.blotter.current_dt, # 委托下单时间
                            "order_dict": buy_stop_order # 记录买单信息
                        }
                        buy_stop_order["order_status"] = "entrusted"
                        
                        # 日志
                        log.info(f"stop买单委托提交: {stock_code} {stock_name}，现价: {current_price}，stop买单触发价: {buy_stop_trigger_price}，委托: {buy_shares}股")
                    else:
                        buy_stop_order["order_status"] = "entrust_failed"
                        # 日志
                        log.warning(f"stop买单委托失败: {stock_code} {stock_name}，现价: {current_price}，stop买单触发价: {buy_stop_trigger_price}，委托: {buy_shares}股")

            for buy_limit_order in info_dict.get("buy_limit", []): # 遍历买单 buy_limit
                # 此买单已匹配
                if buy_limit_order.get("order_done"):
                    continue
                   
                # 触发价
                buy_limit_trigger_price = buy_limit_order["price"]
                if current_price <= buy_limit_trigger_price: # 价格触发，<=
                    # 触发即标记买单已匹配
                    buy_limit_order["order_done"] = True

                    # 股数
                    buy_shares = buy_limit_order["shares"] 
                    
                    # 获取保护限价
                    buy_limit_price = get_quote_level_price(snapshot, "offer_grp", level=5) # 保护限价设置为卖5价
                    if not buy_limit_price:
                        buy_limit_order["order_status"] = "no_limit_price"
                        log.warning(f"limit买单保护限价获取失败: {stock_code} {stock_name}")
                        continue

                    # 核验账户资金
                    current_cash = context.portfolio.cash # 当前可用资金(不包含冻结资金)
                    cash_at_least = buy_shares * current_price # 至少资金
                    if current_cash < cash_at_least: # 资金不足，错过此买单
                        buy_limit_order["order_status"] = "insufficient_cash"
                        log.warning(f"资金不足错过limit买单: {stock_code} {stock_name}，当前可用资金 {current_cash:,.2f} < {cash_at_least:,.2f} 元")
                        continue

                    # 查看最新低价是否小于等于预设最小止损位置，成立则忽略此买单（通常是低开情形）
                    sell_loss_orders = info_dict.get("sell_loss", [])
                    if sell_loss_orders: # 有止损单才检查
                        sell_loss_trigger_price_min = min(sell_loss_order["price"] for sell_loss_order in sell_loss_orders) # 预设最小止损位置
                        if current_low_price <= sell_loss_trigger_price_min:
                            buy_limit_order["order_status"] = "under_loss_price"
                            log.warning(f"低价低于预设止损位置，忽略limit买单: {stock_code} {stock_name}，低价: {current_low_price}，预设止损价: {sell_loss_trigger_price_min}")
                            continue

                    # 下单
                    order_id = order_market(stock_code, amount=buy_shares, market_type=4, limit_price=buy_limit_price) # 正数表示买入，负数表示卖出

                    # 下单成功
                    if order_id is not None:
                        # 记录委托
                        g.entrust_record.setdefault("buy", {})
                        g.entrust_record["buy"][order_id] = {
                            "stock_code": stock_code,
                            "stock_name": stock_name,
                            "current_price": current_price,
                            "entrust_shares": buy_shares,
                            "entrust_time": context.blotter.current_dt, # 委托下单时间
                            "order_dict": buy_limit_order # 记录买单信息
                        }
                        buy_limit_order["order_status"] = "entrusted"
                        
                        # 日志
                        log.info(f"limit买单委托提交: {stock_code} {stock_name}，现价: {current_price}，limit买单触发价: {buy_limit_trigger_price}，委托: {buy_shares}股")
                    else:
                        buy_limit_order["order_status"] = "entrust_failed"
                        # 日志
                        log.warning(f"limit买单委托失败: {stock_code} {stock_name}，现价: {current_price}，limit买单触发价: {buy_limit_trigger_price}，委托: {buy_shares}股")
        
        # -------- 卖出逻辑 --------
        # 当前持仓
        try:
            stock_position = get_position(stock_code).enable_amount # 可用数量
            if stock_position <= 0: # 无效持仓
                continue
        except:
            log.warning(f"持仓获取失败: {stock_code} {stock_name}")
            continue
        
        for sell_profit_order in info_dict.get("sell_profit", []): # 遍历止盈单
            # 此止盈单已匹配
            if sell_profit_order.get("order_done"):
                continue

            # 触发价
            sell_profit_trigger_price = sell_profit_order["price"]
            if current_high_price >= sell_profit_trigger_price or sell_profit_order.get("re_entrust_shares"): # 价格触发，>=    
                # 股数
                sell_profit_shares = min(sell_profit_order.get("re_entrust_shares", sell_profit_order["shares"]), stock_position) # re_entrust_shares由撤单再下单时赋值
                
                # 获取保护限价
                sell_profit_limit_price = get_quote_level_price(snapshot, "bid_grp", level=5) # 保护限价设置为买5价
                if not sell_profit_limit_price:
                    log.warning(f"止盈单保护限价获取失败: {stock_code} {stock_name}")
                    continue
                
                # 下单
                order_id = order_market(stock_code, amount=-sell_profit_shares, market_type=4, limit_price=sell_profit_limit_price) # 正数表示买入，负数表示卖出
                
                # 下单成功
                if order_id is not None:
                    # 记录委托
                    g.entrust_record.setdefault("sell_profit", {})
                    g.entrust_record["sell_profit"][order_id] = {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "current_high_price": current_high_price,
                        "entrust_shares": sell_profit_shares,
                        "entrust_time": context.blotter.current_dt, # 委托下单时间
                        "order_dict": sell_profit_order # 记录止盈单信息
                    }

                    # 标记止盈单已匹配
                    sell_profit_order["order_done"] = True
                    
                    # 日志
                    log.info(f"止盈单委托提交: {stock_code} {stock_name}，现高价: {current_high_price}，止盈单触发价: {sell_profit_trigger_price}，委托: {sell_profit_shares}股")
                else:
                    # 日志
                    log.warning(f"止盈单委托失败: {stock_code} {stock_name}，现高价: {current_high_price}，止盈单触发价: {sell_profit_trigger_price}，委托: {sell_profit_shares}股")
        
        for sell_loss_order in info_dict.get("sell_loss", []): # 遍历止损单
            # 此止损单已匹配
            if sell_loss_order.get("order_done"):
                continue

            # 触发价
            sell_loss_trigger_price = sell_loss_order["price"]
            if current_price <= sell_loss_trigger_price or sell_loss_order.get("re_entrust_shares"): # 价格触发，<=                
                # 股数
                sell_loss_shares = min(sell_loss_order.get("re_entrust_shares", sell_loss_order["shares"]), stock_position) # re_entrust_shares由撤单再下单时赋值
                
                # 获取保护限价
                sell_loss_limit_price = get_quote_level_price(snapshot, "bid_grp", level=5) # 保护限价设置为买5价
                if not sell_loss_limit_price:
                    log.warning(f"止损单保护限价获取失败: {stock_code} {stock_name}")
                    continue
                
                # 下单
                order_id = order_market(stock_code, amount=-sell_loss_shares, market_type=4, limit_price=sell_loss_limit_price) # 正数表示买入，负数表示卖出
                
                # 下单成功
                if order_id is not None:
                    # 记录委托
                    g.entrust_record.setdefault("sell_loss", {})
                    g.entrust_record["sell_loss"][order_id] = {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "current_price": current_price,
                        "entrust_shares": sell_loss_shares,
                        "entrust_time": context.blotter.current_dt, # 委托下单时间
                        "order_dict": sell_loss_order # 记录止损单信息
                    }

                    # 标记止损单已匹配
                    sell_loss_order["order_done"] = True
                    
                    # 日志
                    log.info(f"止损单委托提交: {stock_code} {stock_name}，现价: {current_price}，止损单触发价: {sell_loss_trigger_price}，委托: {sell_loss_shares}股")
                else:
                    # 日志
                    log.warning(f"止损单委托失败: {stock_code} {stock_name}，现价: {current_price}，止损单触发价: {sell_loss_trigger_price}，委托: {sell_loss_shares}股")
                        
    # log.info("当前tick执行完毕")
 

def manage_entrust(context):
    """处理委托，撤单时间由CANCEL_SECONDS参数控制"""
    # 当前时间，datetime.datetime对象(北京时间)
    now = context.blotter.current_dt
    
    # 遍历买单委托，买单未成撤单
    for order_id, entrust_info in g.entrust_record.get("buy", {}).items():
        # 已经核查过
        if entrust_info.get("check_done"):
            continue

        entrust_time = entrust_info["entrust_time"]
        if (now - entrust_time).total_seconds() > g.cancel_seconds_for_buy: # 达到指定时间间隔
            try:
                # 获取指定订单
                order_info = get_order(order_id) # 返回一个list，该list中只包含一个Order对象
                if isinstance(order_info, list):
                    order_info = order_info[0]

                amount = order_info.amount # 下单数量，买入是正数，卖出是负数
                filled = order_info.filled # 成交数量，买入时为正数，卖出时为负数

                if filled != amount: # 没有全部成交，需要撤单
                    log.info(f'买单撤单: {order_info}')
                    cancel_order(order_id)

                # 标记已核查
                entrust_info["check_done"] = True
            except Exception as e:
                log.warning(f"核查买单委托错误: {str(e)}")
                log.warning(f"委托信息: {entrust_info}")
    
    # 遍历卖单委托，卖单未成撤单，并立即重新下单
    sell_entrust_items = []
    sell_entrust_items.extend(g.entrust_record.get("sell_profit", {}).items())
    sell_entrust_items.extend(g.entrust_record.get("sell_loss", {}).items())
    for order_id, entrust_info in sell_entrust_items:
        # 已经核查过
        if entrust_info.get("check_done"):
            continue

        entrust_time = entrust_info["entrust_time"]
        if (now - entrust_time).total_seconds() > g.cancel_seconds_for_sell: # 达到指定时间间隔
            try:
                # 获取指定订单
                order_info = get_order(order_id) # 返回一个list，该list中只包含一个Order对象
                if isinstance(order_info, list):
                    order_info = order_info[0]

                amount = order_info.amount # 下单数量，买入是正数，卖出是负数
                filled = order_info.filled # 成交数量，买入时为正数，卖出时为负数

                if filled != amount: # 没有全部成交，需要撤单
                    # 拿到委托信息
                    stock_code = entrust_info["stock_code"]
                    order_dict = entrust_info["order_dict"]

                    # 判断是否跌停（跌停时不撤单）
                    limit_state = check_limit(stock_code).get(stock_code)
                    if limit_state in [-1, -2]: # 跌停
                        pass
                    else: # 撤单，让tick_logic重新匹配对应单
                        log.info(f'卖单撤单: {order_info}')
                        cancel_order(order_id)
                        order_dict["order_done"] = False
                        order_dict["re_entrust_shares"] = abs(amount) - abs(filled) # tick_logic中不再判断触发价格，立即再次下卖单

                # 标记已核查
                entrust_info["check_done"] = True
            except Exception as e:
                log.warning(f"核查卖单委托错误: {str(e)}")
                log.warning(f"委托信息: {entrust_info}")


def handle_data(context, data):
    """
    该函数每个单位周期执行一次
    如果是日线级别策略，每天执行一次。股票回测场景下，在15:00执行；股票交易场景下，执行时间为券商实际配置时间。
    如果是分钟级别策略，每分钟执行一次，股票回测场景下，执行时间为9:31 -- 15:00，股票交易场景下，执行时间为9:30 -- 14:59。
    """
    pass
    
 
def after_trading_end(context, data):
    """交易日盘后处理，整理当日信息，该函数会在每天交易结束之后调用，执行时间为由券商配置决定，一般为15:30"""
    # 账户 Fund
    Portfolio = context.portfolio # 账户信息
    Fund_dict = {
        "cash": Portfolio.cash, # 当前可用资金(不包含冻结资金)
        "positions_value": Portfolio.positions_value, # 持仓价值
        "portfolio_value": Portfolio.portfolio_value, # 当前持有的标的和现金的总价值
    }

    # 持仓 Hold
    Hold_dict = {}
    for position_info_dict in get_all_positions(): # 获取全部持仓信息，返回列表
        stock_code = position_info_dict["stock_code"]
        ts_code = stock_code_trans(stock_code)
        Hold_dict[ts_code] = position_info_dict

    # 当日成交 Deal
    Deal_dict = get_trades() # 获取策略内当日成交订单，返回字典 {订单编号: 成交信息列表}
    for trade_id, trade_info_list in Deal_dict.items(): # 转换代码
        for trade_info in trade_info_list:
            stock_code = trade_info[2] # 标的代码
            ts_code = stock_code_trans(stock_code)
            trade_info[2] = ts_code

    # 当日监控 Order
    Order_dict = deepcopy(g.order_result)

    # 当日委托 Entrust
    Entrust_dict = deepcopy(g.entrust_record)
    # datetime对象无法直接存为json，转换为字符串
    for entrust_type, entrusts in Entrust_dict.items():
        for order_id, entrust_info in entrusts.items():
            entrust_time = entrust_info["entrust_time"]
            entrust_info["entrust_time"] = entrust_time.isoformat() # 转换为字符串
    
    # 集成后保存文件
    summary = {
        "Fund": Fund_dict,
        "Hold": Hold_dict,
        "Deal": Deal_dict,
        "Order": Order_dict,
        "Entrust": Entrust_dict
    }
    output_json_path = g.notebook_path + g.output_dir + f"{g.current_date}.json"
    update_json(output_json_path, summary)
    
    # 日志
    relative_path = g.output_dir + f"{g.current_date}.json"
    log.info(f"盘后整理数据已存盘，路径: {relative_path}")
    
    log.info("盘后处理完毕")


# 代码结束
