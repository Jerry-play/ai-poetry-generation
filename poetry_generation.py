import os
import json
import time
import re
from typing import Dict, Any, Generator
import gradio as gr
from dashscope import Generation

# ================= 1. 环境配置 =================
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    print("⚠️ 请设置环境变量 DASHSCOPE_API_KEY 以启用模型调用")


# ================= 2. A2A Agent 核心逻辑 =================
class A2APoetryAgent:
    """原生诗歌创作 Agent (只读监控版)"""

    def __init__(self):
        self.logs = []

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")

    def _build_system_prompt(self, config: Dict[str, Any]) -> str:
        is_classical = any(k in config.get("type", "") for k in ["诗", "词", "曲", "绝", "律", "赋"])

        rules = [
            f"1. 诗歌类型: {config['type']}",
            f"2. 核心风格: {config['style']}",
            f"3. 必须融入关键词: {', '.join(config['keywords'])}",
        ]

        if config.get("rhyme_required") is True:
            if is_classical:
                rules.append("4. [强制押韵] 古典体裁必须严格遵循《平水韵》或《词林正韵》，一韵到底不得出韵。")
            else:
                rules.append("4. [强制押韵] 现代诗需保持句末韵脚和谐统一，节奏流畅。")
        else:
            rules.append("4. [非强制押韵] 以意境与节奏为主，押韵仅作参考。")

        limit = config.get("char_limit", 0)
        if limit > 0:
            rules.append(f"5. [严格限字] 全诗总字数（含标点）必须控制在 {limit} 字以内。")
        else:
            rules.append("5. [无字数限制] 遵循该体裁常规篇幅自然延展。")

        rules.extend([
            "6. 仅输出合法 JSON，键名必须为英文双引号，字符串内换行使用 \\n 表示。",
            "7. 禁止输出任何 Markdown 代码块、解释性文字或额外字符。"
        ])

        output_schema = {
            "keywords": ["关键词1", "关键词2"],
            "style": "风格描述",
            "type": "诗歌类型",
            "rhyme_required": True,
            "char_limit": 0,
            "title": "生成的标题",
            "content": "诗歌正文，多行之间用 \\n 分隔"
        }

        return (
                "你是一个精通诗歌创作的AI引擎。请严格根据输入参数生成诗歌，并仅返回以下 JSON Schema 的对象。\n\n"
                f"【输出 JSON 结构】\n{json.dumps(output_schema, ensure_ascii=False, indent=2)}\n\n"
                "【硬性规则】\n" + "\n".join(rules)
        )

    def execute(self, config: Dict[str, Any]) -> Generator[tuple, None, None]:
        self.logs = []
        self._log("🟡 A2A State: CREATED | 接收并校验输入 JSON Payload")
        self._log(f"解析参数: type={config['type']}, style={config['style']}, keywords={config['keywords']}")
        yield "\n".join(self.logs), {}, ""
        time.sleep(0.4)

        self._log("🔵 A2A State: WORKING | 动态构建 System Prompt，注入押韵/字数/风格约束")
        prompt = self._build_system_prompt(config)
        self._log(f"Prompt 构建完成，长度: {len(prompt)} 字符")
        yield "\n".join(self.logs), {}, ""
        time.sleep(0.3)

        self._log("正在发起 DashScope API 请求 (model=qwen-plus)")
        yield "\n".join(self.logs), {}, ""

        try:
            if not DASHSCOPE_API_KEY:
                raise EnvironmentError("未配置环境变量 DASHSCOPE_API_KEY")

            response = Generation.call(
                model="qwen-plus",
                api_key=DASHSCOPE_API_KEY,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(config, ensure_ascii=False)}
                ],
                result_format="message",
                temperature=0.7,
                top_p=0.9
            )

            if response.status_code != 200:
                raise RuntimeError(f"API 错误: code={response.code}, msg={response.message}")

            raw = response.output.choices[0].message.content.strip()
            self._log("📡 成功接收模型响应，执行 JSON 清洗与语法校验...")
            yield "\n".join(self.logs), {}, ""

            clean_json = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.IGNORECASE)
            output_data = json.loads(clean_json)

            required_keys = {"title", "content", "keywords", "style", "type", "rhyme_required", "char_limit"}
            if not required_keys.issubset(output_data.keys()):
                raise ValueError(f"模型返回 JSON 缺失关键字段。当前字段: {list(output_data.keys())}")

            self._log("🟢 A2A State: COMPLETED | 任务执行完毕，封装输出 Artifact")
            self._log("返回结构化 JSON，包含原始要求与生成结果")
            yield "\n".join(self.logs), output_data, self._format_poem(output_data)

        except Exception as e:
            self._log(f"🔴 A2A State: FAILED | 异常中断: {str(e)}")
            yield "\n".join(self.logs), {}, ""

    def _format_poem(self, data: Dict[str, Any]) -> str:
        if not data:
            return ""
        title = data.get("title", "无题")
        content = data.get("content", "").replace("\\n", "\n")
        return f"### {title}\n\n{content}"


# ================= 3. 预定义输入 JSON =================
DEMO_INPUT_JSON = {
    "keywords": ["秋江", "夜泊", "孤舟", "冷月"],
    "style": "沉郁婉约",
    "type": "七言律诗",
    "rhyme_required": True,
    "char_limit": 56
}

# ================= 4. Gradio 只读监控面板 =================
agent = A2APoetryAgent()


# 🔑 核心修复：将生成器调用包装为标准生成器函数，避免 lambda 破坏 Gradio 流式迭代机制
def run_poetry_task():
    yield from agent.execute(DEMO_INPUT_JSON)


with gr.Blocks(title="A2A 诗歌 Agent 行为监控") as demo:
    gr.Markdown("# 📡 A2A 诗歌 Agent 实时行为监控面板 (只读)")
    gr.Markdown(
        "> 页面加载后自动执行预定义任务。所有 A2A 状态流转、Prompt 构建、API 调用与 Artifact 输出均实时流式展示，无用户交互组件。")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Agent 行为日志流")
            log_box = gr.Textbox(
                lines=15, interactive=False, placeholder="等待初始化...",
                label="协议生命周期与执行轨迹"
            )
            gr.Markdown("### 状态图例")
            gr.Markdown("🟡 `CREATED` → 🔵 `WORKING` → 🟢 `COMPLETED` / 🔴 `FAILED`")

        with gr.Column(scale=2):
            gr.Markdown("### 输出 JSON Artifact")
            json_out = gr.JSON(label="结构化结果", height=220)
            gr.Markdown("### 诗歌渲染")
            poem_out = gr.Markdown(label="最终内容", height=180)

    # 🔑 直接绑定生成器函数，Gradio 将自动迭代 yield 并分步更新 outputs
    demo.load(
        fn=run_poetry_task,
        outputs=[log_box, json_out, poem_out]
    )

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False)