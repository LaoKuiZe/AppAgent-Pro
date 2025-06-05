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

def generate_auto_docs(app, task_desc, task_dir, dir_name, log_path, mllm, configs):
    """
    Generate automatic documentation based on task execution process
    """
    print_with_color("Starting automatic document generation...", "yellow")
    
    # Create demo_docs directory (changed to demo_docs instead of auto_docs)
    app_dir = os.path.join("./apps", app)
    demo_docs_dir = os.path.join(app_dir, "demo_docs")
    if not os.path.exists(demo_docs_dir):
        os.makedirs(demo_docs_dir)
        print_with_color(f"Created new demo_docs directory: {demo_docs_dir}", "green")
    
    doc_count = 0
    
    # Check if log file exists
    if not os.path.exists(log_path):
        print_with_color("Log file does not exist, cannot generate documentation", "red")
        return 0
    
    try:
        with open(log_path, "r") as logfile:
            lines = logfile.readlines()
            
        for i, line in enumerate(lines):
            try:
                log_item = json.loads(line.strip())
                step = log_item["step"]
                response = log_item["response"]
                elem_uid = log_item.get("elem_uid")  # Get element uid
                
                # Parse response to get action information
                if "grid" in log_item["image"]:
                    res = parse_grid_rsp(response)
                else:
                    res = parse_explore_rsp(response)
                
                if not res or res[0] == "ERROR" or res[0] == "FINISH":
                    continue
                    
                act_name = res[0]
                
                # Generate documentation based on action type
                if act_name in ["tap", "long_press", "swipe", "text"]:
                    # Only process cases with elem_uid (non-grid mode)
                    if not elem_uid and act_name != "text":
                        continue
                        
                    # Get before and after screenshots
                    img_before = os.path.join(task_dir, f"{dir_name}_{step}_labeled.png")
                    img_after = os.path.join(task_dir, f"{dir_name}_{step + 1}_labeled.png")
                    
                    # Check if screenshots exist
                    if not os.path.exists(img_before) or not os.path.exists(img_after):
                        continue
                    
                    # Extract action parameters
                    action_param = None
                    
                    if act_name == "tap":
                        _, area = res[:-1]
                        action_param = str(area)
                    elif act_name == "long_press":
                        _, area = res[:-1]
                        action_param = str(area)
                    elif act_name == "text":
                        _, input_str = res[:-1]
                        action_param = f"text_input:sep:{input_str}"
                        # For text actions, if no elem_uid, use default name
                        if not elem_uid:
                            elem_uid = "text_input"
                    elif act_name == "swipe":
                        _, area, swipe_dir, dist = res[:-1]
                        action_param = f"{area}:sep:{swipe_dir}"
                        if swipe_dir in ["up", "down"]:
                            act_name = "v_swipe"
                        elif swipe_dir in ["left", "right"]:
                            act_name = "h_swipe"
                    
                    if not action_param or not elem_uid:
                        continue
                    
                    # Generate documentation prompt
                    prompt = None
                    if act_name == "tap":
                        prompt = re.sub(r"<ui_element>", action_param, prompts.tap_doc_template)
                    elif act_name == "text":
                        input_area, input_text = action_param.split(":sep:")
                        prompt = re.sub(r"<ui_element>", input_area, prompts.text_doc_template)
                    elif act_name == "long_press":
                        prompt = re.sub(r"<ui_element>", action_param, prompts.long_press_doc_template)
                    elif act_name in ["v_swipe", "h_swipe"]:
                        swipe_area, swipe_dir = action_param.split(":sep:")
                        prompt = re.sub(r"<swipe_dir>", swipe_dir, prompts.swipe_doc_template)
                        prompt = re.sub(r"<ui_element>", swipe_area, prompt)
                    
                    if not prompt:
                        continue
                        
                    prompt = re.sub(r"<task_desc>", task_desc, prompt)
                    
                    # Document file path (changed to demo_docs directory)
                    doc_name = f"{elem_uid}.txt"
                    doc_path = os.path.join(demo_docs_dir, doc_name)
                    
                    # Check if document already exists
                    doc_content = {
                        "tap": "",
                        "text": "",
                        "v_swipe": "",
                        "h_swipe": "",
                        "long_press": ""
                    }
                    
                    if os.path.exists(doc_path):
                        try:
                            doc_content = ast.literal_eval(open(doc_path).read())
                            if doc_content.get(act_name):
                                print_with_color(f"Document for element {elem_uid} {act_name} already exists, skipping", "yellow")
                                continue
                        except:
                            pass
                    
                    print_with_color(f"Generating document for element {elem_uid} {act_name}...", "yellow")
                    
                    # Call model to generate document
                    status, rsp = mllm.get_model_response(prompt, [img_before, img_after])
                    
                    if status:
                        doc_content[act_name] = rsp
                        with open(doc_path, "w") as outfile:
                            outfile.write(str(doc_content))
                        doc_count += 1
                        print_with_color(f"Document generated and saved to {doc_path}", "green")
                    else:
                        print_with_color(f"Document generation failed: {rsp}", "red")
                    
                    time.sleep(configs["REQUEST_INTERVAL"])
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print_with_color(f"Error processing step {i+1}: {str(e)}", "red")
                continue
                
    except Exception as e:
        print_with_color(f"Error reading log file: {str(e)}", "red")
        return 0
    
    print_with_color(f"Document generation completed, {doc_count} documents generated to demo_docs directory", "green")
    return doc_count

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
        task_desc += "IMPORTANT: You should open the first video excpet the advirtisement and stop after openning it. Remember you need to open a specific video page at the end. You need to provide a concise search keyword!"
    elif app.lower() == "amazon":
        task_desc += "IMPORTANT: You should open the first product except the advirtisement and stop after openning it. You need to provide a concise search keyword or you won't get any results!"

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

    # Initialize recording parameters
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

    # Start running agent
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
            
            # Get element uid for document generation (moved here, after act_name definition)
            elem_uid = None
            if act_name in ["tap", "long_press", "swipe"] and not grid_on:
                if len(res) >= 2:
                    _, area = res[:2]
                    if area <= len(elem_list):
                        elem_uid = elem_list[area - 1].uid
            
            # Update log file, add elem_uid information
            if elem_uid:
                # Rewrite log, include elem_uid
                with open(log_path, "r") as f:
                    lines = f.readlines()
                if lines:
                    # Parse last line and add elem_uid
                    last_log = json.loads(lines[-1].strip())
                    last_log["elem_uid"] = elem_uid
                    lines[-1] = json.dumps(last_log) + "\n"
                    # Rewrite file
                    with open(log_path, "w") as f:
                        f.writelines(lines)
            
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
        
        # Check if automatic document generation is enabled
        if configs.get("AUTO_DOC_GENERATION", False):
            # Generate task documentation
            print_with_color("Starting automatic document generation...", "cyan")
            try:
                doc_count = generate_auto_docs(app, task_desc, task_dir, dir_name, log_path, mllm, configs)
                if doc_count > 0:
                    print_with_color(f"Successfully generated {doc_count} documents, saved in apps/{app}/demo_docs/ directory", "green")
                else:
                    print_with_color("No documents generated", "yellow")
            except Exception as e:
                print_with_color(f"Error occurred during document generation: {str(e)}", "red")
        else:
            print_with_color("Automatic document generation disabled (AUTO_DOC_GENERATION: false)", "yellow")
        
        # get the last screenshot path
        last_screenshot = os.path.join(task_dir, f"{dir_name}_{round_count}.png")
        last_screenshot_labeled = os.path.join(task_dir, f"{dir_name}_{round_count}_labeled.png")
        
        # return the last screenshot with label if it exists
        return_path = last_screenshot_labeled if os.path.exists(last_screenshot_labeled) else last_screenshot
        
        print_with_color(f"**Final screenshot saved at: {return_path}**", "green")
        return return_path
    elif round_count == configs["MAX_ROUNDS"]:
        print_with_color(f"**{app} Task finished due to reaching max rounds**", "yellow")
        
        # Check if automatic document generation is enabled
        if configs.get("AUTO_DOC_GENERATION", False):
            # Even if the task is not completed, generate documentation
            print_with_color("Task reached max rounds, still attempting to generate partial documentation...", "cyan")
            try:
                doc_count = generate_auto_docs(app, task_desc, task_dir, dir_name, log_path, mllm, configs)
                if doc_count > 0:
                    print_with_color(f"Successfully generated {doc_count} documents, saved in apps/{app}/demo_docs/ directory", "green")
                else:
                    print_with_color("No documents generated", "yellow")
            except Exception as e:
                print_with_color(f"Error occurred during document generation: {str(e)}", "red")
        else:
            print_with_color("Automatic document generation disabled (AUTO_DOC_GENERATION: false)", "yellow")
        
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
