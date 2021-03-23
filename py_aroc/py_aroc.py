import os
import re
import sys
import subprocess
import typing as t
from watchgod import watch

def run():
    args = _get_args_for_reloading()
    new_environ = os.environ.copy()
    exit_code = subprocess.call(args, env=new_environ, close_fds=False)

    if exit_code != 3:
        return exit_code

def _get_args_for_reloading() -> t.List[str]:
    rv = [sys.executable]
    py_script = sys.argv[0]
    args = sys.argv[1:]
    __main__ = sys.modules["__main__"]

    if getattr(__main__, "__package__", None) is None or (
        os.name == "nt"
        and __main__.__package__ == ""
        and not os.path.exists(py_script)
        and os.path.exists(f"{py_script}.exe")
    ):
        py_script = os.path.abspath(py_script)

        if os.name == "nt":
            if not os.path.exists(py_script) and os.path.exists(f"{py_script}.exe"):
                py_script += ".exe"

            if (
                os.path.splitext(sys.executable)[1] == ".exe"
                and os.path.splitext(py_script)[1] == ".exe"
            ):
                rv.pop(0)

        rv.append(py_script)
    else:
        if sys.argv[0] == "-m":
            args = sys.argv
        else:
            if os.path.isfile(py_script):
                py_module = t.cast(str, __main__.__package__)
                name = os.path.splitext(os.path.basename(py_script))[0]

                if name != "__main__":
                    py_module += f".{name}"
            else:
                py_module = py_script

            rv.extend(("-m", py_module.lstrip(".")))

    rv.extend(args)
    return rv

def start(patterns: list = ["*.py","*.pyc"], ignore_patterns: list = ["*/__pycache__/*","*/.git/*","*/venv/*"],new_line_count: int = 2):
    try:
        for changes in watch('.'):
            filePath = list(changes)[0][1].replace(os.sep,"/")
            for pattern in ignore_patterns:
                if "group" in dir(re.search(pattern.replace("*","(.+)"),filePath)):
                    continue
            
            new_lines = new_line_count*"\n"

            print(f"{new_lines}")

            sys.exit(print(run()))

    except KeyboardInterrupt:
        pass