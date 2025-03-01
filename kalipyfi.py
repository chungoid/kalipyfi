import logging
import os
import jinja2
from pathlib import Path
from common.logging_setup import setup_logging
from config.constants import UI_DIR, MAIN_UI_YAML_PATH


def main():
    setup_logging()
    # Load the YAML template: utils/ui/tmuxp/main_tmuxp.yaml.
    with open(MAIN_UI_YAML_PATH, "r") as f:
        template_str = f.read()

    # Render templates with path variables
    template = jinja2.Template(template_str)
    rendered_yaml = template.render(UI_DIR=str(UI_DIR.resolve()))

    # Write the rendered YAML to a temporary file.
    tmp_yaml = Path("/tmp/kaliyifi_main.yaml")
    with open(tmp_yaml, "w") as f:
        f.write(rendered_yaml)

    # Launch the tmux session
    os.system(f"tmuxp load {tmp_yaml}")

if __name__ == '__main__':
    main()
