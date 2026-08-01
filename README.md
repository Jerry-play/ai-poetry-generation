# AI智创工坊 - AIGC互动体验站

## 项目简介

本项目是为泉州五中2026年科技节高一班级游园活动设计的AIGC互动体验系统。通过人工智能技术实现诗歌创作创意体验，并结合热敏打印技术提供即时纪念服务。

## 核心功能

- **AI诗歌创作**：基于通义千问API，支持多种诗歌体裁（七言绝句、律诗、宋词、现代诗等）的智能创作
- **自然语言处理**：用户可通过自然语言描述意境，系统自动解析并生成符合要求的诗歌
- **热敏打印服务**：将生成的诗歌作品即时打印成小票作为纪念
- **A2A协议集成**：采用标准Agent-to-Agent协议进行模块间通信(废弃)
- **Web交互界面**：基于Gradio构建的响应式用户界面，支持触屏操作

## 技术架构

- **前端**：Gradio Web界面，支持Kiosk模式运行
- **后端**：Python + FastAPI/Gradio
- **AI引擎**：阿里云通义千问(qwen-plus) API
- **数据库**：JSON文件存储历史记录
- **外设控制**：python-escpos库控制热敏打印机
- **网络部署**：局域网HTTP服务，支持多设备访问

## 项目结构

```
泉五科技节/
├── user.py                 # 主用户界面和调度逻辑
├── poem_generate_agent.py  # 诗歌生成Agent (A2A协议)
├── poem_print_app.py       # 打印服务应用
├── printer.py              # 热敏打印机驱动
├── print_service.py        # 打印服务接口
├── user_agent.py           # 用户代理模块
├── 下游agent2.py           # 下游Agent实现
├── poetry_generation_records.json  # 诗歌生成记录
└── ...
```

## 使用方法

1. 安装依赖：
```bash
pip install gradio dashscope python-escpos
```

2. 设置环境变量：
```bash
export DASHSCOPE_API_KEY="your_api_key_here"
```

3. 启动服务：
```bash
# 启动主用户界面
python user.py

# 启动打印服务
python print_service.py
```

4. 访问界面：
- 主界面：http://localhost:1949
- 打印界面：http://localhost:2026

## 特色亮点

- **零门槛人机共创**：用户只需输入自然语言描述即可生成专业诗歌
- **即时反馈体验**：从创作到打印完成仅需数秒
- **实物纪念品**：热敏打印输出精美诗歌小票
- **标准化协议**：采用A2A协议确保模块间稳定通信
- **轻量化部署**：纯软件方案，易于在局域网内部署

## 应用场景

本系统专为校园科技节设计，适用于：
- 学生创意写作体验
- AI技术科普展示
- 互动式教学活动
- 校园文化宣传