# -*- coding: utf-8 -*-

#  Copyright (©) Meteo-France (2020-)
#
#  This software is a computer program whose purpose is to provide
#   a text-based console client to interact with various workflow schedulers.
#
#  This software is governed by the CeCILL-C license under French law and
#  abiding by the rules of distribution of free software.  You can  use,
#  modify and/ or redistribute the software under the terms of the CeCILL-C
#  license as circulated by CEA, CNRS and INRIA at the following URL
#  "http://www.cecill.info".
#
#  As a counterpart to the access to the source code and  rights to copy,
#  modify and redistribute granted by the license, users are provided only
#  with a limited warranty  and the software's author,  the holder of the
#  economic rights,  and the successive licensors  have only  limited
#  liability.
#
#  In this respect, the user's attention is drawn to the risks associated
#  with loading,  using,  modifying and/or developing or reproducing the
#  software by the user in light of its specific status of free software,
#  that may mean  that it is complicated to manipulate,  and  that  also
#  therefore means  that it is reserved for developers  and  experienced
#  professionals having in-depth computer knowledge. Users are therefore
#  encouraged to load and test the software's suitability as regards their
#  requirements in conditions enabling the security of their systems and/or
#  data to be ensured and,  more generally, to use and operate it in the
#  same conditions as regards security.
#
#  The fact that you are presently reading this means that you have had
#  knowledge of the CeCILL-C license and that you accept its terms.

"""
Abstract and concrete classes that:

  * List available log file for a given task (represented by its path)
  * Fetch the content of a given log file

"""

import abc
import contextlib
from datetime import datetime
import io
import logging
import os
import re
import socket
import tempfile
import typing

__all__ = ["LogsGatewayRuntimeError", "LogsGateway", "get_logs_gateway"]

from abc import ABCMeta

logger = logging.getLogger(__name__)


class LogsGatewayRuntimeError(RuntimeError):
    """Any error raised by the LogsGateway at runtime."""

    pass


class LogsGateway(metaclass=abc.ABCMeta):
    """The abstract class for any class providing access to log files."""

    _ALLOWED_SUFFIXES = r"\.(\d+|job\d+|sms|ecf)"

    def __init__(self, **kwargs):
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

    @staticmethod
    def ping(**kwargs) -> bool:
        """Returns **True** if the logs gateway works properly."""
        return True

    def list_file(self, path: str) -> typing.List[typing.Tuple[str, datetime]]:
        """Return the list of available files for a given task's **path**.

        A list of tuples that contain the filename (or path) to the log file
        and a datetime object representing the log file modification time (UTC).
        """
        path_logs = re.compile(
            r"(.*/)?" + re.escape(path.split("/")[-1]) + self._ALLOWED_SUFFIXES
        )
        found = sorted(
            {
                data
                for data in self._retrieve_files_list(path)
                if path_logs.match(data[0])
            },
            key=lambda x: (x[1], x[0]),
            reverse=True,
        )
        logger.debug("Path=%s. Found the following log files: %s.", path, str(found))
        return found

    @abc.abstractmethod
    def _retrieve_files_list(
        self, path: str
    ) -> typing.Set[typing.Tuple[str, datetime]]:
        """
        Effectively returns the possibly unfiltered set of available files
        for a given task's **path**.
        """
        pass

    @abc.abstractmethod
    def get_as_file(
        self, path: str, log_file: str
    ) -> typing.ContextManager[io.TextIOBase]:
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
    def get_as_file(
        self, path: str, log_file: str
    ) -> typing.ContextManager[io.TextIOBase]:
        """Return a **log_file** content as a FileIO object (with an 'name' attribute)."""
        with tempfile.NamedTemporaryFile(
            "w+",
            encoding="utf-8",
            delete=True,
            prefix="log_{:s}".format(os.path.basename(log_file)),
        ) as t_file:
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

    def _retrieve_files_list(
        self, path: str
    ) -> typing.Set[typing.Tuple[str, datetime]]:
        """Generate some fake log names."""
        basename = path.split("/")[-1]
        # Note: '_some_trash' should be filtered (this is a test)
        return {
            ("{:s}{:s}".format(basename, suffix), datetime(2020, 1, 1, 0, 5 * i, 0))
            for i, suffix in enumerate((".sms", ".job1", ".1", "_some_trash"))
        }

    def get_as_str(self, path: str, log_file: str) -> str:
        """Return a **log_file** content as a string."""
        return _DEMO_LOG_FILE_TPL.format(path, log_file)


class SmsLogSvrGateway(StringBasedLogsGateway):
    """Interact with the "official" SMS log server.

    This class needs to be provided with a **host** name and **port** number
    at object creation time.

    The :class:`LogsGatewayRuntimeError` exception will be raised if an error
    occurs when communicating with the server.
    """

    _SOCKET_BUFFER_SIZE = 64 * 1024  # 64Kb
    _RESULT_MAX_SIZE = 64 * 1024 * 1024  # 64Mb

    @staticmethod
    def _valid_kwargs(kwargs):
        if set(kwargs.keys()) != {"host", "port", "paths"}:
            raise ValueError("paths, host and port attributes are required.")
        kwargs["paths"] = [p.rstrip("/") for p in kwargs["paths"]]

    def _query_server(
        self, command: str, connect_timeout: int = 5, send_timeout: int = 15
    ) -> str:
        """Send a **command** to the log server end get its answer."""
        response = b""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.setblocking(True)
                client.settimeout(connect_timeout)
                client.connect((self.host, self.port))
                client.settimeout(send_timeout)
                client.sendall(command.encode(encoding="utf-8") + b"\n")
                while len(response) < self._RESULT_MAX_SIZE:
                    data = client.recv(self._SOCKET_BUFFER_SIZE)
                    if not data:
                        break
                    response += data
        except OSError as e:
            logger.error(
                "Error when talking to the SMS log server (%s:%d):    \n%s",
                self.host,
                self.port,
                str(e),
            )
            raise LogsGatewayRuntimeError(
                "Error when talking to the SMS log server ({:s}:{:d})".format(
                    self.host, self.port
                )
            )
        return response.decode(encoding="utf-8", errors="replace")

    def ping(self, connect_timeout: int = 2) -> bool:
        """Try a dummy request just to check if the log_server is fine."""
        try:
            self._query_server(
                "list {:s}/fakexp/task.0".format(self.paths[0]),
                connect_timeout=connect_timeout,
            )
        except LogsGatewayRuntimeError:
            return False
        return True

    def _retrieve_files_list(
        self, path: str
    ) -> typing.Set[typing.Tuple[str, datetime]]:
        """Get the log files list (from server)."""
        paths = set()
        for l_path in self.paths:
            f_list = self._query_server(
                "list {:s}/{:s}.0".format(l_path, path.strip("/"))
            )
            if f_list:
                f_list = [
                    line.strip(" ").split(" ")
                    for line in f_list.split("\n")
                    if line.strip(" ")
                ]
                for entry in f_list:
                    if entry:
                        paths.add((entry[-1], datetime.utcfromtimestamp(int(entry[5]))))
        return paths

    def get_as_str(self, path: str, log_file: str) -> str:
        """Return a **log_file** content as a string."""
        return self._query_server("get {:s}".format(log_file))


def get_logs_gateway(kind: str, **kwargs) -> LogsGateway:
    """A simple factory method for LogsGateway classes."""
    logger.debug("Ceating a log gateway. kind=%s. kwargs=%s", kind, kwargs)
    if kind == "demo":
        return DemoLogsGateway(**kwargs)
    elif kind == "sms_log_svr":
        return SmsLogSvrGateway(**kwargs)
    else:
        raise ValueError('No logs gateway is available for kin="%s"'.format(kind))
