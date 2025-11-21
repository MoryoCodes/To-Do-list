import tkinter as tk
import time
import threading

FILENAME = "Tasks.txt"

tasks = []
completed_tasks = []


def save_tasks():
    with open(FILENAME, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(f"{t['text']}||{t['done']}\n")


def draw_task(text, done=False):
    y = 50 + len(tasks) * 30

    # haken box
    box = canvas.create_rectangle(20, y - 10, 35, y + 5, outline="black")

    # haken
    check = canvas.create_line(
        22, y - 2, 28, y + 3, 33, y - 7,
        width=2,
        fill="black" if done else "",
    )

    # malt jeden buchstaben einzeln
    char_items = []
    start_x = 50
    for i, ch in enumerate(text):
        item = canvas.create_text(
            start_x + i * 10, y - 2,
            text=ch,
            anchor="w",
            font=("Courier New", 14),
            fill="black"
        )
        char_items.append(item)

    task = {
        "text": text,
        "done": done,
        "chars": char_items,
        "check": check,
        "y": y,
        "box": box,
    }

    tasks.append(task)

    canvas.tag_bind(box, "<Button-1>", lambda e, t=task: toggle_task(t))
    for ch in char_items:
        canvas.tag_bind(ch, "<Button-1>", lambda e, t=task: toggle_task(t))
    canvas.tag_bind(check, "<Button-1>", lambda e, t=task: toggle_task(t))


# animationen
def erase_animation(task, on_finish=None):
    chars = task["chars"]

    for item in chars:
        for alpha in range(255, -1, -15):
            color = f"#{alpha:02x}{alpha:02x}{alpha:02x}"
            canvas.itemconfig(item, fill=color)
            canvas.update()
            time.sleep(0.01)

        canvas.itemconfig(item, text="")  # fully erased

    if on_finish:
        on_finish()


# fertige task box
def add_completed_task(text):
    y = 50 + len(completed_tasks) * 25

    text_id = completed_canvas.create_text(
        10,
        y,
        anchor="w",
        font=("Courier New", 12),
        text=text,
        fill="black",
    )

    # durch streichen
    bbox = completed_canvas.bbox(text_id)
    if bbox:
        x1, y1, x2, y2 = bbox
        completed_canvas.create_line(
            x1, (y1+y2)//2, x2, (y1+y2)//2,
            fill="black",
            width=2
        )

    completed_tasks.append(text)


# checkmark undso
def toggle_task(task):
    if not task["done"]:
        task["done"] = True
        canvas.itemconfig(task["check"], fill="black")

        # anamtions scheiss
        def after_erase():
            add_completed_task(task["text"])
            delete_task(task)

        threading.Thread(
            target=erase_animation,
            args=(task, after_erase),
            daemon=True
        ).start()

    else:
        # mach zurück wenn unchecjed
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

    tasks.remove(task)
    save_tasks()

    # keine gaps wenn was weg ist
    for i, t in enumerate(tasks):
        new_y = 50 + i * 30
        t["y"] = new_y

        canvas.coords(t["box"], 20, new_y - 10, 35, new_y + 5)
        canvas.coords(t["check"], 22, new_y - 2, 28, new_y + 3, 33, new_y - 7)

        for j, ch_item in enumerate(t["chars"]):
            canvas.coords(ch_item, 50 + j * 10, new_y - 2)


def redraw_lines(event=None):
    canvas.delete("notepad_line")
    width = canvas.winfo_width()
    for i in range(50, canvas.winfo_height(), 30):
        canvas.create_line(10, i, width - 20, i, fill="#d0d0d0", tags="notepad_line")


def add_task():
    text = task_entry.get().strip()
    if not text:
        return

    draw_task(text, False)
    task_entry.delete(0, tk.END)
    save_tasks()


def load_tasks():
    try:
        with open(FILENAME, "r", encoding="utf-8") as f:
            for line in f:
                if "||" in line:
                    text, done = line.strip().split("||")
                    draw_task(text, done == "True")
    except FileNotFoundError:
        pass


#fenster
window = tk.Tk()
window.title("Notepad To-Do")
window.geometry("700x600")

# main schreib ding
canvas = tk.Canvas(window, width=400, height=600, bg="white")
canvas.place(x=0, y=0)

canvas.bind("<Configure>", redraw_lines)

# fertige dingee
completed_canvas = tk.Canvas(window, width=280, height=600, bg="#f0f0f0")
completed_canvas.place(x=410, y=0)

completed_title = completed_canvas.create_text(
    10, 20,
    anchor="w",
    text="Completed Tasks:",
    font=("Courier New", 16, "bold")
)

#eintröge
task_entry = tk.Entry(window, width=25, font=("Courier New", 14))
task_entry.place(x=20, y=10)

add_button = tk.Button(window, text="Add Task", command=add_task)
add_button.place(x=300, y=7)

load_tasks()
redraw_lines()

window.mainloop()
