import os
import sys

from dotenv import load_dotenv

d = os.path.basename(__file__)
sys.path.insert(0, d)

dotenv_path = os.path.join(os.path.dirname(__file__), "eth.env")
load_dotenv(dotenv_path)
