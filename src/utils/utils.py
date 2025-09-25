import importlib
import os
from pathlib import Path


def import_all_models():
    project_root = Path(__file__).resolve().parent.parent
    models_dir = project_root / "models"
    for file in os.listdir(models_dir):
        if file.endswith(".py") and file != "__init__.py":
            module_name = f"models.{file[:-3]}"
            importlib.import_module(module_name)
