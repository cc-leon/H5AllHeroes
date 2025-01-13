import logging
from zipfile import ZipFile

from gui import MainWnd
from tkinter import font


def main():
    logging.basicConfig(level=logging.INFO, filename="TTBereinH5AllHeroes.log", filemode="w",
                        encoding="utf_16", format="%(message)s")

    main_window = MainWnd()
    main_window.mainloop()


if __name__ == "__main__":
    main()
