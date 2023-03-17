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
Concrete implementation of the :class:`FlowInterface` class that interacts
with an SMS CDP client.

Some utility classes related to the use of the SMS CDP client are also provided.
"""

import abc
import collections
import io
import logging
import os
import re
import stat
import subprocess
import threading
import time
import typing

from .flow import FlowInterface, RootFlowNode, FlowNode, FlowStatus, ExtraFlowNodeInfo
from .logs_gateway import LogsGateway, get_logs_gateway

__all__ = [
    "SmsRcFileError",
    "SmsRcPermissionsError",
    "SmsRcReader",
    "CdpOutputParserMixin",
    "CdpInterface",
]

logger = logging.getLogger(__name__)


class SmsRcFileError(OSError):
    """Any exception raised when trying to read the ~/.smsrc file."""

    pass


class SmsRcPermissionsError(SmsRcFileError):
    """Exception raised when the ~/.smsrc file permissions are erroneous."""

    pass


class SmsRcReader(object):
    """Read and process the ``~/.smsrc`` file where SMS passwords are stored.

    Such a file is a simple list of lines: ``host user password``

    :note: The file's permissions will be checked before use (the group and
           others must have null permissions on this file).
    """

    _SMSRC_LOCATION = os.path.join(os.environ["HOME"], ".smsrc")

    def __init__(self, rc_file: str = None):
        """
        :param rc_file: The path to the rc file. If ``None``, the default is
                        used (``~/.smsrc``)
        """
        if rc_file is None and os.path.exists(self._SMSRC_LOCATION):
            rc_file = self._SMSRC_LOCATION
        if rc_file:
            try:
                rc_stats = os.stat(rc_file)
            except OSError:
                raise SmsRcFileError("{:s} file not found.".format(rc_file))
            if not (
                stat.S_ISREG(rc_stats.st_mode)
                and (rc_stats.st_mode & (stat.S_IRWXG | stat.S_IRWXO)) == 0
            ):
                raise SmsRcPermissionsError(
                    "{:s} must be a regular file with permission 0o600.".format(rc_file)
                )
            with io.open(rc_file, encoding="utf-8") as rc_fh:
                smsrc_lines = rc_fh.readlines()
        else:
            smsrc_lines = []
        self._smsrc = collections.defaultdict(dict)
        for line_txt in smsrc_lines:
            line_items = line_txt.rstrip("\n").split()
            logger.debug("Credentials found for host=%s with user=%s", *line_items[:2])
            self._smsrc[line_items[0]][line_items[1]] = line_items[2]

    def get_password(self, host: str, user: str):
        """Return a password for a given **host** and **user** name.

        :exception KeyError: If no matching credential is found.
        """
        for s_host, credentials in self._smsrc.items():
            if s_host.startswith(host):
                return credentials[user]
        raise KeyError(
            "No credentials found for host={:s} and user={:s}.".format(host, user)
        )


class CdpOutputParserMixin(metaclass=abc.ABCMeta):
    """Add the necessary method to process any kind of CDP output."""

    _OUTPUT_IGNORE = re.compile(r"\s*(# MSG|Welcome|Goodbye)")
    # Data for the status command output parser
    _STATUS_DETECT = re.compile(r"([\w/]+)\s*[{\[](\w{3})[]}](\s*)")
    _STATUS_TRANSLATION = dict(
        com=FlowStatus.COMPLETE,
        que=FlowStatus.QUEUED,
        sus=FlowStatus.SUSPENDED,
        abo=FlowStatus.ABORTED,
        sub=FlowStatus.SUBMITTED,
        act=FlowStatus.ACTIVE,
        unk=FlowStatus.UNKNOWN,
    )
    # Data for the info command output parser
    _LIMIT_RE = re.compile(
        r"\s+limit (?P<name>.*)\s+\[running (?P<run>\d+) max (?P<max>\d+)]$"
    )
    _TRIES_CUR_RE = re.compile(r"Current try number:\s*(?P<cur>\d+)$")
    _TRIES_MAX_RE = re.compile(r"\s+SMSTRIES\s*=\s*(?P<max>\d+)\s*\[(?P<from>.*)]$")
    _METER_RE = re.compile(r"\s+METER (?P<n>.*) is (?P<v>.*) limits are \[(?P<l>.*)]$")
    _LABEL_RE = re.compile(r"\s+LABEL (?P<n>.*) '(?P<v>.*)'$")
    _REPEAT_RE = re.compile(
        r"\s*repeat (?P<rtype>integer|date|enumerated|string) "
        + r"variable (?P<n>\w+)\s+(?P<info>.*)\s+currently\s+(?P<v>.*)$"
    )
    _TRIGGERED_BY_RE = re.compile(r"Nodes that trigger this node$")
    _TRIGGER_RE = re.compile(r"\s+(?P<n>[^\s]+)\s+(?P<v>.+)$")

    @property
    @abc.abstractmethod
    def suite(self) -> str:
        """The suite we are working on."""
        return ""

    def _parse_status_output(
        self, output: typing.Union[str, typing.List[str]]
    ) -> typing.Dict[str, RootFlowNode]:
        """Parse the CDP output returned by a 'status' command."""
        root_nodes = collections.OrderedDict()
        from_suite = False
        current_node = None
        last_matches = []
        if isinstance(output, str):
            output = output.split("\n")
        for line in output:
            # Ignore some ot the output lines
            if self._OUTPUT_IGNORE.match(line):
                continue
            # Remove the blank character at the beginning of the line (and count them)
            short_line = line.lstrip(" ")
            initial_blanks = len(line) - len(short_line)
            # Match the regex as many time as necessary
            for i_match, m_obj in enumerate(self._STATUS_DETECT.finditer(short_line)):
                if i_match == 0:
                    # Before dealing with the first match,
                    # Retain the necessary information from the previous match (given
                    # the number of blank characters)
                    base_matches = []
                    matched_blanks = 0
                    for p_obj in last_matches:
                        matched_blanks += len(p_obj.group(0))
                        if matched_blanks > initial_blanks:
                            break
                        base_matches.append(p_obj)
                    last_matches = list(base_matches)
                # Ok, lets process the entry
                name = m_obj.group(1)
                status = self._STATUS_TRANSLATION[m_obj.group(2)]
                if len(last_matches) == 0:
                    # This is the suite itself (just check that it's ok)
                    from_suite = name.strip("/") == self.suite
                    if not from_suite:
                        s_name = name.strip("/").split("/")
                        s_suite = self.suite.strip("/").split("/")
                        if s_name[: len(s_suite)] != s_suite:
                            raise ValueError(
                                "The output's suite name does not match: {:s} vs {:s}".format(
                                    "/".join(s_name[: len(s_suite)]), "/".join(s_suite)
                                )
                            )
                        if len(s_name) > len(s_suite) + 1:
                            raise RuntimeError("Cannot work with such a status tree")
                        current_name = s_name[len(s_suite)]
                        root_nodes[current_name] = RootFlowNode(current_name, status)
                        current_node = root_nodes[current_name]
                elif len(last_matches) == 1 and from_suite:
                    # This is a new root node
                    root_nodes[name] = RootFlowNode(name, status)
                    current_node = root_nodes[name]
                elif (len(last_matches) >= 2) or (
                    not from_suite and len(last_matches) == 1
                ):
                    # This is a usual node
                    terminal_node = current_node
                    for item in last_matches[(1 + int(from_suite)) :]:
                        terminal_node = terminal_node[item.group(1)]
                    terminal_node.add(name, status)
                # Retain the match object
                last_matches.append(m_obj)
        return root_nodes

    def _parse_info_outputs(
        self, output: typing.Union[str, typing.List[str]]
    ) -> typing.List[ExtraFlowNodeInfo]:
        """Parse the CDP output returned by a 'info' command."""
        info = list()

        def _re_test(regex, kind, name, value=None, description="", editable=True):
            re_m = regex.match(line)
            if re_m:
                info.append(
                    ExtraFlowNodeInfo(
                        kind,
                        name.format(**re_m.groupdict()),
                        value=value.format(**re_m.groupdict()) if value else value,
                        description=description.format(**re_m.groupdict())
                        if description
                        else description,
                        editable=editable,
                    ),
                )
            return re_m

        in_trigger_by = False
        if isinstance(output, str):
            output = output.split("\n")
        for line in output:
            line = line.rstrip(" ")
            # Ignore some ot the output lines
            if self._OUTPUT_IGNORE.match(line):
                continue
            if in_trigger_by:
                # We are currently reading triggers
                if _re_test(
                    self._TRIGGER_RE, "trigger", "{n:s}", "{v:s}", editable=False
                ):
                    continue
                else:
                    in_trigger_by = False
            # trigger list begins
            if self._TRIGGERED_BY_RE.match(line):
                in_trigger_by = True
                continue
            # limits
            if _re_test(
                self._LIMIT_RE,
                "limit",
                "{name:s}",
                "{max:s}",
                "currently running: {run:s} - Use the 'reset' special value to reset things",
            ):
                continue
            # tries
            if _re_test(
                self._TRIES_CUR_RE,
                "flowspecific",
                "CurrentTryNumber",
                "{cur:s}",
                editable=False,
            ):
                continue
            if _re_test(
                self._TRIES_MAX_RE,
                "flowspecific",
                "MaxTries",
                "{max:s}",
                "inherited from '{from:s}'",
            ):
                continue
            # meters
            if _re_test(
                self._METER_RE,
                "meter",
                "{n:s}",
                "{v:s}",
                "limits are [{l:s}]",
            ):
                continue
            # labels
            if _re_test(self._LABEL_RE, "label", "{n:s}", "{v:s}", editable=False):
                continue
            # repeats
            if _re_test(
                self._REPEAT_RE,
                "repeat",
                "{n:s}",
                "{v:s}",
                "type: {rtype:s}. info: {info:s}",
            ):
                continue
        return info


class CdpClientError(subprocess.SubprocessError):
    """Any client related to thd cdp client."""

    pass


class CdpClientLoginError(CdpClientError):
    """Error while login into the SMS server (using cdp)."""

    pass


class CdpClientUnknownSuite(CdpClientError):
    """Trying to register to an unknown SMS suite."""

    pass


class CdpClient(object):
    """Bridge with the cdp CLI.

    The cdp CLI is kept openned until the :meth:`close` method is called.
    """

    _END_OF_COMMAND = "TFlowClientCdpCmdDone"
    _PROMPT_RE = re.compile(r"CDP\s*>\s*")
    _ERR_RE = re.compile(r"^#\s*ERR:")

    _LOGIN_RE = re.compile(
        r"^#\s*MSG:SMS-CLIENT-LOGIN:(?P<user>[-\w]+) logged "
        + r"into (?P<host>[-.\w+]+) with password"
    )
    _SUITES1_RE = re.compile(r"^\s*Suites defined in the SMS (?P<host>[-.\w+]+)")
    _SUITES2_RE = re.compile(r"^Suites you are following")

    def __init__(self, credentials: dict, suite: str = None):
        """
        :param credentials: The SMS credentials.
        :param suite: The suite to automatically register to.
        """
        self._suite = None
        self._suites = None
        self._lock = threading.RLock()
        # Start the cdp client
        cmd = [credentials["cdp_path"], "-q", "-d"]
        with self._lock:
            try:
                self._cdp_client_process = subprocess.Popen(
                    cmd,
                    bufsize=0,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.error(
                    "CdpClient: Error while starting cdp:\n exception=%s",
                    str(e),
                )
                raise CdpClientError("Error while starting cdp.")
            # login to the server
            outputs = self.send_command(
                "login {:s} {:s} {:s}".format(
                    credentials["host"], credentials["user"], credentials["password"]
                )
            )
            login_m = self._LOGIN_RE.match(outputs[-1])
            if not (
                login_m
                and login_m.group("host") == credentials["host"]
                and login_m.group("user") == credentials["user"]
            ):
                raise CdpClientLoginError(
                    "unable to login with the provided credentials (host={:s}, user={:s}".format(
                        credentials["host"], credentials["user"]
                    )
                )
            self._last_interaction = time.monotonic()
        # Register to the desired suite
        if suite:
            self.register(suite)

    def register(self, suite: str):
        """Register to a given SMS suite."""
        if self._suite is not None:
            raise CdpClientError("Already registered to < {:s} >".format(self._suite))
        self._suite = suite.split("/", maxsplit=1)[0]
        if self._suite not in self.suites:
            logger.error("The < %s > suite does not exists.", self._suite)
            logger.error("Available suites are:\n%s", "\n".join(self.suites))
            raise CdpClientUnknownSuite(
                "The < {:s} > suite does not exists.".format(self._suite)
            )
        self.send_command("register {:s}".format(self._suite))

    @property
    def idle(self) -> float:
        """The idle time (in seconds)"""
        return time.monotonic() - self._last_interaction

    @property
    def suite(self) -> str:
        """The SMS suite we are registered to."""
        return self._suite

    @property
    def suites(self) -> typing.Set[str]:
        """The list of existing suites (on the server)."""
        if self._suites is None:
            self._suites = set()
            suites_list_started = False
            for l in self.send_command("suites"):
                if suites_list_started:
                    if self._SUITES2_RE.match(l):
                        break
                    self._suites.update(re.split(r"\s+", l))
                else:
                    suites_list_started = self._SUITES1_RE.match(l)
        return self._suites.copy()

    def _raw_send_command(
        self, cmd: str = ""
    ) -> typing.Tuple[typing.Union[int, None], typing.List[str]]:
        with self._lock:
            if self._cdp_client_process.poll() is not None:
                raise CdpClientError("Cannot run commands on a stopped client")
            if cmd:
                self._cdp_client_process.stdin.write(cmd + "\n")
            self._cdp_client_process.stdin.write(
                "echo {:s}\n".format(self._END_OF_COMMAND)
            )
            std_outputs = list()
            rc = None
            for line in self._cdp_client_process.stdout:
                line = self._PROMPT_RE.sub("", line.rstrip())
                if line == self._END_OF_COMMAND:
                    break
                std_outputs.append(line)
            if self._cdp_client_process.poll() is not None:
                rc = self._cdp_client_process.returncode
                for line in self._cdp_client_process.stdout:
                    std_outputs.append(line)
            self._last_interaction = time.monotonic()
        if cmd.startswith("login"):
            # Mask the password...
            cmd = " ".join(
                cmd.split(" ")[:-1]
                + [
                    "password_masked",
                ]
            )
        logger.debug("CdpClient: Command < %s > executed. rc=%s.", cmd, rc)
        if std_outputs and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "CdpClient: Command < %s > executed. outputs:\n%s.",
                cmd,
                "\n".join(std_outputs),
            )
        return rc, std_outputs

    def send_command(self, cmd: str = "") -> typing.List[str]:
        rc, outputs = self._raw_send_command(cmd)
        errors = any([self._ERR_RE.match(l) for l in outputs])
        if errors or rc is not None:
            logger.error(
                "CdpClient: < %s > command outputs:\n%s", cmd, "\n".join(outputs)
            )
        if rc is not None:
            logger.error("CdpClient: The cdp client exited unexpectedly (rc=%s).", rc)
            raise CdpClientError("The cdp client exited unexpectedly")
        if errors:
            logger.error(
                "CdpClient: Unexpected errors while running the < %s > command", cmd
            )
            raise CdpClientError("Unexpected errors")
        return outputs

    def close(self):
        if self._cdp_client_process.poll() is None:
            rc, outputs = self._raw_send_command("exit")
            if rc != 0:
                logger.error("CdpClient: The < exit > command failed (rc=%s).", rc)
                logger.error(
                    "CdpClient: < exit > command outputs:\n%s", "\n".join(outputs)
                )


class CdpInterface(FlowInterface, CdpOutputParserMixin):
    """:class:`FlowInterface` class that interacts with an SMS CDP client."""

    _DUMMY_SUITE_ROOT = RootFlowNode("", FlowStatus.UNKNOWN)

    def __init__(
        self, suite: str, min_refresh_interval: int = 5, cdp_timeout: int = 900
    ):
        super().__init__(suite, min_refresh_interval)
        self._cdp_timeout = cdp_timeout
        self._cdp_client_obj = None
        self._lock = threading.Lock()

    def process_heartbeat(self):
        """This method will be called regularly by the UI."""
        if self._cdp_client_obj is not None:
            with self._lock:
                if self._cdp_client_obj.idle > self._cdp_timeout:
                    self._cdp_client_obj.close()
                    self._cdp_client_obj = None

    def _close_connection(self):
        if self._cdp_client_obj is not None:
            with self._lock:
                self._cdp_client_obj.close()
                self._cdp_client_obj = None

    @property
    def credentials_summary(self) -> str:
        """A string identifying the server name and credentials."""
        return "{:s}@{:s}".format(self.credentials["user"], self.credentials["host"])

    def _valid_credentials(self, credentials: dict) -> dict:
        if {"cdp_path", "host", "user", "password"} != set(credentials.keys()):
            raise ValueError("Improper credentials where provided")
        return credentials

    @property
    def cdp_client(self) -> CdpClient:
        """Return an object that deals cdp interactions."""
        if self._cdp_client_obj is None:
            self._cdp_client_obj = CdpClient(self.credentials, self.suite)
        return self._cdp_client_obj

    def _run_cdp_command(
        self, command: str, root_node: FlowNode, paths: typing.List[str]
    ) -> typing.Tuple[typing.List[str], bool]:
        with self._lock:
            outputs = []
            rc = True
            try:
                for p in self._command_path_expand(root_node, paths):
                    for actual_cmd in command.format("/" + p).split("\n"):
                        outputs.extend(self.cdp_client.send_command(actual_cmd))
            except CdpClientError as e:
                logger.error(
                    "Error while running cdp:\n exception=%s",
                    str(e),
                )
                rc = False
        return outputs, rc

    @staticmethod
    def _build_tree_roots(
        parsed_status: typing.Dict[str, RootFlowNode]
    ) -> RootFlowNode:
        """Return tree roots given a parsed CDP output."""
        rfn = RootFlowNode("", FlowStatus.UNKNOWN)
        for node in parsed_status.values():
            rfn.add(node.name, node.status)
        return rfn

    def _retrieve_tree_roots(self) -> RootFlowNode:
        """Retrieve the list of root nodes form the SMS server."""
        s_output, ok = self._run_cdp_command(
            "status /{:s}", self._DUMMY_SUITE_ROOT, [""]
        )
        if ok:
            parsed_result = self._parse_status_output(s_output)
            return self._build_tree_roots(parsed_result)
        else:
            return RootFlowNode("", FlowStatus.UNKNOWN)

    def _retrieve_status(self, path: str) -> RootFlowNode:
        """Retrieve the full statuses tree for the **path** root node."""
        # Update the tree roots and the tree at once...
        s_output, ok = self._run_cdp_command(
            "\n".join(
                [
                    "status /{:s}".format(self.suite),
                    "status -f /{:s}/{:s}".format(self.suite, path),
                ]
            ),
            self._DUMMY_SUITE_ROOT,
            [
                "fake_path",
            ],
        )
        if ok:
            full_parsed_result = self._parse_status_output(s_output)
            # Update the tree roots nodes
            self._set_tree_roots(self._build_tree_roots(full_parsed_result))
            # Return the appropriate tree of statuses
            new_root_statuses = full_parsed_result.get(path, None)
            return (
                new_root_statuses
                if new_root_statuses
                else RootFlowNode(path, FlowStatus.UNKNOWN)
            )
        else:
            return RootFlowNode(path, FlowStatus.UNKNOWN)

    def do_rerun(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``rerun`` command."""
        output, _ = self._run_cdp_command("force queued {:s}", root_node, paths)
        return "\n".join(output)

    def do_execute(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``execute`` command."""
        output, _ = self._run_cdp_command("run -fc {:s}", root_node, paths)
        return "\n".join(output)

    def do_suspend(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``suspend`` command."""
        output, _ = self._run_cdp_command("suspend {:s}", root_node, paths)
        return "\n".join(output)

    def do_resume(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``resume`` command."""
        output, _ = self._run_cdp_command("resume {:s}", root_node, paths)
        return "\n".join(output)

    def do_complete(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``complete`` command."""
        output, _ = self._run_cdp_command("force -r complete {:s}", root_node, paths)
        return "\n".join(output)

    def do_requeue(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``rerun`` command."""
        output, _ = self._run_cdp_command("requeue -f {:s}", root_node, paths)
        return "\n".join(output)

    def do_cancel(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``cancel`` command."""
        output, _ = self._run_cdp_command("cancel -y {:s}", root_node, paths)
        return "\n".join(output)

    def _logs_gateway_create(self) -> typing.Union[LogsGateway, None]:
        """Create a SMS LogsGateway object."""
        output, _ = self._run_cdp_command(
            "info -v /",
            self._DUMMY_SUITE_ROOT,
            [
                "fake_path",
            ],
        )
        re_log_path_h = re.compile(r"\s*SMSHOME\s*=\s*([^\s]+)")
        re_log_path_o = re.compile(r"\s*SMSOUT\s*=\s*([^\s]+)")
        re_log_host = re.compile(r"\s*SMSLOGHOST\s*=\s*([-.\w]+)")
        re_log_port = re.compile(r"\s*SMSLOGPORT\s*=\s*(\d+)")
        re_my_host = re.compile(r"\s*SMSNODE\s*=\s*([-.\w]+)")
        log_paths = list()
        log_host = None
        my_host = None
        log_port = None
        for line in output:
            m_path = re_log_path_h.match(line)
            if m_path:
                log_paths.append("/".join([m_path.group(1), self.suite]))
            m_path = re_log_path_o.match(line)
            if m_path:
                log_paths.append("/".join([m_path.group(1), self.suite]))
            m_host = re_log_host.match(line)
            if m_host:
                log_host = m_host.group(1)
            m_port = re_log_port.match(line)
            if m_port:
                log_port = int(m_port.group(1))
            m_my_host = re_my_host.match(line)
            if m_my_host:
                my_host = m_my_host.group(1)
        if log_host is None:
            # If SMSLOGHOST is not defined, revert to SMSNODE
            log_host = my_host
        if log_host is not None and log_port is not None and len(log_paths) > 0:
            l_gateway = get_logs_gateway(
                kind="sms_log_svr", paths=log_paths, host=log_host, port=log_port
            )
            if l_gateway.ping():
                return l_gateway
        return None

    def node_info(self, node: FlowNode) -> typing.List[ExtraFlowNodeInfo]:
        """Fetch the node's information."""
        i_output, ok = self._run_cdp_command(
            "info -v /{:s}",
            self._DUMMY_SUITE_ROOT,
            [
                node.full_path,
            ],
        )
        if ok:
            info = self._parse_info_outputs(i_output)
            logger.debug(
                "Info for %s:\n%s", node.full_path, "\n".join([str(i) for i in info])
            )
            return info
        else:
            logger.warning("The info command failed.")
            return [ExtraFlowNodeInfo("error", "The node's could not be retrieved")]

    def _actual_save_node_info(
        self, node: FlowNode, info: typing.List[ExtraFlowNodeInfo]
    ) -> str:
        """Record changes in the node's information."""
        c_stack = []
        node_sms_path = "/{:s}/{:s}".format(self.suite, node.full_path)
        # Generate the list of command to be executed
        for change in info:
            if change.kind == "flowspecific" and change.name == "MaxTries":
                if change.value:
                    c_stack.append(
                        "alter -v {:s} SMSTRIES {!s}".format(
                            node_sms_path, change.value
                        )
                    )
                else:
                    c_stack.append("alter -r -v {:s} SMSTRIES".format(node_sms_path))
            elif change.kind == "limit":
                if not change.value.endswith("reset"):
                    c_stack.append(
                        "alter -M {:s}:{:s} {!s}".format(
                            node_sms_path, change.name, change.value
                        )
                    )
                c_stack.append("reset {:s}:{:s}".format(node_sms_path, change.name))
            elif change.kind == "meter":
                c_stack.append(
                    "alter -m {:s}:{:s} {!s}".format(
                        node_sms_path, change.name, change.value
                    )
                )
            elif change.kind == "repeat":
                c_stack.append(
                    "alter -R {:s}:{:s} {!s}".format(
                        node_sms_path, change.name, change.value
                    )
                )
            else:
                raise NotImplementedError(
                    "Do not know how to update: {!s}".format(change)
                )
        # Execute the command stack
        i_output, _ = self._run_cdp_command(
            "\n".join(c_stack), self._DUMMY_SUITE_ROOT, ["fake_path"]
        )
        return "\n".join(i_output)
