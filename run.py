#!/usr/bin/env python3
"""mubsir - one command to install and run.

    python run.py                 open the page in a browser, drag files in
    python run.py book.pdf        convert a file straight to Word
    python run.py --demo          measure the tool against the bundled pages
    python run.py --test          run the test suite

The first run installs everything: a private Python, the dependencies,
Tesseract, and the models. All of it lands inside your home folder and this
directory - **no administrator rights are needed anywhere**, which is the point,
because the machines this is for are locked down.

This file replaces four platform-specific shell scripts. It is written to run on
whatever Python is already on the machine, so it uses nothing outside the
standard library and re-executes itself inside the private environment once that
exists.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
TESS = os.path.join(ROOT, ".mm-tess")
WINDOWS = platform.system() == "Windows"

VENV_PY = os.path.join(VENV, "Scripts", "python.exe") if WINDOWS \
    else os.path.join(VENV, "bin", "python")
LOCAL_BIN = os.path.join(os.path.expanduser("~"), ".local", "bin")
MM_HOME = os.path.join(os.path.expanduser("~"), ".local", "mm")


def say(step: str, msg: str) -> None:
    print(f"[{step}] {msg}", flush=True)


def run(cmd, **kw) -> int:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([LOCAL_BIN, MM_HOME, env.get("PATH", "")])
    return subprocess.call(cmd, env=env, **kw)


def which(name: str):
    env_path = os.pathsep.join([LOCAL_BIN, MM_HOME, os.environ.get("PATH", "")])
    return shutil.which(name, path=env_path)


# --------------------------------------------------------------------- setup
def ensure_uv() -> str:
    uv = which("uv")
    if uv:
        return uv
    say("1/4", "installing uv (into your home folder, no admin needed)")
    if WINDOWS:
        run(["powershell", "-ExecutionPolicy", "ByPass", "-c",
             "irm https://astral.sh/uv/install.ps1 | iex"])
    else:
        with urllib.request.urlopen("https://astral.sh/uv/install.sh", timeout=120) as r:
            script = r.read()
        p = subprocess.Popen(["sh"], stdin=subprocess.PIPE)
        p.communicate(script)
    uv = which("uv")
    if not uv:
        sys.exit("could not install uv; see https://docs.astral.sh/uv/")
    return uv


def ensure_env(uv: str) -> None:
    if os.path.exists(VENV_PY):
        return
    say("2/4", "installing Python 3.11 and the dependencies")
    run([uv, "python", "install", "3.11"])
    run([uv, "venv", "--python", "3.11", VENV])
    req = os.path.join(ROOT, "requirements.txt")
    if run([uv, "pip", "install", "--python", VENV, "-r", req]) != 0:
        sys.exit("dependency install failed")


def ensure_tesseract() -> None:
    """Tesseract is a binary, so it comes from conda-forge via micromamba.

    That is what makes 'no admin rights' true on Windows as well: micromamba is
    a single executable and the environment lives in this directory.
    """
    exe = os.path.join(TESS, "Library", "bin", "tesseract.exe") if WINDOWS \
        else os.path.join(TESS, "bin", "tesseract")
    if os.path.exists(exe):
        return
    say("3/4", "installing Tesseract (user-local, no admin needed)")
    mm = os.path.join(MM_HOME, "micromamba.exe" if WINDOWS else "bin/micromamba")
    if not os.path.exists(mm):
        os.makedirs(MM_HOME, exist_ok=True)
        if WINDOWS:
            run(["powershell", "-ExecutionPolicy", "ByPass", "-c",
                 "Invoke-WebRequest -Uri https://micro.mamba.pm/api/micromamba/win-64/latest"
                 f" -OutFile $env:TEMP\\mm.tar.bz2; tar -xf $env:TEMP\\mm.tar.bz2"
                 f" -C '{MM_HOME}' Library/bin/micromamba.exe;"
                 f" Move-Item -Force '{MM_HOME}\\Library\\bin\\micromamba.exe' '{mm}'"])
        else:
            plat = "osx" if platform.system() == "Darwin" else "linux"
            arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "64"
            url = f"https://micro.mamba.pm/api/micromamba/{plat}-{arch}/latest"
            run(f"curl -Ls {url} | tar -xj -C '{MM_HOME}' bin/micromamba", shell=True)
    if os.path.exists(mm):
        env = dict(os.environ, MAMBA_ROOT_PREFIX=MM_HOME)
        subprocess.call([mm, "create", "-y", "-q", "-p", TESS,
                         "-c", "conda-forge", "tesseract"], env=env)
    if not os.path.exists(exe):
        print("  note: Tesseract could not be installed. The tool still runs on"
              " its pure-Python recogniser, less accurately.")


def ensure_models() -> None:
    marker = os.path.join(ROOT, "mubsir", "models", "tessdata_best", "ara.traineddata")
    if os.path.exists(marker):
        return
    say("4/4", "downloading the models and wordlists (once, about 55 MB)")
    run([VENV_PY, "-m", "mubsir.fetch_models"], cwd=ROOT)


def setup() -> None:
    if os.path.exists(VENV_PY) and os.path.exists(
            os.path.join(ROOT, "mubsir", "models", "tessdata_best", "ara.traineddata")):
        return
    print("First run: setting this up once. It needs no administrator rights.\n")
    uv = ensure_uv()
    ensure_env(uv)
    ensure_tesseract()
    ensure_models()
    print("\nSetup complete.\n")


# ---------------------------------------------------------------------- main
def main() -> int:
    args = sys.argv[1:]
    setup()

    # Re-execute inside the private environment, where the dependencies live.
    if os.path.abspath(sys.executable) != os.path.abspath(VENV_PY) \
            and os.path.exists(VENV_PY):
        return subprocess.call([VENV_PY, os.path.abspath(__file__)] + args, cwd=ROOT)

    if args and args[0] == "--test":
        return subprocess.call([sys.executable, "-m", "pytest", "mubsir/tests", "-q"], cwd=ROOT)
    if args and args[0] == "--demo":
        return subprocess.call([sys.executable, "mubsir/demo/run_demo.py"], cwd=ROOT)

    sys.path.insert(0, ROOT)
    if args:
        from mubsir.cli import main as cli
        return cli(args)
    from mubsir.webui import serve
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
