"""BioSequenceDataset loads and saves data to/from bio-sequence objects to
file.
"""
import warnings
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Dict, List

import fsspec
from Bio import SeqIO
from kedro.io.core import get_filepath_str, get_protocol_and_path

from kedro_datasets import KedroDeprecationWarning
from kedro_datasets._io import AbstractDataset


class BioSequenceDataset(AbstractDataset[List, List]):
    r"""``BioSequenceDataset`` loads and saves data to a sequence file.

    Example:

    .. code-block:: pycon

        >>> from kedro_datasets.biosequence import BioSequenceDataset
        >>> from io import StringIO
        >>> from Bio import SeqIO
        >>>
        >>> data = ">Alpha\nACCGGATGTA\n>Beta\nAGGCTCGGTTA\n"
        >>> raw_data = []
        >>> for record in SeqIO.parse(StringIO(data), "fasta"):
        ...     raw_data.append(record)
        ...
        >>>
        >>> dataset = BioSequenceDataset(
        ...     filepath="ls_orchid.fasta",
        ...     load_args={"format": "fasta"},
        ...     save_args={"format": "fasta"},
        ... )
        >>> dataset.save(raw_data)
        >>> sequence_list = dataset.load()
        >>>
        >>> assert raw_data[0].id == sequence_list[0].id
        >>> assert raw_data[0].seq == sequence_list[0].seq

    """

    DEFAULT_LOAD_ARGS: Dict[str, Any] = {}
    DEFAULT_SAVE_ARGS: Dict[str, Any] = {}

    def __init__(  # noqa: PLR0913
        self,
        filepath: str,
        load_args: Dict[str, Any] = None,
        save_args: Dict[str, Any] = None,
        credentials: Dict[str, Any] = None,
        fs_args: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """
        Creates a new instance of ``BioSequenceDataset`` pointing
        to a concrete filepath.

        Args:
            filepath: Filepath in POSIX format to sequence file prefixed with a protocol like
                `s3://`. If prefix is not provided, `file` protocol (local filesystem) will be used.
                The prefix should be any protocol supported by ``fsspec``.
            load_args: Options for parsing sequence files by Biopython ``SeqIO.parse()``.
            save_args: file format supported by Biopython ``SeqIO.write()``.
                E.g. `{"format": "fasta"}`.
            credentials: Credentials required to get access to the underlying filesystem.
                E.g. for ``GCSFileSystem`` it should look like `{"token": None}`.
            fs_args: Extra arguments to pass into underlying filesystem class constructor
                (e.g. `{"project": "my-project"}` for ``GCSFileSystem``), as well as
                to pass to the filesystem's `open` method through nested keys
                `open_args_load` and `open_args_save`.
                Here you can find all available arguments for `open`:
                https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.spec.AbstractFileSystem.open
                All defaults are preserved, except `mode`, which is set to `r` when loading
                and to `w` when saving.
            metadata: Any arbitrary metadata.
                This is ignored by Kedro, but may be consumed by users or external plugins.

        Note: Here you can find all supported file formats: https://biopython.org/wiki/SeqIO
        """

        _fs_args = deepcopy(fs_args) or {}
        _fs_open_args_load = _fs_args.pop("open_args_load", {})
        _fs_open_args_save = _fs_args.pop("open_args_save", {})
        _credentials = deepcopy(credentials) or {}

        protocol, path = get_protocol_and_path(filepath)

        self._filepath = PurePosixPath(path)
        self._protocol = protocol
        if protocol == "file":
            _fs_args.setdefault("auto_mkdir", True)

        self._fs = fsspec.filesystem(self._protocol, **_credentials, **_fs_args)

        # Handle default load and save arguments
        self._load_args = deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)
        self._save_args = deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

        _fs_open_args_load.setdefault("mode", "r")
        _fs_open_args_save.setdefault("mode", "w")
        self._fs_open_args_load = _fs_open_args_load
        self._fs_open_args_save = _fs_open_args_save

        self.metadata = metadata

    def _describe(self) -> Dict[str, Any]:
        return {
            "filepath": self._filepath,
            "protocol": self._protocol,
            "load_args": self._load_args,
            "save_args": self._save_args,
        }

    def _load(self) -> List:
        load_path = get_filepath_str(self._filepath, self._protocol)
        with self._fs.open(load_path, **self._fs_open_args_load) as fs_file:
            return list(SeqIO.parse(handle=fs_file, **self._load_args))

    def _save(self, data: List) -> None:
        save_path = get_filepath_str(self._filepath, self._protocol)

        with self._fs.open(save_path, **self._fs_open_args_save) as fs_file:
            SeqIO.write(data, handle=fs_file, **self._save_args)

    def _exists(self) -> bool:
        load_path = get_filepath_str(self._filepath, self._protocol)
        return self._fs.exists(load_path)

    def _release(self) -> None:
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Invalidate underlying filesystem caches."""
        filepath = get_filepath_str(self._filepath, self._protocol)
        self._fs.invalidate_cache(filepath)


_DEPRECATED_CLASSES = {
    "BioSequenceDataSet": BioSequenceDataset,
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
