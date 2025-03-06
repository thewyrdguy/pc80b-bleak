from subprocess import call
from shutil import which
from unittest import main, TestCase


class BlackCheck(TestCase):
    def test_black(self) -> None:
        if not which("black"):
            self.fail(f"black not installed.")
        cmd = ["black", "--check", "--diff", "-l", "79", "pc80b_bleak", "test"]
        self.assertEqual(call(cmd), 0, "black found bad formatting")


if __name__ == "__main__":
    main()
