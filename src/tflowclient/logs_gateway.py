# -*- coding: utf-8 -*-

"""
Abstract and concrete classes that:

  * List available log file for a given task (represented by its path)
  * Fetch the content of a given log file

"""

import abc
import contextlib
import io
import logging
import re
import tempfile
import typing

__all__ = ['LogsGatewayRuntimeError', 'LogsGateway', 'get_logs_gateway']

from abc import ABCMeta

logger = logging.getLogger(__name__)


class LogsGatewayRuntimeError(RuntimeError):
    """Any error raised by the LogsGateway at runtime."""
    pass


class LogsGateway(metaclass=abc.ABCMeta):
    """The abstract class for any class providing access to log files."""

    _ALLOWED_SUFFIXES = r'\.(\d+|job\d+|sms|ecf)'

    def __init__(self, ** kwargs):
        """
        :param kwargs: any arguments that will be recoded in the objects dictionary
        """
        super().__init__()
        self._valid_kwargs(kwargs)
        for k, v in kwargs.items():
            self.__dict__[k] = v

    @staticmethod
    def _valid_kwargs(kwargs: dict):
        assert isinstance(kwargs, dict)

    def list_file(self, path: str) -> typing.List[str]:
        """Return the list of available files for a given task's **path**."""
        path_logs = re.compile(r'(.*/)?' + re.escape(path.split('/')[-1])
                               + self._ALLOWED_SUFFIXES)
        found = sorted({p for p in self._retrieve_files_list(path)
                        if path_logs.match(p)})
        logger.debug('Path=%s. Found the following log files: %s.',
                     path, str(found))
        return found

    @abc.abstractmethod
    def _retrieve_files_list(self, path: str) -> typing.Set[str]:
        """
        Effectively returns the possibly unfiltered set of available files
        for a given task's **path**.
        """
        pass

    @abc.abstractmethod
    def get_as_file(self, path: str, log_file: str) -> typing.ContextManager[io.TextIOBase]:
        """Return a **log_file** content as a FileIO object (with an 'name' attribute).

        This method should be used as a context manager so that the file can be
        cleaned from the file system when we are done with it.
        """
        pass

    @abc.abstractmethod
    def get_as_str(self, path: str, log_file: str) -> str:
        """Return a **log_file** content as a string."""
        pass


class StringBasedLogsGateway(LogsGateway, metaclass=ABCMeta):
    """A variant of LogsGateway where the temporary filename is automatically generated."""

    @contextlib.contextmanager
    def get_as_file(self, path: str, log_file: str) -> typing.ContextManager[io.TextIOBase]:
        """Return a **log_file** content as a FileIO object (with an 'name' attribute)."""
        with tempfile.NamedTemporaryFile('w+', encoding='utf-8', delete=True,
                                         prefix='log_{:s}'.format(log_file)) as t_file:
            t_file.write(self.get_as_str(path, log_file))
            t_file.flush()
            yield t_file


# This is the text that will appears when any log file is requested with the
# DemoLogs Gateway
_DEMO_LOG_FILE_TPL = """This is a demo logfile.

It has been generating for task:
{0:s}

and log_file:
{1:s}
"""


class DemoLogsGateway(StringBasedLogsGateway):
    """Return fake log files for the demonstration script."""

    @staticmethod
    def _valid_kwargs(kwargs):
        """This class does not accepts extra arguments."""
        if kwargs:
            raise ValueError("The DemoLogsGateway takes no additional arguments.")

    def _retrieve_files_list(self, path: str) -> typing.Set[str]:
        """Generate some fake log names."""
        basename = path.split('/')[-1]
        # Note: '_some_trash' should be filtered (this is a test)
        return {'{:s}{:s}'.format(basename, suffix)
                for suffix in ('.1', '.job1', '.sms', '_some_trash')}

    def get_as_str(self, path: str, log_file: str) -> str:
        """Return a **log_file** content as a string."""
        return _DEMO_LOG_FILE_TPL.format(path, log_file)


def get_logs_gateway(kind: str, **kwargs) -> LogsGateway:
    """A simple factory method for LogsGateway classes."""
    if kind == 'demo':
        return DemoLogsGateway(** kwargs)
    else:
        raise ValueError('No logs gateway is available for kin="%s"'
                         .format(kind))
