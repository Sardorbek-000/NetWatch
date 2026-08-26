import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class NetWatchApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("NetWatch")
        self.geometry("800x500")
        self.minsize(640, 420)

        self.profiles = [];

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.frames = {}
        for Frame in (MainMenu, Settings, AddProfile, Profile):
            frame = Frame(self.container, self)
            self.frames[Frame] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_frame(MainMenu)
-6 7889
    def show_frame(self, frame_class):
        self.frames[frame_class].tkraise()


class MainMenu(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
    def refresh_main_menu(self):
        for widget in self.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self, text="NetWatch", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(40, 30))

        # ctk.CTkButton(self, text="Enter Profile", width=220,
        #               command=lambda: app.show_frame(Profile)).pack(pady=10)

        for profile_name in self.app.profiles:
            ctk.CTkButton(self, text=profile_name,width=220,
                      command=lambda: app.show_frame(Profile)).pack(pady=10)

        ctk.CTkButton(self, text="Add Profile", width=220,
                      command=lambda: app.show_frame(AddProfile)).pack(pady=10)
        ctk.CTkButton(self, text="Settings", width=220,
                      command=lambda: app.show_frame(Settings)).pack(pady=10)

    def tkraise(self):
        super().tkraise()
        self.after(100, self.refresh_main_menu())



class Settings(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        ctk.CTkButton(self, text="Delete Profiles", width=220).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)


class AddProfile(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text="Add Profile", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        self.title_entry = ctk.CTkEntry(self, width=260, placeholder_text="Profile title")
        self.title_entry.pack(pady=10)

        ctk.CTkButton(self, text="Create", width=220, command=lambda : self.create_profile()).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)

    def create_profile(self):
        profile_name = self.title_entry.get()

        if profile_name.strip():
            self.app.profiles.append(profile_name)
            self.title_entry.delete(0, "end");
            print(f"Profile added: {profile_name}")
            self.app.show_frame(MainMenu)


class Profile(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")

        ctk.CTkLabel(self, text="Profile", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 30))

        ctk.CTkButton(self, text="Start Scanning", width=220).pack(pady=10)
        ctk.CTkButton(self, text="History", width=220).pack(pady=10)
        ctk.CTkButton(self, text="Go Back to Menu", width=220,
                      command=lambda: app.show_frame(MainMenu)).pack(pady=10)


if __name__ == "__main__":
    app = NetWatchApp()
    app.mainloop()