import itertools as it
import json
import operator as op
import re
import sys
import typing as t
from datetime import datetime, timedelta
from functools import singledispatch

from rich.bar import Bar
from rich.columns import Columns
from rich.console import ConsoleRenderable
from rich.table import Table

from rich_tables.generic import flexitable
from rich_tables.github import pulls_table
from rich_tables.music import albums_table
from rich_tables.utils import (
    FIELDS_MAP,
    border_panel,
    format_with_color,
    get_val,
    make_console,
    make_difftext,
    new_table,
    new_tree,
    predictably_random_color,
    simple_panel,
    time2human,
    wrap,
)

JSONDict = t.Dict[str, t.Any]


console = make_console()
print = console.print


def lights_table(lights: t.List[JSONDict]) -> Table:
    from rgbxy import Converter

    headers = lights[0].keys()
    table = new_table(*headers)
    conv = Converter()
    for light in lights:
        xy = light.get("xy")
        style = ""
        if not light["on"]:
            style = "dim"
            light["xy"] = ""
        elif xy:
            color = conv.xy_to_hex(*xy)
            light["xy"] = wrap("   a", f"#{color} on #{color}")
        table.add_row(*map(str, map(lambda x: light.get(x, ""), headers)), style=style)
    yield table


def calendar_table(events: t.List[JSONDict]) -> t.Iterable[ConsoleRenderable]:
    def get_start_end(start: datetime, end: datetime) -> t.Tuple[int, int]:
        if start.hour == end.hour == 0:
            return 0, 86400
        day_start_ts = start.replace(hour=0).timestamp()
        return int(start.timestamp() - day_start_ts), int(
            end.timestamp() - day_start_ts
        )

    status_map = dict(
        needsAction="[b grey3] ? [/]",
        accepted="[b green] ✔ [/]",
        declined="[b red] ✖ [/]",
        tentative="[b yellow] ? [/]",
    )

    cal_to_color = {e["calendar"]: e["backgroundColor"] for e in events}
    if len(cal_to_color) > 1:
        color_key = "calendar"
        color_id_to_color = cal_to_color
    else:
        color_key = "colorId"
        color_id_to_color = {
            e[color_key]: predictably_random_color(e[color_key]) for e in events
        }
    for e in events:
        e["color"] = color_id_to_color[e[color_key]]
    cal_fmted = [wrap(f" {c} ", f"b black on {clr}") for c, clr in cal_to_color.items()]
    yield Columns(cal_fmted, expand=True, equal=False, align="center")

    new_events: t.List[JSONDict] = []
    for event in events:
        start_iso, end_iso = event["start"], event["end"]
        orig_start = datetime.fromisoformat(
            (start_iso.get("dateTime") or start_iso.get("date")).strip("Z")
        )
        orig_end = datetime.fromisoformat(
            (end_iso.get("dateTime") or end_iso.get("date")).strip("Z")
        )
        h_after_midnight = (
            24 * (orig_end - orig_start).days
            + ((orig_end - orig_start).seconds // 3600)
        ) - (24 - orig_start.hour)

        end = (orig_start + timedelta(days=1)).replace(hour=0, minute=0, second=0)

        def eod(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=23, minute=59, second=59
            )

        def midnight(day_offset: int) -> datetime:
            return (orig_start + timedelta(days=day_offset)).replace(
                hour=0, minute=0, second=0
            )

        days_count = h_after_midnight // 24 + 1
        for start, end in zip(
            [orig_start, *map(midnight, range(1, days_count + 1))],
            [*map(eod, range(days_count)), orig_end],
        ):
            if start == end:
                continue

            color = (
                "grey7" if end.replace(tzinfo=None) < datetime.now() else event["color"]
            )
            new_events.append(
                {
                    **event,
                    **dict(
                        color=color,
                        summary=status_map[event["status"]]
                        + wrap(event["summary"] or "busy", f"b {color}"),
                        start=start,
                        start_day=start.strftime("%d %a"),
                        start_time=wrap(start.strftime("%H:%M"), "white"),
                        end_time=wrap(end.strftime("%H:%M"), "white"),
                        desc=border_panel(get_val(event, "desc"))
                        if event["desc"]
                        else "",
                        bar=Bar(86400, *get_start_end(start, end), color=color),
                    ),
                }
            )

    keys = "summary", "start_time", "end_time", "bar"
    month_events: t.Iterable[JSONDict]
    for month_tuple, month_events in it.groupby(
        new_events, lambda x: (x["start"].month, x["start"].strftime("%Y %B"))
    ):
        month_events = sorted(month_events, key=lambda x: x.get("start_day") or "")
        _, year_and_month = month_tuple

        table = new_table(*keys, highlight=False, padding=0, show_header=False)
        for day, day_events in it.groupby(
            month_events, lambda x: x.get("start_day") or ""
        ):
            table.add_row(wrap(day, "b i"))
            for event in day_events:
                if "Week " in event["summary"]:
                    table.add_row("")
                    table.add_dict_item(event, style=event["color"] + " on grey7")
                else:
                    table.add_dict_item(event)
                    if event["desc"]:
                        table.add_row("", "", "", event["desc"])
            table.add_row("")
        yield border_panel(table, title=year_and_month)


def tasktime(datestr: str):
    return time2human(datetime.strptime(datestr, "%Y%m%dT%H%M%SZ").timestamp())


def tasks_table(tasks: t.List[JSONDict]) -> t.Iterator:
    if not tasks:
        return
    fields_map: JSONDict = dict(
        id=str,
        urgency=lambda x: str(round(x, 1)),
        description=lambda x: x,
        due=tasktime,
        end=tasktime,
        sched=tasktime,
        tags=lambda x: " ".join(map(format_with_color, x or [])),
        project=format_with_color,
        modified=tasktime,
        annotations=lambda l: "\n".join(
            map(
                lambda x: wrap(tasktime(x["entry"]), "b")
                + ": "
                + wrap(x["description"], "i"),
                l,
            )
        ),
    )
    FIELDS_MAP.update(fields_map)
    status_map = {
        "completed": "b s black on green",
        "deleted": "s red",
        "pending": "white",
        "started": "b green",
        "recurring": "i magenta",
    }
    id_to_desc = uuid_to_id = {}
    for task in tasks:
        task["sched"] = task.get("scheduled")
        if not task.get("id"):
            task["id"] = task["uuid"].split("-")[0]
        uuid_to_id[task["uuid"]] = task["id"]

        if task.get("start"):
            task["status"] = "started"

        recur = task.get("recur")
        if recur:
            if task.get("status") == "recurring":
                continue
            else:
                task["status"] = "recurring"
                task["description"] += f" ({recur})"
        desc = wrap(task["description"], status_map[task["status"]])
        if task.get("priority") == "H":
            desc = f"[b]([red]![/])[/] {desc}"
        id_to_desc[task["id"]] = desc

    group_by = tasks[0].get("group_by") or ""
    headers = ["urgency", "id"] + [
        k for k in fields_map.keys() if k not in {group_by, "id", "urgency"}
    ]

    for group, task_group in it.groupby(
        sorted(
            tasks,
            key=lambda x: (x.get(group_by) or "", x.get("urgency") or 0),
            reverse=True,
        ),
        lambda x: x.get(group_by) or f"no [b]{group_by}[/]",
    ):
        project_color = predictably_random_color(str(group))
        table = new_table(padding=(0, 1, 0, 1))
        for task in task_group:
            task_obj = id_to_desc.get(task["id"])
            if not task_obj:
                continue

            task_tree = new_tree(title=task_obj, guide_style=project_color)
            ann = task.pop("annotations", None)
            if ann:
                task_tree.add(FIELDS_MAP["annotations"](ann))
            for kuid in task.get("depends") or []:
                dep = id_to_desc.get(uuid_to_id.get(kuid))
                if dep:
                    task_tree.add(wrap(str(uuid_to_id[kuid]), "b") + " " + dep)
            task["description"] = task_tree
            table.add_row(*map(lambda x: get_val(task, x), headers))

        for col in table.columns.copy():
            try:
                next(filter(op.truth, col.cells))
            except StopIteration:
                table.columns.remove(col)
        panel = simple_panel if group == "started" else border_panel
        yield panel(table, title=wrap(group, "b"), style=project_color)


def load_data() -> t.Any:
    text = re.sub(r"\x00", "", sys.stdin.read())
    try:
        data = json.loads(text or "{}")
        assert data
    except json.JSONDecodeError:
        msg = "Broken JSON"
    except AssertionError:
        msg = "No data"
    else:
        return data
    console.log(wrap(msg, "b red"), log_locals=True)
    exit(1)


@singledispatch
def draw_data(data: t.Union[JSONDict, t.List], title: str = "") -> None:
    pass


@draw_data.register(dict)
def _draw_data_dict(data: JSONDict) -> t.Iterator:
    if "values" in data and "title" in data:
        values, title = data["values"], data["title"]
        calls: t.Dict[str, t.Callable] = {
            "Pull Requests": pulls_table,
            "Hue lights": lights_table,
            "Calendar": calendar_table,
            "Album": albums_table,
            "Tasks": tasks_table,
        }
        if title in calls:
            yield from calls[title](values)
        else:
            yield flexitable(values)
    else:
        yield flexitable(data)


@draw_data.register(list)
def _draw_data_list(data: t.List[JSONDict], title: str = "") -> t.Iterator:
    yield flexitable(data)


def main():
    args = []
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])

    if args and args[0] == "diff":
        console.print(make_difftext(*args[1:]), highlight=False)
        return

    if "-s" in set(args):
        console.record = True

    data = load_data()
    if "-j" in args:
        console.print_json(data=data)
    else:
        try:
            for ret in draw_data(data):
                console.print(ret)
        except Exception:
            console.print_exception(show_locals=True)

    if "-s" in set(args):
        console.save_html("saved.html")


if __name__ == "__main__":
    main()
