import os
import sys
import streamlit as st
from utils import word_iterator
from contextlib import contextmanager
import re

# creat state variables
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

def submit_query():
    st.session_state.submitted = True

st.set_page_config(
    page_title="AppAgent-Pro",
    layout="centered"
)

@contextmanager
def capture_and_stream():
    main_container = st.container()

    sidebar_container = st.sidebar.container()
    sidebar_placeholder = sidebar_container.empty()

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])') # delete the color code

    class StreamCapture:
        def __init__(self):
            self.text = ""
            
        def write(self, text):
            clean_text = ansi_escape.sub('', text)
            
            # clean the text
            clean_text = re.sub(r'[′`]', "'", clean_text)
            
            clean_text = re.sub(r'(\d+)\s*[\'′`]\s*', r'\1\'', clean_text)
            
            clean_text = re.sub(r'([a-zA-Z0-9])\s*<br>', r'\1', clean_text)
            
            if re.search(r'(<br>)?[a-zA-Z0-9](<br>)[a-zA-Z0-9](<br>)', clean_text):
                clean_text = re.sub(r'(<br>)?([a-zA-Z0-9])(<br>)', r'\2', clean_text)

            clean_text = clean_text.rstrip('\n') + ('\n' if clean_text.endswith('\n') else '')
    
            clean_text = re.sub(r'\n{2,}', '\n', clean_text)
            
            html_text = clean_text.replace('\n', '<br>')
            
            self.text += html_text
            
            sidebar_placeholder.markdown(
                self.text + "<div id='end-of-content'></div>", 
                unsafe_allow_html=True
            )
            
            sidebar_placeholder.markdown(
                self.text + "<div id='end-of-content'></div>", 
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

st.markdown("""
<style>
.main .block-container {
    max-width: 1200px;
    padding-left: 1rem;
    padding-right: 1rem;
}
.title {
    text-align: center;
    margin-bottom: 2rem;
    width: 100%;
}
.stTextInput, 
.element-container:has(.thinking-completed),
.element-container:has(.answer-section),
.stMarkdown:has(> div) > div:first-child,
.stMarkdown:has(> div) > div > div {  
    width: 100% !important;
    max-width: 1000px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
div.stTextInput > div > div > input {
    width: 100% !important;
}
.thinking-completed, 
.answer-section {
    width: 100% !important;  
    padding: 20px !important;
    margin: 1rem 0 !important;
    box-sizing: border-box !important;  
}
.thinking-completed {
    background-color: #ffffff;
    border-radius: 5px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.answer-section {
    border: 1px solid #4CAF50;
    border-radius: 5px;
    background-color: #f8f9fa;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.stMarkdown {
    width: 100% !important;
    max-width: 100% !important;
}
.stMarkdown > div > div {
    width: 100% !important;
    max-width: 100% !important;
}
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
.thinking-spinner {
    display: inline-block;
    width: 20px;
    height: 10px;
    border: 3px solid rgba(0, 0, 0, 0.1);
    border-radius: 50%;
    border-top-color: #4CAF50;
    animation: spin 1s ease-in-out infinite;
    margin-right: 10px;
    vertical-align: middle;
}
.thinking-header {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

main_col = st.container()

with main_col:
    st.markdown('<div class="title"><h1>AppAgent-Pro</h1></div>', unsafe_allow_html=True)
    st.write_stream(word_iterator("**What can I help with?**"))

    input_col, button_col = st.columns([4, 1])
    query = input_col.text_input(
        "Ask anything",
        "",
        key="query_input",
        on_change=submit_query,
        placeholder="Enter your task description..."
    )
    run_clicked = button_col.button("Run")

    response_area = st.empty()
    screenshot_area = st.empty()

st.sidebar.title("Executing Process")

if run_clicked or st.session_state.submitted:
    if st.session_state.submitted:
        st.session_state.submitted = False

    response_area.empty()
    screenshot_area.empty()
    
    st.session_state.agent_status = "thinking"
    st.session_state.current_app = ""  # reset current app
    
    if 'status_placeholder' not in st.session_state:
        st.session_state.status_placeholder = st.empty()
    else:
        st.session_state.status_placeholder.empty()
        st.session_state.status_placeholder = st.empty()

    with st.session_state.status_placeholder.container():
        st.markdown('<div style="background-color:#f0f8ff;padding:8px 12px;border-radius:5px;margin:8px 0;"><span style="color:#4CAF50;font-weight:bold;font-size:14px;">🔍Agent is analyzing your question...</span></div>', unsafe_allow_html=True)
    
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
    
    # clear the status placeholder
    st.session_state.status_placeholder.empty()

    # present the output
    with response_area.container():
        st.markdown("### **✅Main answer:**")
        st.markdown(st.session_state.main_response)

    # present the screenshots
    if st.session_state.screenshot_path:
        with screenshot_area.container():
            st.markdown("### **📷Sub-tasks Screenshot:**")
            if isinstance(st.session_state.screenshot_path, list):
                for i, path in enumerate(st.session_state.screenshot_path):
                    if path and os.path.exists(path):
                        if "amazon" in path.lower():
                            st.markdown(f"**Amazon Screenshot:**")
                        elif "youtube" in path.lower():
                            st.markdown(f"**Youtube Screenshot:**")
                        st.image(path, caption=f"App {i+1} Screenshot", width=400)
                    elif path:
                        st.info(f"screenshot path: {path}")
            else:
                path = st.session_state.screenshot_path
                if path and os.path.exists(path):
                    if "amazon" in path.lower():
                        st.markdown(f"**Amazon Screenshot:**")
                    elif "youtube" in path.lower():
                        st.markdown(f"**Youtube Screenshot:**")
                    st.image(path, caption="App Screenshot", width=400)
                elif path:
                    st.info(f"screenshot path: {path}")