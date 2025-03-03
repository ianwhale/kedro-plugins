"""``GBQTableDataset`` loads and saves data from/to Google BigQuery. It uses pandas-gbq
to read and write from/to BigQuery table.
"""
import copy
import warnings
from pathlib import PurePosixPath
from typing import Any, Dict, NoReturn, Union

import fsspec
import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from google.oauth2.credentials import Credentials
from kedro.io.core import (
    get_filepath_str,
    get_protocol_and_path,
    validate_on_forbidden_chars,
)

from kedro_datasets import KedroDeprecationWarning
from kedro_datasets._io import AbstractDataset, DatasetError


class GBQTableDataset(AbstractDataset[None, pd.DataFrame]):
    """``GBQTableDataset`` loads and saves data from/to Google BigQuery.
    It uses pandas-gbq to read and write from/to BigQuery table.

    Example usage for the
    `YAML API <https://kedro.readthedocs.io/en/stable/data/\
    data_catalog_yaml_examples.html>`_:

    .. code-block:: yaml

        vehicles:
          type: pandas.GBQTableDataset
          dataset: big_query_dataset
          table_name: big_query_table
          project: my-project
          credentials: gbq-creds
          load_args:
            reauth: True
          save_args:
            chunk_size: 100

    Example usage for the
    `Python API <https://kedro.readthedocs.io/en/stable/data/\
    advanced_data_catalog_usage.html>`_:

    .. code-block:: pycon

        >>> from kedro_datasets.pandas import GBQTableDataset
        >>> import pandas as pd
        >>>
        >>> data = pd.DataFrame({"col1": [1, 2], "col2": [4, 5], "col3": [5, 6]})
        >>>
        >>> dataset = GBQTableDataset("dataset", "table_name", project="my-project")
        >>> dataset.save(data)
        >>> reloaded = dataset.load()
        >>>
        >>> assert data.equals(reloaded)

    """

    DEFAULT_LOAD_ARGS: Dict[str, Any] = {}
    DEFAULT_SAVE_ARGS: Dict[str, Any] = {"progress_bar": False}

    def __init__(  # noqa: PLR0913
        self,
        dataset: str,
        table_name: str,
        project: str = None,
        credentials: Union[Dict[str, Any], Credentials] = None,
        load_args: Dict[str, Any] = None,
        save_args: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Creates a new instance of ``GBQTableDataset``.

        Args:
            dataset: Google BigQuery dataset.
            table_name: Google BigQuery table name.
            project: Google BigQuery Account project ID.
                Optional when available from the environment.
                https://cloud.google.com/resource-manager/docs/creating-managing-projects
            credentials: Credentials for accessing Google APIs.
                Either ``google.auth.credentials.Credentials`` object or dictionary with
                parameters required to instantiate ``google.oauth2.credentials.Credentials``.
                Here you can find all the arguments:
                https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.credentials.html
            load_args: Pandas options for loading BigQuery table into DataFrame.
                Here you can find all available arguments:
                https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_gbq.html
                All defaults are preserved.
            save_args: Pandas options for saving DataFrame to BigQuery table.
                Here you can find all available arguments:
                https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_gbq.html
                All defaults are preserved, but "progress_bar", which is set to False.
            metadata: Any arbitrary metadata.
                This is ignored by Kedro, but may be consumed by users or external plugins.

        Raises:
            DatasetError: When ``load_args['location']`` and ``save_args['location']``
                are different.
        """
        # Handle default load and save arguments
        self._load_args = copy.deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)
        self._save_args = copy.deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

        self._validate_location()
        validate_on_forbidden_chars(dataset=dataset, table_name=table_name)

        if isinstance(credentials, dict):
            credentials = Credentials(**credentials)

        self._dataset = dataset
        self._table_name = table_name
        self._project_id = project
        self._credentials = credentials
        self._client = bigquery.Client(
            project=self._project_id,
            credentials=self._credentials,
            location=self._save_args.get("location"),
        )

        self.metadata = metadata

    def _describe(self) -> Dict[str, Any]:
        return {
            "dataset": self._dataset,
            "table_name": self._table_name,
            "load_args": self._load_args,
            "save_args": self._save_args,
        }

    def _load(self) -> pd.DataFrame:
        sql = f"select * from {self._dataset}.{self._table_name}"  # nosec
        self._load_args.setdefault("query", sql)
        return pd.read_gbq(
            project_id=self._project_id,
            credentials=self._credentials,
            **self._load_args,
        )

    def _save(self, data: pd.DataFrame) -> None:
        data.to_gbq(
            f"{self._dataset}.{self._table_name}",
            project_id=self._project_id,
            credentials=self._credentials,
            **self._save_args,
        )

    def _exists(self) -> bool:
        table_ref = self._client.dataset(self._dataset).table(self._table_name)
        try:
            self._client.get_table(table_ref)
            return True
        except NotFound:
            return False

    def _validate_location(self):
        save_location = self._save_args.get("location")
        load_location = self._load_args.get("location")

        if save_location != load_location:
            raise DatasetError(
                """"load_args['location']" is different from "save_args['location']". """
                "The 'location' defines where BigQuery data is stored, therefore has "
                "to be the same for save and load args. "
                "Details: https://cloud.google.com/bigquery/docs/locations"
            )


class GBQQueryDataset(AbstractDataset[None, pd.DataFrame]):
    """``GBQQueryDataset`` loads data from a provided SQL query from Google
    BigQuery. It uses ``pandas.read_gbq`` which itself uses ``pandas-gbq``
    internally to read from BigQuery table. Therefore it supports all allowed
    pandas options on ``read_gbq``.

    Example adding a catalog entry with the ``YAML API``:

    .. code-block:: yaml

        vehicles:
          type: pandas.GBQQueryDataset
          sql: "select shuttle, shuttle_id from spaceflights.shuttles;"
          project: my-project
          credentials: gbq-creds
          load_args:
            reauth: True


    Example using Python API:

    .. code-block:: pycon

        >>> from kedro_datasets.pandas import GBQQueryDataset
        >>>
        >>> sql = "SELECT * FROM dataset_1.table_a"
        >>>
        >>> dataset = GBQQueryDataset(sql, project="my-project")
        >>>
        >>> sql_data = dataset.load()
    """

    DEFAULT_LOAD_ARGS: Dict[str, Any] = {}

    def __init__(  # noqa: PLR0913
        self,
        sql: str = None,
        project: str = None,
        credentials: Union[Dict[str, Any], Credentials] = None,
        load_args: Dict[str, Any] = None,
        fs_args: Dict[str, Any] = None,
        filepath: str = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Creates a new instance of ``GBQQueryDataset``.

        Args:
            sql: The sql query statement.
            project: Google BigQuery Account project ID.
                Optional when available from the environment.
                https://cloud.google.com/resource-manager/docs/creating-managing-projects
            credentials: Credentials for accessing Google APIs.
                Either ``google.auth.credentials.Credentials`` object or dictionary with
                parameters required to instantiate ``google.oauth2.credentials.Credentials``.
                Here you can find all the arguments:
                https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.credentials.html
            load_args: Pandas options for loading BigQuery table into DataFrame.
                Here you can find all available arguments:
                https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_gbq.html
                All defaults are preserved.
            fs_args: Extra arguments to pass into underlying filesystem class constructor
                (e.g. `{"project": "my-project"}` for ``GCSFileSystem``) used for reading the
                SQL query from filepath.
            filepath: A path to a file with a sql query statement.
            metadata: Any arbitrary metadata.
                This is ignored by Kedro, but may be consumed by users or external plugins.

        Raises:
            DatasetError: When ``sql`` and ``filepath`` parameters are either both empty
                or both provided, as well as when the `save()` method is invoked.
        """
        if sql and filepath:
            raise DatasetError(
                "'sql' and 'filepath' arguments cannot both be provided."
                "Please only provide one."
            )

        if not (sql or filepath):
            raise DatasetError(
                "'sql' and 'filepath' arguments cannot both be empty."
                "Please provide a sql query or path to a sql query file."
            )

        # Handle default load arguments
        self._load_args = copy.deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)

        self._project_id = project

        if isinstance(credentials, dict):
            credentials = Credentials(**credentials)

        self._credentials = credentials
        self._client = bigquery.Client(
            project=self._project_id,
            credentials=self._credentials,
            location=self._load_args.get("location"),
        )

        # load sql query from arg or from file
        if sql:
            self._load_args["query"] = sql
            self._filepath = None
        else:
            # filesystem for loading sql file
            _fs_args = copy.deepcopy(fs_args) or {}
            _fs_credentials = _fs_args.pop("credentials", {})
            protocol, path = get_protocol_and_path(str(filepath))

            self._protocol = protocol
            self._fs = fsspec.filesystem(self._protocol, **_fs_credentials, **_fs_args)
            self._filepath = path

        self.metadata = metadata

    def _describe(self) -> Dict[str, Any]:
        load_args = copy.deepcopy(self._load_args)
        desc = {}
        desc["sql"] = str(load_args.pop("query", None))
        desc["filepath"] = str(self._filepath)
        desc["load_args"] = str(load_args)

        return desc

    def _load(self) -> pd.DataFrame:
        load_args = copy.deepcopy(self._load_args)

        if self._filepath:
            load_path = get_filepath_str(PurePosixPath(self._filepath), self._protocol)
            with self._fs.open(load_path, mode="r") as fs_file:
                load_args["query"] = fs_file.read()

        return pd.read_gbq(
            project_id=self._project_id,
            credentials=self._credentials,
            **load_args,
        )

    def _save(self, data: None) -> NoReturn:
        raise DatasetError("'save' is not supported on GBQQueryDataset")


_DEPRECATED_CLASSES = {
    "GBQTableDataSet": GBQTableDataset,
    "GBQQueryDataSet": GBQQueryDataset,
}


def __getattr__(name):
    if name in _DEPRECATED_CLASSES:
        alias = _DEPRECATED_CLASSES[name]
        warnings.warn(
            f"{repr(name)} has been renamed to {repr(alias.__name__)}, "
            f"and the alias will be removed in Kedro-Datasets 2.0.0",
            KedroDeprecationWarning,
            stacklevel=2,
        )
        return alias
    raise AttributeError(f"module {repr(__name__)} has no attribute {repr(name)}")
