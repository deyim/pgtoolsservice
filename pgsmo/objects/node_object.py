# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from abc import ABCMeta, abstractmethod
from typing import Callable, Dict, List, Optional, Union, TypeVar


import pgsmo.utils.templating as templating
import pgsmo.utils.querying as querying


class NodeObject(metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def _from_node_query(cls, conn: querying.ServerConnection, **kwargs):
        pass

    def __init__(self, conn: querying.ServerConnection, name: str):
        # Define the state of the object
        self._conn: querying.ServerConnection = conn
        self._child_collections: List[NodeCollection] = []

        # Declare node basic properties
        self._name: str = name
        self._oid: Optional[int] = None

    # PROPERTIES ###########################################################
    @property
    def name(self) -> str:
        return self._name

    @property
    def oid(self) -> Optional[int]:
        return self._oid

    # METHODS ##############################################################
    def refresh(self) -> None:
        """Refreshes and lazily loaded data"""
        self._refresh_child_collections()

    # PROTECTED HELPERS ####################################################
    def _register_child_collection(self, generator: Callable) -> 'NodeCollection':
        """
        Creates a node collection for child objects and registers it with the list of child objects.
        This is very useful for ensuring that all child collections are reset when refreshing.
        :param generator: Callable for generating the list of nodes
        :return: The created node collection
        """
        collection = NodeCollection(generator)
        self._child_collections.append(collection)
        return collection

    def _refresh_child_collections(self) -> None:
        """Iterates over the registered child collections and resets them"""
        for collection in self._child_collections:
            collection.reset()


TNC = TypeVar('TNC')


class NodeCollection:
    def __init__(self, generator: Callable[[], List[TNC]]):
        """
        Initializes a new collection of node objects.
        :param generator: A callable that returns a list of NodeObjects when called
        """
        self._generator: Callable[[], List[TNC]] = generator
        self._items: Optional[List[NodeObject]] = None

    def __getitem__(self, index: Union[int, str]) -> TNC:
        """
        Searches for a node in the list of items by OID or name
        :param index: If an int, the object ID of the item to look up. If a str, the name of the
                      item to look up. Otherwise, TypeError will be raised.
        :raises TypeError: If index is not a str or int
        :raises NameError: If an item with the provided index does not exist
        :return: The instance that matches the provided index
        """
        # Determine how we will be looking up the item
        if isinstance(index, int):
            # Lookup is by object ID
            lookup = (lambda x: x.oid == index)
        elif isinstance(index, str):
            # Lookup is by object name
            lookup = (lambda x: x.name == index)
        else:
            raise TypeError('Index must be either a string or int')

        # Load the items if they haven't been loaded
        self._ensure_loaded()

        # Look up the desired item
        for item in self._items:
            if lookup(item):
                return item

        # If we make it to here, an item with the given index does not exist
        raise NameError('An item with the provided index does not exist')

    def __iter__(self):
        self._ensure_loaded()
        return self._items.__iter__()

    def __len__(self):
        # Load the items if they haven't been loaded
        self._ensure_loaded()
        return len(self._items)

    def reset(self) -> None:
        # Empty the items so that next iteration will reload the collection
        self._items = None

    def _ensure_loaded(self) -> None:
        # Load the items if they haven't been loaded
        if self._items is None:
            self._items = self._generator()


T = TypeVar('T')


def get_nodes(conn: querying.ServerConnection,
              template_root: str,
              generator: Callable[[type, querying.ServerConnection, Dict[str, any]], T],
              **kwargs) -> List[T]:
    """
    Renders and executes nodes.sql for the given database version to generate a list of NodeObjects
    :param conn: Connection to use to execute the nodes query
    :param template_root: Root directory of the templates
    :param generator: Callable to execute with a row from the nodes query to generate the NodeObject
    :param kwargs: Optional parameters provided as the context for rendering the template
    :return: A NodeObject generated by the generator
    """
    sql = templating.render_template(
        templating.get_template_path(template_root, 'nodes.sql', conn.version),
        **kwargs
    )
    cols, rows = conn.execute_dict(sql)

    return [generator(conn, **row) for row in rows]
