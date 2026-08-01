# lottery_app.py
import gradio as gr
import random
import json
import os
import datetime
import threading
import sys

# 1. 导入你提供的打印控制类
try:
    from printer_control import ThermalPrinter
except ImportError:
    print("❌ 未找到 printer_control.py，请确保该文件与本脚本在同一目录下。")
    sys.exit(1)

# 配置常量
RECORD_FILE = "lottery_records.json"
file_lock = threading.Lock()


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


def refresh_history():
    """刷新历史记录表格数据"""
    records = _load_records()
    # 倒序显示，最新的在最上面
    records.reverse()
    data = []
    for r in records:
        if r.get("pool") == "现抽奖池":
            data.append([r["pool"], r["result"], r["time"], "无需打印"])
        else:
            data.append([r["pool"], r["ticket_id"], r["time"], r.get("status", "未知")])
    return data


def draw_pool1():
    """奖池一：现抽逻辑 (10%中奖, 20%重抽, 70%未中)"""
    r = random.random()
    if r <= 0.15:
        result_text = "🎉 恭喜！中奖了！"
    elif r <= 0.45:
        result_text = "🔄 免费再来一次！"
    else:
        result_text = "😢 很遗憾，未中奖。"

    record = {
        "pool": "现抽奖池",
        "result": result_text,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    _save_record(record)
    return result_text


def draw_pool2(vid_hex: str, pid_hex: str):
    """奖池二：生成ID并打印抽奖券"""
    # 解析十六进制 VID/PID
    try:
        vid = int(vid_hex.replace("0x", ""), 16)
        pid = int(pid_hex.replace("0x", ""), 16)
    except ValueError:
        return "", "", "❌ VID/PID 格式错误，请输入十六进制数字（如 0x09C5）"

    # 生成6位数字ID：时间戳后6位 + 随机性增强
    timestamp_ms = int(datetime.datetime.now().timestamp() * 1000)  # 毫秒级时间戳
    random_factor = random.randint(0, 999)  # 随机因子 0-999
    # 取时间戳后3位 + 随机因子后3位，组合成6位ID
    ticket_id = f"{(timestamp_ms % 1000):03d}{random_factor:03d}"
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 保存记录
    record = {
        "pool": "统一奖池",
        "ticket_id": ticket_id,
        "time": current_time,
    }
    _save_record(record)

    # 2. 调用热敏打印机打印
    print_status = "⏳ 连接打印机中..."
    try:
        # 使用上下文管理器自动管理连接与释放
        with ThermalPrinter(vid=vid, pid=pid, timeout=5.0, encoding="gbk") as p:
            p.reset()
            p.set_style(align="center", bold=True)
            p.print_text("抽奖券")
            p.reset()
            p.print_text("抽奖ID: ")
            p.set_style(align="center", bold=True, double_width=True, double_height=True)
            p.print_text(ticket_id)
            p.reset()
            p.print_text(f"时间: {current_time}")
            p.print_text("请妥善保管此券,并于10:00前来登记统一抽奖")
            p.print_line(char="-")
            # 无切刀机型，使用走纸替代切刀
            p.feed(1)
        #
        # print_status = "✅ 打印成功"
        # # 更新记录状态
        # record["status"] = "已打印"
        # _save_record(record)

    except Exception as e:
        print_status = f"❌ 打印失败: {str(e)}"
        record["status"] = f"打印失败: {str(e)[:20]}"
        _save_record(record)

    return ticket_id, current_time, print_status


# ================= Gradio UI 构建 =================

with gr.Blocks(title="抽奖系统") as app:
    gr.Markdown("# 抽奖系统")
    gr.Markdown("系统包含两个独立奖池，支持实时结果展示、热敏小票打印及全量数据 JSON 持久化。")

    with gr.Tabs():
        # 奖池一 Tab
        with gr.Tab("🎲 奖池一：现抽"):
            gr.Markdown("📊 概率规则：`15% 中奖` | `30% 免费再来一次` | `55% 未中奖`")
            btn_draw1 = gr.Button("立即抽奖", variant="primary", size="lg")
            out_res1 = gr.Label(label="抽奖结果")

        # 奖池二 Tab
        with gr.Tab("🎫 奖池二：统一打印"):
            with gr.Row():
                inp_vid = gr.Textbox(label="打印机 VID (十六进制)", value="0x09C5", scale=1)
                inp_pid = gr.Textbox(label="打印机 PID (十六进制)", value="0x58DE", scale=1)
            btn_draw2 = gr.Button("生成ID并打印抽奖券", variant="primary", size="lg")
            out_id = gr.Textbox(label="生成抽奖ID", interactive=False)
            out_time = gr.Textbox(label="抽奖时间", interactive=False)
            out_print = gr.Textbox(label="打印状态", interactive=False)
            gr.Markdown("> 💡 提示：请确保 USB 打印机已连接且 VID/PID 正确。程序已适配无切刀机型。")

        # 记录 Tab
        with gr.Tab("📜 抽奖记录"):
            df_history = gr.Dataframe(
                headers=["奖池类型", "抽奖结果/ID", "抽奖时间", "状态"],
                wrap=True,
                interactive=False
            )
            btn_refresh = gr.Button("🔄 刷新记录")

    # ================= 事件绑定 =================
    # 奖池一：抽奖 -> 显示结果 -> 刷新表格
    btn_draw1.click(fn=draw_pool1, outputs=out_res1).then(fn=refresh_history, outputs=df_history)

    # 奖池二：输入VID/PID -> 生成/打印 -> 显示信息 -> 刷新表格
    btn_draw2.click(
        fn=draw_pool2,
        inputs=[inp_vid, inp_pid],
        outputs=[out_id, out_time, out_print]
    ).then(fn=refresh_history, outputs=df_history)

    # 初始化加载记录
    app.load(fn=refresh_history, outputs=df_history)
    btn_refresh.click(fn=refresh_history, outputs=df_history)

if __name__ == "__main__":
    # 启动 Gradio 服务 (本地访问 http://localhost:7860)
    app.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft())