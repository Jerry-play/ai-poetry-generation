# unified_lottery_app.py
"""
统一奖池抽奖系统
功能：
1. 核销功能：验证并标记已核销的票券ID
2. 抽奖功能：按等级抽取获奖者（特等奖1人、一等奖4人、二等奖10人、三等奖20人）
3. 一键切换：在核销和抽奖模式之间切换
4. Web界面：使用Gradio发布到网页上
"""

import gradio as gr
import json
import os
import datetime
import threading
import random

# 配置常量
RECORD_FILE = "lottery_records.json"
LOTTERY_RESULT_FILE = "lottery_results.json"
file_lock = threading.Lock()

# 奖项配置
PRIZE_CONFIG = {
    "特等奖": 1,
    "一等奖": 4,
    "二等奖": 10,
    "三等奖": 20
}


# ================= 核心逻辑 =================

def _load_records():
    """安全读取 JSON 记录"""
    if not os.path.exists(RECORD_FILE):
        return []
    with file_lock:
        try:
            with open(RECORD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []


def _save_record(record: dict):
    """追加保存记录到 JSON"""
    records = _load_records()
    records.append(record)
    with file_lock:
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)


def _load_lottery_results():
    """加载抽奖结果"""
    if not os.path.exists(LOTTERY_RESULT_FILE):
        return {}
    with file_lock:
        try:
            with open(LOTTERY_RESULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}


def _save_lottery_results(results: dict):
    """保存抽奖结果"""
    with file_lock:
        with open(LOTTERY_RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)


def get_unified_pool_tickets():
    """获取统一奖池中的所有票券ID"""
    records = _load_records()
    tickets = []
    for record in records:
        if record.get("pool") == "统一奖池" and "ticket_id" in record:
            tickets.append({
                "ticket_id": record["ticket_id"],
                "time": record.get("time", ""),
                "verified": record.get("verified", False),
                "verify_time": record.get("verify_time", "未知"),
                "won_prize": record.get("won_prize", "")
            })
    return tickets


def verify_ticket(ticket_id: str):
    """核销票券"""
    if not ticket_id or not ticket_id.strip():
        return "❌ 请输入票券ID", ""
    
    ticket_id = ticket_id.strip()
    records = _load_records()
    found = False
    
    for record in records:
        if record.get("pool") == "统一奖池" and record.get("ticket_id") == ticket_id:
            if record.get("verified", False):
                return f"⚠️ 票券 {ticket_id} 已经核销过了", get_verification_status()
            record["verified"] = True
            record["verify_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            found = True
            break
    
    if not found:
        return f"❌ 票券 {ticket_id} 不存在于统一奖池中", get_verification_status()
    
    # 保存更新后的记录
    with file_lock:
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    
    return f"✅ 票券 {ticket_id} 核销成功", get_verification_status()


def get_verification_status():
    """获取核销状态信息"""
    tickets = get_unified_pool_tickets()
    verified_count = sum(1 for t in tickets if t.get("verified", False))
    total_count = len(tickets)
    
    status_text = f"📊 核销统计：已核销 {verified_count}/{total_count} 张票券\n\n"
    status_text += "已核销的票券ID：\n"
    
    verified_tickets = [t for t in tickets if t.get("verified", False)]
    if verified_tickets:
        for t in verified_tickets:
            status_text += f"  • {t['ticket_id']} (核销时间: {t.get('verify_time', '未知')})\n"
    else:
        status_text += "  暂无已核销的票券\n"
    
    return status_text


def draw_lottery():
    """执行抽奖"""
    tickets = get_unified_pool_tickets()
    
    # 只抽取已核销且未中奖的票券
    eligible_tickets = [t for t in tickets if t.get("verified", False) and not t.get("won_prize", "")]
    
    if not eligible_tickets:
        return "❌ 没有可参与抽奖的已核销票券", "", "", "", ""
    
    # 计算总获奖人数
    total_winners = sum(PRIZE_CONFIG.values())
    
    if len(eligible_tickets) < total_winners:
        # 人数不够，从上向下抽取（即全部抽取，然后按等级分配）
        winners = eligible_tickets[:]
        random.shuffle(winners)
        
        # 按等级分配
        results = {}
        start_idx = 0
        for prize_name, count in PRIZE_CONFIG.items():
            end_idx = min(start_idx + count, len(winners))
            results[prize_name] = [w["ticket_id"] for w in winners[start_idx:end_idx]]
            start_idx = end_idx
            if start_idx >= len(winners):
                break
        
        # 填充空的奖项
        for prize_name in PRIZE_CONFIG.keys():
            if prize_name not in results:
                results[prize_name] = []
    else:
        # 人数足够，正常抽取
        all_eligible_ids = [t["ticket_id"] for t in eligible_tickets]
        random.shuffle(all_eligible_ids)
        
        results = {}
        start_idx = 0
        for prize_name, count in PRIZE_CONFIG.items():
            end_idx = start_idx + count
            results[prize_name] = all_eligible_ids[start_idx:end_idx]
            start_idx = end_idx
    
    # 更新记录中的中奖信息
    records = _load_records()
    for record in records:
        if record.get("pool") == "统一奖池" and "ticket_id" in record:
            ticket_id = record["ticket_id"]
            for prize_name, winner_ids in results.items():
                if ticket_id in winner_ids:
                    record["won_prize"] = prize_name
                    record["win_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break
    
    # 保存更新后的记录
    with file_lock:
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    
    # 保存抽奖结果
    _save_lottery_results(results)
    
    # 格式化输出结果
    result_text = "🎉 抽奖完成！\n\n"
    grand_prize = "\n".join([f"  • {wid}" for wid in results.get("特等奖", [])]) or "  无"
    first_prize = "\n".join([f"  • {wid}" for wid in results.get("一等奖", [])]) or "  无"
    second_prize = "\n".join([f"  • {wid}" for wid in results.get("二等奖", [])]) or "  无"
    third_prize = "\n".join([f"  • {wid}" for wid in results.get("三等奖", [])]) or "  无"
    
    result_text += f"🏆 特等奖（{len(results.get('特等奖', []))}人）：\n{grand_prize}\n\n"
    result_text += f"🥇 一等奖（{len(results.get('一等奖', []))}人）：\n{first_prize}\n\n"
    result_text += f"🥈 二等奖（{len(results.get('二等奖', []))}人）：\n{second_prize}\n\n"
    result_text += f"🥉 三等奖（{len(results.get('三等奖', []))}人）：\n{third_prize}\n"
    
    return result_text, grand_prize, first_prize, second_prize, third_prize


def get_lottery_results_display():
    """获取抽奖结果显示"""
    results = _load_lottery_results()
    if not results:
        return "暂无抽奖结果"
    
    result_text = "🎉 抽奖结果\n\n"
    for prize_name, winner_ids in results.items():
        if winner_ids:
            result_text += f"🏆 {prize_name}（{len(winner_ids)}人）：\n"
            for wid in winner_ids:
                result_text += f"  • {wid}\n"
            result_text += "\n"
    
    return result_text


def refresh_all_displays():
    """刷新所有显示"""
    verification_status = get_verification_status()
    lottery_results = get_lottery_results_display()
    tickets = get_unified_pool_tickets()
    
    # 构建票券列表表格数据
    table_data = []
    for t in tickets:
        table_data.append([
            t["ticket_id"],
            t.get("time", ""),
            "✅ 已核销" if t.get("verified", False) else "❌ 未核销",
            t.get("won_prize", "未中奖") if t.get("verified", False) else "-"
        ])
    
    return verification_status, lottery_results, table_data


# ================= Gradio UI 构建 =================

with gr.Blocks(title="统一奖池抽奖系统") as app:
    gr.Markdown("# 🎯 统一奖池抽奖系统")
    gr.Markdown("> 本系统用于管理统一奖池的票券核销和抽奖活动")
    
    # 模式切换状态
    current_mode = gr.State(value="verification")
    
    with gr.Tabs():
        # 核销模式 Tab
        with gr.Tab("🎫 票券核销") as verification_tab:
            gr.Markdown("### 票券核销功能")
            gr.Markdown("请输入票券ID进行核销验证")
            
            with gr.Row():
                with gr.Column(scale=1):
                    ticket_input = gr.Textbox(
                        label="票券ID",
                        placeholder="请输入6位数字票券ID",
                        max_lines=1
                    )
                    verify_btn = gr.Button("核销票券", variant="primary", size="lg")
                
                with gr.Column(scale=1):
                    verify_result = gr.Textbox(
                        label="核销结果",
                        interactive=False,
                        lines=2
                    )
            
            verification_status = gr.Textbox(
                label="核销状态",
                interactive=False,
                lines=10
            )
        
        # 抽奖模式 Tab
        with gr.Tab("🎲 抽奖") as lottery_tab:
            gr.Markdown("### 抽奖功能")
            gr.Markdown("从已核销的票券中抽取获奖者")
            
            with gr.Row():
                draw_btn = gr.Button("开始抽奖", variant="primary", size="lg")
                refresh_btn = gr.Button("刷新结果", variant="secondary")
            
            lottery_result = gr.Textbox(
                label="抽奖结果",
                interactive=False,
                lines=15
            )
            
            with gr.Accordion("详细获奖名单", open=True):
                with gr.Row():
                    grand_prize_display = gr.Textbox(label="特等奖", interactive=False, lines=3)
                    first_prize_display = gr.Textbox(label="一等奖", interactive=False, lines=5)
                with gr.Row():
                    second_prize_display = gr.Textbox(label="二等奖", interactive=False, lines=8)
                    third_prize_display = gr.Textbox(label="三等奖", interactive=False, lines=12)
        
        # 数据总览 Tab
        with gr.Tab("📊 数据总览"):
            gr.Markdown("### 所有票券信息")
            
            tickets_table = gr.Dataframe(
                headers=["票券ID", "获取时间", "核销状态", "获奖情况"],
                wrap=True,
                interactive=False
            )
            
            refresh_overview_btn = gr.Button("🔄 刷新数据")
    
    # ================= 事件绑定 =================
    
    # 核销按钮点击事件
    verify_btn.click(
        fn=verify_ticket,
        inputs=[ticket_input],
        outputs=[verify_result, verification_status]
    ).then(
        fn=lambda: "",  # 清空输入框
        outputs=[ticket_input]
    )
    
    # 抽奖按钮点击事件
    draw_btn.click(
        fn=draw_lottery,
        outputs=[lottery_result, grand_prize_display, first_prize_display, 
                 second_prize_display, third_prize_display]
    )
    
    # 刷新按钮事件
    refresh_btn.click(
        fn=get_lottery_results_display,
        outputs=[lottery_result]
    )
    
    # 刷新总览数据
    refresh_overview_btn.click(
        fn=refresh_all_displays,
        outputs=[verification_status, lottery_result, tickets_table]
    )
    
    # Tab切换事件 - 只在切换时刷新对应标签页的数据
    verification_tab.select(
        fn=get_verification_status,
        outputs=[verification_status]
    )
    
    lottery_tab.select(
        fn=get_lottery_results_display,
        outputs=[lottery_result]
    )


if __name__ == "__main__":
    # 启动 Gradio 服务（启用队列以支持更好的性能）
    app.queue().launch(server_name="0.0.0.0", server_port=7861, theme=gr.themes.Soft())
