import unittest

from main.progress import set_progress


class FakeProgressBar:
    """Behaves like QProgressBar.setValue(int): rejects anything that is not an int."""

    def __init__(self):
        self.value = None

    def setValue(self, value):
        if not isinstance(value, int):
            raise TypeError("setValue(self, value: int): argument 1 has unexpected type '%s'" % type(value).__name__)
        self.value = value


class SetProgressTest(unittest.TestCase):
    def test_float_from_a_task_is_cast_to_int(self):
        bar = FakeProgressBar()
        set_progress(bar, 37.5)
        self.assertEqual(bar.value, 37)

    def test_int_is_passed_through(self):
        bar = FakeProgressBar()
        set_progress(bar, 100)
        self.assertEqual(bar.value, 100)


if __name__ == "__main__":
    unittest.main()
