import os
import sys
import streamlit as st
from io import StringIO
from utils import word_iterator
from contextlib import contextmanager  # 添加这一行
import re
import base64

# 动态导入 subtask
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from sub_task import subtask

# 添加图片base64编码函数
def get_image_base64(image_path):
    """将图片文件转换为base64编码的字符串"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception as e:
        st.error(f"Error reading image {image_path}: {e}")
        return ""

# 创建会话状态变量
if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'output_lines' not in st.session_state:
    st.session_state.output_lines = []
if 'running' not in st.session_state:
    st.session_state.running = False
if 'screenshot_path' not in st.session_state:
    st.session_state.screenshot_path = None
if 'main_response' not in st.session_state:
    st.session_state.main_response = ""

# add new  state to resent the agent's thinking process
if 'agent_status' not in st.session_state:
    st.session_state.agent_status = ""
if 'current_app' not in st.session_state:
    st.session_state.current_app = ""

# 添加一个用于存储选中示例查询的状态变量
if 'selected_example_query' not in st.session_state:
    st.session_state.selected_example_query = ""

# 定义回调函数
def submit_query():
    st.session_state.submitted = True

st.set_page_config(
    page_title="AppAgent-Pro | CIKM 2025 Demo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/LaoKuiZe/AppAgent-Pro',
        'Report a bug': 'https://github.com/LaoKuiZe/AppAgent-Pro/issues',
        'About': "# AppAgent-Pro\na system that represents a significant advancement towards instilling genuine proactivity within the mobile agent paradigm."
    }
)

# 创建一个用于捕获输出的上下文管理器
@contextmanager
def capture_and_stream():
    # 在主栏目创建一个空容器
    main_container = st.container()
    # 在侧边栏创建一个空容器
    sidebar_container = st.sidebar.container()
    sidebar_placeholder = sidebar_container.empty()

    # 正则表达式，用于匹配并移除 ANSI 转义码
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])') # delete the color code

    # 创建一个自定义的文件对象来捕获输出
    class StreamCapture:
        def __init__(self):
            self.text = ""
            
        def write(self, text):
            # 首先移除 ANSI 代码
            clean_text = ansi_escape.sub('', text)
            
            # 过滤掉特殊字符和异常格式
            # 1. 替换单引号和特殊引号
            clean_text = re.sub(r'[′`]', "'", clean_text)
            
            # 2. 确保数字后面的单引号不会被分隔
            clean_text = re.sub(r'(\d+)\s*[\'′`]\s*', r'\1\'', clean_text)
            
            # 3. 移除单字符后跟<br>的模式 (常见错误模式)
            clean_text = re.sub(r'([a-zA-Z0-9])\s*<br>', r'\1', clean_text)
            
            # 4. 如果是完全乱码的行(每个字符都被分离)，尝试重新组合
            if re.search(r'(<br>)?[a-zA-Z0-9](<br>)[a-zA-Z0-9](<br>)', clean_text):
                clean_text = re.sub(r'(<br>)?([a-zA-Z0-9])(<br>)', r'\2', clean_text)

            # 5. 移除末尾多余的换行符，只保留一个
            clean_text = clean_text.rstrip('\n') + ('\n' if clean_text.endswith('\n') else '')
    
            # 6. 规范化换行符，避免连续多个换行
            clean_text = re.sub(r'\n{2,}', '\n', clean_text)
            
            # 正常将换行符替换为HTML换行
            html_text = clean_text.replace('\n', '<br>')
            
            # 累加处理后的文本
            self.text += html_text
              # 更新侧边栏内容，使用HTML格式，并添加自动滚动脚本
            # 使用更专业的控制台样式展示输出
            formatted_text = f"""
            <div class="process-log" style="font-family: 'Roboto Mono', monospace; font-size: 0.85rem; 
                                           background-color: rgba(0, 0, 0, 0.2); border-radius: 8px; 
                                           padding: 1rem; line-height: 1.5; color: #E0E0E0; 
                                           max-height: 75vh; overflow-y: auto;">
                {self.text}
                <div id='end-of-content'></div>
            </div>
            """
            
            sidebar_placeholder.markdown(formatted_text, unsafe_allow_html=True)
            
            # 然后单独注入自动滚动脚本
            st.sidebar.markdown(
                """
                <script>
                    // 自动滚动到底部
                    function scrollSidebarToBottom() {
                        try {
                            const sidebar = window.parent.document.querySelector("[data-testid='stSidebar']");
                            if(sidebar) {
                                // 直接滚动侧边栏
                                sidebar.scrollTop = sidebar.scrollHeight;
                                
                                // 查找并滚动所有可能的容器
                                const scrollContainers = sidebar.querySelectorAll("div[data-testid='stVerticalBlock'], div[data-testid='stVerticalBlockBorderWrapper']");
                                scrollContainers.forEach(container => {
                                    if(container.scrollHeight > container.clientHeight) {
                                        container.scrollTop = container.scrollHeight;
                                    }
                                });
                            }
                        } catch(e) {
                            console.error("Scroll error:", e);
                        }
                    }
                    
                    // 立即执行一次
                    scrollSidebarToBottom();
                    
                    // 延迟多次执行以确保滚动到底部
                    setTimeout(scrollSidebarToBottom, 300);
                    setTimeout(scrollSidebarToBottom, 600);
                    setTimeout(scrollSidebarToBottom, 1000);
                </script>
                """,
                unsafe_allow_html=True
            )
            
        def flush(self):
            pass
    
    stream_capture = StreamCapture()
    old_stdout = sys.stdout
    sys.stdout = stream_capture
    
    try:
        yield stream_capture, main_container
    finally:
        sys.stdout = old_stdout

# 页面样式和标题 - 优化为适合学术展示的现代界面
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    /* 全局主题颜色 */
    :root {
        --primary-color: #1a202c;          /* 深蓝灰 - 主色调 */
        --secondary-color: #4299e1;        /* 明亮蓝色 - 强调色 */
        --accent-color: #38b2ac;           /* 青绿色 - 特殊强调 */
        --success-color: #48bb78;          /* 成功绿色 */
        --warning-color: #ed8936;          /* 警告橙色 */
        --light-bg: #f7fafc;               /* 浅灰背景 */
        --dark-bg: #2d3748;                /* 深色背景 */
        --card-bg: #ffffff;                /* 卡片背景 */
        --text-color: #2d3748;             /* 主要文本颜色 */
        --light-text: #a0aec0;             /* 浅色文本 */
        --border-color: #e2e8f0;           /* 边框颜色 */
        --border-radius: 12px;             /* 统一边框圆角 */
        --box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.05); /* 精致阴影 */
        --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); /* 平滑过渡 */
    }
    
    /* 全局样式重置 */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* 页面布局 */
    .main .block-container {
        max-width: 1400px;
        padding: 2rem 2rem;
        margin: 0 auto;
    }
    
    /* 隐藏Streamlit默认的header和footer */
    header[data-testid="stHeader"] {
        height: 0;
    }
    
    .stApp > footer {
        display: none;
    }
    
    /* Hero Section样式 */
    .hero-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 3rem 2rem;
        border-radius: var(--border-radius);
        margin-bottom: 3rem;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    
    .hero-section::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="50" cy="50" r="1" fill="white" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
        pointer-events: none;
    }
    
    .hero-content {
        position: relative;
        z-index: 1;
    }
    
    .hero-title {
        font-size: 3.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        letter-spacing: -2px;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    
    .hero-subtitle {
        font-size: 1.4rem;
        font-weight: 400;
        opacity: 0.9;
        margin-bottom: 2rem;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    }
    
    .cikm-badge {
        display: inline-block;
        background: rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(10px);
        padding: 0.5rem 1.5rem;
        border-radius: 25px;
        font-weight: 500;
        font-size: 0.9rem;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* 特色功能卡片 */
    .feature-cards {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        margin: 2rem 0;
    }
    
    .feature-card {
        background: var(--card-bg);
        border-radius: var(--border-radius);
        padding: 1.5rem;
        box-shadow: var(--box-shadow);
        border: 1px solid var(--border-color);
        transition: var(--transition);
        position: relative;
        overflow: hidden;
        min-width: 0;
        cursor: pointer;
    }
    
    .feature-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.12);
        border-color: var(--secondary-color);
    }
    
    .feature-card:active {
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
    }
    
    .feature-icon {
        width: 50px;
        height: 50px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        margin-bottom: 1rem;
        background: linear-gradient(135deg, var(--secondary-color), var(--accent-color));
        color: white;
    }
    
    .feature-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-color);
        margin-bottom: 0.6rem;
        line-height: 1.3;
    }
    
    .feature-description {
        color: var(--light-text);
        line-height: 1.5;
        font-size: 0.85rem;
    }
    
    /* 输入框优化 */
    div.stTextInput > div > div > input {
        width: 100% !important;
        padding: 1.2rem 1.5rem !important; /* 稍微增加padding */
        border-radius: var(--border-radius) !important;
        border: 2px solid var(--border-color) !important;
        font-size: 1.1rem !important;
        transition: var(--transition) !important;
        background: var(--card-bg) !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important; /* 增强阴影 */
    }
    
    div.stTextInput > div > div > input:focus {
        border-color: var(--secondary-color) !important;
        box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1) !important;
        outline: none !important;
    }
    
    /* 输入框和按钮区域的背景 */
    .input-controls-area {
        background: var(--card-bg);
        border-radius: var(--border-radius);
        padding: 1.5rem;
        margin: 1rem 0 2rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid var(--border-color);
    }
    
    /* 按钮样式优化 */
    .stButton > button {
        background: linear-gradient(135deg, var(--secondary-color), var(--accent-color)) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: var(--border-radius) !important;
        padding: 1rem 2rem !important;
        font-size: 1.1rem !important;
        letter-spacing: 0.5px !important;
        height: auto !important;
        transition: var(--transition) !important;
        box-shadow: 0 4px 15px rgba(66, 153, 225, 0.4) !important;
        text-transform: none !important;
        min-height: 3.2rem !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(66, 153, 225, 0.5) !important;
    }
    
    .stButton > button:active {
        transform: translateY(0) !important;
    }
    
    /* 响应容器样式 */
    .response-container {
        background: var(--card-bg);
        border-radius: var(--border-radius);
        box-shadow: var(--box-shadow);
        padding: 2rem;
        margin: 2rem 0;
        border: 1px solid var(--border-color);
    }
    
    .result-header {
        display: flex;
        align-items: center;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--border-color);
    }
    
    .result-icon {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, var(--success-color), #38b2ac);
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 1rem;
        color: white;
        font-size: 1.2rem;
    }
    
    .screenshot-container {
        background: var(--light-bg);
        border-radius: var(--border-radius);
        padding: 2rem;
        margin-top: 2rem;
        border: 1px solid var(--border-color);
    }
    
    .screenshot-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
        margin-top: 1.5rem;
    }
    
    .screenshot-item {
        background: white;
        border-radius: var(--border-radius);
        padding: 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid var(--border-color);
    }
    
    .app-badge {
        display: inline-block;
        background: var(--secondary-color);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-bottom: 0.8rem;
    }
    
    /* 侧边栏样式 */
    [data-testid="stSidebar"] {
        background: var(--dark-bg);
        padding-top: 2rem;
    }
    
    [data-testid="stSidebar"] [data-testid="stMarkdown"] {
        color: #e2e8f0;
    }
    
    .sidebar-title {
        color: white !important;
        font-weight: 700 !important;
        font-size: 1.4rem !important;
        margin-bottom: 1.5rem !important;
        padding-bottom: 0.75rem !important;
        border-bottom: 2px solid rgba(255, 255, 255, 0.2) !important;
    }
    
    .sidebar-info {
        background: rgba(255, 255, 255, 0.1);
        border-radius: var(--border-radius);
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .process-log {
        background: rgba(0, 0, 0, 0.3);
        border-radius: var(--border-radius);
        padding: 1rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        color: #e2e8f0;
        max-height: 70vh;
        overflow-y: auto;
        line-height: 1.5;
        margin-top: 1rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* 状态指示器 */
    .status-indicator {
        background: linear-gradient(135deg, #f0f9ff, #e6f7ff);
        border-radius: var(--border-radius);
        padding: 1.5rem;
        margin: 1.5rem 0;
        display: flex;
        align-items: center;
        border: 1px solid rgba(66, 153, 225, 0.2);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    
    .spinner {
        width: 28px;
        height: 28px;
        border: 3px solid rgba(66, 153, 225, 0.1);
        border-radius: 50%;
        border-top-color: var(--secondary-color);
        animation: spin 1s linear infinite;
        margin-right: 15px;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .status-text {
        color: var(--secondary-color);
        font-weight: 600;
        font-size: 1.1rem;
    }
    
    /* 底部信息 */
    .footer-info {
        margin-top: 4rem;
        padding: 2rem;
        background: var(--light-bg);
        border-radius: var(--border-radius);
        text-align: center;
        border: 1px solid var(--border-color);
    }
    
    .citation-box {
        background: white;
        border-radius: 8px;
        padding: 1.5rem;
        margin-top: 1rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        border: 1px solid var(--border-color);
        text-align: left;
        color: var(--text-color);
    }
    
    /* 响应式设计 */
    @media (max-width: 1200px) {
        .feature-cards {
            grid-template-columns: repeat(3, 1fr);
            gap: 0.8rem; /* 进一步减小间距 */
        }
        
        .feature-card {
            padding: 1.2rem; /* 在中等屏幕上进一步减小padding */
        }
        
        .feature-title {
            font-size: 1rem; /* 稍微减小标题字体 */
        }
        
        .feature-description {
            font-size: 0.8rem; /* 稍微减小描述字体 */
        }
    }
    
    @media (max-width: 900px) {
        .feature-cards {
            grid-template-columns: repeat(2, 1fr);
        }
        
        .input-title {
            font-size: 1.6rem;
        }
        
        .input-controls-area {
            padding: 1.2rem;
        }
    }
    
    @media (max-width: 768px) {
        .hero-title {
            font-size: 2.5rem;
        }
        
        .feature-cards {
            grid-template-columns: 1fr;
        }
        
        .feature-card {
            padding: 1rem; /* 移动设备上最小padding */
        }
        
        .input-title {
            font-size: 1.4rem;
        }
        
        .input-controls-area {
            padding: 1rem;
            margin: 0.5rem 0 1.5rem 0;
        }
        
        .example-queries {
            flex-direction: column;
            align-items: center;
            padding: 0 0.5rem;
        }
        
        .example-queries .stButton {
            width: 100%;
            max-width: 280px; /* 稍微减小最大宽度 */
        }
        
        .main .block-container {
            padding: 1rem;
        }
    }
    
    /* 示例查询按钮 */
    .example-queries {
        display: flex;
        flex-wrap: wrap;
        gap: 0.8rem;
        justify-content: center;
        margin-bottom: 2rem;
        padding: 0 1rem; /* 添加左右padding */
    }
    
    .example-query {
        background: var(--light-bg);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        padding: 0.6rem 1.2rem;
        font-size: 0.85rem;
        color: var(--text-color);
        cursor: pointer;
        transition: var(--transition);
        white-space: nowrap;
    }
    
    .example-query:hover {
        background: var(--secondary-color);
        color: white;
        transform: translateY(-1px);
    }
    
    /* 重新样式化示例查询的Streamlit按钮 */
    .example-queries .stButton > button {
        background: var(--light-bg) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 25px !important; /* 稍微增加圆角 */
        padding: 0.7rem 1.5rem !important; /* 稍微增加padding */
        font-size: 0.9rem !important; /* 稍微增大字体 */
        color: var(--text-color) !important;
        transition: var(--transition) !important;
        white-space: nowrap !important;
        height: auto !important;
        min-height: auto !important;
        font-weight: 500 !important; /* 稍微增加字重 */
        text-transform: none !important;
        letter-spacing: normal !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important; /* 添加轻微阴影 */
    }
    
    .example-queries .stButton > button:hover {
        background: var(--secondary-color) !important;
        color: white !important;
        transform: translateY(-2px) !important; /* 增加悬停移动距离 */
        border-color: var(--secondary-color) !important;
        box-shadow: 0 4px 12px rgba(66, 153, 225, 0.3) !important; /* 增强悬停阴影 */
    }
    
    .example-queries .stButton > button:active {
        transform: translateY(0) !important;
    }
</style>
""", unsafe_allow_html=True)

# 主要内容区
main_col = st.container()

with main_col:
    # Hero Section - 学术展示标题
    st.markdown("""
    <div class="hero-section">
        <div class="hero-content">
            <div class="cikm-badge">CIKM 2025 Demo Track</div>
            <h1 class="hero-title">AppAgent-Pro</h1>
            <p class="hero-subtitle">
                An Intelligent Mobile Application Agent with Proactive App Integration Capabilities
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 特色功能展示
    st.markdown("""
    <div class="feature-cards">
        <div class="feature-card">
            <div class="feature-icon">🧠</div>
            <div class="feature-title">Proactive Decision Making</div>
            <div class="feature-description">
                Automatically determines whether to leverage mobile apps (YouTube, Amazon) based on query context without user intervention.
            </div>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🔄</div>
            <div class="feature-title">Dynamic App Integration</div>
            <div class="feature-description">
                Seamlessly integrates with none, one, or multiple mobile applications to enhance response quality and provide richer information.
            </div>
        </div>
        <div class="feature-card">
            <div class="feature-icon">📱</div>
            <div class="feature-title">Real-time Execution</div>
            <div class="feature-description">
                Observe live interaction with mobile applications and see how the agent navigates apps to gather relevant information.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 标题和说明（不使用容器包装）
    st.markdown("""
        <h2 style="font-size: 1.8rem; font-weight: 600; color: var(--text-color); 
                   margin-bottom: 0.8rem; text-align: center;">Try AppAgent-Pro</h2>
        <p style="color: var(--light-text); text-align: center; margin-bottom: 1.5rem; 
                  font-size: 1rem; max-width: 600px; margin-left: auto; margin-right: auto;">
           Enter your query below and watch how the agent proactively decides which apps to use
        </p>
    """, unsafe_allow_html=True)
    
    # 示例查询按钮
    st.markdown('<div class="example-queries">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3, gap="medium")
    
    with col1:
        if st.button("🌍 How to quickly learn a new foreign language?", key="example1", use_container_width=True):
            st.session_state.selected_example_query = "How to quickly learn a new foreign language?"
    
    with col2:
        if st.button("📱 Best budget smartphones under $300?", key="example2", use_container_width=True):
            st.session_state.selected_example_query = "What are the best budget smartphones under $300?"
    
    with col3:
        if st.button("🥗 Plan healthy meal prep for professionals", key="example3", use_container_width=True):
            st.session_state.selected_example_query = "Plan a healthy meal prep for busy professionals"
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 输入框和执行按钮区域
    st.markdown('<div class="input-controls-area">', unsafe_allow_html=True)
    # 将输入框和按钮放在同一行，优化对齐
    input_col, button_col = st.columns([4, 1], gap="medium")
    with input_col:
        # 如果有选中的示例查询，使用它作为默认值
        default_value = st.session_state.selected_example_query if st.session_state.selected_example_query else ""
        query = st.text_input(
            "",
            value=default_value,
            key="query_input",
            on_change=submit_query,
            placeholder="Describe your task in natural language (e.g., 'How to quickly learn a new foreign language?')",
            label_visibility="collapsed"
        )
        
        # 如果查询被设置了，清除选中的查询状态以避免重复设置
        if st.session_state.selected_example_query and query == st.session_state.selected_example_query:
            st.session_state.selected_example_query = ""
        
    with button_col:
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)  # 减少间距
        run_clicked = st.button("🚀 Execute", use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # 创建占位区域用来显示回答和截图
    response_area = st.empty()
    screenshot_area = st.empty()

# 侧边栏标题和说明
st.sidebar.markdown('<h2 class="sidebar-title">🔍 Execution Monitor</h2>', unsafe_allow_html=True)
st.sidebar.markdown("""
<div class="sidebar-info">
    <h4 style="color: white; margin-top: 0; margin-bottom: 1rem;">Real-time Process</h4>
    <p style="color: #e2e8f0; margin: 0; font-size: 0.9rem; line-height: 1.6;">
        This panel shows the agent's decision-making process in real-time. Watch how it:
    </p>
    <ul style="color: #e2e8f0; font-size: 0.85rem; line-height: 1.5; margin-top: 0.8rem; padding-left: 1.2rem;">
        <li>Analyzes your query</li>
        <li>Decides which apps to use</li>
        <li>Executes mobile interactions</li>
        <li>Integrates information</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# 添加系统状态显示
st.sidebar.markdown("""
<div style="background: rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
    <h5 style="color: white; margin-top: 0; margin-bottom: 0.8rem;">Supported Applications</h5>
    <div style="display: flex; flex-direction: column; gap: 0.5rem;">
        <div style="display: flex; align-items: center; color: #e2e8f0; font-size: 0.85rem;">
            <span style="color: #ff4757; margin-right: 8px;">📺</span> YouTube
        </div>
        <div style="display: flex; align-items: center; color: #e2e8f0; font-size: 0.85rem;">
            <span style="color: #ff9f43; margin-right: 8px;">🛒</span> Amazon
        </div>
        <div style="display: flex; align-items: center; color: #a0aec0; font-size: 0.85rem;">
            <span style="color: #54a0ff; margin-right: 8px;">🔜</span> More apps coming...
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# 处理提交
if run_clicked or st.session_state.submitted:
    if st.session_state.submitted:
        st.session_state.submitted = False
    # 清空之前的输出
    response_area.empty()
    screenshot_area.empty()
    
    # 重置状态变量
    st.session_state.agent_status = "thinking"
    st.session_state.current_app = ""  # reset current app
    
    # 创建一个状态占位符，用于动态更新状态
    if 'status_placeholder' not in st.session_state:
        st.session_state.status_placeholder = st.empty()
    else:
        st.session_state.status_placeholder.empty()
        st.session_state.status_placeholder = st.empty()    # 显示初始状态
    with st.session_state.status_placeholder.container():
        st.markdown("""
        <div class="status-indicator">
            <div class="spinner"></div>
            <span class="status-text">🧠 Agent is analyzing your task request...</span>
        </div>
        """, unsafe_allow_html=True)
    
    from task_executor import execute_task
    try:
        with capture_and_stream() as (output, main_container):
            main_response, screenshot_paths = execute_task(query)
            st.session_state.main_response = main_response
            st.session_state.screenshot_path = screenshot_paths
    except Exception as e:
        st.error(f"Error: {e}")
        st.session_state.main_response = f"ERROR: {e}"
        st.session_state.screenshot_path = None
    
    # 清除状态提示
    st.session_state.status_placeholder.empty()    # 显示主回答
    with response_area.container():
        st.markdown("""
        <div class="response-container">
            <div class="result-header">
                <div class="result-icon">✓</div>
                <div>
                    <h3 style="margin: 0; color: var(--text-color); font-size: 1.4rem;">Task Completed Successfully</h3>
                    <p style="margin: 0; color: var(--light-text); font-size: 0.9rem;">Enhanced response with mobile app integration</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        st.markdown(st.session_state.main_response)
        st.markdown("</div>", unsafe_allow_html=True)    # 显示最终截图
    if st.session_state.screenshot_path:
        with screenshot_area.container():
            st.markdown("""
            <div class="screenshot-container">
                <div style="display: flex; align-items: center; margin-bottom: 1.5rem;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, var(--secondary-color), var(--accent-color)); 
                             display: flex; align-items: center; justify-content: center; margin-right: 1rem; color: white; font-size: 1.2rem;">📱</div>
                    <div>
                        <h3 style="margin: 0; color: var(--text-color); font-size: 1.4rem;">Application Screenshots</h3>
                        <p style="margin: 0; color: var(--light-text); font-size: 0.9rem;">Live captures from mobile app interactions</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            if isinstance(st.session_state.screenshot_path, list):
                st.markdown('<div class="screenshot-grid">', unsafe_allow_html=True)
                for i, path in enumerate(st.session_state.screenshot_path):
                    if path and os.path.exists(path):
                        app_name = "Unknown App"
                        app_color = "#6c757d"
                        if "amazon" in path.lower():
                            app_name = "Amazon"
                            app_color = "#ff9500"
                        elif "youtube" in path.lower():
                            app_name = "YouTube"
                            app_color = "#ff0000"
                        
                        st.markdown(f"""
                        <div class="screenshot-item">
                            <div class="app-badge" style="background-color: {app_color};">{app_name}</div>
                            <img src="data:image/png;base64,{get_image_base64(path)}" style="width: 100%; border-radius: 8px;" alt="{app_name} Screenshot">
                        </div>
                        """, unsafe_allow_html=True)
                    elif path:
                        st.info(f"Screenshot path: {path}")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                path = st.session_state.screenshot_path
                if path and os.path.exists(path):
                    app_name = "Unknown App"
                    app_color = "#6c757d"
                    if "amazon" in path.lower():
                        app_name = "Amazon"
                        app_color = "#ff9500"
                    elif "youtube" in path.lower():
                        app_name = "YouTube"
                        app_color = "#ff0000"
                    
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        st.markdown(f'<div class="app-badge" style="background-color: {app_color}; text-align: center; margin-bottom: 1rem;">{app_name}</div>', unsafe_allow_html=True)
                        st.image(path, use_container_width=True)
                elif path:
                    st.info(f"Screenshot path: {path}")
            
            st.markdown("</div>", unsafe_allow_html=True)
            
    # 添加学术引用和CIKM信息
    st.markdown("""
    <div style="margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #e1e4e8; text-align: center;">
        <p style="font-size: 0.9rem; color: #6c757d;">
            <strong>AppAgent-Pro</strong> - A Demo Paper for CIKM 2025
        </p>
        <p style="font-size: 0.85rem; color: #6c757d; margin-top: 0.5rem;">
            If you use this system in your research, please cite our paper.
        </p>
    </div>
    """, unsafe_allow_html=True)