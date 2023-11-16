"""
Cohere dataset definition.
"""

from typing import Any, Dict, NoReturn

from cohere import AsyncClient, Client
from kedro.io import AbstractDataset, DatasetError
from langchain.llms import Cohere


class CohereDataset(AbstractDataset[None, Cohere]):
    """``CohereDataset`` loads a Cohere `langchain <https://python.langchain.com/>`_ model.

    Example usage for the :doc:`YAML API <kedro:data/data_catalog_yaml_examples>`:

    catalog.yml:

    .. code-block:: yaml
       command:
         type: langchain.cohere.CohereDataset
         kwargs:
           model: "command"
           temperature: 0.0
         credentials: cohere


    credentials.yml:

    .. code-block:: yaml
       cohere:
         cohere_api_url: <cohere-api-base>
         cohere_api_key: <cohere-api-key>
    """

    def __init__(self, credentials: Dict[str, str], kwargs: Dict[str, Any] = None):
        """Constructor.

        Args:
            credentials: must contain `cohere_api_url` and `cohere_api_key`.
            kwargs: keyword arguments passed to the underlying constructor.
        """
        self.cohere_api_url = credentials["cohere_api_url"]
        self.cohere_api_key = credentials["cohere_api_key"]
        self.kwargs = kwargs or {}

    def _describe(self) -> dict[str, Any]:
        return {**self.kwargs}

    def _save(self, data: None) -> NoReturn:
        raise DatasetError(f"{self.__class__.__name__} is a read only data set type")

    def _load(self) -> Cohere:
        llm = Cohere(cohere_api_key="_", **self.kwargs)

        client_kwargs = {
            "api_key": self.cohere_api_key,
            "api_url": self.cohere_api_url,
        }
        llm.client = Client(**client_kwargs, client_name=llm.user_agent)
        llm.async_client = AsyncClient(**client_kwargs, client_name=llm.user_agent)

        return llm
