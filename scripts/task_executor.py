import argparse
import ast
import datetime
import json
import os
import re
import sys
import time

import prompts
from config import load_config
from and_controller import list_all_devices, AndroidController, traverse_tree
from model import parse_explore_rsp, parse_grid_rsp, OpenAIModel, parse_main_rsp
from utils import print_with_color, draw_bbox_multi, draw_grid
from sub_task import subtask
import streamlit as st

arg_desc = "AppAgent Executor"
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=arg_desc)
parser.add_argument("--app")
parser.add_argument("--root_dir", default="./")
args = vars(parser.parse_args())

def execute_task(query=None):
    configs = load_config()

    if configs["MODEL"] == "OpenAI":
        mllm = OpenAIModel(base_url=configs["OPENAI_API_BASE"],
                        api_key=configs["OPENAI_API_KEY"],
                        model=configs["OPENAI_API_MODEL"],
                        temperature=configs["TEMPERATURE"],
                        max_tokens=configs["MAX_TOKENS"])
    elif configs["MODEL"] == "Qwen":
        mllm = QwenModel(api_key=configs["DASHSCOPE_API_KEY"],
                        model=configs["QWEN_MODEL"])
    else:
        print_with_color(f"ERROR: Unsupported model type {configs['MODEL']}!", "red")
        return "❗Unsupported model type", None

    if query is None:
        print_with_color("Please enter the description of the task you want me to complete in a few sentences:", "blue")
        main_desc = input()
    else:
        main_desc = query
        
    main_prompt = re.sub(r"<task_description>", main_desc, prompts.main_task_template)

    # Update status to "analyzing problem"
    if 'agent_status' in st.session_state:
        st.session_state.agent_status = "thinking"
        update_status_display()

    # First get the text answer for the main task
    print_with_color("App-Agent is thinking...", "blue")
    main_status, main_task_response = mllm.get_main_response(main_prompt)
    main_task_response = main_task_response.replace("**","")
    
    if not main_status:
        print_with_color(f"ERROR: Main task response failed: {main_task_response}", "red")
        return f"ERROR: {main_task_response}", None
    else:
        try:
            # Extract three parts using regular expressions
            answer_match = re.search(r'Answer:(.*?)(?=App:|$)', main_task_response, re.DOTALL)
            answer = answer_match.group(1).strip() if answer_match else ""
            
            app_match = re.search(r'App:(.*?)(?=Sub-tasks:|$)', main_task_response, re.DOTALL)
            app = app_match.group(1).strip() if app_match else "None"
            
            subtasks_match = re.search(r'Sub-tasks:(.*?)$', main_task_response, re.DOTALL)
            subtasks = subtasks_match.group(1).strip() if subtasks_match else ""
            
            # If answer is empty, try using response as answer
            if not answer:
                answer = main_task_response.strip()
            
            print_with_color(f"Answer: {answer}", "green")
            print_with_color(f"Selected app(s): {app}", "green")
            if subtasks:
                print_with_color(f"Sub-tasks: {subtasks}", "green")

            app_tasks = {}
            if subtasks:
                if app.lower() != "both" and app.lower() != "none" and ":" not in subtasks:
                    app_tasks[app] = subtasks
                else:
                    app_task_matches = re.findall(r'[-\s]*([^:]+):\s*(.*?)(?=\n\s*[-]*\s*[^:]+:|$)', subtasks, re.DOTALL)
                    for app_name, task in app_task_matches:
                        app_tasks[app_name.strip()] = task.strip()
            
            task_desc = main_desc  
            
        except Exception as e:
            print_with_color(f"ERROR: Failed to parse main task response: {str(e)}", "red")
            print_with_color(f"Original response: {main_task_response}", "red")
            return f"ERROR OCCURRED WHEN PARSING MAIN TASK RESPONSE: {str(e)}", None

    screenshot_paths = []

    if len(app_tasks) == 0:
        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "completed"
            update_status_display()
        formatted_answer = f"🌟 {answer}"
        return formatted_answer, None

    elif len(app_tasks) == 1:
        app = list(app_tasks.keys())[0]
        task_desc = f"First, tap the icon of {app}." + app_tasks[app]
        print_with_color(f"**APP: {app}**", "yellow")
        print_with_color(f"**Sub-tasks: {task_desc}**", "yellow")
        
        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "executing"
            st.session_state.current_app = app
            update_status_display()
        
        app = app.lower()
        result_path = subtask(app, task_desc)
        
        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "completed"
            st.session_state.current_app = ""
            update_status_display()
            
        print_with_color(f"**Sub-tasks completed!**", "blue")
        print_with_color(f"**APP {app} screenshot path: {result_path}**", "yellow")
        
        formatted_answer = f"🌟 {answer}"
        return formatted_answer, result_path
        
    elif len(app_tasks) == 2:
        app_names = list(app_tasks.keys())
        app1 = app_names[0]
        app2 = app_names[1]
        
        task_desc1 = f"First, tap the icon of {app1}." + app_tasks[app1]
        task_desc2 = f"First, tap the icon of {app2}." + app_tasks[app2]
        
        print_with_color(f"{app1} sub-task: {task_desc1}", "yellow")
        print_with_color(f"{app2} sub-task: {task_desc2}", "yellow")
        
        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "executing"
            st.session_state.current_app = app1
            update_status_display()
            
        app1 = app1.lower()
        result_path1 = subtask(app1, task_desc1)
        screenshot_paths.append(result_path1)

        device_list = list_all_devices()
        if device_list:
            device = device_list[0]
            controller = AndroidController(device)
            print_with_color(f"**Back to home page...**", "yellow")
            controller.home()
            time.sleep(2)

        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "executing"
            st.session_state.current_app = app2
            update_status_display()
            
        app2 = app2.lower()
        result_path2 = subtask(app2, task_desc2)
        screenshot_paths.append(result_path2)

        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "completed"
            st.session_state.current_app = ""
            update_status_display()

        print_with_color(f"\n\n🎊All sub-tasks completed!", "blue")
        print_with_color(f"{app1} screenshot path: {result_path1}", "blue")
        print_with_color(f"{app2} screenshot path: {result_path2}", "blue")
        
        formatted_answer = f"🌟 {answer}"
        return formatted_answer, screenshot_paths

def update_status_display():
    if not hasattr(st, 'session_state') or 'agent_status' not in st.session_state:
        return
    
    status = st.session_state.agent_status
    app = st.session_state.current_app
    
    if status == "thinking":
        status_html = """
        <div style="display:flex;align-items:center;background-color:#f0f8ff;padding:8px 12px;border-radius:5px;margin:8px 0;">
            <span style="color:#4CAF50;font-weight:bold;margin-left:8px;font-size:14px;">🧠 Agent is analyzing your question...</span>
        </div>
        """
    elif status == "executing":
        app_name = app.capitalize() if app else "app"
        status_html = f"""
        <div style="display:flex;align-items:center;background-color:#fff8e1;padding:8px 12px;border-radius:5px;margin:8px 0;">
            <span style="color:#ff9800;font-weight:bold;margin-left:8px;font-size:14px;">🔍 Agent is executing {app_name} tasks...</span>
        </div>
        """
    elif status == "completed":
        status_html = """
        <div style="display:flex;align-items:center;background-color:#f1f8e9;padding:8px 12px;border-radius:5px;margin:8px 0;">
            <span style="color:#4CAF50;font-weight:bold;font-size:14px;">✅ Tasks completed!</span>
        </div>
        """
    else:
        status_html = ""
    
    if hasattr(st, 'session_state') and 'status_placeholder' in st.session_state:
        st.session_state.status_placeholder.empty()
        st.session_state.status_placeholder.markdown(status_html, unsafe_allow_html=True)

if __name__ == "__main__":
    result, screenshots = execute_task()
    print(f"Result: {result}\n")
    print(f"Screenshots: {screenshots}\n")