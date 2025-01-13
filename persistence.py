import os
import sys
import xml.etree.ElementTree as ET
import uuid
import itertools
from copy import deepcopy


class Persistence:
    FILE_NAME = "TTBereinH5AllHeroes.ini"
    CHK_NAME = "TTBereinAllHeroes.chk"
    VERSION = "0.01"

    def __init__(self):
        if os.path.isfile(Persistence.FILE_NAME):
            with open(Persistence.FILE_NAME) as fp:
                contents = tuple(line.rstrip() for line in fp)
        else:
            contents = ("", "True", "300,10", "1150,10")

        self.last_path = contents[0]
        self.show_log = True if contents[1] == "True" else False
        self.main_x, self.main_y = [int(i) for i in contents[2].split(",")]
        self.log_x, self.log_y = [int(i) for i in contents[3].split(",")]
        self.rc_path = ""
        self._artificer_artefact_names = {}

        self._get_resource_path()

    def save(self):
        contents = (self.last_path, self.show_log,
                    f"{self.main_x},{self.main_y}",
                    f"{self.log_x},{self.log_y}")

        with open(Persistence.FILE_NAME, 'w') as fp:
            for i in contents:
                fp.write(f"{i}\n")

    def get_about_txt(self):
        return open(self._get_file("About.txt")).read()

    def get_xml(self, xml_name):
        return open(self._get_file(xml_name)).read()

    def get_7za(self):
        return self._get_file("7z.exe")

    def get_ico(self):
        return self._get_file("BlackDragon.ico")

    def _get_resource_path(self):
        try:
            self.rc_path = sys._MEIPASS
        except Exception:
            self.rc_path = os.path.abspath(".")

    def _get_file(self, file_name):
        result = os.path.join(self.rc_path, file_name)
        if os.path.isfile(result):
            return result
        else:
            raise FileNotFoundError(result)


per = Persistence()
