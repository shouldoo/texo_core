"""texo seed: the seed of the industries of a fabric into its hub.

Every industry may carry hub/seed.toml: the activities, sections, organisation rules and project templates
of its sector. The hub writes them by stable key (route admin/seed, administrators only): a dry run first,
then --apply. The http threads with hub_channel = true become channels of the external sources of the hub
(texo_sources), once: a channel with the same website is left as it is.
"""
import sys
import tomllib

from .config import ConfigError

KINDS = ("activities", "sections", "rules", "project_templates")


def payload(fabric, industry):
    path = fabric.industry_dir(industry) / "hub" / "seed.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from None
    unknown = sorted(set(data) - set(KINDS) - {"lang"})
    if unknown:
        raise ConfigError(f"{path}: unknown tables {', '.join(unknown)} (known: {', '.join(KINDS)})")
    result = {kind: data.get(kind) or [] for kind in KINDS}
    result["industry"] = industry["name"]
    if data.get("lang"):
        result["lang"] = data["lang"]
    return result


def render(answer, out):
    counts = ", ".join(f"{count} {status}" for status, count in sorted(answer["counts"].items())) or "nothing"
    out.write(f"{answer['industry']}: {counts}{'' if answer['applied'] else ' (dry run)'}\n")
    for item in answer["items"]:
        if item["status"] == "unchanged":
            continue
        detail = item.get("reason") or ""
        if item.get("changes"):
            detail = f"{detail} {', '.join(item['changes'])}".strip()
        out.write(f"  [{item['status']}] {item['kind']} {item['key']}: {item['name']}"
                  f"{f' ({detail})' if detail else ''}\n")


def channels(fabric, hub, apply, out):
    for thread in fabric.threads:
        if thread.get("driver") != "http" or not thread.get("hub_channel"):
            continue
        found = hub.call("search_read", {"model": "memory.source.channel", "fields": ["id"],
                                         "domain": [["website", "=", thread["url"]]], "limit": 1})
        if found:
            out.write(f"  [unchanged] channel {thread['id']}: {thread['url']}\n")
            continue
        if apply:
            hub.call("sources/channel", {"name": thread.get("name") or thread["id"], "website": thread["url"],
                                         "kind": thread.get("channel_kind") or "other", "look_for": thread.get("guide"),
                                         "every_days": thread.get("every_days") or 7,
                                         "feeds": thread.get("feeds") or []})
        out.write(f"  [created] channel {thread['id']}: {thread['url']}{'' if apply else ' (dry run)'}\n")


def seed(fabric, hub, apply=False, out=sys.stdout):
    for industry in fabric.industries:
        data = payload(fabric, industry)
        if data is None:
            out.write(f"{industry['name']}: no hub/seed.toml\n")
            continue
        render(hub.call("admin/seed", dict(data, apply=apply)), out)
    if any(t.get("hub_channel") for t in fabric.threads):
        out.write("channels of the external sources:\n")
        channels(fabric, hub, apply, out)
    if not apply:
        out.write("Dry run: nothing written. Read the list with the person, then texo seed --apply --yes.\n")
    return 0
