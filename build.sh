python3 -m venv .venv

. .venv/bin/activate

pip install --upgrade pip
python -m pip install fake-bpy-module

pip freeze > requirements.txt

source .venv/bin/activate