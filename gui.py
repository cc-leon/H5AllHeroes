import logging
from threading import Thread, Lock
from queue import Queue, Empty
from collections.abc import Callable
from tkinter import END
from tkinter import messagebox, Tk, Menu, scrolledtext, Toplevel, filedialog, LabelFrame, simpledialog
from tkinter.ttk import Label, Progressbar, Style, Checkbutton, Button

from data_parser import (RawData, GameInfo, MapsStatusClass, HeroesStatusClass, HeroesStatusNames,PATCH_FILE_NAME,
                         remove_merged_patch)
from persistence import per
import data_parser as gg


TITLE = "英雄无敌5MOD兼容工具 V{} by 天天英吧".format(per.VERSION)


class CancelWnd(Toplevel):
    def __init__(self, parent: Tk, cancel_func: Callable):
        super(CancelWnd, self).__init__(parent)
        self.title("进行中……")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        Label(self, text="任务进行中……").grid(row = 0, column=0, padx=20, pady=20)
        self.button = Button(self, text="取消", command=self.on_cancel_click)
        self.attributes("-toolwindow", True)
        self.attributes("-topmost", True)
        self.button.grid(row = 1, column=0, padx=20, pady=20)

        x = parent.winfo_rootx() + parent.winfo_width()/2 - 80
        y = parent.winfo_rooty() + parent.winfo_height()/2 - 50
        self.geometry("+{}+{}".format(int(x), int(y)))

        self.cancel_func = cancel_func
        self.parent = parent

    def on_cancel_click(self):
        self.cancel_func()
        self.destroy()
        self.parent.deiconify()


class AboutWnd(simpledialog.Dialog):
    def __init__(self, parent, title="关于“英雄无敌5MOD兼容工具 V{}”".format(per.VERSION)):
        super(AboutWnd, self).__init__(parent=parent, title=title)

    def body(self, master):
        self.attributes("-toolwindow", True)
        self.attributes("-topmost", True)
        textbox = scrolledtext.ScrolledText(self, height=20, width=80)
        textbox.configure(font=('TkFixedFont', 11))
        textbox.insert(END, per.get_about_txt())
        textbox.pack()
        textbox.configure(state="disabled")
        textbox.config(spacing1=5, spacing2=5, spacing3=5)

    def buttonbox(self):
        pass  # no buttons!


class LogWnd(Toplevel):
    class _TextHandler(logging.Handler):
        def __init__(self, queue):
            super(LogWnd._TextHandler, self).__init__()
            self.queue = queue
        def emit(self, record):
            self.queue.put(self.format(record))

    def __init__(self, parent):
        super(LogWnd, self).__init__(parent)
        self.queue = Queue()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.iconbitmap(per.get_ico())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.title("日志记录")

        self.log_box = scrolledtext.ScrolledText(self, state='disabled', height=60, width=80)
        self.log_box.configure(font=('TkFixedFont', 11))
        self.log_box.grid(column=0, row=0, sticky="NEWS")
        text_handler = LogWnd._TextHandler(self.queue)
        logger = logging.getLogger()
        logger.addHandler(text_handler)
        self.after(0, self.append_msg)
        self._parent = parent

    def append_msg(self):
        msgs = []

        while(True):
            try:
                msg = self.queue.get_nowait()
                msgs.append(msg)
            except Empty:
                break

        if len(msgs) > 0:
            msgs.append("")
            self.log_box.configure(state="normal")
            self.log_box.insert(END, "\n".join(msgs))
            self.log_box.configure(state="disabled")
            self.log_box.yview(END)

        self.after(100, self.append_msg)

    def on_close(self):
        per.log_x = self.winfo_x()
        per.log_y = self.winfo_y()
        per.save()
        self._parent._on_menu_showlog()

class MainWnd(Tk):
    def __init__(self, *args):
        super(MainWnd, self).__init__(*args)
        self.lock = Lock()

        font=("TkFixedFont", 11)
        sty = Style(self)
        sty.configure(".", font=font)
        self.num_rows = 0

        self.log_wnd = LogWnd(self)
        self.log_wnd.update()
        self.log_wnd.geometry("+{}+{}".format(per.log_x, per.log_y))

        self.title(TITLE)
        self.resizable(False, False)

        self.status_text = Label(self, text="已启动", border=1, relief="sunken", padding=2, font=("TkFixedFont", 10))
        self.status_text.grid(column=0, row=5, sticky="ew")
        self.status_prog = Progressbar(self)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.iconbitmap(per.get_ico())
        self.update()
        self.geometry("+{}+{}".format(per.main_x, per.main_y))
        self._asking_game_data()

    def on_close(self):
        per.main_x = self.winfo_x()
        per.main_y = self.winfo_y()
        per.save()
        self.destroy()

    def _build_top_menu(self):
        self.top_menu = Menu(self)
        self.config(menu=self.top_menu)

        self.top_menu.add_command(label="生成兼容文件", command=self._on_menu_createmod)
        self.top_menu.add_command(label="移除兼容文件", command=self._on_menu_removemod)
        self.top_menu.add_command(label="", command=self._on_menu_showlog)
        per.show_log = not per.show_log
        self._on_menu_showlog()
        self.top_menu.add_command(label="帮助与关于",command=self._on_menu_about)

    def _on_menu_createmod(self):
        self.status_text.grid(column=0, row=self.num_rows, sticky="we", columnspan=1)
        self.status_prog.grid(column=1, row=self.num_rows, sticky="we")
        self.attributes("-disabled", True)
        map_options = {k: MapsStatusClass(*("selected" in i.state() for i in v)) for k, v in self.map_checkboxes.items()}
        hero_options = HeroesStatusClass(*["selected" in i.state() for i in self.hero_checkboxes])
        Thread(target=self._creatmod_thread, args=(self.data, map_options, hero_options)).start()
        self.cancel_wnd = CancelWnd(self, self.data.cancel)
        self.cancel_wnd.update()
        self.cancel_wnd.deiconify()
        self.after(10, self._createmod_thread_after, self.data)

    def _creatmod_thread(self, data: GameInfo, map_options: dict[str, MapsStatusClass[bool]],
                         hero_options: dict[str, bool]):
        gg.info = None
        try:
            gg.info = data.work(map_options, hero_options)
        except ValueError as e:
            gg.info = e
        except InterruptedError as e:
            gg.info = e

    def _createmod_thread_after(self, data):
        def clean_up(finished_text):
            self.attributes("-disabled", False)
            self.status_prog.grid_forget()
            self.status_text.grid(column=0, row=self.num_rows, sticky="ew", columnspan=2)
            self.status_text.config(text=finished_text)
            self.cancel_wnd.destroy()

        with self.lock:
            if type(gg.info) == ValueError:
                clean_up("生成兼容补丁失败")
                messagebox.showerror(TITLE , str(gg.info))
            elif type(gg.info) == InterruptedError:
                clean_up("任务中断")
            elif type(gg.info) == GameInfo:
                clean_up("生成兼容补丁成功")
                messagebox.showinfo(TITLE, "兼容补丁“UserMODS/" + PATCH_FILE_NAME + "”生成完成！")
            else:
                status_text = ""
                prog_value = 0.0

                status_text = data.get_stage()
                prog_value = data.get_progress() * 100

                prog_value = 100.00 if prog_value > 100.00 else prog_value
                status_text = f"{status_text}, 总进度{prog_value:.2f}%"
                status_text += (65 - len(status_text)) * " "
                self.status_text.config(text=status_text)
                self.status_prog.config(value=prog_value)
                self.after(10, self._createmod_thread_after, data)

    def _on_menu_removemod(self):
        try:
            if remove_merged_patch()[1] is True:
                messagebox.showinfo(TITLE, "生成的补丁已经移除")
            else:
                messagebox.showwarning(TITLE, f"找不到补丁文件“UserMODS/" + PATCH_FILE_NAME+"”")
        except PermissionError as e:
            messagebox.showerror(TITLE, str(e))

    def _on_menu_showlog(self):
        if per.show_log:
            new_text = "显示日志"
            self.log_wnd.withdraw()
        else:
            new_text = "隐藏日志"
            self.log_wnd.deiconify()
            self.focus_set()

        per.show_log = not per.show_log
        self.top_menu.entryconfig(3, label=new_text)

    def _on_menu_about(self):
        self.about_wnd = AboutWnd(self)

    def _build_main_frame(self):
        pass

    def _asking_game_data(self):
        self.withdraw()

        h5_path = "E:\\games\\TOE31\\"
        #h5_path = filedialog.askdirectory(title="请选择英雄无敌5安装文件夹", initialdir=per.last_path)
        h5_path = h5_path.replace("/", "\\")
        if h5_path == "":
            messagebox.showerror(TITLE, "本程序依赖已安装的英雄无敌5游戏数据！\n无游戏数据，退出。")
            return self.on_close()

        per.last_path = h5_path

        self.deiconify()
        self.status_text.grid(column=0, row=self.num_rows, sticky="we", columnspan=1)
        self.status_prog.grid(column=1, row=self.num_rows, sticky="we")
        gg.info = None
        raw_data = RawData(h5_path)
        game_info = GameInfo()
        Thread(target=self._ask_game_data_thread, args=(raw_data, game_info)).start()
        self.after(10, self._ask_game_data_after, raw_data, game_info)

    def _ask_game_data_thread(self, raw_data: gg.RawData, game_info: GameInfo):
        try:
            raw_data.run()
        except ValueError as e:
            with self.lock:
                gg.info = e
            return

        try:
            game_info.preload(raw_data)
        except ValueError as e:
            with self.lock:
                gg.info = e
            return

        with self.lock:
            gg.info = game_info

    def _ask_game_data_after(self, raw_data: gg.RawData, game_info: GameInfo):
        with self.lock:
            if type(gg.info) is ValueError:
                self.withdraw()
                messagebox.showerror(TITLE, str(gg.info))
                exit()
            elif type(gg.info) is GameInfo:
                self.data = gg.info
                self.status_prog.grid_forget()
                self.status_text.grid(column=0, row=5, sticky="ew", columnspan=2)
                self.status_text.config(text="游戏数据加载完毕")
                self._build_top_menu()
                self._build_main_frame()
                #self._on_menu_createmod()
            else:
                status_text = ""
                prog_value = 0.0
                total_weight = RawData.get_time_weightage() + GameInfo.get_time_weightage()

                if game_info.get_stage() is None:
                    status_text = raw_data.get_stage()
                    prog_value = raw_data.get_progress() * 100 * \
                        RawData.get_time_weightage() / total_weight
                else:
                    status_text = game_info.get_stage()
                    prog_value = game_info.get_progress() * 100 * GameInfo.get_time_weightage() / total_weight \
                        + RawData.get_time_weightage() * 100 / total_weight

                prog_value = 100.00 if prog_value > 100.00 else prog_value
                status_text = f"{status_text}, 总进度{prog_value:.2f}%"
                status_text += (65 - len(status_text)) * " "
                self.status_text.config(text=status_text)
                self.status_prog.config(value=prog_value)
                self.after(10, self._ask_game_data_after, raw_data, game_info)
