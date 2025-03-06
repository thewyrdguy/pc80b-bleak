from os import path
from subprocess import call
from shutil import which
from unittest import main, expectedFailure, TestCase

CONF = path.join(path.dirname(__file__), "pylint.conf")


class LintCheck(TestCase):
    @expectedFailure  # TODO enable later
    def test_pylint(self) -> None:
        if not which("pylint"):
            self.fail("pylint not installed.")
        cmd = [
            "pylint",
            "--rcfile",
            CONF,
            "--",
            # "--strict",
            "pc80b_bleak",
            "test",
        ]
        self.assertEqual(call(cmd), 0, "lint check")


if __name__ == "__main__":
    main()
