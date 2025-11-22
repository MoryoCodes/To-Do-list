import tkinter as tk
import time
import threading

FILENAME = "Tasks.txt"

tasks = []
completed_tasks = []

# typing state
current_text = ""
current_text_items = []
caret = None
caret_active = False
current_y = None

CHAR_WIDTH = 10
TEXT_START_X = 50
LINE_START_Y = 50
LINE_HEIGHT = 30


def save_tasks():
    with open(FILENAME, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(f"{t['text']}||{t['done']}||{t['priority']}\n")


def create_task(text, done=False, priority=0):
    """Create a new task at the bottom of the list."""
    y = LINE_START_Y + len(tasks) * LINE_HEIGHT

    # checkbox
    box = canvas.create_rectangle(20, y - 10, 35, y + 5, outline="black")

    # checkmark
    check = canvas.create_line(
        22, y - 2, 28, y + 3, 33, y - 7,
        width=2,
        fill="black" if done else "",
    )

    # draw characters individually
    char_items = []
    for i, ch in enumerate(text):
        item = canvas.create_text(
            TEXT_START_X + i * CHAR_WIDTH, y - 2,
            text=ch,
            anchor="w",
            font=("Courier New", 14),
            fill="black"
        )
        char_items.append(item)

    # star priority
    stars_text = "★" * priority + "☆" * (3 - priority)
    star_item = canvas.create_text(
        360, y - 2,
        text=stars_text,
        anchor="e",
        font=("Courier New", 14),
        fill="gold"
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

    # bindings
    canvas.tag_bind(box, "<Button-1>", lambda e, t=task: toggle_task(t))
    for ch_item in char_items:
        canvas.tag_bind(ch_item, "<Button-1>", lambda e, t=task: toggle_task(t))
    canvas.tag_bind(check, "<Button-1>", lambda e, t=task: toggle_task(t))
    canvas.tag_bind(star_item, "<Button-1>", lambda e, t=task: toggle_priority(t))


# -------------------------------------------------
# INDIVIDUAL CHARACTER FADE ANIMATION
# -------------------------------------------------
def erase_animation(task, on_finish=None):
    chars = task["chars"]

    for item in chars:
        # fade each letter
        for alpha in range(255, -1, -15):
            color = f"#{alpha:02x}{alpha:02x}{alpha:02x}"
            canvas.itemconfig(item, fill=color)
            canvas.update()
            time.sleep(0.01)

        canvas.itemconfig(item, text="")  # erase fully

    if on_finish:
        on_finish()


# -------------------------------------------------
# COMPLETED TASKS BOX
# -------------------------------------------------
def add_completed_task(text, priority=0):
    y = 50 + len(completed_tasks) * 25

    text_id = completed_canvas.create_text(
        10,
        y,
        anchor="w",
        font=("Courier New", 12),
        text=text,
        fill="black",
    )

    # strike-through line
    bbox = completed_canvas.bbox(text_id)
    if bbox:
        x1, y1, x2, y2 = bbox
        completed_canvas.create_line(
            x1, (y1 + y2) // 2, x2, (y1 + y2) // 2,
            fill="black",
            width=2
        )

    # tiny star indication on the right
    stars_text = "★" * priority + "☆" * (3 - priority)
    completed_canvas.create_text(
        260, y,
        anchor="e",
        font=("Courier New", 10),
        text=stars_text,
        fill="gold"
    )

    completed_tasks.append(text)


# -------------------------------------------------
# PRIORITY STAR TOGGLING
# -------------------------------------------------
def toggle_priority(task):
    priority = (task["priority"] + 1) % 4
    task["priority"] = priority
    stars_text = "★" * priority + "☆" * (3 - priority)
    canvas.itemconfig(task["star"], text=stars_text)
    save_tasks()


# -------------------------------------------------
# CHECK / UNCHECK TASK
# -------------------------------------------------
def toggle_task(task):
    if not task["done"]:
        task["done"] = True
        canvas.itemconfig(task["check"], fill="black")

        # animation then move to completed list
        def after_erase():
            add_completed_task(task["text"], task["priority"])
            delete_task(task)

        threading.Thread(
            target=erase_animation,
            args=(task, after_erase),
            daemon=True
        ).start()

    else:
        # If you ever want to restore tasks, logic goes here
        task["done"] = False
        canvas.itemconfig(task["check"], fill="")
        for i, ch in enumerate(task["text"]):
            canvas.itemconfig(task["chars"][i], text=ch, fill="black")

    save_tasks()


def delete_task(task):
    for item in task["chars"]:
        canvas.delete(item)

    canvas.delete(task["check"])
    canvas.delete(task["box"])
    canvas.delete(task["star"])

    tasks.remove(task)
    save_tasks()

    # shift remaining tasks up
    for i, t in enumerate(tasks):
        new_y = LINE_START_Y + i * LINE_HEIGHT
        t["y"] = new_y

        canvas.coords(t["box"], 20, new_y - 10, 35, new_y + 5)
        canvas.coords(t["check"], 22, new_y - 2, 28, new_y + 3, 33, new_y - 7)

        for j, ch_item in enumerate(t["chars"]):
            canvas.coords(ch_item, TEXT_START_X + j * CHAR_WIDTH, new_y - 2)

        canvas.coords(t["star"], 360, new_y - 2)


# -------------------------------------------------
# NOTEPAD LINES
# -------------------------------------------------
def redraw_lines(event=None):
    canvas.delete("notepad_line")
    width = canvas.winfo_width()
    for i in range(LINE_START_Y, canvas.winfo_height(), LINE_HEIGHT):
        canvas.create_line(10, i, width - 20, i, fill="#d0d0d0", tags="notepad_line")


# -------------------------------------------------
# TYPING DIRECTLY ON THE PAPER
# -------------------------------------------------
def clear_current_input():
    global current_text, current_text_items, caret, caret_active, current_y
    for item in current_text_items:
        canvas.delete(item)
    current_text_items.clear()

    if caret is not None:
        canvas.delete(caret)
        caret = None

    current_text = ""
    current_y = None
    caret_active = False


def blink_caret():
    global caret
    if not caret_active or caret is None:
        return
    # toggle visibility
    state = canvas.itemcget(caret, "state")
    new_state = "hidden" if state == "normal" else "normal"
    canvas.itemconfig(caret, state=new_state)
    window.after(500, blink_caret)


def start_typing():
    """Start typing on the next free line at the bottom."""
    global current_text, current_text_items, caret, caret_active, current_y

    clear_current_input()

    current_text = ""
    current_y = LINE_START_Y + len(tasks) * LINE_HEIGHT
    caret_active = True

    # caret at start of line
    caret_x = TEXT_START_X
    caret_y1 = current_y - 10
    caret_y2 = current_y + 5
    caret_obj = canvas.create_line(caret_x, caret_y1, caret_x, caret_y2, width=2)
    # ensure visible initially
    canvas.itemconfig(caret_obj, state="normal")

    caret = caret_obj
    blink_caret()


def on_canvas_click(event):
    """Click near the bottom to start typing a new task."""
    # Only allow typing in the left notepad area, near the next empty line
    if event.x > 400:
        return  # right side click (completed area) - ignore

    next_y = LINE_START_Y + len(tasks) * LINE_HEIGHT
    # if click is roughly near the next line region, start typing
    if event.y >= next_y - 15:
        start_typing()
    # else: clicking on existing tasks is handled by tag_bind, do nothing here


def on_key_press(event):
    global current_text, current_text_items, caret, caret_active, current_y

    if not caret_active or current_y is None:
        return

    # handle Enter -> create task
    if event.keysym == "Return":
        text = current_text.strip()
        if text:
            create_task(text, done=False, priority=0)
            save_tasks()
            clear_current_input()
            redraw_lines()
        return

    # handle Backspace
    if event.keysym == "BackSpace":
        if current_text_items:
            last_item = current_text_items.pop()
            canvas.delete(last_item)
            current_text = current_text[:-1]

            # move caret back
            new_x = TEXT_START_X + len(current_text_items) * CHAR_WIDTH
            canvas.coords(caret, new_x, current_y - 10, new_x, current_y + 5)
        return

    # ignore control keys (Shift, Ctrl, arrows, etc.)
    if len(event.char) == 0:
        return
    if not event.char.isprintable():
        return

    # add character
    ch = event.char
    x = TEXT_START_X + len(current_text_items) * CHAR_WIDTH
    y = current_y - 2

    item = canvas.create_text(
        x, y,
        text=ch,
        anchor="w",
        font=("Courier New", 14),
        fill="black"
    )
    current_text_items.append(item)
    current_text += ch

    # move caret forward
    new_x = x + CHAR_WIDTH
    canvas.coords(caret, new_x, current_y - 10, new_x, current_y + 5)



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



window = tk.Tk()
window.title("Notepad To-Do")
window.geometry("700x600")


canvas = tk.Canvas(window, width=400, height=600, bg="white")
canvas.place(x=0, y=0)

canvas.bind("<Configure>", redraw_lines)
canvas.bind("<Button-1>", on_canvas_click)


completed_canvas = tk.Canvas(window, width=280, height=600, bg="#f0f0f0")
completed_canvas.place(x=410, y=0)

completed_canvas.create_text(
    10, 20,
    anchor="w",
    text="Completed Tasks:",
    font=("Courier New", 16, "bold")
)

# key handling for typing on paper
window.bind("<Key>", on_key_press)

load_tasks()
redraw_lines()

window.mainloop()
