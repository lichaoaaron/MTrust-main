import yaml
from pathlib import Path


class SpecLoader:

    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def load_yaml(self, path):
        with open(self.base_path / path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_scenario(self, scenario_path):
        return self.load_yaml(scenario_path)