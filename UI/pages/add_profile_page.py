import customtkinter as ctk



class AddProfilePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text="Add Profile", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        self.title_entry = ctk.CTkEntry(self, width=260, placeholder_text="Profile title")
        self.title_entry.pack(pady=10)

        self.error_label = ctk.CTkLabel(self, text="", text_color="red")
        self.error_label.pack(pady=(0, 10))

        ctk.CTkButton(self, text="Create", width=220, command=self.create_profile).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: self.app.show_frame("MainMenuPage")).pack(pady=10)

    def on_show(self, **kwargs):
        self.title_entry.delete(0, "end")
        self.error_label.configure(text="")

    def create_profile(self):
        name = self.title_entry.get().strip()

        if not name:
            self.error_label.configure(text="Empty name")
            return
        if len(name) > 30:
            self.error_label.configure(text="Name too long (max 30 characters)")
            return

        existing_names = [p["name"] for p in self.app.storage.list_profiles()]
        if name in existing_names:
            self.error_label.configure(text="Profile already exists")
            return

        self.app.storage.get_or_create_profile(name)
        self.title_entry.delete(0, "end")
        self.error_label.configure(text="")
        self.app.show_frame("MainMenuPage")