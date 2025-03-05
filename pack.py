import shutil
import os
if os.path.exists("__temp"):
    shutil.rmtree("__temp")
os.makedirs("__temp", exist_ok=True)
for file in os.listdir("."):
    if file == "pack.py" or file == "__temp" or file.endswith(".mcdr"):
        continue
    if os.path.isdir(file):
        shutil.copytree(file, os.path.join("__temp", file))
    else:
        shutil.copy(file, "__temp")

for root, dirs, files in os.walk("__temp"):
    for dir in dirs:
        if dir == "__pycache__":
            shutil.rmtree(os.path.join(root, dir))
            break

os.chdir("__temp")
os.system("mcdreforged pack -o ../")

shutil.rmtree("__temp")