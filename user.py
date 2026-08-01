import os
import json
import time
import re
import uuid
from datetime import datetime
from typing import Generator, Tuple, Any
import gradio as gr
from dashscope import Generation

# 引入下游 Agent (请确保 poem_generate.py 与当前脚本在同一目录)
try:
    from poetry_generation import A2APoetryAgent
except ImportError:
    raise ImportError("未找到下游模块。请确保 poem_generate.py 存在且可导入。")

# ================= 配置与初始化 =================
DASHSCOPE_API_KEY = 'sk-d8de2b002ce34a4e804d30ba3f75f465'
RECORDS_FILE = "poetry_generation_records.json"
downstream_agent = A2APoetryAgent()


# ================= 核心功能函数 =================

def save_to_local(record: dict) -> None:
    """将单次请求记录追加保存至本地 JSON 文件"""
    records = []
    if os.path.exists(RECORDS_FILE):
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError:
                records = []
    records.append(record)
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def parse_natural_language_to_json(
        prompt: str, p_type: str, p_style: str, p_rhyme: bool, p_limit: float
) -> dict:
    """
    调用通义千问 API，将用户自然语言与界面选项融合，
    解析为严格符合下游 A2APoetryAgent 输入要求的 JSON。
    """
    system_content = (
        "你是一个专业的诗歌创作参数解析助手。请根据用户的自然语言描述和界面固定选项，"
        "提取核心意象作为关键词，并生成严格符合下游 Agent 输入要求的 JSON。"
        "【硬性要求】仅输出合法 JSON，键名必须使用英文双引号，禁止任何额外字符或 Markdown。"
    )
    user_content = (
        f"用户自然语言描述: {prompt}\n"
        f"界面指定体裁: {p_type}\n"
        f"界面指定风格: {p_style if p_style else '默认'}\n"
        f"界面指定押韵: {p_rhyme}\n"
        f"界面指定字数限制: {p_limit}\n\n"
        "请生成 JSON，必须且仅包含以下 5 个键：\n"
        "- keywords (list[str]): 从描述中提取 3-5 个核心意象/关键词\n"
        "- style (str): 综合用户描述和指定风格，生成一句精炼的风格指令\n"
        "- type (str): 必须与界面指定体裁完全一致\n"
        "- rhyme_required (bool): 必须与界面指定一致\n"
        "- char_limit (int): 必须与界面指定一致(若<=0则设为0)"
    )

    response = Generation.call(
        model="qwen-plus",
        api_key=DASHSCOPE_API_KEY,
        messages=[{"role": "system", "content": system_content}, {"role": "user", "content": user_content}],
        result_format="message",
        temperature=0.3,  # 低温度确保结构稳定
        top_p=0.9
    )

    if response.status_code != 200:
        raise RuntimeError(f"千问解析 API 错误: {response.message}")

    raw = response.output.choices[0].message.content.strip()
    # 安全剥离可能存在的 Markdown 包裹
    clean_json = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.IGNORECASE)
    parsed = json.loads(clean_json)

    # 🔒 强制契约校验与兜底 (确保 100% 符合下游要求)
    parsed["type"] = p_type
    parsed["rhyme_required"] = bool(p_rhyme)
    parsed["char_limit"] = max(0, int(p_limit))
    if "style" not in parsed or not isinstance(parsed["style"], str):
        parsed["style"] = p_style or "意境优美，符合体裁规范"
    if "keywords" not in parsed or not isinstance(parsed["keywords"], list) or len(parsed["keywords"]) == 0:
        parsed["keywords"] = ["自然意象"] if not prompt else [prompt[:15]]

    return parsed


def update_char_limit_ui(poetry_type: str) -> gr.update:
    """根据诗歌类型动态控制字数限制输入框的可用性与默认值"""
    classical_keywords = ["绝句", "律诗", "词", "曲", "赋"]
    is_classical = any(kw in poetry_type for kw in classical_keywords)
    if is_classical:
        return gr.update(value=0, interactive=False, label="字数限制 (古典体裁依循固定格律，已自动锁定)")
    return gr.update(value=0, interactive=True, label="字数限制 (输入 >0 的整数启用，0 表示不限制)")


# ================= 上游调度流水线 =================

def run_upstream_pipeline(
        natural_prompt: str, poetry_type: str, style: str, rhyme: bool, char_limit: float
) -> Generator[Tuple[dict, str, str], None, None]:
    """
    完整调度流：自然语言解析 -> JSON构建 -> 下发下游 -> 流式生成 -> 本地归档
    """
    # 使用6位数字ID（基于时间戳毫秒），方便记忆且保证不重复
    record_id = str(int(time.time() * 1000))[-6:]
    timestamp = datetime.now().isoformat()

    # 1. 初始化
    log = f"🟡 [{record_id}] INIT | 接收自然语言输入，准备调用 Qwen 进行意图解析..."
    yield {}, log, ""

    try:
        # 2. 调用千问解析意图
        log += "\n🔵 PARSING | 正在通过大模型提取关键词与风格约束..."
        yield {}, log, ""

        payload = parse_natural_language_to_json(natural_prompt, poetry_type, style, rhyme, char_limit)

        # 3. 首次 Yield：展示即将下发的标准 JSON
        log += "\n✅ PARSED | 参数提取完成，标准化 Payload 已构建。"
        yield payload, log, ""
        time.sleep(0.5)  # 预留时间让用户看清 JSON 结构

        # 4. 下发至下游 Agent 并流式转发
        log += "\n🔵 FORWARDING | Payload 已下发至 A2APoetryAgent，进入流式生成..."
        yield payload, log, ""

        final_poem_md = ""
        downstream_output = {}

        for dl_logs, d_json, d_poem in downstream_agent.execute(payload):
            log = dl_logs
            downstream_output = d_json
            if d_poem:
                final_poem_md = d_poem
            # 持续更新三栏 UI
            yield payload, log, final_poem_md

        # 5. 任务完成，持久化记录
        record = {
            "id": record_id,
            "timestamp": timestamp,
            "user_prompt": natural_prompt,
            "options": {"type": poetry_type, "style": style, "rhyme": rhyme, "limit": int(char_limit)},
            "downstream_payload": payload,
            "generated_poem": {
                "title": downstream_output.get("title", "无题"),
                "content": downstream_output.get("content", "")
            },
            "status": "success"
        }
        save_to_local(record)
        log += f"\n🟢 COMPLETED | 任务结束。记录已安全归档至 {RECORDS_FILE} (ID: {record_id})"
        yield payload, log, final_poem_md

    except Exception as e:
        err_log = log + f"\n🔴 FAILED | 执行异常: {str(e)}"
        # 即使失败也保存记录便于排查
        save_to_local({
            "id": record_id,
            "timestamp": timestamp,
            "user_prompt": natural_prompt,
            "options": {"type": poetry_type, "style": style, "rhyme": rhyme, "limit": int(char_limit)},
            "status": "failed",
            "error": str(e)
        })
        yield {}, err_log, ""


# ================= Gradio 界面构建 =================

with gr.Blocks(title="诗歌创作智能 Agent") as upstream_app:
    gr.Markdown("# 诗歌创作交互面板", elem_classes=["page-title"])
    gr.Markdown("> 输入自然语言描述，AI 将自动解析意图并生成标准 JSON 调度下游 Agent。")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 创作参数配置")
            prompt_input = gr.Textbox(
                label="自然语言提示 (描述意境/场景/情感)",
                lines=3,
                placeholder="例: 描写秋日傍晚在江边独自饮酒，思念故乡，带有一丝孤寂与豁达..."
            )
            style_input = gr.Textbox(label="核心风格倾向 (可选)", placeholder="例: 沉郁婉约 / 豪放旷达 / 清新自然")
            type_input = gr.Radio(
                label="诗歌体裁",
                choices=["七言绝句", "七言律诗", "五言绝句", "五言律诗", "宋词", "元曲", "现代诗", "自由诗"],
                value="现代诗"
            )
            rhyme_input = gr.Checkbox(label="是否强制押韵", value=False, info="开启后模型将严格遵循对应韵律规则")
            char_input = gr.Number(label="字数限制", value=0, precision=0, interactive=True)

            submit_btn = gr.Button("提交并生成", variant="primary", size="lg")

        with gr.Column(scale=1):
            gr.Markdown("### 下游调度 JSON Payload (解析后)")
            json_display = gr.JSON(label="标准化请求结构 (实时预览)", height=300)

            gr.Markdown("### Agent 行为日志流")
            log_display = gr.Textbox(
                lines=10, interactive=False, placeholder="等待任务触发...",
                label="协议生命周期与执行轨迹"
            )

        # 右半侧：独立的诗歌生成结果展示块
        with gr.Column(scale=1):
            gr.Markdown("### 📜 诗歌生成结果", elem_classes=["poem-section-title"])
            
            # ID 显示模块：位于标题下方，内容上方
            gr.Markdown(
                """
                <div style="background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 15px; margin-bottom: 15px; text-align: center;">
                    <p style="color: #856404; font-size: 1.1em; margin: 0; font-weight: bold;">
                        ⚠️ 重要提示：此ID为打印诗歌的唯一凭证，请牢记！
                    </p>
                </div>
                """,
                elem_classes=["id-warning-box"]
            )
            
            poem_id_display = gr.Textbox(
                label="诗词 ID", 
                interactive=False, 
                value="---", 
                show_label=True,
                container=True,
                elem_classes=["poem-id-box"]
            )
            
            poem_display = gr.Markdown(
                label="最终渲染文本", 
                height=550,
                elem_classes=["poem-container"]
            )
            
            # 添加自定义 CSS 以增强诗歌格式感并强制统一跨设备显示
            gr.HTML("""
            <style>
                /* 整体放大1.2倍 */
                body {
                    zoom: 1.2;
                    -moz-transform: scale(1.2);
                    -moz-transform-origin: 0 0;
                }
                
                /* 强制固定布局，防止响应式变化 */
                .gradio-container {
                    max-width: 1400px !important;
                    margin: 0 auto !important;
                }
                    
                /* 禁用移动端断点切换 */
                @media (max-width: 768px) {
                    .gradio-row {
                        flex-direction: row !important;
                        flex-wrap: nowrap !important;
                    }
                    .gradio-column {
                        min-width: 300px !important;
                        flex: 1 1 0% !important;
                    }
                }
                    
                @media (max-width: 640px) {
                    .gradio-row {
                        flex-direction: row !important;
                        flex-wrap: nowrap !important;
                    }
                    .gradio-column {
                        min-width: 280px !important;
                        flex: 1 1 0% !important;
                    }
                }
                    
                .page-title h1 {
                    font-size: 2.5em !important;
                    text-align: center !important;
                    margin: 20px 0 !important;
                }
                .poem-section-title h3 {
                    font-size: 1.6em !important;
                    text-align: center !important;
                }
                .id-warning-box {
                    margin: 15px 0;
                }
                .poem-id-box input {
                    font-size: 1.1em;
                    color: #333;
                    text-align: center;
                    border: 2px solid #ffc107;
                    background: #fff9e6;
                    margin-bottom: 15px;
                    font-weight: bold;
                    padding: 10px;
                }
                .poem-container {
                    background-color: #fdfbf7;
                    border: 1px solid #e0e0e0;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    padding: 25px;
                    font-family: 'KaiTi', 'STKaiti', serif;
                    font-size: 1.3em;
                    line-height: 1.6;
                    white-space: pre-wrap;
                    min-height: 300px;
                    max-height: 430px;
                    overflow-y: auto;
                }
                .poem-container h1,
                .poem-container h2,
                .poem-container h3,
                .poem-container h4 {
                    text-align: center !important;
                    font-size: 1.6em !important;
                    margin: 10px 0 !important;
                }
                .poem-container p {
                    margin: 5px 0 !important;
                }
                    
                /* 固定列宽比例 */
                .gradio-row > .gradio-column {
                    flex: 1 1 0% !important;
                    min-width: 0 !important;
                }
                    
                /* 确保输入框在小屏幕上不换行 */
                .gradio-input, .gradio-textbox, .gradio-radio, .gradio-checkbox, .gradio-number {
                    width: 100% !important;
                }
            </style>
            """)

    # 包装函数以适配新的输出顺序和 ID 提取
    def run_upstream_pipeline_with_id(
            natural_prompt: str, poetry_type: str, style: str, rhyme: bool, char_limit: float
    ) -> Generator[Tuple[dict, str, str, str], None, None]:
        """
        包装原有的流水线，增加 ID 的实时回传
        """
        current_pid = "---"  # 保存当前 ID，确保持续显示
        for payload, log, poem in run_upstream_pipeline(natural_prompt, poetry_type, style, rhyme, char_limit):
            # 从 log 中提取 ID (正则匹配 [record_id]，6位数字)
            import re
            match = re.search(r'\[(\d{6})\]', log)
            if match:
                current_pid = match.group(1)  # 更新 ID
            # 始终使用 current_pid，确保 ID 持续显示
            yield payload, log, current_pid, poem

    # 绑定交互事件
    type_input.change(fn=update_char_limit_ui, inputs=type_input, outputs=char_input)
    submit_btn.click(
        fn=run_upstream_pipeline_with_id,
        inputs=[prompt_input, type_input, style_input, rhyme_input, char_input],
        outputs=[json_display, log_display, poem_id_display, poem_display]
    )
    
    # 页面底部版权信息
    gr.Markdown(
        """
        <div style="text-align: center; margin-top: 10px; padding: 8px; color: #888; font-size: 1em;">
            Made & Designed by <strong>Jerry</strong> | 高一七班 | Powered by Qwen3
        </div>
        """
    )

if __name__ == "__main__":
    # 必须启用 queue() 以支持 Python Generator 流式输出
    custom_css = ".gradio-container { max-width: 1400px !important; }"
    upstream_app.queue().launch(
        server_name="0.0.0.0",
        server_port=2027,
        share=False,
        css=custom_css
    )