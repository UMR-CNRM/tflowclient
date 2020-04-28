# -*- coding: utf-8 -*-

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
import sys
import typing

from .flow import FlowInterface, RootFlowNode, FlowNode, FlowStatus
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
    _STATUS_DETECT = re.compile(r"([\w/]+)\s*[{\[](\w{3})[\]}](\s*)")
    _STATUS_TRANSLATION = dict(
        com=FlowStatus.COMPLETE,
        que=FlowStatus.QUEUED,
        sus=FlowStatus.SUSPENDED,
        abo=FlowStatus.ABORTED,
        sub=FlowStatus.SUBMITTED,
        act=FlowStatus.ACTIVE,
        unk=FlowStatus.UNKNOWN,
    )

    @property
    @abc.abstractmethod
    def suite(self) -> str:
        """The suite we are working on."""
        return ""

    def _parse_status_output(self, output: str) -> typing.Dict[str, RootFlowNode]:
        """Parse the CDP output returned by a 'status' command."""
        root_nodes = collections.OrderedDict()
        from_suite = False
        current_node = None
        last_matches = []
        for line in output.split("\n"):
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
                    from_suite = name == self.suite
                    if not from_suite:
                        s_name = name.strip("/").split("/")
                        if s_name[0] != self.suite:
                            raise ValueError(
                                "The output's suite name does not match: {:s} vs {:s}".format(
                                    name, self.suite
                                )
                            )
                        if len(s_name) > 2:
                            raise RuntimeError("Cannot work with such a status tree")
                        root_nodes[s_name[1]] = RootFlowNode(s_name[1], status)
                        current_node = root_nodes[s_name[1]]
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


class CdpInterface(FlowInterface, CdpOutputParserMixin):
    """:class:`FlowInterface` class that interacts with an SMS CDP client."""

    @property
    def credentials_summary(self) -> str:
        return "{:s}@{:s}".format(self.credentials["user"], self.credentials["host"])

    def _valid_credentials(self, credentials: dict) -> dict:
        if {"cdp_path", "host", "user", "password"} != set(credentials.keys()):
            raise ValueError("Improper credentials where provided")
        return credentials

    def _run_cdp_command(
        self, command: str, paths: typing.List[str]
    ) -> typing.Tuple[str, bool]:
        todo = "\n".join([command.format(p) for p in paths] + ["exit"])
        todo = todo.encode(encoding="utf-8")
        cmd = [
            self.credentials["cdp_path"],
            self.credentials["host"],
            self.credentials["user"],
            self.credentials["password"],
        ]
        displayable_cmd = " ".join(cmd[:-1] + ["masked_password"])
        rc = 0
        try:
            output = subprocess.check_output(cmd, input=todo, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            logger.error(
                "Error while running cdp:\n  cmd=%s\n  exception=%s",
                displayable_cmd,
                str(e),
            )
            rc = e.returncode
            output = (
                "Error while running cdp: "
                + str(e)
                + "\n"
                + "Standard Output:\n"
                + e.stdout.decode(encoding=sys.getfilesystemencoding())
                + "Standard Error:\n"
                + e.stderr.decode(encoding=sys.getfilesystemencoding())
            )
        else:
            output = output.decode(encoding=sys.getfilesystemencoding())
        logger.debug('"%s" command result:\n%s', command, output)
        return output, rc == 0

    def _build_tree_roots(
        self, parsed_status: typing.Dict[str, RootFlowNode]
    ) -> RootFlowNode:
        """Return tree roots given a parsed CDP output."""
        rfn = RootFlowNode(self.suite, FlowStatus.UNKNOWN)
        for node in parsed_status.values():
            rfn.add(node.name, node.status)
        return rfn

    def _retrieve_tree_roots(self) -> RootFlowNode:
        """Retrieve the list of root nodes form the SMS server."""
        s_output, ok = self._run_cdp_command(
            "status {:s}", ["/{:s}".format(self.suite)]
        )
        if ok:
            parsed_result = self._parse_status_output(s_output)
            return self._build_tree_roots(parsed_result)
        else:
            return RootFlowNode(self.suite, FlowStatus.UNKNOWN)

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
            ["fake_path"],
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
        output, _ = self._run_cdp_command("force queued {:s}", paths)
        return output

    def do_execute(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``execute`` command."""
        output, _ = self._run_cdp_command("run -fc {:s}", paths)
        return output

    def do_suspend(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``suspend`` command."""
        output, _ = self._run_cdp_command("suspend {:s}", paths)
        return output

    def do_resume(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``resume`` command."""
        output, _ = self._run_cdp_command("resume {:s}", paths)
        return output

    def do_complete(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``complete`` command."""
        output, _ = self._run_cdp_command("force -r complete {:s}", paths)
        return output

    def do_requeue(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """The SMS ``rerun`` command."""
        output, _ = self._run_cdp_command("requeue -f {:s}", paths)
        return output

    def _logs_gateway_create(self) -> typing.Union[LogsGateway, None]:
        """Create a SMS LogsGateway object."""
        output, _ = self._run_cdp_command("info -v /", ["/",])
        re_log_path = re.compile(r"\s*SMSHOME\s*=\s*([^\s]+)")
        re_log_host = re.compile(r"\s*SMSLOGHOST\s*=\s*([-.\w]+)")
        re_log_port = re.compile(r"\s*SMSLOGPORT\s*=\s*(\d+)")
        log_path = None
        log_host = None
        log_port = None
        for line in output.split("\n"):
            m_path = re_log_path.match(line)
            if m_path:
                log_path = m_path.group(1)
            m_host = re_log_host.match(line)
            if m_host:
                log_host = m_host.group(1)
            m_port = re_log_port.match(line)
            if m_port:
                log_port = int(m_port.group(1))
        if log_host is not None and log_port is not None:
            l_gateway = get_logs_gateway(
                kind="sms_log_svr", path=log_path, host=log_host, port=log_port
            )
            if l_gateway.ping():
                return l_gateway
        return None
