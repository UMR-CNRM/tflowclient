# tflowclient

The ``tflowclient`` package (Text-based workFlow scheduler Client) provides all
the necessary bits to build text-based console clients to interact with
various workflow schedulers. For now, only ``SMS`` is supported: see the
``bin/tflowclient_cdp.py`` executable.

The default display is a tree-view of the workload currently being managed by
the workflow scheduler. An alternative display/"app" is available and can
be trigger by adding `-a Cancel`` on the command-line: it allows to select
several root nodes and to cancel (i.e. delete) them.

## Requirements & Dependencies

The ``tflowclient`` package is only compatible with Python >= 3.7.

The ``tflowclient`` package itself only depends on the non-standard ``urwid``
package that is available on PyPi.

Developers will also need to install the ``pytest`` and ``black`` PyPi
packages in order to respectively test the code and format the code.

To use the ``bin/tflowclient_cdp.py`` executable, a ``cdp`` executable needs to
be available in the system's path. Otherwise, its path can be specified in the
user-specific configuration file ``~/.tflowclientrc.ini``.

## Installation

### Manually

Just fetch the code and add the ``src`` directory to your ``PYTHONPATH``.

### Via ``pip``

Install ``pip``'s build package:

    pip install build

Build the ``tflowclient`` package (from the repository root directory):

    python -m build

After this step, a ready to use pip package should be located in the ``dist``
subdirectory. It may be installed using pip:

    pip install ./dist/package_name.tar.gz

## Rules regarding developments

All the Python code (including the code in ``bin`` and ``tests`` subdirectories)
must comply with PEP8. Prior to any commit in the central repository, all
the Python code **must** be automatically formatted using the black formatter:

    black .

All the unit tests must succeed at any time. The ``pytest`` launcher should
be used (from the repository root directory):

    pytest

## The ``~/.tflowclientrc.ini`` configuration file

The configuration file is optional. You do not need to create it unless you
want to customise some the default configuration

It could look like that:

    [logging]
    ; Activate logging in a ``~/.tflowclient.log`` file for messages with a
    ; severity greater or equal to ``CRITICAL``.
    level = CRITICAL
    
    [urwid]
    ; The backend for ``urwid``. The other possible value is ``curses``.
    backend = raw
    
    [palette]
    ; The platette that will be used by urwid.
    ; For example, you might want to print aborted tasks with black
    ; characters on a ``dark magenta`` background
    ABORTED = black,dark magenta

The default ``tflowclient`` palette can be dumped using the
``bin/tflowclient_palette.py`` executable. More details, on the various
color schemes can be obtained in the ``urwid`` documentation.

By default, only 16 colors are available to build the "palette". Some of may
want to expand their horizons... Theoretically, it is possible to support 256
colors (see the configuration) but beware that it is not supported by all
terminals (that's why it's not activated by default).

Use of a 256-colors palette:

    [urwid]
    backend = raw
    terminal_colors = 256
    
    [palette]
    ABORTED = black, dark magenta, , g74, #f86

The first to entries of the palette still represent foreground and background
colors for the 16-colors palette but the 4th and 5th elements represents
foreground and background colors for the 256-colors palette
(see https://urwid.readthedocs.io/en/latest/examples/index.html#palette-test-py).                                                    

## Extra configuration for SMS/CDP

When running the ``tflowclient_cdp.py`` utility, the server name, user name and
SMS suite to follow have to be specified:

    tflowclient_cdp.py -s sms_server -u sms_user -r sms_suite

For a day to day use, default values can be specified in the
``~/.tflowclientrc.ini`` file:

    [cdp]
    path=path_to_the_cdp_binary
    host=sms_server
    user=sms_user
    suite=sms_suite

``path`` may be omitted if it is properly configured system-wide.

In addition, the user must provide his credentials in a ``~/.smsrc`` file.
The ``~/.smsrc`` file may contain several lines for each of the
server_name/user_name pair the user wants to connect to. The ``.smsrc``
file looks like:

    sms_server sms_user sms_user_s_password

The ``~/.smsrc`` file needs to be accessible **only** by the user ("600"
permissions in octal notation).