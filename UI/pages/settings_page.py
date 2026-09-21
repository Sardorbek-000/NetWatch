import customtkinter as ctk
from tkinter.messagebox import askyesno



class SettingsPage(ctk.CTkFrame):
    """Multi-select delete screen for profiles. Selection state is keyed by profile id, not name."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.selected = set()
        self.profile_buttons = {}

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 20))

        self.profile_list = ctk.CTkScrollableFrame(self, width=260, height=220, label_text="Profiles")
        self.profile_list.pack(pady=10)

        self.delete_btn = ctk.CTkButton(self, text="Delete Selected", width=220, fg_color="darkred",
                                        hover_color="#8b0000", state="disabled",
                                        command=self.delete_selected)
        self.delete_btn.pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: self.app.show_frame("MainMenuPage")).pack(pady=10)

    def on_show(self, **kwargs):
        self.refresh_profiles()

    def refresh_profiles(self):
        for widget in self.profile_list.winfo_children():
            widget.destroy()
        self.selected.clear()
        self.profile_buttons.clear()
        self.delete_btn.configure(state="disabled")
        for profile in self.app.storage.list_profiles():
            btn = ctk.CTkButton(self.profile_list, text=profile["name"], width=220,
                                fg_color="transparent",
                                command=lambda p=profile: self.toggle_profile(p["id"]))
            btn.pack(pady=5)
            self.profile_buttons[profile["id"]] = btn

    def toggle_profile(self, profile_id):
        btn = self.profile_buttons[profile_id]
        if profile_id in self.selected:
            self.selected.remove(profile_id)
            btn.configure(fg_color="transparent")
        else:
            self.selected.add(profile_id)
            btn.configure(fg_color="darkred")
        self.delete_btn.configure(state="normal" if self.selected else "disabled")

    def delete_selected(self):
        if not askyesno("Delete profiles", f"Delete {len(self.selected)} profile(s)? This cannot be undone."):
            return
        for profile_id in self.selected:
            self.app.storage.delete_profile(profile_id)
        self.refresh_profiles()