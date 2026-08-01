import gradio as gr
import json
from datetime import datetime
from printer_control import ThermalPrinter


def load_poetry_records():
    """加载诗歌生成记录"""
    try:
        with open('poetry_generation_records.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def format_timestamp(timestamp_str):
    """将ISO格式的时间戳转换为可读格式"""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y年%m月%d日 %H:%M:%S")
    except Exception:
        return timestamp_str


def search_poem_by_id(poem_id):
    """根据ID搜索诗歌记录"""
    records = load_poetry_records()
    
    for record in records:
        if record.get('id') == poem_id:
            return record
    
    return None


def display_poem_info(poem_id):
    """显示诗歌信息"""
    if not poem_id or not poem_id.strip():
        return "", "请输入ID"
    
    record = search_poem_by_id(poem_id.strip())
    
    if not record:
        return "", f"❌ 未找到ID为 '{poem_id}' 的诗歌记录"
    
    # 格式化时间
    gen_time = format_timestamp(record.get('timestamp', ''))
    
    # 构建显示内容
    title = record.get('generated_poem', {}).get('title', '无题')
    content = record.get('generated_poem', {}).get('content', '')
    user_prompt = record.get('user_prompt', '')
    options = record.get('options', {})
    
    # 格式化选项 - 显示所有选项（包括空值和0值）
    options_text = ""
    if options:
        options_text = "\n".join([f"{k}: {v}" for k, v in options.items()])
    
    display_text = f"""📜 诗歌信息

标题: {title}

内容:
{content}

---
用户提示: {user_prompt}

生成时间: {gen_time}

选项:
{options_text}
"""
    
    return display_text, "✅ 找到诗歌记录，可以点击打印按钮进行打印"


def print_poem_receipt(poem_id):
    """打印诗歌收据（使用正式的热敏打印机）"""
    if not poem_id or not poem_id.strip():
        return "❌ 请先输入有效的ID"
    
    record = search_poem_by_id(poem_id.strip())
    
    if not record:
        return f"❌ 未找到ID为 '{poem_id}' 的诗歌记录"
    
    # 获取各项数据
    pid = record.get('id', '')
    gen_time = format_timestamp(record.get('timestamp', ''))
    print_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    user_prompt = record.get('user_prompt', '')
    options = record.get('options', {})
    poem_data = record.get('generated_poem', {})
    title = poem_data.get('title', '无题')
    content = poem_data.get('content', '')
    
    try:
        # 初始化打印机（需要根据实际打印机修改VID和PID）
        USB_VID = 0x09C5
        USB_PID = 0x58DE
        
        with ThermalPrinter(vid=USB_VID, pid=USB_PID, encoding='gbk') as p:
            # 标题部分 - 居中加粗
            p.reset()
            p.set_style(align="center", bold=True, double_height=False, double_width=False)
            p.print_text("AI智创工坊")
            # p.feed(1)
            p.reset()
            
            p.set_style(align="center", bold=True, double_height=True, double_width=True)
            p.print_text("诗歌打印服务")
            p.feed(1)
            p.reset()
            
            # ID和时间信息 - 居中对齐
            p.set_style(align="center", bold=False)
            p.print_text(f"ID: {pid}")
            p.reset()
            p.feed(1)
            p.set_style(align="left", bold=False)
            p.print_text(f"生成: {gen_time}")
            p.print_text(f"打印: {print_time}")
            # p.feed(1)
            p.reset()
            
            # 分隔线
            p.set_style(align="center")
            p.print_line(32, "-")
            # p.feed(1)
            p.reset()
            
            # 用户提示 - 左对齐
            p.set_style(align="left", bold=True)
            p.print_text("用户提示:")
            p.set_style(align="left", bold=False)
            p.print_text(user_prompt)
            p.feed(1)
            p.reset()
            
            # 选项部分
            p.set_style(align="left", bold=True)
            p.print_text("选项:")
            p.set_style(align="left", bold=False)
            if options:
                for k, v in options.items():
                    p.print_text(f"{k}: {v}")
            # p.feed(1)
            p.reset()
            
            # 分隔线
            p.set_style(align="center")
            p.print_line(32, "-")
            # p.feed(1)
            p.reset()

            # 诗歌内容 - 左对齐
            p.set_style(align="left", bold=True)
            p.print_text("诗歌内容:")
            p.reset()

            # 诗歌标题 - 居中加粗
            p.set_style(align="center", bold=True, double_height=True)
            p.print_text(f"《{title}》")
            p.feed(1)
            p.reset()
            
            # 诗歌内容 - 居中
            p.set_style(align="center", bold=False, double_height=False)
            # 按行打印诗歌内容

            lines_list = [line for line in content.split('\n') if line.strip()]
            for i, line in enumerate(lines_list):
                p.print_text(line)
                # 如果不是最后一行，则打印空行作为段落间隔或行间间隔
                # 这里简单处理：每行之后都feed，但最后一行不feed，避免末尾多余空行
                # 或者根据原逻辑，原逻辑是按双换行分块，块内单行打印后块末feed。
                # 为了更精确控制，我们重新审视原逻辑：
                # 原逻辑: split('\n\n') -> blocks. For each block, split('\n') -> lines. Print non-empty lines. Then feed(1).
                # 问题在于最后一个block打印完后也feed(1)，导致末尾多一行。
                # 修改方案：遍历所有非空行，打印后，如果不是最后一行，则feed(1)或者根据需求调整。
                # 但诗歌通常需要保留一定的行间距离。
                # 让我们保持原有的“段”的概念，但只在段之间加空行，且最后一段结束后不加。
                
                # 更简单的改法：收集所有要打印的行，然后统一处理。

            p.reset()

            # 底部分隔线和提示
            p.set_style(align="center")
            p.print_line(32, "-")
            # p.feed(1)
            p.reset()

            p.set_style(align="center", bold=True)
            p.print_text('Made & Designed by Jerry')
            p.set_style(align="center", bold=False)
            p.print_text('高一7班    Powered by Qwen3')
            p.feed(1)
            p.print_text('感谢您的参与:)    祝您生活愉快！')
            p.reset()
            
            # 底部装饰线
            p.print_line(32, ".")
            p.feed(2)
            p.reset()
        
        return "✅ 打印成功！"
    
    except Exception as e:
        error_msg = f"❌ 打印失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


# 创建Gradio界面
with gr.Blocks(title="AI诗歌打印系统") as app:
    gr.Markdown("# 🎨 AI智创工坊 - 诗歌打印系统")
    gr.Markdown("输入诗歌ID，查看并打印诗歌作品")
    
    # 添加自定义 CSS 实现整体放大和布局优化
    gr.HTML("""
    <style>
        /* 整体放大1.5倍 */
        body {
            zoom: 1.5;
            -moz-transform: scale(1.5);    
            -moz-transform-origin: 0 0;
        }
    </style>
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            id_input = gr.Textbox(
                label="请输入诗歌ID",
                placeholder="例如: 036735",
                lines=1
            )
            
            with gr.Row():
                search_btn = gr.Button("🔍 查询", variant="primary")
                print_btn = gr.Button("🖨️ 打印", variant="secondary")
        
        with gr.Column(scale=2):
            poem_display = gr.Textbox(
                label="诗歌内容",
                lines=15,
                interactive=False
            )
            status_msg = gr.Textbox(
                label="状态信息",
                lines=2,
                interactive=False
            )
    
    # 绑定事件
    search_btn.click(
        fn=display_poem_info,
        inputs=id_input,
        outputs=[poem_display, status_msg]
    )
    
    print_btn.click(
        fn=print_poem_receipt,
        inputs=id_input,
        outputs=status_msg
    )
    
    # 支持回车查询
    id_input.submit(
        fn=display_poem_info,
        inputs=id_input,
        outputs=[poem_display, status_msg]
    )


if __name__ == "__main__":
    print("🚀 启动AI诗歌打印系统...")
    print("💡 提示：")
    print("   - 本机访问: http://127.0.0.1:2026")
    print("   - 局域网访问: 使用本机的IP地址 + :2026")
    print("   - 例如: http://192.168.1.100:2026")
    print("\n📌 查看本机IP地址方法:")
    print("   Windows: 打开命令提示符，输入 ipconfig")
    print("   找到 'IPv4 地址' 即为你的局域网IP\n")
    
    # server_name="0.0.0.0" 允许所有网络接口访问
    # share=False 不使用内网穿透（更快更稳定）
    custom_css = ".gradio-container { max-width: 1200px !important; }"
    app.launch(
        server_name="0.0.0.0",
        server_port=2026,
        share=False,
        css=custom_css
    )