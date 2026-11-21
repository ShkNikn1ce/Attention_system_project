"""Извлекает из исходного кода описание классов проекта (атрибуты, операции, стереотипы) в JSON.
Диаграммы классов проекта строятся по этому файлу, поэтому всегда совпадают с кодом."""
import ast
import json
import pathlib

КОРЕНЬ = pathlib.Path(__file__).resolve().parent.parent / "attention_system"
ТИПЫ = {"str": "Строка", "int": "Целое", "float": "Число", "bool": "Логич", "datetime": "ДатаВремя",
        "date": "Дата", "object": "Объект", "Future": "Будущее", "Random": "ГенераторСлучайных",
        "Lock": "Замок", "RLock": "Замок", "Connection": "Соединение", "ThreadPoolExecutor": "ПулПотоков", "Row": "СтрокаБД", "Callable": "Вызываемое"}


def тип(узел) -> str:
    if узел is None:
        return ""
    if isinstance(узел, ast.Constant):
        return "ничего" if узел.value is None else str(узел.value)
    if isinstance(узел, ast.Name):
        return ТИПЫ.get(узел.id, узел.id)
    if isinstance(узел, ast.Attribute):
        return ТИПЫ.get(узел.attr, узел.attr)
    if isinstance(узел, ast.BinOp):
        return тип(узел.left) + " | " + тип(узел.right)
    if isinstance(узел, ast.Subscript):
        основа = узел.value.id if isinstance(узел.value, ast.Name) else ""
        срез = узел.slice
        части = [тип(э) for э in срез.elts] if isinstance(срез, ast.Tuple) else [тип(срез)]
        if основа == "Optional":
            return части[0] + "?"
        имя = {"list": "Список", "dict": "Словарь", "tuple": "Кортеж", "Callable": "Вызываемое"}.get(основа, основа)
        return f"{имя}[{', '.join(части)}]"
    if isinstance(узел, ast.List):
        return "[" + ", ".join(тип(э) for э in узел.elts) + "]"
    return ast.unparse(узел)


def видимость(имя: str) -> str:
    if имя.startswith("__"):
        return "-"
    return "#" if имя.startswith("_") else "+"


def значение(узел) -> str:
    if isinstance(узел, ast.Constant):
        return repr(узел.value).replace("None", "ничего") if узел.value is not None else "ничего"
    if isinstance(узел, ast.Attribute):
        return узел.attr
    return ""


def разобрать(путь: pathlib.Path):
    дерево = ast.parse(путь.read_text(encoding="utf-8"))
    for узел in ast.walk(дерево):
        if not isinstance(узел, ast.ClassDef):
            continue
        стерео = ""
        for д in узел.decorator_list:
            if isinstance(д, ast.Call) and isinstance(д.func, ast.Name) and д.func.id == "стереотип":
                стерео = д.args[0].value
        базы = [ast.unparse(б) for б in узел.bases]
        if "Enum" in базы or "Exception" in " ".join(базы) or "ОшибкаПредметнойОбласти" in базы:
            continue
        атрибуты, операции, вызовы = [], [], {}
        for эл in узел.body:
            if isinstance(эл, ast.AnnAssign) and isinstance(эл.target, ast.Name):
                знач = значение(эл.value) if эл.value is not None else ""
                атрибуты.append({"вид": видимость(эл.target.id), "имя": эл.target.id, "тип": тип(эл.annotation), "знач": знач})
            elif isinstance(эл, ast.Assign) and isinstance(эл.targets[0], ast.Name) and эл.targets[0].id.isupper():
                атрибуты.append({"вид": "+", "имя": эл.targets[0].id, "тип": "", "знач": значение(эл.value)})
            elif isinstance(эл, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if эл.name == "__init__":
                    for вл in ast.walk(эл):
                        if (isinstance(вл, ast.AnnAssign) and isinstance(вл.target, ast.Attribute)
                                and isinstance(вл.target.value, ast.Name) and вл.target.value.id == "self"):
                            атрибуты.append({"вид": видимость(вл.target.attr), "имя": вл.target.attr,
                                             "тип": тип(вл.annotation), "знач": ""})
                    continue
                if эл.name.startswith("__") and эл.name.endswith("__"):
                    continue
                парам = [[а.arg, тип(а.annotation)] for а in эл.args.args if а.arg != "self"]
                возвр = тип(эл.returns)
                операции.append({"вид": видимость(эл.name), "имя": эл.name, "парам": парам,
                                 "возвр": "" if возвр in ("ничего", "") else возвр})
                for вызов in ast.walk(эл):
                    if (isinstance(вызов, ast.Call) and isinstance(вызов.func, ast.Attribute)
                            and isinstance(вызов.func.value, ast.Attribute)
                            and isinstance(вызов.func.value.value, ast.Name) and вызов.func.value.value.id == "self"):
                        вызовы.setdefault(вызов.func.value.attr, [])
                        if вызов.func.attr not in вызовы[вызов.func.value.attr]:
                            вызовы[вызов.func.value.attr].append(вызов.func.attr)
        yield {"имя": узел.name, "модуль": str(путь.relative_to(КОРЕНЬ.parent)), "стереотип": стерео,
               "базы": базы, "атрибуты": атрибуты, "операции": операции, "вызовы": вызовы}


итог = {}
for путь in sorted(КОРЕНЬ.rglob("*.py")):
    if путь.name in ("__init__.py", "main.py", "markup.py"):
        continue
    for к in разобрать(путь):
        итог[к["имя"]] = к
pathlib.Path(__file__).resolve().parent.parent.joinpath("diagrams", "classes.json").write_text(
    json.dumps(итог, ensure_ascii=False, indent=1), encoding="utf-8")
print("классов извлечено:", len(итог))
for имя in ("КонтроллерТестирования", "ФормаТестирования", "IХранилище"):
    к = итог[имя]
    print(имя, к["стереотип"], len(к["атрибуты"]), "атрибутов,", len(к["операции"]), "операций; вызовы:", {k: len(v) for k, v in к["вызовы"].items()})
