"""
Control de Cigarros — Kivy + SQLite (OFFLINE)
- +1 cigarro (smoke)
- Antojo (craving)
- Undo 10s
- Historial
- Stats básicos (texto con barras)
"""

import sqlite3
import time
from datetime import datetime, timedelta, date

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView

DB_NAME = "control_de_cigarros.db"
UNDO_SECONDS = 10


def now_ts() -> int:
    return int(time.time())


def fmt_dt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def human_delta(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    mins = seconds // 60
    hrs = mins // 60
    mins = mins % 60
    if hrs <= 0:
        return f"{mins} min"
    return f"{hrs} h {mins} min"


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('smoke','craving'))
            );
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);")
        self.conn.commit()

    def add(self, etype: str) -> int:
        cur = self.conn.cursor()
        cur.execute("INSERT INTO events (ts, type) VALUES (?, ?);", (now_ts(), etype))
        self.conn.commit()
        return int(cur.lastrowid)

    def delete(self, event_id: int):
        self.conn.execute("DELETE FROM events WHERE id=?;", (event_id,))
        self.conn.commit()

    def wipe(self):
        self.conn.execute("DELETE FROM events;")
        self.conn.commit()

    def latest(self, limit: int = 300):
        return self.conn.execute(
            "SELECT id, ts, type FROM events ORDER BY ts DESC LIMIT ?;",
            (limit,),
        ).fetchall()

    def last_smoke(self):
        return self.conn.execute(
            "SELECT id, ts FROM events WHERE type='smoke' ORDER BY ts DESC LIMIT 1;"
        ).fetchone()

    def count_smokes_in_range(self, start_ts: int, end_ts: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='smoke' AND ts>=? AND ts<?;",
            (start_ts, end_ts),
        ).fetchone()
        return int(row[0] if row else 0)

    def count_smokes_today(self) -> int:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.count_smokes_in_range(int(start.timestamp()), int(end.timestamp()))

    def intervals_today(self):
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        rows = self.conn.execute(
            "SELECT ts FROM events WHERE type='smoke' AND ts>=? AND ts<? ORDER BY ts ASC;",
            (int(start.timestamp()), int(end.timestamp())),
        ).fetchall()
        ts = [int(r[0]) for r in rows]
        if len(ts) < 2:
            return []
        return [ts[i] - ts[i - 1] for i in range(1, len(ts))]

    def counts_last_7_days(self):
        today = date.today()
        out = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            start = datetime(d.year, d.month, d.day)
            end = start + timedelta(days=1)
            c = self.count_smokes_in_range(int(start.timestamp()), int(end.timestamp()))
            out.append((d.strftime("%m-%d"), c))
        return out

    def hourly_last_14_days(self):
        end = datetime.now()
        start = end - timedelta(days=14)
        rows = self.conn.execute(
            "SELECT ts FROM events WHERE type='smoke' AND ts>=? AND ts<?;",
            (int(start.timestamp()), int(end.timestamp())),
        ).fetchall()
        buckets = [0] * 24
        for (ts,) in rows:
            h = datetime.fromtimestamp(int(ts)).hour
            buckets[h] += 1
        return buckets

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class HomeScreen(Screen):
    today_count = NumericProperty(0)
    last_time = StringProperty("—")
    since_last = StringProperty("—")
    avg_interval = StringProperty("—")
    shortest_interval = StringProperty("—")

    undo_visible = BooleanProperty(False)
    undo_text = StringProperty("")
    _undo_id = None
    _undo_deadline = None
    _undo_ev = None

    def on_pre_enter(self):
        self.refresh()

    def refresh(self, *_):
        app = App.get_running_app()
        s = app.store

        self.today_count = s.count_smokes_today()

        last = s.last_smoke()
        if last:
            _, ts = last
            self.last_time = fmt_dt(int(ts))
            self.since_last = human_delta(now_ts() - int(ts))
        else:
            self.last_time = "—"
            self.since_last = "—"

        intervals = s.intervals_today()
        if intervals:
            avg = int(sum(intervals) / len(intervals))
            self.avg_interval = human_delta(avg)
            self.shortest_interval = human_delta(min(intervals))
        else:
            self.avg_interval = "—"
            self.shortest_interval = "—"

    def add_smoke(self):
        app = App.get_running_app()
        eid = app.store.add("smoke")
        self._arm_undo(eid)
        self.refresh()

    def add_craving(self):
        app = App.get_running_app()
        eid = app.store.add("craving")
        self._arm_undo(eid)
        self.refresh()

    def _arm_undo(self, eid: int):
        self._undo_id = eid
        self._undo_deadline = now_ts() + UNDO_SECONDS
        self.undo_visible = True
        if self._undo_ev:
            self._undo_ev.cancel()
        self._undo_ev = Clock.schedule_interval(self._tick_undo, 0.2)

    def _tick_undo(self, *_):
        if self._undo_deadline is None:
            return False
        remaining = self._undo_deadline - now_ts()
        if remaining <= 0:
            self.undo_visible = False
            self._undo_id = None
            self._undo_deadline = None
            self.undo_text = ""
            return False
        self.undo_text = f"Deshacer disponible: {remaining}s"
        return True

    def undo(self):
        if not self._undo_id:
            return
        app = App.get_running_app()
        app.store.delete(self._undo_id)
        self.undo_visible = False
        self._undo_id = None
        self._undo_deadline = None
        self.undo_text = ""
        self.refresh()
        app.root_sm.get_screen("history").refresh()
        app.root_sm.get_screen("stats").refresh()


class HistoryScreen(Screen):
    items_text = StringProperty("")

    def on_pre_enter(self):
        self.refresh()

    def refresh(self, *_):
        app = App.get_running_app()
        rows = app.store.latest(300)
        if not rows:
            self.items_text = "Sin registros todavía."
            return

        lines = []
        for _, ts, t in rows:
            tag = "🚬" if t == "smoke" else "⚡"
            lines.append(f"{fmt_dt(int(ts))}  {tag}  {t}")
        self.items_text = "\n".join(lines)


class StatsScreen(Screen):
    stats_text = StringProperty("")

    def on_pre_enter(self):
        self.refresh()

    def refresh(self, *_):
        app = App.get_running_app()
        s = app.store

        last7 = s.counts_last_7_days()
        hours = s.hourly_last_14_days()

        top_hour = max(range(24), key=lambda h: hours[h]) if any(hours) else None
        top_hour_txt = f"{top_hour:02d}:00" if top_hour is not None and hours[top_hour] > 0 else "—"

        lines = []
        lines.append("📈 Últimos 7 días (cigarros):")
        for d, c in last7:
            bar = "▮" * min(c, 20)
            lines.append(f"  {d}: {c:>2} {bar}")

        lines.append("")
        lines.append("🕒 Distribución por hora (últimos 14 días):")
        lines.append(f"  Hora pico: {top_hour_txt}")
        for h in range(0, 24, 2):
            c = hours[h] + hours[h + 1]
            bar = "▮" * min(c, 30)
            lines.append(f"  {h:02d}-{h+2:02d}: {c:>2} {bar}")

        lines.append("")
        lines.append("🧠 Hoy:")
        lines.append(f"  Total hoy: {s.count_smokes_today()}")
        intervals = s.intervals_today()
        if intervals:
            avg = int(sum(intervals) / len(intervals))
            lines.append(f"  Intervalo promedio: {human_delta(avg)}")
            lines.append(f"  Intervalo más corto: {human_delta(min(intervals))}")
        else:
            lines.append("  Intervalos: —")

        self.stats_text = "\n".join(lines)

    def wipe_all(self):
        app = App.get_running_app()
        if app.confirm_wipe():
            app.store.wipe()
            self.refresh()
            app.root_sm.get_screen("home").refresh()
            app.root_sm.get_screen("history").refresh()


class ControlDeCigarrosApp(App):
    def build(self):
        self.title = "Control de Cigarros"
        self.store = Store(DB_NAME)

        sm = ScreenManager()
        self.root_sm = sm

        home = HomeScreen(name="home")
        hist = HistoryScreen(name="history")
        stats = StatsScreen(name="stats")

        home.add_widget(self._home_layout(home))
        hist.add_widget(self._text_screen_layout("Historial", hist, "items_text", on_refresh=hist.refresh))
        stats.add_widget(self._stats_layout(stats))

        sm.add_widget(home)
        sm.add_widget(hist)
        sm.add_widget(stats)

        root = BoxLayout(orientation="vertical")
        root.add_widget(sm)

        nav = BoxLayout(size_hint_y=None, height=dp(56), padding=dp(6), spacing=dp(6))
        nav.add_widget(Button(text="Home", on_release=lambda *_: setattr(sm, "current", "home")))
        nav.add_widget(Button(text="Historial", on_release=lambda *_: setattr(sm, "current", "history")))
        nav.add_widget(Button(text="Stats", on_release=lambda *_: setattr(sm, "current", "stats")))
        root.add_widget(nav)

        Clock.schedule_interval(lambda *_: home.refresh(), 10)
        return root

    def _home_layout(self, screen: HomeScreen):
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))

        lbl_count = Label(text="0", font_size="64sp", size_hint_y=None, height=dp(110))
        lbl_sub = Label(text="Cigarros hoy", font_size="18sp", size_hint_y=None, height=dp(30))

        def upd_count(*_):
            lbl_count.text = str(screen.today_count)

        screen.bind(today_count=lambda *_: upd_count())
        upd_count()

        btn_smoke = Button(text="+1 (Fumé)", font_size="24sp", size_hint_y=None, height=dp(84))
        btn_crave = Button(text="Antojo (urge)", font_size="18sp", size_hint_y=None, height=dp(64))
        btn_smoke.bind(on_release=lambda *_: screen.add_smoke())
        btn_crave.bind(on_release=lambda *_: screen.add_craving())

        undo_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        lbl_undo = Label(text="", font_size="14sp", halign="left", valign="middle")
        btn_undo = Button(text="Deshacer", size_hint_x=None, width=dp(140))
        btn_undo.bind(on_release=lambda *_: screen.undo())

        def upd_undo(*_):
            if screen.undo_visible:
                lbl_undo.text = screen.undo_text
                btn_undo.disabled = False
            else:
                lbl_undo.text = ""
                btn_undo.disabled = True

        screen.bind(undo_visible=lambda *_: upd_undo())
        screen.bind(undo_text=lambda *_: upd_undo())
        upd_undo()

        lbl_last = Label(text="", font_size="16sp", halign="left", valign="top")
        lbl_since = Label(text="", font_size="16sp", halign="left", valign="top")
        lbl_avg = Label(text="", font_size="16sp", halign="left", valign="top")
        lbl_short = Label(text="", font_size="16sp", halign="left", valign="top")

        def upd_quick(*_):
            lbl_last.text = f"Último: {screen.last_time}"
            lbl_since.text = f"Desde el último: {screen.since_last}"
            lbl_avg.text = f"Promedio hoy: {screen.avg_interval}"
            lbl_short.text = f"Más corto hoy: {screen.shortest_interval}"

        for prop in ("last_time", "since_last", "avg_interval", "shortest_interval"):
            screen.bind(**{prop: lambda *_: upd_quick()})
        upd_quick()

        undo_row.add_widget(lbl_undo)
        undo_row.add_widget(btn_undo)

        root.add_widget(lbl_count)
        root.add_widget(lbl_sub)
        root.add_widget(btn_smoke)
        root.add_widget(btn_crave)
        root.add_widget(undo_row)
        root.add_widget(lbl_last)
        root.add_widget(lbl_since)
        root.add_widget(lbl_avg)
        root.add_widget(lbl_short)
        return root

    def _text_screen_layout(self, title: str, screen_obj, prop_name: str, on_refresh):
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))

        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        header.add_widget(Label(text=title, font_size="20sp"))
        header.add_widget(Button(text="Refrescar", size_hint_x=None, width=dp(160), on_release=lambda *_: on_refresh()))
        root.add_widget(header)

        sv = ScrollView()
        lbl = Label(text="", font_size="14sp", halign="left", valign="top", size_hint_y=None)
        lbl.bind(width=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))

        def upd(*_):
            text = getattr(screen_obj, prop_name)
            lbl.text = text
            lbl.texture_update()
            lbl.height = lbl.texture_size[1] + dp(20)

        screen_obj.bind(**{prop_name: lambda *_: upd()})
        upd()

        sv.add_widget(lbl)
        root.add_widget(sv)
        return root

    def _stats_layout(self, screen: StatsScreen):
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))

        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        header.add_widget(Label(text="Stats", font_size="20sp"))
        header.add_widget(Button(text="Refrescar", size_hint_x=None, width=dp(160), on_release=lambda *_: screen.refresh()))
        header.add_widget(Button(text="Borrar todo", size_hint_x=None, width=dp(160), on_release=lambda *_: screen.wipe_all()))
        root.add_widget(header)

        # reuse text layout
        tmp = self._text_screen_layout("", screen, "stats_text", on_refresh=screen.refresh)
        # remove empty title header from tmp (first child is header)
        tmp.remove_widget(tmp.children[-1])  # header
        root.add_widget(tmp.children[0])     # scrollview
        return root

    def confirm_wipe(self) -> bool:
        result = {"ok": False}

        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(Label(text="¿Borrar TODOS los registros?\nEsto no se puede deshacer.", halign="center"))

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_cancel = Button(text="Cancelar")
        b_ok = Button(text="Borrar")
        row.add_widget(b_cancel)
        row.add_widget(b_ok)
        box.add_widget(row)

        popup = Popup(title="Confirmar", content=box, size_hint=(0.85, 0.35), auto_dismiss=False)

        def _cancel(*_):
            result["ok"] = False
            popup.dismiss()

        def _ok(*_):
            result["ok"] = True
            popup.dismiss()

        b_cancel.bind(on_release=_cancel)
        b_ok.bind(on_release=_ok)
        popup.open()

        # Bloqueo simple (ok para prototipo)
        from kivy.base import EventLoop
        while popup.parent is not None:
            EventLoop.idle()

        return result["ok"]

    def on_stop(self):
        self.store.close()


if __name__ == "__main__":
    ControlDeCigarrosApp().run()
