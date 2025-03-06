from subprocess import call
from shutil import which
from unittest import main, TestCase


class TypeCheck(TestCase):
    def test_mypy(self) -> None:
        if not which("mypy"):
            self.fail("mypy not installed.")
        cmd = [
            "mypy",
            "--cache-dir",
            "/dev/null",
            # "--strict",
            "pc80b_bleak",
            "test",
        ]
        self.assertEqual(call(cmd), 0, "mypy typecheck")


if __name__ == "__main__":
    main()
