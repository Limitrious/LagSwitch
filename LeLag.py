import subprocess as sp
import ctypes as ct
import atexit
import psutil
import threading
import customtkinter as ctk
import sys
from typing import Optional
from win32gui import GetForegroundWindow, GetWindowRect, SetWindowPos
import win32con as wc
import win32process
from pynput import keyboard, mouse

RULE_NAME = "Roblox_Block"
DEFAULT_KEYBIND = "f6"

class LeLag:
    def __init__(self) -> None:
        self.settings = {
            'Keybind': DEFAULT_KEYBIND,
            'Lagswitch': 'off',
            'AutoTurnOff': False,
            'AutoTurnBackOn': False,
            'Overlay': False
        }
        self.block_flag: bool = False
        self.lagswitch_active: bool = False
        self.manual_override: bool = False
        self.timer_duration: float = 9.8
        self.reactivation_duration: float = 0.2
        self.active_timer: Optional[threading.Timer] = None
        self.timer_lock = threading.Lock()
        self.lagswitch_cycle_event = threading.Event()
        self.auto_cycle_thread: Optional[threading.Thread] = None
        self.status_window: Optional[ctk.CTkToplevel] = None
        self.overlay_update_event = threading.Event()
        self.overlay_update_thread: Optional[threading.Thread] = None
        self.changing_keybind = False
        self.keyboard_listener = None
        self.mouse_listener = None

        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')
        self.root = ctk.CTk()
        self.root.title('LeLag V1, Original idea: SquareszLeaf')
        self.root.geometry('370x185')
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        self.check_requirements()
        self.setup_ui()
        self.setup_keybind()

    def setup_ui(self) -> None:
        self.status_label = ctk.CTkLabel(
            self.root, text='LagSwitch off.', text_color='red',
            font=('TkDefaultFont', 15, 'bold')
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=0)
        ctk.CTkLabel(self.root, text='Improved by LMRT').grid(row=0, column=1, padx=10, pady=0)
        self.keybind_label = ctk.CTkLabel(
            self.root, text=f"Keybind: {self.settings['Keybind']}"
        )
        self.keybind_label.grid(row=1, column=0, padx=10, pady=4)
        ctk.CTkButton(self.root, text='Change Keybind', command=self.change_keybind).grid(row=2, column=0, padx=10, pady=4)
        self.auto_turnoff_var = ctk.BooleanVar(value=self.settings['AutoTurnOff'])
        ctk.CTkCheckBox(
            self.root, text='Anti-Timeout', variable=self.auto_turnoff_var,
            command=self.update_auto_turnoff
        ).grid(row=3, column=0, padx=10, pady=4)
        self.auto_turnbackon_var = ctk.BooleanVar(value=self.settings['AutoTurnBackOn'])
        ctk.CTkCheckBox(
            self.root, text='Reactivate', variable=self.auto_turnbackon_var,
            command=self.update_auto_turnbackon
        ).grid(row=4, column=0, padx=10, pady=4)
        self.always_on_top_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self.root, text='Always on Top', variable=self.always_on_top_var,
            command=self.toggle_always_on_top
        ).grid(row=2, column=1, padx=10, pady=4)
        self.timer_slider = ctk.CTkSlider(
            self.root, from_=0, to=10, number_of_steps=100,
            command=self.update_timer_duration
        )
        self.timer_slider.set(self.timer_duration)
        self.timer_slider.grid(row=3, column=1, padx=10, pady=4)
        self.timer_label = ctk.CTkLabel(
            self.root, text=f"{self.timer_duration:.1f}s"
        )
        self.timer_label.grid(row=3, column=1, padx=10, pady=4)
        self.reactivation_slider = ctk.CTkSlider(
            self.root, from_=0, to=1, number_of_steps=10,
            command=self.update_reactivation_duration
        )
        self.reactivation_slider.set(self.reactivation_duration)
        self.reactivation_slider.grid(row=4, column=1, padx=10, pady=4)
        self.reactivation_label = ctk.CTkLabel(
            self.root, text=f"{self.reactivation_duration:.1f}s"
        )
        self.reactivation_label.grid(row=4, column=1, padx=10, pady=4)
        self.overlay_var = ctk.BooleanVar(value=self.settings['Overlay'])
        ctk.CTkCheckBox(
            self.root, text='Overlay', variable=self.overlay_var,
            command=self.toggle_status_window
        ).grid(row=1, column=1, padx=10, pady=4)

    def toggle_status_window(self) -> None:
        if self.overlay_var.get():
            self.open_status_window()
            self.start_overlay_update()
        else:
            self.close_status_window()
            self.stop_overlay_update()

    def open_status_window(self) -> None:
        if self.status_window is None or not self.status_window.winfo_exists():
            self.status_window = ctk.CTkToplevel(self.root)
            self.status_window.overrideredirect(True)
            self.status_window.attributes('-topmost', True)
            self.status_window.attributes('-transparentcolor', self.status_window['bg'])
            self.status_window_label = ctk.CTkLabel(
                self.status_window, text='LagSwitch off.', text_color='red',
                font=('TkDefaultFont', 15, 'bold')
            )
            self.status_window_label.place(relx=0.5, rely=0.5, anchor='center', y=60)
            self.update_status_window()

    def close_status_window(self) -> None:
        if self.status_window and self.status_window.winfo_exists():
            self.status_window.destroy()
            self.status_window = None

    def start_overlay_update(self) -> None:
        if not self.overlay_update_thread or not self.overlay_update_thread.is_alive():
            self.overlay_update_event.clear()
            self.overlay_update_thread = threading.Thread(target=self.overlay_update_loop, daemon=True)
            self.overlay_update_thread.start()

    def stop_overlay_update(self) -> None:
        self.overlay_update_event.set()

    def overlay_update_loop(self) -> None:
        previous_rect = None
        previous_active = None
        while not self.overlay_update_event.is_set():
            self.overlay_update_event.wait(0.05)
            try:
                if self.overlay_var.get() and self.status_window and self.status_window.winfo_exists():
                    current_window = GetForegroundWindow()
                    rect = GetWindowRect(current_window)
                    _, pid = win32process.GetWindowThreadProcessId(current_window)
                    current_process = psutil.Process(pid)
                    is_roblox = current_process.name().lower() == 'robloxplayerbeta.exe'
                    if is_roblox and (previous_rect != rect or previous_active != is_roblox):
                        self.status_window.deiconify()
                        width, height = rect[2] - rect[0], rect[3] - rect[1]
                        self.status_window.geometry(f"{width}x{height}+{rect[0]}+{rect[1]}")
                        SetWindowPos(
                            self.status_window.winfo_id(), wc.HWND_TOPMOST,
                            rect[0], rect[1], width, height, wc.SWP_NOACTIVATE
                        )
                    elif not is_roblox and previous_active != is_roblox:
                        self.status_window.withdraw()
                    previous_rect = rect
                    previous_active = is_roblox
            except Exception:
                pass

    def update_status_window(self) -> None:
        status_text = 'LagSwitch on.' if self.block_flag else 'LagSwitch off.'
        status_color = 'green' if self.block_flag else 'red'
        try:
            if self.status_window and hasattr(self, "status_window_label"):
                self.status_window_label.configure(text=status_text, text_color=status_color)
        except Exception:
            pass

    def update_status_label(self) -> None:
        status_text = 'LagSwitch on.' if self.block_flag else 'LagSwitch off.'
        status_color = 'green' if self.block_flag else 'red'
        self.status_label.configure(text=status_text, text_color=status_color)
        self.update_status_window()

    def update_auto_turnoff(self) -> None:
        self.settings['AutoTurnOff'] = self.auto_turnoff_var.get()

    def update_auto_turnbackon(self) -> None:
        self.settings['AutoTurnBackOn'] = self.auto_turnbackon_var.get()

    def update_timer_duration(self, value: float) -> None:
        self.timer_duration = float(value)
        self.timer_label.configure(text=f"{self.timer_duration:.1f}s")

    def update_reactivation_duration(self, value: float) -> None:
        self.reactivation_duration = float(value)
        self.reactivation_label.configure(text=f"{self.reactivation_duration:.1f}s")

    def toggle_always_on_top(self) -> None:
        self.root.attributes('-topmost', self.always_on_top_var.get())

    def change_keybind(self) -> None:
        self.changing_keybind = True
        self.stop_listeners()
        self.keybind_label.configure(text='Press a key or side mouse button (Mouse4/Mouse5)...')
        self.start_temp_listeners()

    def start_temp_listeners(self):
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press_temp)
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click_temp)
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def on_key_press_temp(self, key):
        if not self.changing_keybind:
            return
        try:
            key_name = key.char if hasattr(key, 'char') and key.char else str(key).split('.')[-1]
            self.set_keybind(key_name)
        except AttributeError:
            pass

    def on_mouse_click_temp(self, x, y, button, pressed):
        if not self.changing_keybind or not pressed:
            return
        if button == mouse.Button.x1:
            self.set_keybind("Mouse4")
        elif button == mouse.Button.x2:
            self.set_keybind("Mouse5")

    def set_keybind(self, key: str) -> None:
        if not self.changing_keybind:
            return
        self.settings['Keybind'] = key
        self.keybind_label.configure(text=f"Keybind: {key}")
        self.stop_listeners()
        self.setup_new_keybind(key)
        self.changing_keybind = False

    def stop_listeners(self) -> None:
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None

    def setup_new_keybind(self, key: str) -> None:
        self.stop_listeners()
        if key == "Mouse4":
            self.mouse_listener = mouse.Listener(on_click=lambda x, y, b, p: self.toggle_block(b == mouse.Button.x1 and p))
        elif key == "Mouse5":
            self.mouse_listener = mouse.Listener(on_click=lambda x, y, b, p: self.toggle_block(b == mouse.Button.x2 and p))
        else:
            self.keyboard_listener = keyboard.Listener(on_press=lambda k: self.toggle_block(k, key))
        if self.keyboard_listener:
            self.keyboard_listener.start()
        if self.mouse_listener:
            self.mouse_listener.start()

    def toggle_block(self, event, expected_key=None) -> None:
        if self.changing_keybind:
            return
        if expected_key:
            try:
                key_name = event.char if hasattr(event, 'char') and event.char else str(event).split('.')[-1]
                if key_name == expected_key:
                    self._toggle_lagswitch()
            except AttributeError:
                pass
        elif event:  # Mouse event
            self._toggle_lagswitch()

    def _toggle_lagswitch(self) -> None:
        if self.lagswitch_active:
            self.deactivate_lagswitch()
        else:
            self.activate_lagswitch()

    def activate_lagswitch(self) -> None:
        self.lagswitch_active = True
        self.manual_override = False
        self.turn_on_lag_switch()
        if self.settings['AutoTurnOff']:
            self.lagswitch_cycle_event.clear()
            self.auto_cycle_thread = threading.Thread(target=self.lagswitch_cycle_loop, daemon=True)
            self.auto_cycle_thread.start()

    def deactivate_lagswitch(self) -> None:
        self.lagswitch_active = False
        self.lagswitch_cycle_event.set()
        if self.active_timer:
            self.active_timer.cancel()
            self.active_timer = None
        self.turn_off_lag_switch()

    def lagswitch_cycle_loop(self) -> None:
        while self.lagswitch_active and not self.lagswitch_cycle_event.is_set():
            if self.lagswitch_cycle_event.wait(self.timer_duration):
                break
            self.turn_off_lag_switch()
            if self.lagswitch_cycle_event.wait(self.reactivation_duration):
                break
            if self.lagswitch_active:
                if self.settings['AutoTurnBackOn']:
                    self.turn_on_lag_switch()
                else:
                    self.lagswitch_active = False
                    self.update_status_label()
                    break

    def turn_on_lag_switch(self) -> None:
        self.block_flag = True
        self.update_firewall_rules('block')
        self.update_status_label()

    def turn_off_lag_switch(self) -> None:
        self.block_flag = False
        self.update_firewall_rules('delete')
        self.update_status_label()

    def update_firewall_rules(self, action: str) -> None:
        try:
            roblox_process = next(
                (proc for proc in psutil.process_iter(['pid', 'name', 'exe'])
                 if proc.info['name'] == 'RobloxPlayerBeta.exe' and
                    proc.info.get('exe', '').lower().find('roblox') != -1),
                None
            )
            if not roblox_process:
                self.disable_lag_switch()
                return
            exe_path = roblox_process.exe()
            if action == 'block':
                cmd = ['netsh', 'advfirewall', 'firewall', 'add', 'rule',
                       f'name={RULE_NAME}', 'dir=out', 'action=block', f'program={exe_path}']
            else:
                cmd = ['netsh', 'advfirewall', 'firewall', 'delete', 'rule', f'name={RULE_NAME}']
            sp.run(cmd, creationflags=sp.CREATE_NO_WINDOW)
        except psutil.NoSuchProcess:
            self.disable_lag_switch()
        except Exception:
            pass

    def check_requirements(self) -> None:
        if not self.is_admin():
            self.show_message('LeLagSwitch requires administrator privileges to run.')
            sys.exit(1)
        if not any(proc.info['name'] == 'RobloxPlayerBeta.exe' for proc in psutil.process_iter(['name'])):
            self.show_message('Roblox is not running. Please start Roblox and try again.')
            sys.exit(1)

    def is_admin(self) -> bool:
        try:
            return bool(ct.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def show_message(self, message: str) -> None:
        ct.windll.user32.MessageBoxW(0, message, 'LeLag V1', 0)

    def disable_lag_switch(self) -> None:
        try:
            result = sp.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule', 'name=all'],
                            capture_output=True, text=True)
            rules = [line.split(':')[1].strip() for line in result.stdout.splitlines() if 'Rule Name:' in line]
            for rule in rules:
                if RULE_NAME in rule:
                    sp.run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule', f"name={rule}"])
        except Exception:
            pass
        self.root.destroy()
        sys.exit(1)

    def setup_keybind(self) -> None:
        key = self.settings.get('Keybind', DEFAULT_KEYBIND)
        self.settings['Keybind'] = key
        self.keybind_label.configure(text=f"Keybind: {key}")
        self.setup_new_keybind(key)

    def run(self) -> None:
        atexit.register(self.exit_handler)
        self.root.mainloop()

    def exit_handler(self) -> None:
        self.lagswitch_cycle_event.set()
        self.update_firewall_rules('delete')
        self.overlay_update_event.set()
        self.stop_listeners()

if __name__ == '__main__':
    try:
        app = LeLag()
        app.run()
    except Exception:
        pass