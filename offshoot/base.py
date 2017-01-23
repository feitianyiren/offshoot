import yaml
import warnings

import sys
import inspect
import os

import ast

from offshoot.pluggable import Pluggable
from offshoot.manifest import Manifest


def default_configuration():
    return {
        "modules": [],
        "file_paths": {
            "plugins": "plugins",
            "config": "config/config.plugins.yml",
            "libraries": "requirements.plugins.txt"
        },
        "allow": {
            "files": True,
            "config": True,
            "libraries": True,
            "callbacks": True
        },
        "sandbox_configuration_keys": True
    }


def load_configuration(file_path):
    try:
        with open(file_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        warnings.warn("'offshoot.yml' not found! Using default configuration.")
        config = default_configuration()

    return config


def generate_configuration_file():
    with open("offshoot.yml", "w") as f:
        yaml.dump(default_configuration(), f, default_flow_style=False, indent=4)


def map_pluggable_classes(config):
    pluggable_classes = dict()

    for m in config.get("modules"):
        try:
            exec("import %s" % m)
            classes = inspect.getmembers(sys.modules[m], inspect.isclass)

            for c in classes:
                if not issubclass(c[1], Pluggable):
                    continue

                pluggable_classes[c[0]] = c[1]
        except ImportError:
            warnings.warn("'%s' does not appear to be a valid module. Skipping!" % m)

    return pluggable_classes


def validate_plugin_file(file_path, pluggable, directives):
    is_valid = True
    messages = list()

    with open(file_path, "r") as f:
        syntax_tree = ast.parse(f.read())

    seen_pluggable = False

    for statement in ast.walk(syntax_tree):
        if isinstance(statement, ast.ClassDef):
            class_name = statement.name

            current_expected = directives["expected"][:]
            bases = list(map(lambda b: b.id if isinstance(b, ast.Name) else b.attr, statement.bases))

            if pluggable in bases:
                seen_pluggable = True

                for body_item in statement.body:
                    if isinstance(body_item, ast.FunctionDef):
                        if body_item.name in directives["forbidden"]:
                            is_valid = False
                            messages.append("%s: '%s' method should not appear in the class." % (class_name, body_item.name))

                        if body_item.name in current_expected:
                            current_expected.remove(body_item.name)

                if len(current_expected):
                    is_valid = False
                    messages.append("%s: Some expected methods are missing from the class: %s" % (class_name, ", ".join(current_expected)))

    if seen_pluggable is False:
        is_valid = False
        messages.append("No classes inherit from the pluggable '%s'." % pluggable)

    return [is_valid, messages]


def installed_plugins():
    manifest = Manifest()
    plugins = manifest.list_plugins()

    installed = list()

    for name, plugin in plugins.items():
        installed.append("%s - %s" % (plugin.get("name"), plugin.get("version")))

    return installed


def discover(pluggable, scope):
    manifest = Manifest()

    plugin_file_paths = manifest.plugin_files_for_pluggable(pluggable)

    import_statements = list()

    for plugin_file_path, pluggable in plugin_file_paths:
        plugin_module = plugin_file_path.replace(os.sep, ".").replace(".py", "")
        plugin_class = None

        with open(plugin_file_path, "r") as f:
            syntax_tree = ast.parse(f.read())

        for statement in ast.walk(syntax_tree):
            if isinstance(statement, ast.ClassDef):
                class_name = statement.name
                bases = list(map(lambda b: b.id if isinstance(b, ast.Name) else b.attr, statement.bases))

                if pluggable in bases:
                    plugin_class = class_name

        if plugin_class:
            import_statements.append("from %s import %s" % (plugin_module, plugin_class))

    for import_statement in import_statements:
        exec(import_statement, scope)


def executable_hook(plugin_class):
    command = sys.argv[1]

    if command == "install":
        plugin_class.install()
    elif command == "uninstall":
        plugin_class.uninstall()


# Magic Validation Decorators
def accepted(func):
    return func


def expected(func):
    return func


def forbidden(func):
    return func
