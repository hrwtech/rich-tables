import itertools as it
import random
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    SupportsFloat,
    Tuple,
    Union
)

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from pycountry import countries
from rich import box
from rich.align import Align
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.tree import Tree

JSONDict = Dict[str, Any]


def format_new(string: str) -> str:
    return wrap(re.sub(r"(^\s+$)", "[u green]\\1[/u green]", string), "b green")


def format_old(string: str) -> str:
    return wrap(string, "b s red")


def fmtdiff(change: str, before: str, after: str) -> str:
    if change == "insert":
        return format_new(after)
    elif change == "delete":
        return format_old(before)
    elif change == "replace":
        return format_old(before) + format_new(after)
    else:
        return before


def make_difftext(
    before: str, after: str, junk: str = " qwertyuiopasdfghjkllzxcvbnm"
) -> str:
    # def preparse(value: str) -> str:
    #     return value.strip().replace("[]", "~")

    # before = preparse(before)
    # after = preparse(after)

    matcher = SequenceMatcher(lambda x: x not in junk, autojunk=False, a=before, b=after)
    diff = ""
    for code, a1, a2, b1, b2 in matcher.get_opcodes():
        diff = diff + (fmtdiff(code, before[a1:a2], after[b1:b2]) or "")
    return diff


def fmt_time(diff: timedelta, pad: bool = True) -> Iterable[str]:
    opts: List[Tuple[int, str]] = [
        (diff.days, "d"),
        (diff.seconds // 3600, "h"),
        (diff.seconds % 3600 // 60, "min"),
        (diff.seconds % 60, "s"),
    ]
    fmt = "{:>3}{}" if pad else "{}{}"
    return it.starmap(fmt.format, filter(lambda x: x[0], opts))  # type: ignore


def duration2human(duration: SupportsFloat, acc: int = 1) -> str:
    return " ".join(it.islice(fmt_time(timedelta(seconds=float(duration))), acc))


def time2human(
    timestamp: Union[int, str], acc: int = 1, use_colors=False, pad: bool = True
) -> str:
    if isinstance(timestamp, str):
        seconds = int(parse(timestamp).timestamp())
    else:
        seconds = timestamp
    if not seconds:
        return "-"
    diff = time.time() - seconds
    fmted = " ".join(it.islice(fmt_time(timedelta(seconds=abs(diff)), pad), acc))

    fut, past = ("[b green]{}[/]", "[b red]-{}[/]") if use_colors else ("in {}", "{} ago")
    return past.format(fmted) if diff > 0 else fut.format(fmted)


def make_console(**kwargs: Any) -> Console:
    default: JSONDict = dict(force_terminal=True, force_interactive=True)
    return Console(**{**default, **kwargs})


def wrap(text: str, tag: str) -> str:
    return f"[{tag}]{text}[/{tag}]"


class NewTable(Table):
    def __init__(self, *args, **kwargs) -> None:
        overflow = kwargs.pop("overflow", None)
        justify = kwargs.pop("justify", None)

        super().__init__(*args, **kwargs)

        for col in self.columns:
            col.overflow = overflow or col.overflow
            col.justify = justify or col.justify

    def add_rows(self, rows: Iterable) -> None:
        """Add multiple rows to the table."""
        for row in rows:
            # row = map(lambda x: str(x) if type(x, (int, bool, ))
            self.add_row(*row)

    @property
    def colmap(self) -> Dict[str, Column]:
        """Provide a mapping between columns names / ids and columns."""
        pass

    # def col(self, name: str) -> Column:


def new_table(*args: Any, **kwargs: Any) -> Table:
    default: JSONDict = dict(
        border_style="black",
        show_edge=False,
        show_header=False,
        highlight=True,
        row_styles=["white"],
        expand=False,
    )
    if args:
        default.update(
            header_style="bold misty_rose1",
            box=box.SIMPLE_HEAVY,
            show_header=True,
        )
    rows = kwargs.pop("rows", [])
    table = NewTable(*args, **{**default, **kwargs})
    if rows:
        table.add_rows(rows)
    return table


def predictably_random_color(string: str) -> str:
    random.seed(string)
    rand = partial(random.randint, 60, 190)
    return "#{:0>2X}{:0>2X}{:0>2X}".format(rand(), rand(), rand())


def format_with_color(name: str) -> str:
    return wrap(name, f"b i {predictably_random_color(name)}")


def simple_panel(content: RenderableType, **kwargs: Any) -> Panel:
    default: JSONDict
    default = dict(title_align="left", subtitle_align="left", box=box.SIMPLE, expand=True)
    if kwargs.get("align", "") == "center":
        content = Align.center(content)
    return Panel(content, **{**default, **kwargs})


def border_panel(content: RenderableType, **kwargs: Any) -> Panel:
    return simple_panel(content, **{**dict(box=box.ROUNDED), **kwargs})


def md_panel(content: str, **kwargs: Any) -> Panel:
    return border_panel(Markdown(content), **kwargs)


def new_tree(values: List[str] = [], **kwargs) -> Tree:
    default: JSONDict = dict(guide_style="black")
    tree = Tree(kwargs.pop("title", None) or "", **{**default, **kwargs})
    for val in values:
        tree.add(val)
    return tree


def tstamp2timedate(timestamp: Optional[str], fmt: str = "%F %H:%M") -> str:
    return datetime.fromtimestamp(int(float(timestamp or 0))).strftime(fmt)


def get_country(code: str) -> str:
    try:
        country = countries.lookup(code).name.replace("Russian Federation", "Russia")
        return f":flag_for_{country.lower().replace(' ', '_')}: {country}"
    except LookupError:
        return "Worldwide"


def colored_with_bg(string: str) -> str:
    return wrap(f" {format_with_color(string)} ", "on #000000")


split_pat = re.compile(r"[;,] ")


def colored_split(string: str) -> str:
    return "  ".join(map(format_with_color, sorted(split_pat.split(string))))


FIELDS_MAP: Dict[str, Callable] = defaultdict(
    lambda: str,
    albumtype=lambda x: colored_split(x.replace("compilation", "comp")),
    albumtypes=lambda x: "; ".join(map(colored_split, x.split("; "))),
    label=format_with_color,
    catalognum=format_with_color,
    last_played=lambda x: time2human(x, use_colors=True, pad=False),
    avg_last_played=lambda x: time2human(x, acc=2, use_colors=True, pad=False),
    added=lambda x: x
    if isinstance(x, str)
    else datetime.fromtimestamp(x).strftime("%F %H:%M"),
    mtime=lambda x: re.sub(r"\] *", "]", time2human(x, pad=False)),
    bpm=lambda x: wrap(
        x,
        "green" if x < 135 else "#000000" if x > 230 else "red" if x > 165 else "yellow",
    ),
    style=format_with_color,
    genre=colored_split,
    stats=lambda x: "[green]{:<3}[/green] [red]{}[/red]".format(
        f"🞂{x[0]}" if x[0] else "", f"🞩{x[1]}" if x[1] else ""
    ),
    length=lambda x: re.sub(
        r"^00:",
        "",
        (datetime.fromtimestamp(x) - relativedelta(hours=1)).strftime("%H:%M:%S"),
    ),
    tracktotal=lambda x: (wrap("{}", "b cyan") + "/" + wrap("{}", "b cyan")).format(*x)
    if isinstance(x, Iterable)
    else str(x),
    country=get_country,
    data_source=format_with_color,
    helicopta={1: wrap("", "b red"), 0: "", None: ""}.get,
    keywords=lambda x: " ".join(
        map(colored_with_bg, map(format_with_color, x.split(", ")))
    )
    if isinstance(x, str)
    else x,
    ingr=lambda x: simple_panel(colored_split(x)),
    content=md_panel,
    notes=md_panel,
    text=md_panel,
    instructions=md_panel,
    comments=lambda x: md_panel(x.replace("---", "\n---\n")),
    tags=lambda x: simple_panel(colored_split(x)),
    released=lambda x: x.replace("-00", ""),
    desc=lambda x: md_panel(x) if x else "",
    calendar=format_with_color,
    source=format_with_color,
    category=format_with_color,
    categories=lambda x: " ".join(map(format_with_color, x.split(","))),
    price=lambda x: x if x else colored_with_bg(x),
)
