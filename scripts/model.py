import re
from abc import abstractmethod
from typing import List
from http import HTTPStatus

import requests
import dashscope
import json

from utils import print_with_color, encode_image


class BaseModel:
    def __init__(self):
        pass    

    @abstractmethod
    def get_model_response(self, prompt: str, images: List[str]) -> (bool, str):
        pass


class OpenAIModel(BaseModel):
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float, max_tokens: int):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def get_model_response(self, prompt: str, images: List[str]) -> (bool, str):
        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]
        for img in images:
            base64_img = encode_image(img)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_img}"
                }
            })
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        response = requests.post(self.base_url, headers=headers, json=payload).json()
        if "error" not in response:
            usage = response["usage"]
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
            print_with_color(f"Request cost is "
                             f"\${'{0:.2f}'.format(prompt_tokens / 1000 * 0.01 + completion_tokens / 1000 * 0.03)}",
                             "yellow")
        else:
            return False, response["error"]["message"]
        return True, response["choices"][0]["message"]["content"]

    def get_main_response(self, prompt: str)-> (bool, str):
        # get response for main task
        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content":content
                }
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        response = requests.post(self.base_url, headers=headers, json=payload).json()
        if "error" in response:
            return False, response["error"]["message"]
        else:
            usage = response["usage"]["prompt_tokens"] + response["usage"]["completion_tokens"]
            print(f"Tokens consumed:{usage}")
            return True, response["choices"][0]["message"]["content"]


def parse_explore_rsp(rsp):
    try:
        # check if the response is a JSON string
        if rsp.strip().startswith('{') and rsp.strip().endswith('}'):
            try:
                # try to parse the response as JSON
                data = json.loads(rsp)
                observation = data.get("Observation", "")
                think = data.get("Thought", "")
                act = data.get("Action", "")
                last_act = data.get("Summary", "")
            except json.JSONDecodeError:
                # if parsing fails, fall back to regex
                observation = re.findall(r"Observation: (.*?)$", rsp, re.MULTILINE)[0]
                think = re.findall(r"Thought: (.*?)$", rsp, re.MULTILINE)[0]
                act = re.findall(r"Action: (.*?)$", rsp, re.MULTILINE)[0]
                last_act = re.findall(r"Summary: (.*?)$", rsp, re.MULTILINE)[0]
        else:
            # use the original regex method
            observation = re.findall(r"Observation: (.*?)$", rsp, re.MULTILINE)[0]
            think = re.findall(r"Thought: (.*?)$", rsp, re.MULTILINE)[0]
            act = re.findall(r"Action: (.*?)$", rsp, re.MULTILINE)[0]
            last_act = re.findall(r"Summary: (.*?)$", rsp, re.MULTILINE)[0]
        
        print_with_color("+ Observation:", "yellow")
        print_with_color(observation, "magenta")
        print_with_color("+ Thought:", "yellow")
        print_with_color(think, "magenta")
        print_with_color("+ Action:", "yellow")
        print_with_color(act, "magenta")
        print_with_color("+ Summary:", "yellow")
        print_with_color(last_act, "magenta")
        
        if "FINISH" in act:
            return ["FINISH"]
        act_name = act.split("(")[0]
        # process the act string to remove unwanted characters and spaces
        act_name = act_name.replace("`", "").replace("*", "").replace(" ", "")
        if act_name == "tap":
            area = int(re.findall(r"tap\((.*?)\)", act)[0])
            return [act_name, area, last_act]
        elif act_name == "text":
            input_str = re.findall(r"text\((.*?)\)", act)[0][1:-1]
            return [act_name, input_str, last_act]
        elif act_name == "long_press":
            area = int(re.findall(r"long_press\((.*?)\)", act)[0])
            return [act_name, area, last_act]
        elif act_name == "swipe":
            params = re.findall(r"swipe\((.*?)\)", act)[0]
            area, swipe_dir, dist = params.split(",")
            area = int(area)
            swipe_dir = swipe_dir.strip()[1:-1]
            dist = dist.strip()[1:-1]
            return [act_name, area, swipe_dir, dist, last_act]
        elif act_name == "grid":
            return [act_name]
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(f"ERROR: an exception occurs while parsing the model response: {e}", "red")
        print_with_color(rsp, "red")
        return ["ERROR"]

def parse_main_rsp(rsp):
    try:
        answer = re.findall(r"Answer: (.*?)$", rsp, re.MULTILINE)[0]
        app = re.findall(r"App: (.*?)$", rsp, re.MULTILINE)[0]
        subtasks = re.findall(r"Subtasks: (.*?)$", rsp, re.MULTILINE)[0]
        print_with_color(f"Answer: {answer}", "yellow")
        print_with_color(f"App: {app}", "yellow")
        print_with_color(f"Subtasks: {subtasks}", "yellow")
        print_with_color(f"The type of subtasks is {type(subtasks)}", "yellow")
        if app == "None":
            subtasks = []
            return [answer]
        else:
            return [answer, app, subtasks]
    except Exception as e:
        print_with_color(f"ERROR: an exception occurs while parsing the model response: {e}", "red")
        print_with_color(rsp, "red")
        return ["ERROR"]


def parse_grid_rsp(rsp):
    try:
        observation = re.findall(r"Observation: (.*?)$", rsp, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", rsp, re.MULTILINE)[0]
        act = re.findall(r"Action: (.*?)$", rsp, re.MULTILINE)[0]
        last_act = re.findall(r"Summary: (.*?)$", rsp, re.MULTILINE)[0]
        print_with_color("Observation:", "yellow")
        print_with_color(observation, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        print_with_color("Action:", "yellow")
        print_with_color(act, "magenta")
        print_with_color("Summary:", "yellow")
        print_with_color(last_act, "magenta")
        if "FINISH" in act:
            return ["FINISH"]
        act_name = act.split("(")[0]
        # process the act string to remove unwanted characters and spaces
        act_name = act_name.replace("`", "").replace("*", "").replace(" ", "")
        if act_name == "tap":
            params = re.findall(r"tap\((.*?)\)", act)[0].split(",")
            area = int(params[0].strip())
            subarea = params[1].strip()[1:-1]
            return [act_name + "_grid", area, subarea, last_act]
        elif act_name == "long_press":
            params = re.findall(r"long_press\((.*?)\)", act)[0].split(",")
            area = int(params[0].strip())
            subarea = params[1].strip()[1:-1]
            return [act_name + "_grid", area, subarea, last_act]
        elif act_name == "swipe":
            params = re.findall(r"swipe\((.*?)\)", act)[0].split(",")
            start_area = int(params[0].strip())
            start_subarea = params[1].strip()[1:-1]
            end_area = int(params[2].strip())
            end_subarea = params[3].strip()[1:-1]
            return [act_name + "_grid", start_area, start_subarea, end_area, end_subarea, last_act]
        elif act_name == "grid":
            return [act_name]
        else:
            print_with_color(f"ERROR:  {act_name}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(f"ERROR: an exception occurs while parsing the model response: {e}", "red")
        print_with_color(rsp, "red")
        return ["ERROR"]

def parse_reflect_rsp(rsp):
    try:
        decision = re.findall(r"Decision: (.*?)$", rsp, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", rsp, re.MULTILINE)[0]

        # clean the decision string
        cleaned_decision = decision.strip().replace("**","")

        print_with_color("Decision:", "yellow")
        print_with_color(cleaned_decision, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        if cleaned_decision == "INEFFECTIVE":
            return [cleaned_decision, think]
        elif cleaned_decision == "BACK" or cleaned_decision == "CONTINUE" or cleaned_decision == "SUCCESS":
            doc = re.findall(r"Documentation: (.*?)$", rsp, re.MULTILINE)[0]
            print_with_color("Documentation:", "yellow")
            print_with_color(doc, "magenta")
            return [cleaned_decision, think, doc]
        else:
            print_with_color(f"ERROR: Undefined decision {cleaned_decision}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(f"ERROR: an exception occurs while parsing the model response: {e}", "red")
        print_with_color(rsp, "red")
        return ["ERROR"]
