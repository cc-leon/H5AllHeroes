import logging
import os
import xml.etree.ElementTree as ET
from collections import namedtuple
from copy import deepcopy
from time import time
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED
from threading import Lock
from tempfile import NamedTemporaryFile
from dataclasses import dataclass
import subprocess

from persistence import per


# Global and game info
MapsStatusClass = namedtuple("MapsStatusClass", ["all_heroes", "all_spells_artefacts", "racial_ability_boost"])
MapsStatusNames = ("全英雄Mod", "全魔法全宝物Mod", "种族能力增强Mod")
HeroesStatusClass = namedtuple("HeroesStatusClass", ["racial_ability_boost", ])
CreatureInfoClass = namedtuple("CreatureInfoClass", ["name", "cost"])
HeroesStatusNames = ("种族能力增强mod", )
PATCH_FILE_NAME = "TTBereinMergedPatch.h5u"
TOWN_VALUE = { 
    "TOWN_HEAVEN" : 0, "TOWN_PRESERVE" : 1,  "TOWN_ACADEMY" : 2, "TOWN_DUNGEON" : 3, "TOWN_NECROMANCY" : 4,
    "TOWN_INFERNO" : 5, "TOWN_FORTRESS" : 6, "TOWN_STRONGHOLD" : 7, "TOWN_NEUTRAL" : 8, }


def remove_merged_patch():
    merged_patch = os.path.join(per.last_path, "UserMODs", PATCH_FILE_NAME)
    if os.path.isfile(merged_patch):
        try:
            os.remove(merged_patch)
            return merged_patch, True
        except PermissionError:
            err_msg = f"无法移除{merged_patch}。\n请检查游戏或者地图编辑器是否正在运行，如果是的话请关闭游戏或者地图编辑器。"
            raise PermissionError(err_msg)

    return merged_patch, False


@dataclass(frozen=True)
class CreatureInfo:
    town: str
    cost: int
    text: str
    tier: int
    upgrades: tuple[str, str]


@dataclass(frozen=False)
class SpecializationInfo:
    name: str
    cost: int
    text: str
    tier: int
    upgrades: tuple[str, str]


class RawData:
    DIRS = {"data": ".pak", "UserMods": ".h5u", "Maps": ".h5m"}
    PREFIX_FILTERS = ("ttberein/", "mapobjects/", )
    SUFFIX_FILTERS = (".xdb", ".chk", ".lua", ".txt")

    def __init__(self, h5_path: str):
        self.h5_path = h5_path
        self.zip_q = None
        self.manifest = None
        self.tree = None
        self.curr_stage = "估计中"
        self.curr_prog = 0
        self.total_prog = 1
        self.lock = Lock()

    def run(self):
        self._gen_stats()
        self._build_zip_list()

    def _gen_stats(self):
        with self.lock:
            self.total_prog = 0

        for folder, file_suf in RawData.DIRS.items():
            fullpath = os.path.join(self.h5_path, folder)
            if os.path.isdir(fullpath):
                self.total_prog += len(tuple(f for f in os.listdir(fullpath)
                                             if f.lower().endswith(file_suf)
                                             and PATCH_FILE_NAME.lower() not in f.lower())) + 1
            elif folder.lower() == "data":
                raise ValueError(f"\"{self.h5_path}\"中没有找到\"{folder}\"，\n请检查是否是正确的英雄无敌5安装文件夹")

    def _build_zip_list(self):
        self.manifest = {}
        self.zip_q = {}
        self.curr_prog = 0
        prev_timeit = time()
        logging.info(f"开始对\"{self.h5_path}\"的所有游戏数据文件扫描……")

        zfs = []
        zis = []
        self.zip_q = {}
        for folder, file_suf in RawData.DIRS.items():
            fullpath = os.path.join(self.h5_path, folder)
            if not os.path.isdir(fullpath):
                continue
            with self.lock:
                self.curr_stage = f"正在扫描\"{folder}\"文件夹"
            for f in os.listdir(fullpath):

                fullname = os.path.join(fullpath, f)
                if os.path.isfile(fullname) and fullname.lower().endswith(file_suf) and \
                    PATCH_FILE_NAME.lower() not in f.lower():
                    zfs.append(fullname)
                    try:
                        zip_file_fp = ZipFile(fullname)
                        self.zip_q[fullname] = zip_file_fp
                        zis.append(zip_file_fp.infolist())
                    except BadZipFile:
                        logging.info(f"  {folder}中的{f}并不是有效的压缩文件")

                    with self.lock:
                        self.curr_prog += 1

        with self.lock:
            self.curr_stage = f"生成文件清单……"
            self.curr_prog += 1
        zs = sorted([(j.filename.lower(), j.filename, j.date_time, f) for i, f in zip(zis, zfs) if len(i) > 0 for j in i
                     if any(j.filename.lower().startswith(k) for k in RawData.PREFIX_FILTERS) \
                     and any(j.filename.lower().endswith(k) for k in RawData.SUFFIX_FILTERS)
                     and not j.is_dir()],
                    key=lambda x:(x[0], x[2]))
        self.manifest = {i[0]: (i[1], i[3]) for i in zs}
        logging.warning(f"游戏数据文件信息扫描完毕，发现{len(self.zip_q)}个相关文件，用时{time() - prev_timeit:.2f}秒。")

    def listdir(self, target: str, zips_to_exclude=set()):
        target = target.lower()
        if not target.endswith("/"):
            target = target + "/"
        if target.startswith("/"):
            target = target[1:]

        all_dirs = set()
        all_files = {}
        for filename, (true_name, zip_name) in self.manifest.items():
            if zip_name[-4:].lower() in zips_to_exclude:
                continue
            if filename.startswith(target):
                remaining = filename[len(target):]
                if "/" not in remaining:
                    all_files[filename] = (true_name, zip_name) 
                else:
                    all_dirs.add(target + remaining.split("/")[0])

        return sorted(list(all_dirs)), sorted(list(all_files.values()))

    def walk(self, target: str, zips_to_exclude=set()):
        target = target.lower()
        if not target.endswith("/"):
            target = target + "/"
        if target.startswith("/"):
            target = target[1:]

        all_files = {}
        for filename, (true_name, zip_name) in self.manifest.items():
            if zip_name[-4:].lower() in zips_to_exclude:
                continue
            if filename.startswith(target):
                all_files[filename] = (true_name, zip_name) 

        return sorted(list(all_files.values()))

    def get_file(self, target: str):
        try:
            zip_name = self.get_zipname(target)
            return self.zip_q[zip_name].read(target)
        except BadZipFile:
            logging.warning(f"来自“{zip_name}”的“{target}”无法正常读取，尝试另外手段……")
            tmp_path = os.path.dirname(NamedTemporaryFile().name)
            cmd = "{} e {} -i!*{} -y -o{}".format(per.get_7za(), zip_name, target, tmp_path)
            tmp_file = os.path.join(tmp_path, os.path.basename(target))
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            proc.communicate()
            if proc.returncode == 0:
                try:
                    result = open(tmp_file).read()
                except FileNotFoundError:
                    logging.warning(f"另外手段也无法读取来自“{zip_name}”的“{target}”……")
                    return None
                try:
                    os.remove(tmp_file)
                except:
                    pass
                return result
            else:
                return None
        except:
            return None

    def get_zipname(self, target: str):
        try:
            return self.manifest[target.lower()][1]
        except:
            return None

    def get_progress(self):
        with self.lock:
            return self.curr_prog / self.total_prog

    def get_stage(self):
        with self.lock:
            return self.curr_stage

    @staticmethod
    def get_time_weightage():
        return 2.80


class GameInfo:
    def __init__(self):
        self.curr_prog = 0
        self.total_prog = 2
        self.curr_stage = None
        self.lock = Lock()
        self.work_done = False
        self.spell_xdbs = None
        self.creature_conn = None

    def preload(self, data:RawData):
        self._data = data
        self._preload_heroes(data)

        jobs = ("TTBereinAllHeroes.chk", "TTBereinAllSpellsArtefacts.chk", "TTBereinRacialAbilityBoost.chk")
        return self

    def _preload_heroes(self, data: RawData):
        def _get_hero_xdbs(hero_dir):
            result = {}
            files = data.walk(hero_dir)
            for file_name, _ in files:
                if os.path.basename(file_name.lower()).endswith(".xdb"):
                    xdb_content = data.get_file(file_name)
                    if xdb_content is None:
                        continue
                    if b"<AdvMapHeroShared" in xdb_content:
                        et = ET.fromstring(xdb_content)
                        if et.tag == "AdvMapHeroShared":
                            result[file_name] = et
            return result

        with self.lock:
            self.curr_prog += 1
            self.curr_stage = "正在预加载英雄相关XDB文件入内存……"

        prev_timeit = time()
        self.hero_xdbs = _get_hero_xdbs("MapObjects/")
        logging.warning(f"英雄数据预加载完毕，发现{len(self.hero_xdbs)}个相关文件，用时{time() - prev_timeit:.2f}秒。")

    def work(self, map_options: dict[str, MapsStatusClass[bool]], hero_options: HeroesStatusClass):
        with self.lock:
            self.curr_prog = 1
            self.work_done = False

        if all(j is False for i in map_options.values() for j in i):
            raise ValueError("无任何选项被勾选，退回！")

        mod_dir = os.path.join(per.last_path, "UserMODs")
        if not os.path.isdir(mod_dir):
            try:
                os.makedirs(mod_dir)
            except FileExistsError:
                err_msg = f"{mod_dir}是个文件，不是文件夹，请删除该文件后再运行。"
                logging.warning("出错，任务中断！" + err_msg)
                raise ValueError(err_msg)
            except OSError:
                err_msg = f"无法创建{mod_dir}，请检查游戏文件夹是否是只读。"
                logging.warning("出错，任务中断！"+ err_msg)
                raise ValueError(err_msg)
        map_options["nochange"] = deepcopy(map_options["customized"])
        num_map_xmls = sum(len(v) for k, v in self.map_xdbs.items() if any(i for i in map_options[k]))
        num_hero_xmls = 0 if all(i.racial_ability_boost is False for i in map_options.values()) else len(self.hero_xdbs)
        with self.lock:
            self.total_prog = num_map_xmls +  1 if num_hero_xmls else 0

        try:
            merged_patch, _ = remove_merged_patch()
        except PermissionError as e:
            raise ValueError(str(e))

        try:
            with ZipFile(merged_patch, "w", compression=ZIP_DEFLATED,
                        compresslevel=9) as zfp:
                logging.warning("开始生成兼容文件")
                if num_map_xmls > 0:
                    logging.warning(f"  共有{num_map_xmls}个地图xdb文件需要处理")
                    self._work_maps(map_options, zfp)
                if num_hero_xmls > 0:
                    logging.warning(f"  共有{num_hero_xmls}个英雄xdb文件需要处理")
                    self._work_heroes(hero_options, zfp)
                self._work_creatures(zfp)
                logging.warning(f"兼容补丁文件{merged_patch}已经生成")

        except PermissionError:
            err_msg = f"无法创建{merged_patch}。请检查你是否对该文件夹有写权限。"
            logging.warning("出错，任务中断！"+ err_msg)
            raise ValueError()

        with self.lock:
            self.work_done = True

        return self

    def _work_heroes(self, hero_options: HeroesStatusClass, zfp: ZipFile):
        def _load_spell_xdb(hero_class):
            xml_name = "spells_{}.xml".format(hero_class[len("HERO_CLASS_"):])
            try:
                spell_et = ET.fromstring(per.get_xml(xml_name))
            except FileNotFoundError:
                return set()
            return {i.text for i in spell_et.findall("Item")}

        def __union_items_btw_et_and_set(et1: ET.Element, set2: set[str]):
            result = 0
            # et1 will be modified
            set1 = set(i.text for i in et1)
            for i in set2:
                if i not in set1:
                    ele = ET.Element("Item")
                    ele.text = i
                    et1.append(ele)
                    result += 1
            return result

        def _swap_skills(hero_et: ET.Element):
            result = 0

            skills = set()
            for i in hero_et.find("PrimarySkill"):
                if i.tag == "SkillID":
                    skills.add(i.text)
            for i in hero_et.find("Editable").find("skills"):
                skills.add(i.find("SkillID").text)

            perks_et = hero_et.find("Editable").find("perkIDs")
            for i in perks_et:
                if i.text in per.perk_swaps:
                    if per.perk_swaps[i.text][1] in skills:
                        i.text = per.perk_swaps[i.text][0]
                        result += 1

            return result

        def _swap_specialization(hero_et: ET.Element):
            result = 0

            hero_specialization = hero_et.find("Specialization").text
            if hero_specialization in per.specialization_swaps:
                hero_et.find("Specialization").text = per.specialization_swaps[hero_specialization][0]
                hero_et.find("SpecializationNameFileRef").attrib["href"] = \
                    per.specialization_swaps[hero_specialization][1]
                hero_et.find("SpecializationDescFileRef").attrib["href"] = \
                    per.specialization_swaps[hero_specialization][2]
                hero_et.find("SpecializationIcon").attrib["href"] = \
                    per.specialization_swaps[hero_specialization][3]
                result += 1

            return result

        def _get_hero_name_and_specialization(hero_et: ET.Element):
            return hero_et.find("InternalName").text, hero_et.find("Specialization").text

        if self.spell_xdbs is None:
            self.spell_xdbs = {}

        with self.lock:
            self.curr_stage = f"正在处理英雄文件数据文件"

        prev_timeit = time()
        hero_spec_info = {i: set() for i in SPECIALIZATION_INFO.keys()}
        for hero_xml, hero_et in self.hero_xdbs.items():
            changes = 0
            if hero_options.racial_ability_boost is True:
                hero_class = hero_et.find("Class").text
                if hero_class not in self.spell_xdbs:
                    self.spell_xdbs[hero_class] = _load_spell_xdb(hero_class)
                changes += __union_items_btw_et_and_set(hero_et.find("Editable").find("spellIDs"),
                                                        self.spell_xdbs[hero_class])

                changes += _swap_skills(hero_et)
                changes += _swap_specialization(hero_et)

                # After specialization swap, process special handling needed in script
                hero_name, hero_spec = _get_hero_name_and_specialization(hero_et)
                for k in SPECIALIZATION_INFO.keys():
                    if hero_spec == k:
                        hero_spec_info[k].add(hero_name)

            if changes > 0:
                ET.indent(hero_et, space="    ", level = 0)
                zfp.writestr(hero_xml, ET.tostring(hero_et, short_empty_elements=True, encoding='utf8', method='xml'))
                logging.info(f"    英雄文件{hero_xml}处理完毕；")
            else:
                logging.info(f"    英雄文件{hero_xml}无需处理，略过……")

            with self.lock:
                if self.work_done is True:
                    logging.warning("用户中断了操作！")
                    raise InterruptedError

        with self.lock:
            self.curr_stage = f"正在处理特殊特长脚本文件"

        for k, v in hero_spec_info.items():
            if len(v) > 0:
                lua_content = "{0} = {{{1}}}".format(SPECIALIZATION_INFO[k].var,
                                                     ", ".join(sorted(["\"{}\"".format(i) for i in v])))
                zfp.writestr(SPECIALIZATION_INFO[k].script, lua_content)
                logging.info(f"    特殊英雄信息已经写入{SPECIALIZATION_INFO[k].script}；")

            with self.lock:
                if self.work_done is True:
                    logging.warning("用户中断了操作！")
                    raise InterruptedError

        logging.warning(f"  英雄xdb文件处理完毕，共耗时{time() - prev_timeit:.2f}秒。")

        return self

    def cancel(self):
        with self.lock:
            self.work_done = True

    @property
    def mod_status(self):
        return self._mods_status

    @property
    def hero_status(self):
        return self._hero_status

    @staticmethod
    def get_time_weightage():
        return 0.25

    def get_progress(self):
        with self.lock:
            return self.curr_prog / self.total_prog

    def get_stage(self):
        with self.lock:
            return self.curr_stage
