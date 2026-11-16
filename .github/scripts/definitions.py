#!/usr/bin/env python3
"""Checks this repository's definitions with a real isx, and says which templates a change reaches.

  definitions.py configure [--build]
      Write config.yaml for CI: this checkout in searchPaths, and a placeholder credential for
      every account the templates name, so that a missing credential is no finding. With
      --build, no GitHub account: a build with a GitHub token asks GitHub whose it is, to set
      the git identity, and fails when it cannot. A run's own token belongs to no user, so a
      build clones anonymously and stamps no identity.
  definitions.py check
      Load every definition through isx and fail on anything isx would skip, ignore or refuse.
  definitions.py reach <base-ref>
      Print, as a JSON list, the templates to build for the changes since <base-ref>.
  definitions.py pick <names>
      The same list for templates asked for by name, space-separated, or 'all' for every one.
  definitions.py tool-template <name>
      Write the template a name from reach's list stands for when it starts with ci-tool-: one
      tool on tpl-dev, for a changed tool that no template here lists.

check and reach expect isx on PATH and config.yaml written by configure. They read isx's
--format=json output, which is a contract; of isx's warnings, check reads only whether one names
a file of this repository.
"""

import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMAGES = os.path.join(ROOT, "images")
TOOLS = os.path.join(ROOT, "tools")

# Built when only the CI itself or a file no definition is read from changed, so that a change to
# the workflow still proves the build path: tpl-dev, tpl-java and tpl-mydev under it, a repository
# clone with a prime, and this repository's own gradle tool.
CANARY = ["tpl-tamboui"]

# A changed tool that no template here lists is built on its own, in a template reach names with
# this prefix and tool-template writes, so that a tool only users' templates list is built too.
TOOL_TEMPLATE_PREFIX = "ci-tool-"
TOOL_TEMPLATE_PARENT = "tpl-dev"


def isx(*args, check=True, quiet=False):
    """
    Runs isx, returning (exit code, stdout, stderr). Its stderr is shown unless quiet and it
    succeeded: every isx run repeats the loaders' warnings, which load() has shown once.
    """
    proc = subprocess.run(["isx", *args], capture_output=True, text=True, cwd="/")
    if proc.stderr.strip() and (not quiet or proc.returncode != 0):
        sys.stderr.write(proc.stderr)
    if check and proc.returncode != 0:
        sys.exit(f"'isx {' '.join(args)}' exited {proc.returncode}")
    return proc.returncode, proc.stdout, proc.stderr


def yaml_files(directory):
    return sorted(os.path.join(directory, f) for f in os.listdir(directory)
                  if f.endswith((".yaml", ".yml")))


def read_yaml(path):
    """The file's YAML, or {} when it does not parse: isx's own loading reports that one."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def real(path):
    """The file a definition's source names, resolved; None for 'built-in' and other non-files."""
    return os.path.realpath(path) if path and os.path.isabs(path) else None


def ours(definition):
    """Whether isx loaded the definition from this checkout."""
    source = real(definition["source"])
    return source is not None and source.startswith(ROOT + os.sep)


def tool_names(entries):
    """The names a template's or tool's list gives: each entry is a name or a one-key map."""
    names = []
    for entry in entries or []:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict) and len(entry) == 1:
            names.append(next(iter(entry)))
        else:
            names.append(repr(entry))
    return names


def load():
    """isx's view: templates and tools by name, the file each came from, and the loaders' warnings."""
    _, out, templates_err = isx("templates", "list", "--format=json")
    templates = {t["name"]: t for t in json.loads(out)}
    _, out, tools_err = isx("tools", "list", "--format=json")
    tools = {t["name"]: t for t in json.loads(out)}
    return templates, tools, templates_err + tools_err


CONFIG = os.path.expanduser("~/.config/incus-spawn/config.yaml")

# What a placeholder credential looks like in each namespace a template may pin an account of.
PLACEHOLDERS = {
    "claude": lambda: {"type": "api-key", "apiKey": "sk-ant-placeholder-for-ci"},
    "github": lambda: {"token": "ghp_placeholder_for_ci"},
}


def configure(build):
    config = {}
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    config["searchPaths"] = [ROOT]
    named = {ns: {"default"} for ns in PLACEHOLDERS}
    for path in yaml_files(IMAGES):
        for ns, account in (read_yaml(path).get("accounts") or {}).items():
            if ns not in PLACEHOLDERS:
                sys.exit(f"{os.path.relpath(path, ROOT)} pins a '{ns}' account, and "
                         f"definitions.py has no placeholder for that namespace: add one to PLACEHOLDERS")
            named[ns].add(account)
    if build:
        if named["github"] != {"default"}:
            sys.exit("A template pins a GitHub account, which a build here cannot have: see configure")
        del named["github"]
        config.pop("github", None)
    for ns, accounts in named.items():
        config[ns] = {"accounts": {a: PLACEHOLDERS[ns]() for a in sorted(accounts)}, "default": "default"}
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False)
    os.chmod(CONFIG, 0o600)
    print(f"Configured {CONFIG}: " + "; ".join(f"{ns}: {', '.join(sorted(a))}" for ns, a in named.items()))


def check():
    templates, tools, warnings = load()
    problems = []

    by_source = {}
    for t in list(templates.values()) + list(tools.values()):
        by_source.setdefault(real(t["source"]), []).append(t["name"])

    # A file that does not parse, or whose name another file takes, is skipped by the loader with
    # a warning on stderr; here it is a file no definition comes from.
    for path in yaml_files(IMAGES) + yaml_files(TOOLS):
        rel = os.path.relpath(path, ROOT)
        names = by_source.get(real(path), [])
        if len(names) != 1:
            problems.append(f"{rel}: isx loads {len(names)} definitions from it ({', '.join(names) or 'none'}), not one")
        # The loader's warning names the file it is about (an unknown key, which isx ignores, or a
        # file it cannot read) or, from a tool's validation, the definition in quotes. The message
        # is shown above; that one exists is all this reads. Whole words only, so that a warning
        # about mydev.yaml is not one about dev.yaml.
        mentions = [re.escape(os.path.basename(path))] + [re.escape(f"'{n}'") for n in names]
        mentioned = re.compile(r"(?<![\w.-])(?:" + "|".join(mentions) + r")(?![\w.-])")
        if any(mentioned.search(line) for line in warnings.splitlines()):
            problems.append(f"{rel}: isx warned about this file while loading it (see above)")

    for path in yaml_files(TOOLS):
        rel = os.path.relpath(path, ROOT)
        for name in by_source.get(real(path), []):
            code, out, _ = isx("tools", "show", name, "--format=json", check=False, quiet=True)
            if code != 0:
                problems.append(f"{rel}: 'isx tools show {name}' exited {code}")
                continue
            for required in json.loads(out).get("requires") or []:
                if required not in tools:
                    problems.append(f"{rel}: requires '{required}', which is not a tool isx knows")

    for path in yaml_files(IMAGES):
        rel = os.path.relpath(path, ROOT)
        code, out, _ = isx("templates", "validate", path, "--format=json", check=False, quiet=True)
        try:
            result = json.loads(out)
        except json.JSONDecodeError:
            problems.append(f"{rel}: 'isx templates validate' exited {code} without a result")
            continue
        if code != 0 or not result.get("valid"):
            problems.append(f"{rel}: 'isx templates validate' says it is not valid")
        for finding in result.get("findings") or []:
            problems.append(f"{rel}: {finding['severity']} on {finding.get('field') or 'the file'}: {finding['message']}")
        # isx builds a template whose tool it does not know, with a warning, and without the tool.
        for name in tool_names(read_yaml(path).get("tools")):
            if name not in tools:
                problems.append(f"{rel}: lists tool '{name}', which is not a tool isx knows")

    for p in problems:
        print(f"::error::{p}")
    if problems:
        sys.exit(f"{len(problems)} problem(s) in the definitions")
    print(f"{len(yaml_files(IMAGES))} templates and {len(yaml_files(TOOLS))} tools load and validate")


def changed_files(base):
    out = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def minimal(templates, targets):
    """
    The targets to build, less those another target's build covers: building a template builds
    every parent it is missing, so a target whose descendant is also a target is built in that
    descendant's job.
    """
    def parent_of(name):
        if name.startswith(TOOL_TEMPLATE_PREFIX) and name not in templates:
            return TOOL_TEMPLATE_PARENT
        return templates.get(name, {}).get("parent")

    def ancestors(name):
        seen = []
        parent = parent_of(name)
        while parent and parent not in seen:
            seen.append(parent)
            parent = parent_of(parent)
        return seen

    covered = {a for t in targets for a in ancestors(t)}
    return sorted(targets - covered)


def reach(base):
    templates, tools, _ = load()
    source_of = {real(t["source"]): name for name, t in templates.items()}
    tool_source_of = {real(t["source"]): name for name, t in tools.items()}

    targets = set()
    changed_tools = set()
    other = False
    for rel in changed_files(base):
        path = real(os.path.join(ROOT, rel))
        if path in source_of:
            targets.add(source_of[path])
        elif path in tool_source_of:
            changed_tools.add(tool_source_of[path])
        elif not os.path.exists(path) and rel.startswith(("images/", "tools/")):
            pass  # a removed definition: check covers whatever still names it
        elif rel.endswith(".md") or rel == "LICENSE":
            pass  # read by people, never by isx
        else:
            other = True

    # A tool reaches the templates that list it, or list a tool that requires it.
    requires = {}
    for name in tools if changed_tools else []:
        requires[name] = json.loads(isx("tools", "show", name, "--format=json", quiet=True)[1]).get("requires") or []

    def closure(name, seen):
        if name in seen:
            return seen
        seen.add(name)
        for r in requires.get(name, []):
            closure(r, seen)
        return seen

    unlisted = set(changed_tools)
    for name, t in templates.items():
        if ours(t) and changed_tools:
            reached = set().union(*(closure(n, set()) for n in tool_names(read_yaml(t["source"]).get("tools"))))
            if changed_tools & reached:
                targets.add(name)
                unlisted -= reached
    # One that another of them requires is built in that one's template (a cycle keeps both).
    closures = {t: closure(t, set()) for t in unlisted}
    targets.update(TOOL_TEMPLATE_PREFIX + t for t in unlisted
                   if not any(t in closures[u] and u not in closures[t] for u in unlisted))

    if other and not targets:
        targets.update(CANARY)

    print(json.dumps(minimal(templates, targets)))


def pick(requested):
    templates, _, _ = load()
    names = sorted(n for n, t in templates.items() if ours(t)) if requested.strip() == "all" else requested.split()
    unknown = [n for n in names if n not in templates]
    if unknown:
        sys.exit(f"No template named {', '.join(unknown)}")
    print(json.dumps(minimal(templates, set(names))))


def tool_template(name):
    if not name.startswith(TOOL_TEMPLATE_PREFIX):
        sys.exit(f"{name} is not a tool template: its name starts with {TOOL_TEMPLATE_PREFIX}")
    _, tools, _ = load()
    tool = name[len(TOOL_TEMPLATE_PREFIX):]
    if tool not in tools:
        sys.exit(f"No tool named {tool}")
    images = os.path.join(os.path.dirname(CONFIG), "images")
    os.makedirs(images, exist_ok=True)
    path = os.path.join(images, name + ".yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"name": name, "description": f"CI: the {tool} tool alone",
                        "parent": TOOL_TEMPLATE_PARENT, "tools": [tool]}, f, sort_keys=False)
    print(f"Wrote {path}: {tool} on {TOOL_TEMPLATE_PARENT}")


def main():
    if len(sys.argv) in (2, 3) and sys.argv[1] == "configure" and sys.argv[2:] in ([], ["--build"]):
        configure(build=sys.argv[2:] == ["--build"])
    elif len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) == 3 and sys.argv[1] == "reach":
        reach(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "pick":
        pick(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "tool-template":
        tool_template(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
