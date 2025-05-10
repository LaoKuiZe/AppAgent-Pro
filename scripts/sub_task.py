import argparse
import ast
import datetime
import json
import os
import re
import sys
import time
import glob

import prompts
from config import load_config
from and_controller import list_all_devices, AndroidController, traverse_tree
from model import parse_explore_rsp, parse_grid_rsp, OpenAIModel
from utils import print_with_color, draw_bbox_multi, draw_grid

def subtask(app: str, task_desc: str):
    configs = load_config()
    root_dir = "./"
    mllm = OpenAIModel(base_url=configs["OPENAI_API_BASE"],
                       api_key=configs["OPENAI_API_KEY"],
                       model=configs["OPENAI_API_MODEL"],
                       temperature=configs["TEMPERATURE"],
                       max_tokens=configs["MAX_TOKENS"])
    
    # update the status of the agent
    if 'st' in sys.modules and hasattr(sys.modules['st'], 'session_state'):
        import streamlit as st
        if 'agent_status' in st.session_state:
            st.session_state.agent_status = "executing"
            st.session_state.current_app = app
            if 'update_status_display' in sys.modules['__main__'].__dict__:
                from __main__ import update_status_display
                update_status_display()
            elif 'task_executor' in sys.modules and hasattr(sys.modules['task_executor'], 'update_status_display'):
                from task_executor import update_status_display
                update_status_display()
    
    if app.lower() == "youtube":
        task_desc += "IMPORTANT: You should open the first video excpet the advirtisement and stop after openning it. Remember you need to open a specific video page at the end."
    elif app.lower() == "amazon":
        task_desc += "IMPORTANT: You should open the first product except the advirtisement and stop after openning it. "

    app_dir = os.path.join(os.path.join(root_dir, "apps"), app)
    work_dir = os.path.join(root_dir, "tasks")
    if not os.path.exists(work_dir):
        os.mkdir(work_dir)
    auto_docs_dir = os.path.join(app_dir, "auto_docs")
    demo_docs_dir = os.path.join(app_dir, "demo_docs")
    task_timestamp = int(time.time())
    dir_name = datetime.datetime.fromtimestamp(task_timestamp).strftime(f"task_{app}_%Y-%m-%d_%H-%M-%S")
    task_dir = os.path.join(work_dir, dir_name)
    os.mkdir(task_dir)
    log_path = os.path.join(task_dir, f"log_{app}_{dir_name}.txt")

    # Choose document directory based on availability
    no_doc = False
    
    # Check if demo docs directory exists and contains documents
    demo_docs_available = False
    if os.path.exists(demo_docs_dir):
        # Check if there are any documents in the demo_docs directory
        if glob.glob(os.path.join(demo_docs_dir, "*.txt")):
            demo_docs_available = True
    
    # Check if auto docs directory exists and contains documents
    auto_docs_available = False
    if os.path.exists(auto_docs_dir):
        # Check if there are any documents in the auto_docs directory
        if glob.glob(os.path.join(auto_docs_dir, "*.txt")):
            auto_docs_available = True
    
    # Prioritize human demo docs, fallback to self-exploration docs if needed
    if demo_docs_available:
        docs_dir = demo_docs_dir
        print_with_color("Using human demonstration documents for task execution.", "green")
    elif auto_docs_available:
        docs_dir = auto_docs_dir
        print_with_color("Using autonomous exploration documents for task execution.", "green")
    else:
        no_doc = True
        docs_dir = demo_docs_dir  # Default value, won't be used with no_doc=True
        print_with_color("No documents available for this app. Proceeding without documentation.", "yellow")

    device_list = list_all_devices()
    if not device_list:
        print_with_color("**ERROR: No device found!**", "red")
        sys.exit()
    print_with_color(f"List of devices attached:\n{str(device_list)}", "yellow")
    if len(device_list) == 1:
        device = device_list[0]
        print_with_color(f"Device selected: {device}", "yellow")
    else:
        print_with_color("Please choose the Android device to start demo by entering its ID:", "blue")
        device = input()
    controller = AndroidController(device)
    width, height = controller.get_device_size()
    if not width and not height:
        print_with_color("ERROR: Invalid device size!", "red")
        sys.exit()
    print_with_color(f"Screen resolution of {device}: {width}x{height}", "yellow")

    # 初始化记录参数
    round_count = 0
    last_act = "None"
    task_complete = False
    grid_on = False
    rows, cols = 0, 0


    def area_to_xy(area, subarea):
        area -= 1
        row, col = area // cols, area % cols
        x_0, y_0 = col * (width // cols), row * (height // rows)
        if subarea == "top-left":
            x, y = x_0 + (width // cols) // 4, y_0 + (height // rows) // 4
        elif subarea == "top":
            x, y = x_0 + (width // cols) // 2, y_0 + (height // rows) // 4
        elif subarea == "top-right":
            x, y = x_0 + (width // cols) * 3 // 4, y_0 + (height // rows) // 4
        elif subarea == "left":
            x, y = x_0 + (width // cols) // 4, y_0 + (height // rows) // 2
        elif subarea == "right":
            x, y = x_0 + (width // cols) * 3 // 4, y_0 + (height // rows) // 2
        elif subarea == "bottom-left":
            x, y = x_0 + (width // cols) // 4, y_0 + (height // rows) * 3 // 4
        elif subarea == "bottom":
            x, y = x_0 + (width // cols) // 2, y_0 + (height // rows) * 3 // 4
        elif subarea == "bottom-right":
            x, y = x_0 + (width // cols) * 3 // 4, y_0 + (height // rows) * 3 // 4
        else:
            x, y = x_0 + (width // cols) // 2, y_0 + (height // rows) // 2
        return x, y

    # 开始运行agent
    while round_count < configs["MAX_ROUNDS"]:
        round_count += 1
        print_with_color(f"Round {round_count}", "yellow")
        screenshot_path = controller.get_screenshot(f"{dir_name}_{round_count}", task_dir)
        xml_path = controller.get_xml(f"{dir_name}_{round_count}", task_dir)
        if screenshot_path == "ERROR" or xml_path == "ERROR":
            break
        if grid_on:
            rows, cols = draw_grid(screenshot_path, os.path.join(task_dir, f"{dir_name}_{round_count}_grid.png"))
            image = os.path.join(task_dir, f"{dir_name}_{round_count}_grid.png")
            prompt = prompts.task_template_grid
        else:
            clickable_list = []
            focusable_list = []
            traverse_tree(xml_path, clickable_list, "clickable", True)
            traverse_tree(xml_path, focusable_list, "focusable", True)
            elem_list = clickable_list.copy()
            for elem in focusable_list:
                bbox = elem.bbox
                center = (bbox[0][0] + bbox[1][0]) // 2, (bbox[0][1] + bbox[1][1]) // 2
                close = False
                for e in clickable_list:
                    bbox = e.bbox
                    center_ = (bbox[0][0] + bbox[1][0]) // 2, (bbox[0][1] + bbox[1][1]) // 2
                    dist = (abs(center[0] - center_[0]) ** 2 + abs(center[1] - center_[1]) ** 2) ** 0.5
                    if dist <= configs["MIN_DIST"]:
                        close = True
                        break
                if not close:
                    elem_list.append(elem)
            draw_bbox_multi(screenshot_path, os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png"), elem_list,
                            dark_mode=configs["DARK_MODE"])
            image = os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png")

            if no_doc:
                prompt = re.sub(r"<ui_document>", "", prompts.task_template)
            else:
                ui_doc = ""
                for i, elem in enumerate(elem_list):
                    doc_path = os.path.join(docs_dir, f"{elem.uid}.txt")
                    if not os.path.exists(doc_path):
                        continue
                    ui_doc += f"Documentation of UI element labeled with the numeric tag '{i + 1}':\n"
                    doc_content = ast.literal_eval(open(doc_path, "r").read())
                    if doc_content["tap"]:
                        ui_doc += f"This UI element is clickable. {doc_content['tap']}\n\n"
                    if doc_content["text"]:
                        ui_doc += f"This UI element can receive text input. The text input is used for the following " \
                                f"purposes: {doc_content['text']}\n\n"
                    if doc_content["long_press"]:
                        ui_doc += f"This UI element is long clickable. {doc_content['long_press']}\n\n"
                    if doc_content["v_swipe"]:
                        ui_doc += f"This element can be swiped directly without tapping. You can swipe vertically on " \
                                f"this UI element. {doc_content['v_swipe']}\n\n"
                    if doc_content["h_swipe"]:
                        ui_doc += f"This element can be swiped directly without tapping. You can swipe horizontally on " \
                                f"this UI element. {doc_content['h_swipe']}\n\n"
                print_with_color(f"Documentations retrieved for the current interface:\n{ui_doc}", "magenta")
                ui_doc = """
                You also have access to the following documentations that describes the functionalities of UI 
                elements you can interact on the screen. These docs are crucial for you to determine the target of your 
                next action. You should always prioritize these documented elements for interaction:""" + ui_doc
                prompt = re.sub(r"<ui_document>", ui_doc, prompts.task_template)
        prompt = re.sub(r"<task_description>", task_desc, prompt)
        prompt = re.sub(r"<last_act>", last_act, prompt)
        print_with_color("Thinking about what to do in the next step...", "yellow")
        status, rsp = mllm.get_model_response(prompt, [image])

        if status:
            with open(log_path, "a") as logfile:
                log_item = {"step": round_count, "prompt": prompt, "image": f"{dir_name}_{round_count}_labeled.png",
                            "response": rsp}
                logfile.write(json.dumps(log_item) + "\n")
            if grid_on:
                res = parse_grid_rsp(rsp)
            else:
                res = parse_explore_rsp(rsp)
            act_name = res[0]
            if act_name == "FINISH":
                task_complete = True
                break
            if act_name == "ERROR":
                break
            last_act = res[-1]
            res = res[:-1]
            if act_name == "tap":
                _, area = res
                tl, br = elem_list[area - 1].bbox
                x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
                ret = controller.tap(x, y)
                if ret == "ERROR":
                    print_with_color("ERROR: tap execution failed", "red")
                    break
            elif act_name == "text":
                _, input_str = res
                ret = controller.text(input_str)
                if ret == "ERROR":
                    print_with_color("ERROR: text execution failed", "red")
                    break
            elif act_name == "long_press":
                _, area = res
                tl, br = elem_list[area - 1].bbox
                x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
                ret = controller.long_press(x, y)
                if ret == "ERROR":
                    print_with_color("ERROR: long press execution failed", "red")
                    break
            elif act_name == "swipe":
                _, area, swipe_dir, dist = res
                tl, br = elem_list[area - 1].bbox
                x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
                ret = controller.swipe(x, y, swipe_dir, dist)
                if ret == "ERROR":
                    print_with_color("ERROR: swipe execution failed", "red")
                    break
            elif act_name == "grid":
                grid_on = True
            elif act_name == "tap_grid" or act_name == "long_press_grid":
                _, area, subarea = res
                x, y = area_to_xy(area, subarea)
                if act_name == "tap_grid":
                    ret = controller.tap(x, y)
                    if ret == "ERROR":
                        print_with_color("ERROR: tap execution failed", "red")
                        break
                else:
                    ret = controller.long_press(x, y)
                    if ret == "ERROR":
                        print_with_color("ERROR: tap execution failed", "red")
                        break
            elif act_name == "swipe_grid":
                _, start_area, start_subarea, end_area, end_subarea = res
                start_x, start_y = area_to_xy(start_area, start_subarea)
                end_x, end_y = area_to_xy(end_area, end_subarea)
                ret = controller.swipe_precise((start_x, start_y), (end_x, end_y))
                if ret == "ERROR":
                    print_with_color("ERROR: tap execution failed", "red")
                    break
            if act_name != "grid":
                grid_on = False
            time.sleep(configs["REQUEST_INTERVAL"])
        else:
            print_with_color(rsp, "red")
            break

    if task_complete:
        print_with_color(f"**{app} Task completed successfully**", "yellow")
        # get the last screenshot path
        last_screenshot = os.path.join(task_dir, f"{dir_name}_{round_count}.png")
        last_screenshot_labeled = os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png")
        
        # return the last screenshot with label if it exists
        return_path = last_screenshot_labeled if os.path.exists(last_screenshot_labeled) else last_screenshot
        
        print_with_color(f"**Final screenshot saved at: {return_path}**", "green")
        return return_path
    elif round_count == configs["MAX_ROUNDS"]:
        print_with_color(f"**{app} Task finished due to reaching max rounds**", "yellow")
        # return the last screenshot path even if the task is not completed
        last_screenshot = os.path.join(task_dir, f"{dir_name}_{round_count}.png")
        last_screenshot_labeled = os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png")
        
        return_path = last_screenshot_labeled if os.path.exists(last_screenshot_labeled) else last_screenshot
        
        print_with_color(f"**Final screenshot saved at: {return_path}**", "green")
        return return_path
    else:
        print_with_color(f"**{app} Task finished unexpectedly**", "red")
        # if successfully executed but not completed, return the last screenshot
        if round_count > 0:
            last_screenshot = os.path.join(task_dir, f"{dir_name}_{round_count}.png")
            last_screenshot_labeled = os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png")
            
            return_path = last_screenshot_labeled if os.path.exists(last_screenshot_labeled) else last_screenshot
            
            if os.path.exists(return_path):
                print_with_color(f"**Last available screenshot saved at: {return_path}**", "green")
                return return_path
        # no screenshot available, return the task directory
        return("No screenshots available, task directory: " + task_dir)
