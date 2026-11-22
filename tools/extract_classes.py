"""Извлекает из исходного кода описание классов проекта (атрибуты, операции, стереотипы) в JSON.
Диаграммы классов проекта строятся по этому файлу, поэтому всегда совпадают с кодом."""
import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "attention_system"
TYPE_LABELS = {"str": "Строка", "int": "Целое", "float": "Число", "bool": "Логич", "datetime": "ДатаВремя",
        "date": "Дата", "object": "Объект", "Future": "Будущее", "Random": "ГенераторСлучайных",
        "Lock": "Замок", "RLock": "Замок", "Connection": "Соединение", "ThreadPoolExecutor": "ПулПотоков", "Row": "СтрокаБД", "Callable": "Вызываемое"}


def format_type(node) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return "ничего" if node.value is None else str(node.value)
    if isinstance(node, ast.Name):
        return TYPE_LABELS.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return TYPE_LABELS.get(node.attr, node.attr)
    if isinstance(node, ast.BinOp):
        return format_type(node.left) + " | " + format_type(node.right)
    if isinstance(node, ast.Subscript):
        origin = node.value.id if isinstance(node.value, ast.Name) else ""
        slice_node = node.slice
        parts = [format_type(e) for e in slice_node.elts] if isinstance(slice_node, ast.Tuple) else [format_type(slice_node)]
        if origin == "Optional":
            return parts[0] + "?"
        name = {"list": "Список", "dict": "Словарь", "tuple": "Кортеж", "Callable": "Вызываемое"}.get(origin, origin)
        return f"{name}[{', '.join(parts)}]"
    if isinstance(node, ast.List):
        return "[" + ", ".join(format_type(e) for e in node.elts) + "]"
    return ast.unparse(node)


def visibility(name: str) -> str:
    if name.startswith("__"):
        return "-"
    return "#" if name.startswith("_") else "+"


def stored(node) -> str:
    if isinstance(node, ast.Constant):
        return repr(node.value).replace("None", "ничего") if node.value is not None else "ничего"
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def parse_file(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        stereo = ""
        for decor in node.decorator_list:
            if isinstance(decor, ast.Call) and isinstance(decor.func, ast.Name) and decor.func.id == "stereotype":
                stereo = decor.args[0].value
        bases = [ast.unparse(base_node) for base_node in node.bases]
        if "Enum" in bases or "Exception" in " ".join(bases) or "DomainError" in bases:
            continue
        attributes, operations, calls = [], [], {}
        for element in node.body:
            if isinstance(element, ast.AnnAssign) and isinstance(element.target, ast.Name):
                shown = stored(element.value) if element.value is not None else ""
                attributes.append({"вид": visibility(element.target.id), "имя": element.target.id, "тип": format_type(element.annotation), "знач": shown})
            elif isinstance(element, ast.Assign) and isinstance(element.targets[0], ast.Name) and element.targets[0].id.isupper():
                attributes.append({"вид": "+", "имя": element.targets[0].id, "тип": "", "знач": stored(element.value)})
            elif isinstance(element, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if element.name == "__init__":
                    for inner in ast.walk(element):
                        if (isinstance(inner, ast.AnnAssign) and isinstance(inner.target, ast.Attribute)
                                and isinstance(inner.target.value, ast.Name) and inner.target.value.id == "self"):
                            attributes.append({"вид": visibility(inner.target.attr), "имя": inner.target.attr,
                                             "тип": format_type(inner.annotation), "знач": ""})
                    continue
                if element.name.startswith("__") and element.name.endswith("__"):
                    continue
                param_list = [[a.arg, format_type(a.annotation)] for a in element.args.args if a.arg != "self"]
                returned = format_type(element.returns)
                operations.append({"вид": visibility(element.name), "имя": element.name, "парам": param_list,
                                 "возвр": "" if returned in ("ничего", "") else returned})
                for call in ast.walk(element):
                    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and isinstance(call.func.value, ast.Attribute)
                            and isinstance(call.func.value.value, ast.Name) and call.func.value.value.id == "self"):
                        calls.setdefault(call.func.value.attr, [])
                        if call.func.attr not in calls[call.func.value.attr]:
                            calls[call.func.value.attr].append(call.func.attr)
        yield {"имя": node.name, "модуль": str(path.relative_to(ROOT.parent)), "stereotype": stereo,
               "базы": bases, "атрибуты": attributes, "операции": operations, "вызовы": calls}


outcome = {}
for path in sorted(ROOT.rglob("*.py")):
    if path.name in ("__init__.py", "main.py", "markup.py"):
        continue
    for item in parse_file(path):
        outcome[item["имя"]] = item
pathlib.Path(__file__).resolve().parent.parent.joinpath("diagrams", "classes.json").write_text(
    json.dumps(outcome, ensure_ascii=False, indent=1), encoding="utf-8")
print("классов извлечено:", len(outcome))
for name in ("TestingController", "TestingForm", "Storage"):
    item = outcome[name]
    print(name, item["stereotype"], len(item["атрибуты"]), "атрибутов,", len(item["операции"]), "операций; вызовы:", {k: len(v) for k, v in item["вызовы"].items()})
