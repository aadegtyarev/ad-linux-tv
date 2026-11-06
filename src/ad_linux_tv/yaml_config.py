"""YAML parser that rejects duplicate mapping keys."""

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                None, None, "duplicate mapping key", key_node.start_mark
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
)


def load_yaml(text):
    return yaml.load(text, Loader=UniqueKeyLoader)


class ShortcutRecoveryLoader(UniqueKeyLoader):
    """Ignore only the top-level shortcut subtree; reject other duplicates."""

    def __init__(self, stream):
        super().__init__(stream)
        self.root_node = None
        self.removed_shortcuts = False

    def construct_document(self, node):
        self.root_node = node
        return super().construct_document(node)


def construct_recovery_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if node is loader.root_node and key == "tv_shortcuts":
            loader.removed_shortcuts = True
            continue
        if key in result:
            raise ValueError("duplicate mapping key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


ShortcutRecoveryLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_recovery_mapping
)


def load_yaml_for_shortcut_recovery(text):
    loader = ShortcutRecoveryLoader(text)
    try:
        data = loader.get_single_data()
        return data, loader.removed_shortcuts
    finally:
        loader.dispose()
