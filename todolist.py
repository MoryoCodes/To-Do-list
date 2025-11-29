import tkinter as tk
import time
import threading
import random
import openai  # pip install openai

FILENAME = "Tasks.txt"

# =========================
# THEME SYSTEM
# =========================
current_theme = "light"

THEMES = {
    "light": {
        "BG_WINDOW": "#f0f0f0",
        "BG_CANVAS": "#fdfcf7",
        "BG_COMPLETED": "#f5f5f5",
        "FG_TEXT": "#222222",
        "FG_SUBTLE": "#999999",
        "LINE_BLUE": "#d3e4ff",
        "LINE_MARGIN": "#ff9999",
        "BTN_BG": "#ffffff",
        "BTN_FG": "#333333",
        "DIM_TEXT": "#bbbbbb",
    },
    "dark": {
        "BG_WINDOW": "#1e1e1e",
        "BG_CANVAS": "#252526",
        "BG_COMPLETED": "#1e1e1e",
        "FG_TEXT": "#f5f5f5",
        "FG_SUBTLE": "#777777",
        "LINE_BLUE": "#3a4d6e",
        "LINE_MARGIN": "#a65c5c",
        "BTN_BG": "#3a3d41",
        "BTN_FG": "#f5f5f5",
        "DIM_TEXT": "#555555",
    }
}

COLORS = THEMES[current_theme].copy()

# =========================
# GLOBAL STATE
# =========================
tasks = []            # list of {text, done, chars, check, y, box, priority, star}
completed_tasks = []  # list of {"text": str, "priority": int}
postits = []          # list of post-it dicts

# typing state
current_text = ""
current_text_items = []
caret = None
caret_active = False
current_y = None

# post-it placement state
placing_postit = False
postit_text_to_place = ""
postit_color_to_place = "#FFF9B0"
preview_postit = None  # {"rect": ..., "text": ...}

# dragging post-its
dragging_postit = None
last_drag_pos = (0, 0)

CHAR_WIDTH = 10
TEXT_START_X = 70
LINE_START_Y = 70
LINE_HEIGHT = 30

NOTE_WIDTH_RATIO = 0.75      # writing area
COMPLETE_WIDTH_RATIO = 0.25  # completed area

POSTIT_COLORS = {
    "Yellow": "#FFF9B0",
    "Pink":   "#FFD1DC",
    "Blue":   "#D0E8FF",
    "Green":  "#E4FFD1",
    "Purple": "#EAD9FF",
}

# widgets (assigned later)
window = None
canvas = None
completed_canvas = None
postit_button = None
search_label = None
search_entry = None
ai_button = None
toggle_canvas = None
toggle_bg = None
toggle_knob = None
tab_frame = None
cleanup_button = None

# tabs
tabs = {}          # name -> {"tasks": [...], "completed": [...], "postits": [...]}
current_tab = None


# =========================
# THEME APPLY
# =========================
def apply_theme():
    global COLORS
    COLORS = THEMES[current_theme].copy()

    if window is None:
        return

    window.configure(bg=COLORS["BG_WINDOW"])
    if canvas:
        canvas.configure(bg=COLORS["BG_CANVAS"])
    if completed_canvas:
        completed_canvas.configure(bg=COLORS["BG_COMPLETED"])
        for item in completed_canvas.find_all():
            completed_canvas.itemconfig(item, fill=COLORS["FG_TEXT"])

    if postit_button:
        postit_button.configure(bg=COLORS["BTN_BG"], fg=COLORS["BTN_FG"])
    if search_label:
        search_label.configure(bg=COLORS["BG_WINDOW"], fg=COLORS["FG_TEXT"])
    if search_entry:
        search_entry.configure(
            bg=COLORS["BG_CANVAS"],
            fg=COLORS["FG_TEXT"],
            insertbackground=COLORS["FG_TEXT"],
        )
    if ai_button:
        ai_button.configure(bg=COLORS["BTN_BG"], fg=COLORS["BTN_FG"])
    if cleanup_button:
        cleanup_button.configure(bg=COLORS["BTN_BG"], fg=COLORS["BTN_FG"])

    # Recolor tasks
    for t in tasks:
        canvas.itemconfig(t["box"], outline=COLORS["FG_SUBTLE"])
        canvas.itemconfig(t["check"], fill=COLORS["FG_TEXT"] if t["done"] else "")
        for ch_item in t["chars"]:
            canvas.itemconfig(ch_item, fill=COLORS["FG_TEXT"])
        canvas.itemconfig(t["star"], fill="#e6b800")

    redraw_lines()


# =========================
# TASKS: SAVE / CREATE / ERASE / COMPLETE
# =========================
def save_tasks():
    with open(FILENAME, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(f"{t['text']}||{t['done']}||{t['priority']}\n")


def create_task(text, done=False, priority=0):
    """Create a new task at the bottom of the list."""
    y = LINE_START_Y + len(tasks) * LINE_HEIGHT

    # checkbox
    box = canvas.create_rectangle(
        35, y - 10, 50, y + 5,
        outline=COLORS["FG_SUBTLE"], width=2
    )

    # checkmark
    check = canvas.create_line(
        37, y - 2, 43, y + 3, 48, y - 7,
        width=2,
        fill=COLORS["FG_TEXT"] if done else "",
    )

    # one canvas text item per letter
    char_items = []
    for i, ch in enumerate(text):
        item = canvas.create_text(
            TEXT_START_X + i * CHAR_WIDTH, y - 2,
            text=ch,
            anchor="w",
            font=("Courier New", 14),
            fill=COLORS["FG_TEXT"]
        )
        char_items.append(item)

    # priority stars
    star_x = max(200, canvas.winfo_width() * 0.72 or 480)
    stars_text = "★" * priority + "☆" * (3 - priority)
    star_item = canvas.create_text(
        star_x, y - 2,
        text=stars_text,
        anchor="e",
        font=("Courier New", 14),
        fill="#e6b800"
    )

    task = {
        "text": text,
        "done": done,
        "chars": char_items,
        "check": check,
        "y": y,
        "box": box,
        "priority": priority,
        "star": star_item,
    }

    tasks.append(task)

    # click bindings
    canvas.tag_bind(box, "<Button-1>", lambda e, t=task: toggle_task(t))
    canvas.tag_bind(check, "<Button-1>", lambda e, t=task: toggle_task(t))
    canvas.tag_bind(star_item, "<Button-1>", lambda e, t=task: toggle_priority(t))
    for ch_item in char_items:
        canvas.tag_bind(ch_item, "<Button-1>", lambda e, t=task: toggle_task(t))


# ------------------- ERASER CRUMBS ----------------------
def spawn_crumb(x, y):
    """Small crumb that falls and fades."""
    crumb = canvas.create_oval(x, y, x + 3, y + 3, fill="#C8B8A8", outline="")

    def animate():
        for i in range(15):
            dx = random.randint(-1, 1)
            dy = random.randint(1, 3)
            canvas.move(crumb, dx, dy)
            alpha = max(0, 255 - i * 12)
            canvas.itemconfig(crumb, fill=f"#{alpha:02x}{alpha:02x}{alpha:02x}")
            canvas.update()
            time.sleep(0.02)
        canvas.delete(crumb)

    threading.Thread(target=animate, daemon=True).start()


def erase_animation(task, on_finish=None):
    """Erase letters with fade + crumbs."""
    for item in task["chars"]:
        box = canvas.bbox(item)
        if box:
            mid_x = (box[0] + box[2]) // 2
            mid_y = (box[1] + box[3]) // 2
        else:
            mid_x = mid_y = 0

        for alpha in range(255, -1, -15):
            canvas.itemconfig(item, fill=f"#{alpha:02x}{alpha:02x}{alpha:02x}")
            if alpha % 45 == 0 and box:
                spawn_crumb(mid_x, mid_y)
            canvas.update()
            time.sleep(0.01)

        canvas.itemconfig(item, text="")

    if on_finish:
        on_finish()


# ---------------- COMPLETED TASKS COLUMN ----------------
def add_completed_task(text, priority=0):
    y = 60 + len(completed_tasks) * 25

    text_id = completed_canvas.create_text(
        10,
        y,
        anchor="w",
        font=("Courier New", 12),
        text=text,
        fill=COLORS["FG_TEXT"],
    )

    # strikethrough
    bbox = completed_canvas.bbox(text_id)
    if bbox:
        x1, y1, x2, y2 = bbox
        completed_canvas.create_line(
            x1, (y1 + y2) // 2, x2, (y1 + y2) // 2,
            fill=COLORS["FG_TEXT"],
            width=2
        )

    stars_text = "★" * priority + "☆" * (3 - priority)
    completed_canvas.create_text(
        completed_canvas.winfo_width() - 10,
        y,
        anchor="e",
        font=("Courier New", 10),
        text=stars_text,
        fill="#e6b800"
    )

    completed_tasks.append({"text": text, "priority": priority})


# ------------------ PRIORITY STARS ----------------------
def toggle_priority(task):
    task["priority"] = (task["priority"] + 1) % 4
    stars_text = "★" * task["priority"] + "☆" * (3 - task["priority"])
    canvas.itemconfig(task["star"], text=stars_text)
    save_tasks()


# ---------------- CHECK / UNCHECK TASK ------------------
def toggle_task(task):
    if not task["done"]:
        task["done"] = True
        canvas.itemconfig(task["check"], fill=COLORS["FG_TEXT"])

        def after():
            add_completed_task(task["text"], task["priority"])
            delete_task(task)

        threading.Thread(
            target=erase_animation,
            args=(task, after),
            daemon=True
        ).start()
    else:
        task["done"] = False
        canvas.itemconfig(task["check"], fill="")
        for i, ch in enumerate(task["text"]):
            canvas.itemconfig(task["chars"][i], text=ch, fill=COLORS["FG_TEXT"])

    save_tasks()


def delete_task(task):
    # unpin post-its attached to this task
    for p in postits:
        if p.get("pinned_task") is task:
            p["pinned_task"] = None
            canvas.itemconfig(p["pin"], fill="grey")

    for item in task["chars"]:
        canvas.delete(item)
    canvas.delete(task["check"])
    canvas.delete(task["box"])
    canvas.delete(task["star"])

    tasks.remove(task)
    save_tasks()

    # re-layout tasks and pinned post-its
    for i, t in enumerate(tasks):
        new_y = LINE_START_Y + i * LINE_HEIGHT
        t["y"] = new_y

        canvas.coords(t["box"], 35, new_y - 10, 50, new_y + 5)
        canvas.coords(t["check"], 37, new_y - 2, 43, new_y + 3, 48, new_y - 7)

        for j, ch_item in enumerate(t["chars"]):
            canvas.coords(ch_item, TEXT_START_X + j * CHAR_WIDTH, new_y - 2)

        star_x = max(200, canvas.winfo_width() * 0.72 or 480)
        canvas.coords(t["star"], star_x, new_y - 2)

        # move post-its pinned to this task
        for p in postits:
            if p.get("pinned_task") is t:
                x1, y1, x2, y2 = canvas.coords(p["rect"])
                target_y = new_y - 40
                dy = target_y - y1
                for obj in (p["shadow"], p["rect"], p["text"], p["delete"], p["pin"]):
                    canvas.move(obj, 0, dy)


# =========================
# NOTEBOOK LINES + MARGIN
# =========================
def redraw_lines(event=None):
    canvas.delete("notepad_line")
    width = canvas.winfo_width()

    # red margin on the left
    canvas.create_line(
        60, LINE_START_Y - 40, 60, canvas.winfo_height() - 10,
        fill=COLORS["LINE_MARGIN"],
        width=2,
        tags="notepad_line"
    )

    # horizontal blue lines
    for i in range(LINE_START_Y, canvas.winfo_height(), LINE_HEIGHT):
        canvas.create_line(
            20, i, width - 20, i,
            fill=COLORS["LINE_BLUE"],
            tags="notepad_line"
        )


# =========================
# TYPING DIRECTLY ON PAPER
# =========================
def clear_current_input():
    global current_text, current_text_items, caret, caret_active, current_y
    for item in current_text_items:
        canvas.delete(item)
    current_text_items.clear()

    if caret:
        canvas.delete(caret)

    caret = None
    current_text = ""
    current_y = None
    caret_active = False


def blink_caret():
    if not caret_active or caret is None:
        return
    state = canvas.itemcget(caret, "state")
    canvas.itemconfig(caret, state="hidden" if state == "normal" else "normal")
    window.after(500, blink_caret)


def start_typing():
    global current_text, caret_active, current_y, caret
    clear_current_input()

    current_y = LINE_START_Y + len(tasks) * LINE_HEIGHT
    caret_active = True

    caret = canvas.create_line(
        TEXT_START_X, current_y - 10,
        TEXT_START_X, current_y + 5,
        width=2,
        fill=COLORS["FG_TEXT"]
    )
    blink_caret()


def on_key_press(event):
    global current_text, current_text_items, caret, current_y, caret_active

    if not caret_active or current_y is None:
        return

    if event.keysym == "Return":
        txt = current_text.strip()
        if txt:
            create_task(txt)
            save_tasks()
        clear_current_input()
        redraw_lines()
        on_search_change()
        return

    if event.keysym == "BackSpace":
        if current_text_items:
            last = current_text_items.pop()
            canvas.delete(last)
            current_text = current_text[:-1]
            new_x = TEXT_START_X + len(current_text_items) * CHAR_WIDTH
            canvas.coords(caret, new_x, current_y - 10, new_x, current_y + 5)
        return

    if not event.char.isprintable():
        return

    ch = event.char
    x = TEXT_START_X + len(current_text_items) * CHAR_WIDTH
    y = current_y - 2

    item = canvas.create_text(
        x, y,
        text=ch,
        anchor="w",
        font=("Courier New", 14),
        fill=COLORS["FG_TEXT"]
    )

    current_text_items.append(item)
    current_text += ch

    new_x = x + CHAR_WIDTH
    canvas.coords(caret, new_x, current_y - 10, new_x, current_y + 5)


# =========================
# POST-ITS: DELETE / PIN / DRAG
# =========================
def delete_postit(p):
    for part in (p["shadow"], p["rect"], p["text"], p["delete"], p["pin"]):
        canvas.delete(part)
    postits.remove(p)


def toggle_pin(p):
    """Pin to nearest task, or unpin."""
    if p.get("pinned_task") is None:
        if not tasks:
            return
        x1, y1, x2, y2 = canvas.coords(p["rect"])
        center_y = (y1 + y2) / 2

        nearest = min(tasks, key=lambda t: abs(t["y"] - center_y))
        p["pinned_task"] = nearest

        target_y = nearest["y"] - 40
        dy = target_y - y1
        for obj in (p["shadow"], p["rect"], p["text"], p["delete"], p["pin"]):
            canvas.move(obj, 0, dy)

        canvas.itemconfig(p["pin"], fill="red")
    else:
        p["pinned_task"] = None
        canvas.itemconfig(p["pin"], fill="grey")


def start_postit_drag(p, event):
    """Begin dragging a post-it if it is not pinned."""
    global dragging_postit, last_drag_pos
    if p.get("pinned_task") is not None:
        return
    dragging_postit = p
    last_drag_pos = (event.x, event.y)


def drag_postit_motion(event):
    global dragging_postit, last_drag_pos
    if dragging_postit is None:
        return
    x, y = event.x, event.y
    dx = x - last_drag_pos[0]
    dy = y - last_drag_pos[1]
    last_drag_pos = (x, y)

    for obj in (dragging_postit["shadow"], dragging_postit["rect"],
                dragging_postit["text"], dragging_postit["delete"], dragging_postit["pin"]):
        canvas.move(obj, dx, dy)


def end_postit_drag(event):
    global dragging_postit
    dragging_postit = None


# =========================
# POST-ITS: CREATE / PLACE
# =========================
def create_postit_at(x, y, text, color):
    shadow = canvas.create_rectangle(
        x + 4, y + 6, x + 144, y + 126,
        fill="#c4c4c4", outline="", width=0
    )

    rect = canvas.create_rectangle(
        x, y, x + 140, y + 120,
        fill=color, outline="#E0C96F", width=3
    )
    text_id = canvas.create_text(
        x + 10, y + 10,
        anchor="nw",
        text=text,
        width=120,
        font=("Segoe UI", 11),
        fill="#111111"
    )

    delete_btn = canvas.create_text(
        x + 130, y + 10,
        text="✖",
        font=("Segoe UI", 11),
        fill="grey"
    )

    pin_btn = canvas.create_text(
        x + 120, y + 30,
        text="📌",
        font=("Segoe UI", 11),
        fill="grey"
    )

    canvas.tag_raise(rect)
    canvas.tag_raise(text_id)
    canvas.tag_raise(delete_btn)
    canvas.tag_raise(pin_btn)

    p = {
        "shadow": shadow,
        "rect": rect,
        "text": text_id,
        "delete": delete_btn,
        "pin": pin_btn,
        "color": color,
        "pinned_task": None,
    }
    postits.append(p)

    # bindings
    canvas.tag_bind(rect, "<Button-1>", lambda e, p=p: start_postit_drag(p, e))
    canvas.tag_bind(text_id, "<Button-1>", lambda e, p=p: start_postit_drag(p, e))
    canvas.tag_bind(delete_btn, "<Button-1>", lambda e, p=p: delete_postit(p))
    canvas.tag_bind(pin_btn, "<Button-1>", lambda e, p=p: toggle_pin(p))


def place_postit_at(x, y, text, color):
    start_y = y - 30
    final_y = y

    # shadow (behind)
    shadow = canvas.create_rectangle(
        x + 4, start_y + 6, x + 144, start_y + 126,
        fill="#c4c4c4", outline="", width=0
    )

    rect = canvas.create_rectangle(
        x, start_y, x + 140, start_y + 120,
        fill=color, outline="#E0C96F", width=3
    )
    text_id = canvas.create_text(
        x + 10, start_y + 10,
        anchor="nw",
        text=text,
        width=120,
        font=("Segoe UI", 11),
        fill="#111111"
    )

    delete_btn = canvas.create_text(
        x + 130, start_y + 10,
        text="✖",
        font=("Segoe UI", 11),
        fill="grey"
    )

    pin_btn = canvas.create_text(
        x + 120, start_y + 30,
        text="📌",
        font=("Segoe UI", 11),
        fill="grey"
    )

    # bring controls on top
    canvas.tag_raise(rect)
    canvas.tag_raise(text_id)
    canvas.tag_raise(delete_btn)
    canvas.tag_raise(pin_btn)

    # drop animation
    for _ in range(10):
        dy = (final_y - start_y) / 10
        for obj in (shadow, rect, text_id, delete_btn, pin_btn):
            canvas.move(obj, 0, dy)
        canvas.update()
        time.sleep(0.02)

    # small bounce
    for _ in range(3):
        for obj in (shadow, rect, text_id, delete_btn, pin_btn):
            canvas.move(obj, 0, -2)
        canvas.update()
        time.sleep(0.02)

    for _ in range(3):
        for obj in (shadow, rect, text_id, delete_btn, pin_btn):
            canvas.move(obj, 0, 2)
        canvas.update()
        time.sleep(0.02)

    p = {
        "shadow": shadow,
        "rect": rect,
        "text": text_id,
        "delete": delete_btn,
        "pin": pin_btn,
        "color": color,
        "pinned_task": None,
    }
    postits.append(p)

    # bindings
    canvas.tag_bind(rect, "<Button-1>", lambda e, p=p: start_postit_drag(p, e))
    canvas.tag_bind(text_id, "<Button-1>", lambda e, p=p: start_postit_drag(p, e))
    canvas.tag_bind(delete_btn, "<Button-1>", lambda e, p=p: delete_postit(p))
    canvas.tag_bind(pin_btn, "<Button-1>", lambda e, p=p: toggle_pin(p))


# =========================
# POST-IT PREVIEW (GHOST)
# =========================
def create_postit_preview(text):
    global placing_postit, postit_text_to_place, preview_postit

    if preview_postit:
        canvas.delete(preview_postit["rect"])
        canvas.delete(preview_postit["text"])
        preview_postit = None

    placing_postit = True
    postit_text_to_place = text

    x, y = 150, 150

    rect = canvas.create_rectangle(
        x, y, x + 140, y + 120,
        fill="#FFFDE1",
        outline="#E0C96F",
        width=2
    )
    text_id = canvas.create_text(
        x + 10,
        y + 10,
        anchor="nw",
        text=text,
        width=120,
        font=("Segoe UI", 11),
        fill="#555555"
    )

    preview_postit = {"rect": rect, "text": text_id}


def open_postit_input():
    """Popup to type a post-it and choose color."""
    popup = tk.Toplevel(window)
    popup.title("New Post-it")
    popup.geometry("300x200")
    popup.configure(bg=COLORS["BG_WINDOW"])

    tk.Label(popup, text="Write your Post-it:", fg=COLORS["FG_TEXT"], bg=COLORS["BG_WINDOW"]).pack(pady=5)
    entry = tk.Entry(popup, width=30)
    entry.pack(pady=5)

    tk.Label(popup, text="Color:", fg=COLORS["FG_TEXT"], bg=COLORS["BG_WINDOW"]).pack(pady=5)

    color_var = tk.StringVar(popup)
    color_var.set("Yellow")
    tk.OptionMenu(popup, color_var, *POSTIT_COLORS.keys()).pack(pady=5)

    def confirm():
        global postit_color_to_place
        txt = entry.get().strip()
        if txt:
            postit_color_to_place = POSTIT_COLORS[color_var.get()]
            create_postit_preview(txt)
        popup.destroy()

    tk.Button(popup, text="Add", command=confirm).pack(pady=10)


def on_mouse_move(event):
    """Move ghost preview while placing."""
    if not placing_postit or preview_postit is None:
        return

    x, y = event.x, event.y
    max_w = canvas.winfo_width() - 140
    max_h = canvas.winfo_height() - 120

    x = max(0, min(x, max_w))
    y = max(0, min(y, max_h))

    canvas.coords(preview_postit["rect"], x, y, x + 140, y + 120)
    canvas.coords(preview_postit["text"], x + 10, y + 10)


def on_right_click(event):
    """Right-click to stick the post-it."""
    global placing_postit, postit_text_to_place, preview_postit

    if not placing_postit or preview_postit is None:
        return

    x1, y1, x2, y2 = canvas.coords(preview_postit["rect"])
    text = postit_text_to_place
    color = postit_color_to_place

    canvas.delete(preview_postit["rect"])
    canvas.delete(preview_postit["text"])
    preview_postit = None

    placing_postit = False
    postit_text_to_place = ""

    threading.Thread(
        target=place_postit_at,
        args=(x1, y1, text, color),
        daemon=True
    ).start()


# =========================
# SEARCH BAR + HIGHLIGHT
# =========================
def clear_search(event=None):
    """Clear search and reset text colors."""
    search_entry.delete(0, tk.END)
    for t in tasks:
        for ch in t["chars"]:
            canvas.itemconfig(ch, fill=COLORS["FG_TEXT"], font=("Courier New", 14))


def on_search_change(event=None):
    """Highlight matching tasks by bright text, dim others."""
    query = search_entry.get().strip().lower()

    for t in tasks:
        text_lower = t["text"].lower()
        if query and query in text_lower:
            # highlight match
            for ch_item in t["chars"]:
                canvas.itemconfig(ch_item, fill="#ffd300", font=("Courier New", 14, "bold"))
        else:
            # dim or reset
            color = COLORS["DIM_TEXT"] if query else COLORS["FG_TEXT"]
            for ch_item in t["chars"]:
                canvas.itemconfig(ch_item, fill=color, font=("Courier New", 14))


# =========================
# CLICK HANDLING / LOAD / LAYOUT
# =========================
def on_canvas_click(event):
    if placing_postit:
        return

    # click off search
    clear_search()

    # if clicking on a post-it element, don't start typing
    item = canvas.find_withtag("current")
    if item:
        for p in postits:
            if item[0] in (p["shadow"], p["rect"], p["text"], p["delete"], p["pin"]):
                return

    next_y = LINE_START_Y + len(tasks) * LINE_HEIGHT
    if event.y >= next_y - 15:
        start_typing()


def load_tasks():
    try:
        with open(FILENAME, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("||")
                if len(parts) == 2:
                    text, done = parts
                    priority = 0
                elif len(parts) == 3:
                    text, done, priority = parts
                    priority = int(priority)
                else:
                    continue
                create_task(text, done == "True", priority)
    except FileNotFoundError:
        pass


def clear_current_page_ui():
    global tasks, completed_tasks, postits
    # clear tasks
    for t in tasks:
        for item in t["chars"]:
            canvas.delete(item)
        canvas.delete(t["check"])
        canvas.delete(t["box"])
        canvas.delete(t["star"])
    tasks = []

    # clear completed
    completed_canvas.delete("all")
    completed_tasks = []
    completed_canvas.create_text(
        10, 20,
        anchor="w",
        text="Completed Tasks",
        font=("Segoe UI", 14, "bold"),
        fill=COLORS["FG_TEXT"]
    )

    # clear post-its
    for p in postits:
        for part in (p["shadow"], p["rect"], p["text"], p["delete"], p["pin"]):
            canvas.delete(part)
    postits = []

    clear_current_input()
    redraw_lines()


# =========================
# TABS: SAVE / LOAD / SWITCH
# =========================
def save_current_tab_model():
    if current_tab is None:
        return

    model = {"tasks": [], "completed": [], "postits": []}

    for t in tasks:
        model["tasks"].append({
            "text": t["text"],
            "done": t["done"],
            "priority": t["priority"],
        })

    for c in completed_tasks:
        model["completed"].append({
            "text": c["text"],
            "priority": c["priority"],
        })

    for p in postits:
        x1, y1, x2, y2 = canvas.coords(p["rect"])
        txt = canvas.itemcget(p["text"], "text")
        model["postits"].append({
            "text": txt,
            "color": p["color"],
            "x": x1,
            "y": y1,
        })

    tabs[current_tab] = model


def load_tab_model(name):
    global current_tab
    clear_current_page_ui()

    model = tabs.get(name, {"tasks": [], "completed": [], "postits": []})

    for tmodel in model["tasks"]:
        create_task(tmodel["text"], tmodel["done"], tmodel["priority"])

    for cmodel in model["completed"]:
        add_completed_task(cmodel["text"], cmodel["priority"])

    for pmodel in model["postits"]:
        create_postit_at(pmodel["x"], pmodel["y"], pmodel["text"], pmodel["color"])

    current_tab = name
    refresh_tab_bar()


def switch_tab(name):
    global current_tab
    if current_tab == name:
        return

    save_current_tab_model()

    if name not in tabs:
        tabs[name] = {"tasks": [], "completed": [], "postits": []}

    load_tab_model(name)


def add_new_tab():
    idx = len(tabs) + 1
    name = f"Page {idx}"
    tabs[name] = {"tasks": [], "completed": [], "postits": []}
    switch_tab(name)


def refresh_tab_bar():
    if tab_frame is None:
        return

    for w in tab_frame.winfo_children():
        w.destroy()

    for name in tabs.keys():
        is_active = (name == current_tab)
        btn = tk.Button(
            tab_frame,
            text=name,
            relief="sunken" if is_active else "flat",
            bg="#dddddd" if is_active else "#cccccc",
            padx=8,
            pady=1,
            command=lambda n=name: switch_tab(n)
        )
        btn.pack(side="left", padx=(0, 2))

    plus_btn = tk.Button(
        tab_frame,
        text="+",
        relief="flat",
        bg="#cccccc",
        padx=6,
        pady=1,
        command=add_new_tab
    )
    plus_btn.pack(side="left")


def init_tabs():
    global current_tab
    if not tabs:
        tabs["Page 1"] = {"tasks": [], "completed": [], "postits": []}
    current_tab = "Page 1"
    save_current_tab_model()
    refresh_tab_bar()


def update_layout(event=None):
    """Resize left (notepad) and right (completed) areas."""
    W = window.winfo_width()
    H = window.winfo_height()

    note_w = int(W * NOTE_WIDTH_RATIO)
    comp_w = W - note_w

    canvas.place(x=0, y=45, width=note_w, height=H - 55)
    completed_canvas.place(x=note_w, y=45, width=comp_w, height=H - 55)

    if cleanup_button:
        cleanup_button.place(x=note_w - 140, y=10)

    redraw_lines()

    star_x = max(200, canvas.winfo_width() * 0.72 or 480)
    for t in tasks:
        canvas.coords(t["star"], star_x, t["y"] - 2)


# =========================
# DARK / LIGHT SLIDER TOGGLE
# =========================
def slide_toggle(event=None):
    global current_theme
    if toggle_canvas is None:
        return

    if current_theme == "light":
        # slide right
        for _ in range(10):
            toggle_canvas.move(toggle_knob, 2, 0)
            toggle_canvas.update()
            time.sleep(0.01)
        toggle_canvas.itemconfig(toggle_bg, fill="#555555")
        toggle_canvas.itemconfig(toggle_knob, fill="#dddddd")
        current_theme = "dark"
    else:
        # slide left
        for _ in range(10):
            toggle_canvas.move(toggle_knob, -2, 0)
            toggle_canvas.update()
            time.sleep(0.01)
        toggle_canvas.itemconfig(toggle_bg, fill="#cccccc")
        toggle_canvas.itemconfig(toggle_knob, fill="#ffffff")
        current_theme = "light"

    apply_theme()


# =========================
# AI CLEANUP BUTTON
# =========================
def cleanup_notes():
    items_text = []

    for t in tasks:
        status = "done" if t["done"] else "todo"
        items_text.append(f"- [{status}] {t['text']} (priority {t['priority']})")

    for c in completed_tasks:
        items_text.append(f"- [done] {c['text']} (priority {c['priority']})")

    for p in postits:
        txt = canvas.itemcget(p["text"], "text")
        items_text.append(f"- [note] {txt}")

    if not items_text:
        return

    prompt = (
        "You are cleaning up a messy personal notepad.\n"
        "Here are the current items (tasks + notes):\n" +
        "\n".join(items_text) +
        "\n\nReturn a cleaned-up, organized list of TASKS ONLY.\n"
        "Rules:\n"
        "- Remove duplicates and vague items.\n"
        "- Merge similar items.\n"
        "- Keep it concise.\n"
        "- One task per line.\n"
        "- Do NOT number them.\n"
        "- Just output the task lines, nothing else.\n"
    )

    client = openai.OpenAI(api_key="YOUR_API_KEY_HERE")

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You clean and organize to-do lists."},
                {"role": "user", "content": prompt},
            ],
        )
        cleaned = response.choices[0].message.content.strip()
    except Exception as e:
        cleaned = f"Error calling AI: {e}"

    popup = tk.Toplevel(window)
    popup.title("AI Cleaned Tasks")
    popup.geometry("400x400")

    tk.Label(popup, text="Review and edit the cleaned tasks:", anchor="w").pack(
        pady=5, padx=10, fill="x"
    )

    text = tk.Text(popup, wrap="word")
    text.pack(fill="both", expand=True, padx=10, pady=5)
    text.insert("1.0", cleaned)

    def apply_changes():
        lines = [line.strip() for line in text.get("1.0", "end").splitlines() if line.strip()]
        clear_current_page_ui()
        for line in lines:
            create_task(line, done=False, priority=0)
        save_tasks()
        save_current_tab_model()
        popup.destroy()

    btn_frame = tk.Frame(popup)
    btn_frame.pack(pady=8)

    tk.Button(btn_frame, text="Apply", command=apply_changes).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=popup.destroy).pack(side="left", padx=5)


# =========================
# AI CHAT PANEL
# =========================
def open_ai_panel():
    """Resizable AI chat panel with input bar and arrow button."""
    if hasattr(window, "ai_panel") and window.ai_panel.winfo_exists():
        window.ai_panel.lift()
        return

    panel = tk.Toplevel(window)
    panel.title("AI Assistant")
    panel.geometry("420x480")
    panel.minsize(320, 320)
    window.ai_panel = panel

    panel.grid_rowconfigure(0, weight=1)
    panel.grid_columnconfigure(0, weight=1)

    chat_frame = tk.Frame(panel, bg="#f3f3f3")
    chat_frame.grid(row=0, column=0, sticky="nsew")

    scroll_y = tk.Scrollbar(chat_frame)
    scroll_y.pack(side="right", fill="y")

    chat_log = tk.Text(
        chat_frame,
        wrap="word",
        state="disabled",
        bg="#ffffff",
        fg="#222222",
        font=("Segoe UI", 10),
        yscrollcommand=scroll_y.set,
        bd=0,
        padx=10,
        pady=10
    )
    chat_log.pack(side="left", fill="both", expand=True)
    scroll_y.config(command=chat_log.yview)

    chat_log.tag_configure("user", foreground="#1a73e8", justify="right")
    chat_log.tag_configure("ai", foreground="#222222", justify="left")

    input_frame = tk.Frame(panel, bg="#f3f3f3")
    input_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
    panel.grid_rowconfigure(1, weight=0)

    entry = tk.Entry(
        input_frame,
        font=("Segoe UI", 10),
        relief="solid",
        bd=1
    )
    entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

    send_btn = tk.Button(
        input_frame,
        text="➤",
        font=("Segoe UI", 12, "bold"),
        width=3,
        relief="flat",
        bg="#e0e0e0",
        activebackground="#d0d0d0"
    )
    send_btn.pack(side="right")

    def send_message(event=None):
        user_msg = entry.get().strip()
        if not user_msg:
            return
        entry.delete(0, tk.END)

        # show user message
        chat_log.config(state="normal")
        chat_log.insert("end", f"You: {user_msg}\n\n", "user")
        chat_log.config(state="disabled")
        chat_log.see("end")

        # collect context
        notes_context = []
        for t in tasks:
            notes_context.append(f"[Task] {t['text']}")
        for c in completed_tasks:
            notes_context.append(f"[Done] {c['text']}")

        # --- OpenAI call (insert your key locally) ---
        client = openai.OpenAI(api_key="YOUR_API_KEY_HERE")

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an assistant living inside a clean notebook "
                            "to-do app. Help the user plan, organize and reflect "
                            "using their tasks and notes."
                        ),
                    },
                    {
                        "role": "system",
                        "content": "Here are the user's notes and tasks:\n"
                                   + "\n".join(notes_context),
                    },
                    {"role": "user", "content": user_msg},
                ],
            )
            ai_answer = response.choices[0].message.content
        except Exception as e:
            ai_answer = f"(AI error: {e})"

        chat_log.config(state="normal")
        chat_log.insert("end", f"AI: {ai_answer}\n\n", "ai")
        chat_log.config(state="disabled")
        chat_log.see("end")

    entry.bind("<Return>", send_message)
    send_btn.config(command=send_message)


# =========================
# WINDOW SETUP
# =========================
window = tk.Tk()
window.title("Notepad To-Do")
window.geometry("950x700")
window.minsize(650, 450)
window.configure(bg=COLORS["BG_WINDOW"])

canvas = tk.Canvas(window, bg=COLORS["BG_CANVAS"], highlightthickness=0)
completed_canvas = tk.Canvas(window, bg=COLORS["BG_COMPLETED"], highlightthickness=0)

completed_canvas.create_text(
    10, 20,
    anchor="w",
    text="Completed Tasks",
    font=("Segoe UI", 14, "bold"),
    fill=COLORS["FG_TEXT"]
)

# top controls
postit_button = tk.Button(
    window,
    text="Add Post-it",
    command=open_postit_input,
    bg=COLORS["BTN_BG"],
    fg=COLORS["BTN_FG"],
    relief="flat",
    padx=10,
    pady=2
)
postit_button.place(x=70, y=10)

# theme toggle (top-left)
toggle_frame = tk.Frame(window, bg=COLORS["BG_WINDOW"])
toggle_frame.place(x=10, y=10)

toggle_canvas = tk.Canvas(toggle_frame, width=50, height=24, bg=COLORS["BG_WINDOW"], highlightthickness=0)
toggle_canvas.pack()

toggle_bg = toggle_canvas.create_rectangle(2, 2, 48, 22, fill="#cccccc", outline="")
toggle_knob = toggle_canvas.create_oval(2, 2, 22, 22, fill="#ffffff", outline="")

toggle_canvas.bind("<Button-1>", slide_toggle)

# tabs frame
tab_frame = tk.Frame(window, bg=COLORS["BG_WINDOW"])
tab_frame.place(x=180, y=8)

search_label = tk.Label(window, text="Search:", fg=COLORS["FG_TEXT"], bg=COLORS["BG_WINDOW"])
search_label.place(x=360, y=12)
search_entry = tk.Entry(window, width=25)
search_entry.place(x=420, y=12)
search_entry.bind("<KeyRelease>", on_search_change)

cleanup_button = tk.Button(
    window,
    text="Clean Up Notes",
    bg=COLORS["BTN_BG"],
    fg=COLORS["BTN_FG"],
    relief="flat",
    padx=10,
    pady=2,
    command=cleanup_notes
)

ai_button = tk.Button(
    window,
    text="🤖",
    font=("Segoe UI", 13),
    command=open_ai_panel,
    bg=COLORS["BTN_BG"],
    fg=COLORS["BTN_FG"],
    relief="flat"
)
ai_button.place(relx=0.97, rely=0.97, anchor="se")

# bindings
window.bind("<Configure>", update_layout)
window.bind("<Key>", on_key_press)
window.bind("<Escape>", clear_search)

canvas.bind("<Button-1>", on_canvas_click)
canvas.bind("<Motion>", on_mouse_move)
canvas.bind("<Button-3>", on_right_click)
canvas.bind("<B1-Motion>", drag_postit_motion)
canvas.bind("<ButtonRelease-1>", end_postit_drag)

# init
update_layout()
apply_theme()
load_tasks()
init_tabs()
on_search_change()

window.mainloop()
