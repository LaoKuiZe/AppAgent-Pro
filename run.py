import argparse
import os

from scripts.utils import print_with_color

arg_desc = "AppAgent - deployment phase"
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=arg_desc)
parser.add_argument("--app")
parser.add_argument("--root_dir", default="./")
args = vars(parser.parse_args())

root_dir = args["root_dir"]

print_with_color("Welcome to the deployment phase of AppAgent-Pro!\nProvide a task description, and I'll proactively complete it for you — no further input needed.", "yellow")

os.system(f"python scripts/task_executor.py --root_dir {root_dir}")