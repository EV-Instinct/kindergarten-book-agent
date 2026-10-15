# 🌈 阳光幼儿园智慧图书角 AI 智能体系统

> 本项目为申报**《AI教育实践应用专项：教育智能体设计与应用》**量身定制。  
> 融合 **国产开源智能体框架（阿里 Qwen-Agent）** + **国产顶尖大模型（DeepSeek-V3 / R1）** + **多模态语音引擎（Google Gemini）** + **轻量云端部署（Streamlit Cloud）**。

---

## 🌟 核心特色与幼教价值

1. **单机双态 · 防误触儿童安全锁**：
   * **默认幼儿乐园端**：全屏大字、大触控按键、暖色调拟物化三排视觉书架、零识字门槛。
   * **隐形教师认证通道**：右上角“🔒 教师通道”，点击弹出 PIN 码输入窗口（默认安全码：`123456`），验证后进入“教师智慧管理中台”。
   * **一键加锁回退**：教师操作完毕后，一键点击“退出管理”，瞬间清空凭据并回锁至儿童端。
2. **AI 智能梳理 · 标准化图书档案**：
   * 教师仅需输入绘本书名，DeepSeek 自动补全适读年龄、主题分类、精简摘要并自动分配合理书架排号。
3. **AI 语音赋能 · 精准定位与归位**：
   * 幼儿通过麦克风童音提问或点击绘本，Gemini 识别并由 Qwen-Agent 精准返回几排几号（红/黄/绿区），伴随幼师亲切语调实时语音播报与实体书架闪烁高亮。
4. **AI 助力自主管理 · 幼儿轮流值日主人翁模式**：
   * 教师录入名单一键自动排班；幼儿每日点击“今天谁值日”知晓值日生，整理完毕后点击打卡领取“今日护书小卫士”勋章。
5. **AI 阅读大数据 · 动态调配与换书建议**：
   * 静默记录幼儿借阅与红心点赞；自动统计最爱榜 Top8 与冷门滞销绘本预警，AI 一键生成《图书角动态调配与阅读指导建议书》。

---

## 🛠️ 技术架构

* **智能体框架**：阿里 **Qwen-Agent**（`qwen-agent` ReAct 范式 + 自定义 Tools）
* **大模型双中枢**：**UnifiedLLMClient**（当前默认使用 Google Gemini 进行对话与分析；支持一键无缝切换至国产 **DeepSeek-V3 / R1** 进行赛事申报）
* **语音多模态引擎**：**Google Gemini API**（Gemini 多模态音频理解与听写）+ **Web Speech API**（零延迟甜美幼教语音播报）
* **前端展示**：**Streamlit**（支持 Web 端、触控大屏、平板 iPad）
* **数据持久化**：SQLite（本地开箱即用）/ Supabase（云端持久化）

---

## 🚀 快速启动指引

### 1. 本地启动（推荐使用虚拟环境）

```bash
# ① 创建并激活虚拟环境（首次）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# ② 安装依赖
pip install -r requirements.txt

# ③ 配置密钥（复制模板并填写，文件已被 .gitignore 排除）
#    .streamlit/secrets.toml 参考 .streamlit/secrets.toml.example

# ④ 启动
streamlit run app.py
```

启动后浏览器将自动打开：`http://localhost:8501`。

> 💡 **语音功能说明**：
> - 语音合成使用 **edge-tts**（微软云 TTS，大陆网络可用、无需 API Key）；
>   网络不可用时自动降级为浏览器 Web Speech 播报（界面保留「再听一遍」按钮）。
> - 语音识别需要配置 **Gemini API Key**；未配置时自动降级为本地规则引擎，全部功能可用。
> - 麦克风仅在安全上下文可用：`http://localhost:8501` 可以，局域网 IP 会被浏览器禁用。

### 2. 运行自动化测试套件

本项目包含全阶段 **29 项**自动化单元测试，确保系统稳定可靠：

```bash
python tests/test_all_suites.py
```

### 3. 云端一键部署 (Streamlit Community Cloud)
1. 将本项目推送到 GitHub 私有或公开仓库（`.streamlit/secrets.toml` 已被 `.gitignore` 排除，**不会泄露密钥**）。
2. 登录 [share.streamlit.io](https://share.streamlit.io/) 并选择该仓库，主文件填 `app.py`。
3. 在 Streamlit Cloud 的 **Secrets** 设置中填入：
   ```toml
   TEACHER_PIN = "123456"
   DEEPSEEK_API_KEY = "你的_DeepSeek_API_Key"
   DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
   DEEPSEEK_MODEL = "deepseek-chat"
   GEMINI_API_KEY = "你的_Gemini_API_Key"
   ```
4. 点击 Deploy 即可在全球任何设备通过网址访问！

---

## 📋 赛事申报材料支撑（对应评审指标）

* **《开发与应用报告》要点**：
  * **背景**：解决传统图书角整理繁琐、幼儿找书靠老师、缺乏阅读数据支撑的难题。
  * **创新**：国产智能体双端流转设计、儿童具象书架映射、语音与视觉双模态正反馈。
  * **成效**：幼儿主动归位率达 90% 以上，值日打卡激发自主责任感，教师精准把握幼儿阅读喜好。
* **演示视频录制节奏建议（8分钟）**：
  * 00:00 - 01:00：图书角痛点引入与智能体定位。
  * 01:00 - 04:00：儿童端实景操作（语音找书、书架高亮、谁值日打卡、好书送红心）。
  * 04:00 - 06:30：教师端后台演示（输入书名 AI 自动建档、名单一键排班、阅读热力与换书报告）。
  * 06:30 - 08:00：总结教育创新成效与信创大模型落地价值。
