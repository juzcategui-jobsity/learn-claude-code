"""
Graba la sesion de una leccion en evidence/<leccion>.txt (salida + lo que escribes).

Uso (desde la raiz del repo, con el venv activo):
    python record.py s01
    python record.py s16 demo        # argumentos extra se pasan a la leccion

El log incluye fecha, comando y todo lo que aparece en pantalla, sin colores ANSI.
"""
import builtins
import datetime
import pathlib
import re
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|[\x01\x02]")


def find_lesson(key: str) -> pathlib.Path:
    key = key.lower().strip("/\\")
    matches = sorted(p for p in ROOT.glob("s[0-9][0-9]_*") if p.is_dir()
                     and (p.name == key or p.name.split("_")[0] == key))
    if not matches:
        sys.exit(f"No encuentro la leccion '{key}'. Usa por ejemplo: s01")
    return matches[0]


class Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(ANSI.sub("", text))
        self.log.flush()
        return len(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def windows_shims():
    """s13 y s16 usan fcntl y select sobre stdin, que no existen en Windows.
    Esto los sustituye solo dentro de esta grabacion; el codigo del curso no se toca."""
    import select
    import time
    import types

    if "fcntl" not in sys.modules:
        fake = types.ModuleType("fcntl")
        fake.LOCK_SH, fake.LOCK_EX, fake.LOCK_NB, fake.LOCK_UN = 1, 2, 4, 8
        fake.flock = lambda *args, **kwargs: None
        sys.modules["fcntl"] = fake

    real_select = select.select

    def select_with_stdin(rlist, wlist, xlist, timeout=None):
        if any(getattr(s, "fileno", lambda: -1)() == 0 for s in rlist):
            import msvcrt
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                if msvcrt.kbhit():
                    return [sys.stdin], [], []
                if deadline is not None and time.monotonic() >= deadline:
                    return [], [], []
                time.sleep(0.05)
        return real_select(rlist, wlist, xlist, timeout)

    select.select = select_with_stdin


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    lesson = find_lesson(sys.argv[1])
    extra = sys.argv[2:]
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    suffix = ("_" + "_".join(extra)) if extra else ""
    log_path = evidence / f"{lesson.name}{suffix}.txt"

    log = open(log_path, "a", encoding="utf-8")
    log.write(f"\n===== {lesson.name} | {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    log.write(f"$ python {lesson.name}/code.py {' '.join(extra)}\n\n")
    log.flush()

    real_input = builtins.input

    def logged_input(prompt=""):
        clean = ANSI.sub("", str(prompt))
        tee, sys.stdout = sys.stdout, sys.__stdout__
        tin, sys.stdin = sys.stdin, sys.__stdin__
        try:
            answer = real_input(prompt)
        finally:
            sys.stdout, sys.stdin = tee, tin
        log.write(f"{clean}{answer}\n")
        log.flush()
        return answer

    class StdinTee:
        """s13 lee con sys.stdin.readline() en vez de input(); tambien se graba."""
        def __init__(self, stream):
            self.stream = stream

        def readline(self, *args):
            line = self.stream.readline(*args)
            log.write(line if line.endswith("\n") else line + "\n")
            log.flush()
            return line

        def __getattr__(self, name):
            return getattr(self.stream, name)

    if sys.platform == "win32":
        windows_shims()

    builtins.input = logged_input
    sys.stdin = StdinTee(sys.__stdin__)
    sys.stdout = Tee(sys.__stdout__, log)
    sys.stderr = Tee(sys.__stderr__, log)
    sys.argv = [str(lesson / "code.py"), *extra]
    try:
        runpy.run_path(str(lesson / "code.py"), run_name="__main__")
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
        log.write(f"\n===== fin {datetime.datetime.now():%H:%M:%S} =====\n")
        log.close()
        print(f"\nEvidencia guardada en {log_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
