"""The catalog of the grounder as data: which models a question in plain words may be about, and how each is
recognised.

    {"models": {"account.move": {
        "description": "...",
        "priority": 40,                                  # the higher wins when more than one model matches
        "match": [["fattur"], ["nota di credito"]],      # alternatives; each a list of substrings, all needed
        "synonyms": [...], "default_fields": [...], "allowed_fields": [...],
        "date_field": "...", "business_filters": {...}, "field_aliases": {...}}}}

`match` says how a model is chosen: one alternative is enough, and an alternative holds when every one of its
substrings is in the question, so that "fornitor" with "ordin" is one way to mean a purchase order while
"fornitor" alone means a partner. The rules were code; as data a sector adds its own.

Three layers, each replacing the whole entry of a model of the one before:

    core      texo/catalog.json
    packs     catalog.json in the folder of each installed pack
    folder    texo.catalog.json at the root of the working folder

Two packs that define the same model differently are a conflict: texo mount refuses it and names both. Two
models of the union with the same priority and an alternative in common are reported: which one a question
means would depend on the order they were read in. texo mount leaves what the packs and the folder add in
.texo/catalog.json, where the grounder reads it next to the core's.
"""
import itertools
import json
from pathlib import Path

CORE_FILE = Path(__file__).with_name("catalog.json")
PACK_FILE = "catalog.json"
FOLDER_FILE = "texo.catalog.json"
MOUNTED_FILE = ".texo/catalog.json"
LISTS = ("synonyms", "default_fields", "allowed_fields")


def read_models(path):
    """The models of a catalog file: ({model: entry}, problems). A file that is missing gives nothing; one that
    cannot be read, or an entry in the wrong form, is a problem and its models are left out."""
    path = Path(path)
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, [f"{path} cannot be read: {error}"]
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        return {}, [f"{path}: a catalog is {{\"models\": {{model: entry}}}}"]
    problems = [f"{path}: {problem}" for model, entry in models.items() for problem in entry_problems(model, entry)]
    return ({} if problems else models), problems


def entry_problems(model, entry):
    """The problems of the entry of a model: what the grounder would trip on."""
    if not isinstance(model, str) or not model or not isinstance(entry, dict):
        return [f"the entry of {model!r} is an object"]
    problems = []
    if not isinstance(entry.get("priority", 0), int) or isinstance(entry.get("priority", 0), bool):
        problems.append(f"{model}: priority is a whole number")
    match = entry.get("match", [])
    def words(alternative):
        return isinstance(alternative, list) and alternative and all(isinstance(w, str) and w for w in alternative)

    if not isinstance(match, list) or not all(words(alternative) for alternative in match):
        problems.append(f"{model}: match is a list of alternatives, each a list of substrings")
    for key in LISTS:
        if not isinstance(entry.get(key, []), list) or not all(isinstance(item, str) for item in entry.get(key, [])):
            problems.append(f"{model}: {key} is a list of names")
    if not entry.get("allowed_fields"):
        problems.append(f"{model}: allowed_fields says which fields a question may read and filter by")
    for key in ("business_filters", "field_aliases"):
        if not isinstance(entry.get(key, {}), dict):
            problems.append(f"{model}: {key} is an object")
    return problems


def core_models():
    return json.loads(CORE_FILE.read_text(encoding="utf-8")).get("models", {})


def union(layers):
    """(catalog, origin, problems) of the layers [(name, kind, {model: entry})], kind core, pack or folder, in
    the order they apply. problems are (level, message): a conflict between two packs is an error, two models
    that would answer the same words at the same priority a warning."""
    catalog, origin, conflicts = {}, {}, {}
    for name, kind, models in layers:
        for model, entry in models.items():
            if kind == "pack" and origin.get(model, ("", ""))[1] == "pack" and catalog[model] != entry:
                conflicts[model] = (f"catalog: the packs {origin[model][0]} and {name} both define {model}, "
                                    "differently: one of them gives it up, or the folder decides with its own "
                                    f"entry in {FOLDER_FILE}")
                continue
            catalog[model], origin[model] = entry, (name, kind)
    # a model the folder defines is the folder's: what the packs disagree on no longer matters
    problems = [("error", message) for model, message in conflicts.items() if origin[model][1] != "folder"]
    for (first, one), (second, other) in itertools.combinations(catalog.items(), 2):
        shared = [alternative for alternative in one.get("match", []) if alternative in other.get("match", [])]
        if shared and one.get("priority", 0) == other.get("priority", 0):
            problems.append(("warning", f"catalog: {first} ({origin[first][0]}) and {second} ({origin[second][0]}) "
                                        f"answer to {' + '.join(shared[0])} at the same priority "
                                        f"{one.get('priority', 0)}: give one of them a higher one"))
    return catalog, origin, problems


def added_layers(fabric):
    """(layers, problems) of what the installed packs and the folder add to the catalog of the core."""
    from . import packs  # packs reads the configuration: imported here, not at the top
    layers, problems = [], []
    for pack in fabric.packs:
        if packs.manifest(fabric, pack) is None:
            continue
        models, found = read_models(packs.folder(fabric, pack) / PACK_FILE)
        problems += [("error", f"pack {pack['name']}: {problem}") for problem in found]
        if models:
            layers.append((pack["name"], "pack", models))
    models, found = read_models(fabric.root / FOLDER_FILE)
    problems += [("error", problem) for problem in found]
    if models:
        layers.append(("this folder", "folder", models))
    return layers, problems


def of_fabric(fabric):
    """(what the packs and the folder add, its origin, problems) for a working folder: the union is made with
    the core, so that a conflict or a tie with a model of the core is seen, and the core's own entries are
    left out of what is kept."""
    layers, problems = added_layers(fabric)
    catalog, origin, found = union([("core", "core", core_models()), *layers])
    added = {model: entry for model, entry in catalog.items() if origin[model][1] != "core"}
    return added, {model: origin[model][0] for model in added}, problems + found


def mounted_models(root):
    """What texo mount left for a folder (MOUNTED_FILE): the models the packs and the folder add or replace."""
    if not root:
        return {}
    try:
        data = json.loads((Path(root) / MOUNTED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    models = data.get("models") if isinstance(data, dict) else None
    return models if isinstance(models, dict) else {}


def models_of(root=None):
    """The catalog a question is grounded on: the core's, with what the folder mounted on top."""
    return {**core_models(), **mounted_models(root)}


def match_model(catalog, text):
    """The model a question is about, by the rules of the catalog: among the models one of whose alternatives
    holds (all its substrings are in the question), the one with the highest priority; at the same priority,
    the first of the catalog. None when no rule holds."""
    text = text.lower()
    best, best_priority = None, None
    for model, entry in catalog.items():
        if any(all(word in text for word in alternative) for alternative in entry.get("match", [])):
            priority = entry.get("priority", 0)
            if best is None or priority > best_priority:
                best, best_priority = model, priority
    return best
