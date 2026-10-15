"""CheeseStickTrainer entry point:  python main.py [path\to\th4sp_0.ssv]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cheesestick.app import run

if __name__ == "__main__":
    sys.exit(run())
