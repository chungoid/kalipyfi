import os
from pathlib import Path
import jinja2
from config.constants import UI_DIR, MAIN_UI_YAML

def main():
    # Load the YAML template: utils/ui/tmuxp/main_tmuxp.yaml.
    with open(MAIN_UI_YAML, "r") as f:
        template_str = f.read()

    # Render templates with path variables
    template = jinja2.Template(template_str)
    rendered_yaml = template.render(UI_DIR=str(UI_DIR.resolve()))

    # Write the rendered YAML to a temporary file.
    tmp_yaml = Path("/tmp/kalipifi_main.yaml")
    with open(tmp_yaml, "w") as f:
        f.write(rendered_yaml)

    # Launch the tmux session
    os.system(f"tmuxp load {tmp_yaml}")

if __name__ == '__main__':
    main()
