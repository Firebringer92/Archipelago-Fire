"""The client window's own tabs (needs Kivy; everything it shows is made by k2_status.py, which is tested without a window).

  Archipelago   the main log: connection, the patch result, new checks, items received, warnings
  Heartbeat     the bookkeeping log (k2_status.heartbeat): jobs sent, the game's wrapper lines, what each randomizer changed, one line every 30 s
  Status        the numbers and warnings at a glance, refreshed every second
"""
import typing


def manager_class(base: type) -> type:
    """The client's window class, made from the Archipelago text client's (CommonContext.make_gui). Imports Kivy only now, so the module loads without it."""
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.scrollview import ScrollView
    from kivymd.uix.label import MDLabel

    def label(text: str = "") -> "MDLabel":
        # grows with its text, so a long list wraps onto more lines instead of running into the label below it
        return MDLabel(text=text, size_hint_y=None, adaptive_height=True)

    class StatusView(BoxLayout):
        ORDER = ("warnings", "server", "game", "state", "patch", "checks", "jobs", "waiting", "failed", "recent")

        def __init__(self, ctx, **kwargs):
            super().__init__(orientation="vertical", **kwargs)
            self.ctx = ctx
            column = BoxLayout(orientation="vertical", padding=10, spacing=6, size_hint_y=None)
            column.bind(minimum_height=column.setter("height"))
            scroll = ScrollView(do_scroll_x=False)
            scroll.add_widget(column)
            self.labels: typing.Dict[str, MDLabel] = {key: label() for key in self.ORDER}
            for key in self.ORDER:
                column.add_widget(self.labels[key])
            self.add_widget(scroll)
            self.refresh()

        def refresh(self) -> None:
            try:
                text = self.ctx.status_text()
            except Exception as e:                  # a fault in the status must never take the window down
                text = {key: "" for key in self.ORDER}
                text["warnings"] = "! The status could not be read: %s" % e
            for key, widget in self.labels.items():
                widget.text = text.get(key, "")

    class Manager(base):
        logging_pairs = [("Client", "Archipelago"), ("Heartbeat", "Heartbeat")]
        base_title = "KOTOR 2 Archipelago Client"

        def build(self):
            container = super().build()
            self.status_view = StatusView(self.ctx)
            self.add_client_tab("Status", self.status_view)
            Clock.schedule_interval(lambda _dt: self.status_view.refresh(), 1.0)
            return container

    return Manager
